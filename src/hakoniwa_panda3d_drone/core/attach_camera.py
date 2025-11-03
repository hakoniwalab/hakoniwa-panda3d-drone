from typing import Optional, Tuple
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    NodePath, Camera, PerspectiveLens, GraphicsWindow, LineSegs,
    Texture, PNMImage, StringStream, FrameBufferProperties, 
    WindowProperties, GraphicsPipe, GraphicsOutput
)
from hakoniwa_panda3d_drone.primitive.render import RenderEntity


class AttachCamera(RenderEntity):
    def __init__(
        self,
        loader,
        parent: NodePath,
        aspect2d: NodePath,
        name: str = "entity",
        fov: float = 70.0,
        near: float = 0.1,
        far: float = 1000.0,
        background_color: Tuple[float,float,float,float] = (0,0,0,1),
        model_config: dict = None,
    ):
        super().__init__(parent, name)

        # === 表示用カメラ ===
        self.np = parent.attachNewNode(Camera(name + "_camera"))
        self.lens = PerspectiveLens()
        self.lens.set_fov(fov)
        self.lens.set_near_far(near, far)
        self.np.node().set_lens(self.lens)

        # === キャプチャ専用カメラ ===
        self.cap_cam_np = parent.attachNewNode(Camera(name + "_cap_camera"))
        self.cap_lens = PerspectiveLens()
        self.cap_lens.set_fov(fov)
        self.cap_lens.set_near_far(near, far)
        self.cap_cam_np.node().set_lens(self.cap_lens)
        self.cap_cam_np.reparentTo(self.np)  # 表示カメラと姿勢共有

        # モデル読み込み
        if model_config is not None:
            self.load_model(loader, self.resolve_model_path(model_config.get("model_path")), copy=True, cache=False)
            self._geom_np.set_pos(*model_config.get("pos", [0,0,0]))
            self._geom_np.set_hpr(*model_config.get("hpr", [0,0,0]))

        # その他設定
        self.aspect2d = aspect2d
        self.front_cam_border_np: Optional[NodePath] = None
        self.background_color = background_color
        self.display_region = None
        self.dr_coords = None

        # キャプチャバッファ
        self.capture_tex = None
        self.capture_buf = None
        self.capture_dr = None
        self._init_done = False

    # --- DisplayRegion設定 ---
    def set_display_region(self, win: GraphicsWindow, sort: int, x: float, y: float, width: float, height: float):
        x1, y1 = x, y
        x2, y2 = x + width, y + height
        dr = win.make_display_region(x1, x2, y1, y2)
        dr.set_camera(self.np)
        dr.set_sort(sort)
        dr.set_clear_depth_active(True)
        dr.set_clear_color_active(True)
        dr.set_clear_color(self.background_color)
        self.display_region = dr

        win_w, win_h = win.get_x_size(), win.get_y_size()
        region_aspect = (win_w * (x2 - x1)) / (win_h * (y2 - y1))
        self.lens.set_aspect_ratio(region_aspect)
        print(f"[AttachCamera] Created DisplayRegion at UV({x1:.2f},{y1:.2f})-({x2:.2f},{y2:.2f})")

    def _get_aspect_ratio(self, win: GraphicsWindow) -> float:
        width, height = win.get_x_size(), win.get_y_size()
        return (width / height) if height else 1.0

    # --- キャプチャバッファ生成 ---
    def ensure_capture_target(self, base, w=None, h=None, use_alpha=False):
        win_w, win_h = base.win.get_x_size() or 1280, base.win.get_y_size() or 720
        w, h = w or win_w, h or win_h

        if (self.capture_buf and
            self.capture_tex.get_x_size() == w and
            self.capture_tex.get_y_size() == h):
            return

        if self.capture_buf:
            base.graphicsEngine.remove_window(self.capture_buf)
            self.capture_buf = None

        fb = FrameBufferProperties()
        fb.set_rgb_color(True)
        fb.set_rgba_bits(8, 8, 8, 8 if use_alpha else 0)
        fb.set_depth_bits(24)

        wp = WindowProperties.size(w, h)
        flags = GraphicsPipe.BFRefuseWindow

        buf = base.graphicsEngine.make_output(
            base.pipe, f"{self.np.get_name()}_buf",
            -2, fb, wp, flags,
            base.win.getGsg(), base.win
        )

        tex = Texture()
        tex.set_keep_ram_image(True)
        tex.set_format(Texture.F_rgba if use_alpha else Texture.F_rgb)
        buf.add_render_texture(tex, GraphicsOutput.RTMCopyRam)
        buf.set_clear_color_active(True)
        buf.set_clear_color(self.background_color)

        dr = buf.make_display_region()
        dr.set_camera(self.cap_cam_np)  # ★キャプチャ専用カメラを使う
        dr.set_clear_depth_active(True)
        dr.set_clear_color_active(True)
        dr.set_clear_color(self.background_color)

        self.capture_tex = tex
        self.capture_buf = buf
        self.capture_dr = dr
        self._init_done = False

    # --- キャプチャ処理 ---
    def capture_rgb_bytes(self, base, w=1280, h=720) -> tuple[bytes, int, int, int]:
        self.ensure_capture_target(base, w, h, use_alpha=False)
        prev_ar = self.cap_lens.get_aspect_ratio()
        self.cap_lens.set_aspect_ratio(w / float(h))

        base.graphicsEngine.render_frame()
        if not self._init_done:
            base.graphicsEngine.render_frame()
            self._init_done = True

        self.cap_lens.set_aspect_ratio(prev_ar)
        gsg = base.win.getGsg()
        if gsg and not self.capture_tex.hasRamImage():
            base.graphicsEngine.extract_texture_data(self.capture_tex, gsg)
        if not self.capture_tex.hasRamImage():
            raise RuntimeError("no RAM image")

        ram = self.capture_tex.getRamImageAs("RGB")
        return (bytes(ram), self.capture_tex.get_x_size(), self.capture_tex.get_y_size(), 3)

    def capture_png_bytes(self, base, w=1280, h=720) -> bytes:
        data, ww, hh, _ = self.capture_rgb_bytes(base, w, h)
        img = PNMImage()
        self.capture_tex.store(img)
        ss = StringStream()
        img.write(ss, "png")
        return ss.get_data()
