from typing import Optional, Tuple
from direct.showbase.ShowBase import ShowBase
from panda3d.core import NodePath, Camera, PerspectiveLens, GraphicsWindow, LineSegs, Texture, PNMImage, Filename

from hakoniwa_panda3d_drone.primitive.render import RenderEntity

class AttachCamera(RenderEntity):
    def __init__(
        self,
        parent: NodePath,
        aspect2d: NodePath,               # ★ ShowBase.aspect2d を渡す
        name: str = "entity",
        fov: float = 70.0,
        background_color: Tuple[float,float,float,float] = (0,0,0,1)
    ):
        super().__init__(parent, name)
        # np をカメラに差し替え
        self.np = parent.attachNewNode(Camera(name + "_camera"))

        # レンズ設定
        self.lens = PerspectiveLens()
        self.lens.set_fov(fov)
        self.lens.set_near_far(0.01, 1000)
        self.np.node().set_lens(self.lens)

        # ボーダー用
        self.aspect2d = aspect2d
        self.front_cam_border_np: Optional[NodePath] = None

        # クリア色
        self.background_color = background_color

        # 最後に作ったDRとそのUVを保持
        self.display_region = None
        self.dr_coords = None  # (x1, x2, y1, y2)

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
        self.dr_coords = (x1, x2, y1, y2)
        self._draw_front_cam_border(win)

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

