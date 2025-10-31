from panda3d.core import NodePath, Vec3, Point3
from hakoniwa_panda3d_drone.primitive.polygon import Polygon, Cube, Plane
from hakoniwa_panda3d_drone.primitive.render import RenderEntity
from direct.showbase.ShowBase import ShowBase
from panda3d.core import TextNode
from direct.gui.OnscreenText import OnscreenText
from hakoniwa_panda3d_drone.core.camera import OrbitCamera 
from hakoniwa_panda3d_drone.core.light import LightRig
import panda3d
import json
from pathlib import Path
from panda3d.core import Camera, NodePath, PerspectiveLens, DisplayRegion, LineSegs

print(f"--- Running Panda3D Version: {panda3d.__version__} ---")

class App(ShowBase):
    def __init__(self, drone_config_path: str):
        super().__init__()
        self.disableMouse()

        self.background_color = (0.7, 0.7, 0.7, 1)

        self.set_background_color(*self.background_color)
        self.render.setShaderAuto()

        self.drone_config_path = drone_config_path
        with open(drone_config_path, 'r') as f:
            config = json.load(f)

        drone_model = self._create_entity_from_config(config, copy=True)

        if 'children' in config:
            for child_config in config['children']:
                child_entity = self._create_entity_from_config(child_config, copy=True)
                drone_model.add_child(child_entity)

        # --- 照明セットアップ（先に設定） ---
        self.lights = LightRig(self.render, shadows=True)

        # 床
        floor = RenderEntity(self.render, "floor")
        plane = Plane(size=5.0, color=(0.8, 0.8, 0.7, 1))
        floor.set_polygon(plane)
        floor.set_pos(0, 0, -0.3)
        #floor.np.set_tag('ShadowReceiver', 'true')

        # 床は影を受ける
        floor.np.show()  # 念のため

        self.entity = drone_model


        self.entity.np.set_tag('ShadowCaster', 'true')

        # === 前方カメラをドローンに取り付ける ===
        self._setup_front_camera()
        
        # --- ここからカメラ ---
        target = Point3(drone_model.np.getPos(self.render))
        self.cam_ctrl = OrbitCamera(
            self,
            target=target,
            distance=2.0,
            yaw_deg=35.0,
            pitch_deg=30.0
        )
        self.cam_ctrl.enable()

        # キーバインド
        #self.accept("1", lambda: self.lights.toggle(True))
        #self.accept("2", lambda: self.lights.toggle(False))

        # テキスト（右下）
        self.pos_text = OnscreenText(
            text="", pos=(1.2, -0.95),
            scale=0.05, fg=(1, 1, 1, 1), align=TextNode.ARight, mayChange=True
        )
        self.taskMgr.add(self.update_text, "update_text_task")

    def _resolve_model_path(self, path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            return str(p)
        base = Path.cwd()
        rp = str((base / p).resolve())
        print(f"Resolved model path: {rp}")
        return rp

    def _create_entity_from_config(self, config, copy=False):
        entity = RenderEntity(self.render, config['name'])
        entity.load_model(self.loader, self._resolve_model_path(config['model']), copy=copy)
        if 'pos' in config:
            entity.set_pos(*config['pos'])
        if 'hpr' in config:
            entity._geom_np.setHpr(*config['hpr'])
        return entity

    def set_pose_and_rotation(self, pos: Vec3, hpr: Vec3, rotation_speed: float = 1.0):
        self.entity.set_pos(x = pos.x, y = pos.y, z = pos.z)
        self.entity.set_hpr(h = hpr.x, p = hpr.y, r = hpr.z)
        index = 0
        for rotor in self.entity.children:
            if index % 2 == 0:
                rotor.rotate_child_yaw(-rotation_speed)
            else:
                rotor.rotate_child_yaw(rotation_speed)
            index += 1

    def _setup_front_camera(self):
        # ドローンノードにカメラノードを追加
        front_cam_np = self.entity.np.attach_new_node(Camera("FrontCam"))

        # 視野レンズを設定
        lens = PerspectiveLens()
        lens.set_fov(70)
        front_cam_np.node().set_lens(lens)

        # ドローン前方に少しずらす（前: -Y方向）
        front_cam_np.set_pos(0, 0.2, 0.05)
        front_cam_np.set_hpr(0, 0, 0)

        # === 表示領域をサブウィンドウとして作る ===
        x_len = 0.3
        y_len = 0.3
        x1 = 1.0 - x_len - 0.01  # 右端から少し内側
        y1 = 1.0 - y_len - 0.01  # 上端から少し内側
        x2 = x1 + x_len
        y2 = y1 + y_len
        dr = self.win.make_display_region(x1, x2, y1, y2)  # 右上小窓
        dr.set_camera(front_cam_np)

        dr.set_sort(20)                     # メインより後に描く
        dr.set_clear_depth_active(True)     # デプスバッファを小窓でクリア
        dr.set_clear_color_active(True)     # カラーバッファも小窓でクリア
        dr.set_clear_color(self.background_color)

        # --- ★ ここが今回のポイント：レンズのアスペクトを小窓に合わせる ---
        win_aspect = self.getAspectRatio()                 # ウィンドウの幅/高さ
        region_aspect = win_aspect * ((x2 - x1) / (y2 - y1))
        lens.set_aspect_ratio(region_aspect)

        # ついでに near/far も明示
        lens.set_near_far(0.01, 1000)


        self.front_cam_np = front_cam_np
        self.dr_coords = (x1, x2, y1, y2)  # (x1, x2, y1, y2)
        self._draw_front_cam_border()


    def _uv_to_aspect(self, x: float, y: float):
        """DisplayRegionのUV([0,1])→aspect2d座標への変換"""
        aspect = self.getAspectRatio()
        ax = (x - 0.5) * 2.0 * aspect
        ay = (y - 0.5) * 2.0
        return ax, ay

    def _draw_front_cam_border(self, thickness: float = 2.0, inset: float = 0.0):
        x1, x2, y1, y2 = self.dr_coords

        # ほんの少し内側に寄せたい場合は inset を使う（0.0でぴったり）
        x1i, x2i = x1 + inset, x2 - inset
        y1i, y2i = y1 + inset, y2 - inset

        ax1, ay1 = self._uv_to_aspect(x1i, y1i)
        ax2, ay2 = self._uv_to_aspect(x2i, y2i)

        ls = LineSegs()
        ls.set_thickness(thickness)
        ls.set_color(1, 1, 1, 1)  # 白

        ls.move_to(ax1, 0, ay1)
        ls.draw_to(ax2, 0, ay1)
        ls.draw_to(ax2, 0, ay2)
        ls.draw_to(ax1, 0, ay2)
        ls.draw_to(ax1, 0, ay1)

        # 2Dオーバーレイに追加（最前面に出すためbin指定）
        if hasattr(self, "front_cam_border_np") and not self.front_cam_border_np.is_empty():
            self.front_cam_border_np.remove_node()
        self.front_cam_border_np = aspect2d.attach_new_node(ls.create())
        self.front_cam_border_np.set_bin("fixed", 100)
        self.front_cam_border_np.set_depth_test(False)
        self.front_cam_border_np.set_depth_write(False)

    def update_text(self, task):
        pos = self.entity.np.getPos(self.render)
        self.pos_text.setText(f"x={pos.x:.2f}  y={pos.y:.2f}  z={pos.z:.2f}")
        return task.cont

if __name__ == "__main__":
    App().run()