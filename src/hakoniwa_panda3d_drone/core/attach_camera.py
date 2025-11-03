from typing import Optional, Tuple
from direct.showbase.ShowBase import ShowBase
from panda3d.core import NodePath, Camera, PerspectiveLens, GraphicsWindow, LineSegs, Texture, PNMImage, Filename
from panda3d.core import Texture, PNMImage, StringStream
from panda3d.core import FrameBufferProperties, WindowProperties, GraphicsPipe, GraphicsOutput, Texture

from hakoniwa_panda3d_drone.primitive.render import RenderEntity

class AttachCamera(RenderEntity):
    def __init__(
        self,
        loader,
        parent: NodePath,
        aspect2d: NodePath,               # ★ ShowBase.aspect2d を渡す
        name: str = "entity",
        fov: float = 70.0,
        near: float = 0.1,
        far: float = 1000.0,
        background_color: Tuple[float,float,float,float] = (0,0,0,1),
        model_config: dict = None,
    ):
        super().__init__(parent, name)
        # np をカメラに差し替え
        self.np = parent.attachNewNode(Camera(name + "_camera"))
        if model_config is not None:
            self.load_model(loader, self.resolve_model_path(model_config.get("model_path")), copy=True, cache=False)
            self._geom_np.set_pos(*model_config.get("pos", [0,0,0]))
            self._geom_np.set_hpr(*model_config.get("hpr", [0,0,0]))

        # レンズ設定
        self.lens = PerspectiveLens()
        self.lens.set_fov(fov)
        self.lens.set_near_far(near, far)
        self.np.node().set_lens(self.lens)

        # ボーダー用
        self.aspect2d = aspect2d
        self.front_cam_border_np: Optional[NodePath] = None

        # クリア色
        self.background_color = background_color

        # 最後に作ったDRとそのUVを保持
        self.display_region = None
        self.dr_coords = None  # (x1, x2, y1, y2)

        self.capture_tex = None
        self.capture_buf = None
        self.capture_dr  = None
        self._init_done  = False        

    def set_display_region(
        self,
        win: GraphicsWindow,
        sort: int,
        x: float, y: float, width: float, height: float
    ):
        """DisplayRegion を (x,y,width,height) の UV 指定で作成"""
        # UVそのまま使う（左下基準）
        x1, y1 = x, y
        x2, y2 = x + width, y + height

        dr = win.make_display_region(x1, x2, y1, y2)
        dr.set_camera(self.np)
        dr.set_sort(sort)
        dr.set_clear_depth_active(True)
        dr.set_clear_color_active(True)
        dr.set_clear_color(self.background_color)
        self.display_region = dr

        print(f"[AttachCamera] Created DisplayRegion at UV({x1:.2f},{y1:.2f})-({x2:.2f},{y2:.2f})")
        #flush print
        # レンズのアスペクトを小窓に合わせる
        win_w = win.get_x_size()
        win_h = win.get_y_size()
        region_aspect = (win_w * (x2 - x1)) / (win_h * (y2 - y1))
        self.lens.set_aspect_ratio(region_aspect)

        # 枠を描く
        #self.dr_coords = (x1, x2, y1, y2)
        #self._draw_front_cam_border(win)

    # ---- 2D枠線描画 ---------------------------------------------------------
    def _uv_to_aspect(self, win: GraphicsWindow, x: float, y: float):
        """DisplayRegionのUV([0,1])→aspect2d座標への変換"""
        aspect = self._get_aspect_ratio(win)
        ax = (x - 0.5) * 2.0 * aspect
        ay = (y - 0.5) * 2.0
        return ax, ay

    def _draw_front_cam_border(self, win: GraphicsWindow, thickness: float = 2.0, inset: float = 0.0):
        if self.dr_coords is None:
            return
        # 既存枠があれば消す（再設定時に重複しないように）
        if self.front_cam_border_np and not self.front_cam_border_np.is_empty():
            self.front_cam_border_np.removeNode()
            self.front_cam_border_np = None

        x1, x2, y1, y2 = self.dr_coords
        # ほんの少し内側に寄せたい場合は inset を使う
        x1i, x2i = x1 + inset, x2 - inset
        y1i, y2i = y1 + inset, y2 - inset

        ax1, ay1 = self._uv_to_aspect(win, x1i, y1i)
        ax2, ay2 = self._uv_to_aspect(win, x2i, y2i)

        ls = LineSegs()
        ls.set_thickness(thickness)
        ls.set_color(1, 1, 1, 1)  # 白

        ls.move_to(ax1, 0, ay1)
        ls.draw_to(ax2, 0, ay1)
        ls.draw_to(ax2, 0, ay2)
        ls.draw_to(ax1, 0, ay2)
        ls.draw_to(ax1, 0, ay1)

        self.front_cam_border_np = self.aspect2d.attachNewNode(ls.create())
        self.front_cam_border_np.set_bin("fixed", 100)
        self.front_cam_border_np.set_depth_test(False)
        self.front_cam_border_np.set_depth_write(False)

    def _get_aspect_ratio(self, win: GraphicsWindow) -> float:
        width = win.get_x_size()
        height = win.get_y_size()
        return (width / height) if height else 1.0

    def ensure_capture_target(self, base, w=None, h=None, use_alpha=False):
        # 1) 画面サイズ→デフォルト
        win_w = base.win.get_x_size() or 1280
        win_h = base.win.get_y_size() or 720
        w = w or win_w
        h = h or win_h

        # 既存サイズ一致なら再利用
        if (self.capture_buf is not None
            and self.capture_tex.get_x_size() == w
            and self.capture_tex.get_y_size() == h):
            return

        # 古いバッファ破棄
        if self.capture_buf is not None:
            base.graphicsEngine.remove_window(self.capture_buf)
            self.capture_buf = None

        # 2) FBP/WP を明示指定
        fb = FrameBufferProperties()
        fb.set_rgb_color(True)
        if use_alpha:
            fb.set_rgba_bits(8, 8, 8, 8)
        else:
            fb.set_rgba_bits(8, 8, 8, 0)
        fb.set_depth_bits(24)
        fb.set_stereo(False)
        fb.set_float_color(False)

        wp = WindowProperties.size(w, h)

        # 3) バッファ作成（ウィンドウを拒否）
        flags = GraphicsPipe.BFRefuseWindow
        buf = base.graphicsEngine.make_output(
            base.pipe,
            f"{self.np.get_name()}_buf",
            -2,                 # sort
            fb,
            wp,
            flags,
            base.win.getGsg(),  # gsg
            base.win            # host（★ get_host_window ではなく base.win を渡す）
        )
        if buf is None:
            # 環境依存で失敗する場合のフォールバック
            tex = Texture()
            tex.set_keep_ram_image(True)
            tex.set_format(Texture.F_rgba if use_alpha else Texture.F_rgb)
            buf = base.win.make_texture_buffer(f"{self.np.get_name()}_buf", w, h, tex)

        # 4) テクスチャを明示的にアタッチ（RAMへコピー）
        tex = Texture()
        tex.set_keep_ram_image(True)
        tex.set_format(Texture.F_rgba if use_alpha else Texture.F_rgb)
        buf.add_render_texture(tex, GraphicsOutput.RTMCopyRam)

        buf.set_clear_color_active(True)
        buf.set_clear_color(self.background_color)

        dr = buf.make_display_region()
        dr.set_camera(self.np)
        dr.set_clear_depth_active(True)
        dr.set_clear_color_active(True)
        dr.set_clear_color(self.background_color)

        self.capture_tex = tex
        self.capture_buf = buf
        self.capture_dr  = dr
        self._init_done  = False



    def _with_temp_aspect(self, aspect: float):
        # 小さなヘルパ（ジェネレータでもOK）
        class AspectGuard:
            def __init__(self, lens, new_aspect):
                self.lens = lens
                self.prev = lens.get_aspect_ratio()
                self.new = new_aspect
            def __enter__(self):
                self.lens.set_aspect_ratio(self.new)
            def __exit__(self, exc_type, exc, tb):
                self.lens.set_aspect_ratio(self.prev)
        return AspectGuard(self.lens, aspect)

    def capture_rgb_bytes(self, base, w=1280, h=720) -> tuple[bytes, int, int, int]:
        self.ensure_capture_target(base, w, h, use_alpha=False)

        # ★ ここで一時的に w/h に合わせる
        with self._with_temp_aspect(w / h):
            base.graphicsEngine.render_frame()
            if not self._init_done:
                base.graphicsEngine.render_frame()
                self._init_done = True

        gsg = base.win.getGsg()
        if gsg is not None and not self.capture_tex.hasRamImage():
            base.graphicsEngine.extract_texture_data(self.capture_tex, gsg)

        if not self.capture_tex.hasRamImage():
            raise RuntimeError("no RAM image")

        ram = self.capture_tex.getRamImageAs("RGB")
        return (bytes(ram), self.capture_tex.get_x_size(), self.capture_tex.get_y_size(), 3)

    
    def capture_png_bytes(self, base, w=1280, h=720) -> bytes:
        self.ensure_capture_target(base, w, h, use_alpha=False)

        # ★ ここで一時的にレンズARを w/h に
        with self._with_temp_aspect(w / h):
            base.graphicsEngine.render_frame()
            if not self._init_done:
                base.graphicsEngine.render_frame()
                self._init_done = True

        gsg = base.win.getGsg()
        if gsg is not None and not self.capture_tex.hasRamImage():
            base.graphicsEngine.extract_texture_data(self.capture_tex, gsg)

        if not self.capture_tex.hasRamImage():
            raise RuntimeError("no RAM image")

        img = PNMImage()
        self.capture_tex.store(img)

        ss = StringStream()
        img.write(ss, "png")
        return ss.get_data()
    

