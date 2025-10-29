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

print(f"--- Running Panda3D Version: {panda3d.__version__} ---")

class App(ShowBase):
    def __init__(self, drone_config_path: str):
        super().__init__()
        self.disableMouse()

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
        floor.set_polygon(Plane(size=5.0))
        floor.set_pos(0, 0, -0.3)
        #floor.np.set_tag('ShadowReceiver', 'true')

        # 床は影を受ける
        floor.np.show()  # 念のため

        self.entity = drone_model


        self.entity.np.set_tag('ShadowCaster', 'true')


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

    def update_text(self, task):
        pos = self.entity.np.getPos(self.render)
        self.pos_text.setText(f"x={pos.x:.2f}  y={pos.y:.2f}  z={pos.z:.2f}")
        return task.cont

if __name__ == "__main__":
    App().run()