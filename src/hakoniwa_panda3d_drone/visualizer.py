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
from hakoniwa_panda3d_drone.core.attach_camera import AttachCamera
from hakoniwa_panda3d_drone.core.environment import EnvironmentEntity
from hakoniwa_pdu.pdu_msgs.hako_msgs.pdu_pytype_GameControllerOperation import GameControllerOperation

import sys
import argparse

print(f"--- Running Panda3D Version: {panda3d.__version__} ---")

class App(ShowBase):

    def build_drone_model(self, config):
        drone_models = []
        for drone_cfg in config['drones']:
            droen_name = drone_cfg.get('name', 'Drone')
            print(f"[Visualizer] Building drone model: {droen_name}")
            drone_model = self._create_entity_from_config(drone_cfg, copy=True)
            drone_model.set_purpose('drone')

            if 'rotors' in drone_cfg:
                for child_config in drone_cfg['rotors']:
                    child_entity = self._create_entity_from_config(child_config, copy=True)
                    child_entity.set_purpose('rotor')
                    drone_model.add_child(child_entity)

            drone_model.np.set_tag('ShadowCaster', 'true')

            # === 前方カメラをドローンに取り付ける ===
            for cam_config in drone_cfg.get('cameras', []):
                attach_cam = AttachCamera(
                    self.loader,
                    parent=drone_model.np,
                    aspect2d=self.aspect2d,
                    name=cam_config.get('name', 'AttachedCam'),
                    fov=cam_config.get('fov', 70.0),
                    near=cam_config.get('near', 0.1),
                    far=cam_config.get('far', 1000.0),
                    background_color=self.background_color,
                    model_config=cam_config.get('model', None),
                )
                if 'window' in cam_config:
                    attach_cam.set_display_region(
                        win=self.win,
                        sort=cam_config.get('sort', 20),
                        x=cam_config.get('window', {}).get('x', 0.7),
                        y=cam_config.get('window', {}).get('y', 0.7),
                        width=cam_config.get('window', {}).get('width', 0.3),
                        height=cam_config.get('window', {}).get('height', 0.3)
                    )
                pos = cam_config.get('pos', [0, -0.2, 0.05])
                hpr = cam_config.get('hpr', [0, 0, 0])
                attach_cam.set_pos(*pos)
                attach_cam.set_hpr(*hpr)
                if self.drone_cam is None or self.drone_cam.get(droen_name) is None:
                    self.drone_cam[droen_name] = attach_cam
                drone_model.add_child(attach_cam)
            drone_models.append(drone_model)

        self.drone_models = drone_models

    def __init__(self, drone_config_path: str):
        super().__init__()
        self.disableMouse()

        self.background_color = (0.7, 0.7, 0.7, 1)
        #self.background_color = (0.12, 0.12, 0.14, 1) 

        self.set_background_color(*self.background_color)
        self.render.setShaderAuto()

        self.drone_config_path = drone_config_path
        with open(drone_config_path, 'r') as f:
            config = json.load(f)

        self.drone_cam = {}
        self.build_drone_model(config)

        # --- 照明セットアップ（先に設定） ---
        self.lights = LightRig(self.render, shadows=False)

        self.envs = []
        for env_config in config.get('environments', []):
            env = EnvironmentEntity(
                render=self.render,
                name=env_config.get('name', 'environment'),
                model_path=env_config['model'],
                pos=env_config.get('pos'),
                hpr=env_config.get('hpr'),
                scale=env_config.get('scale', 1.0),
                cache=env_config.get('cache', False),
                copy=env_config.get('copy', False),
                loader=self.loader,
            )
            self.envs.append(env)

        sys.stdout.flush()

        # --- ここからカメラ ---
        target = Point3(self.drone_models[0].np.getPos(self.render))
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
        self.active_drone = "Drone"
        self.accept("s", lambda: self.snapshot_attach_camera(self.active_drone, "cam.png"))

    def snapshot_attach_camera(self, drone_name: str, path: str, w: int = 1280, h: int = 720):
        from direct.task import Task
        def _do(task):
            cam = self.drone_cam.get(drone_name)
            if cam is None:
                print(f"[snapshot] ERROR: camera for {drone_name} not found")
                return Task.done

            png = cam.capture_png_bytes(self, w, h)
            with open(path, "wb") as f:
                f.write(png)
            print(f"[snapshot] saved: {path}")
            return Task.done

        self.taskMgr.add(_do, "snapshot_once")


    def capture_camera(self, drone_name: str, image_type: str, w: int = 1280, h: int = 720) -> bytes:
        """
        カメラ画像をバイト列で取得。
        image_type: "png" | "jpeg" などを想定
        """
        if self.drone_cam is None or self.drone_cam.get(drone_name) is None:
            # 空画像を返す／例外を投げる等、方針に合わせて
            # ここでは例外で返して RPC 側でメッセージにするのがわかりやすい
            raise RuntimeError("Attached camera is not initialized")

        # AttachCamera 側に jpeg 版があるなら使う。なければ png を共通化でもOK
        itype = (image_type or "png").lower()
        if itype in ("jpg", "jpeg") and hasattr(self.drone_cam, "capture_jpeg_bytes"):
            return self.drone_cam[drone_name].capture_jpeg_bytes(self, w, h)

        # 既存の png をデフォルトに
        return self.drone_cam[drone_name].capture_png_bytes(self, w, h)

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

    def set_pose_and_rotation(self, drone_name: str, pos: Vec3, hpr: Vec3, rotation_speed: float = 1.0):
        for drone_model in self.drone_models:
            if drone_model.name == drone_name:
                drone_model.set_pos(x=pos.x, y=pos.y, z=pos.z)
                drone_model.set_hpr(h=hpr.x, p=hpr.y, r=hpr.z)
                index = 0
                for rotor in drone_model.children:
                    if rotor.purpose != 'rotor':
                        continue
                    if index % 2 == 0:
                        rotor.rotate_child_yaw(-rotation_speed)
                    else:
                        rotor.rotate_child_yaw(rotation_speed)
                    index += 1

    def update_game_controller_ui(self, drone_name: str, game_ctrl: GameControllerOperation):
        if self.drone_cam is not None and self.drone_cam.get(drone_name) is not None:
            #up down drone camera pitch based on buttons: up=11, down=12
            if game_ctrl.button[11]:
                self.drone_cam[drone_name].rotate_pitch(1.0)
            if game_ctrl.button[12]:
                self.drone_cam[drone_name].rotate_pitch(-1.0)
        #print(f"Game Controller State: {drone_name} {game_ctrl}")


    def update_text(self, task):
        pos = self.drone_models[0].np.getPos(self.render)
        self.pos_text.setText(f"x={pos.x:.2f}  y={pos.y:.2f}  z={pos.z:.2f}")
        self.cam_ctrl.set_target(pos)
        return task.cont

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Panda3D Drone Visualizer")
    parser.add_argument(
        "--config",
        type=str,
        default="../drone_config/drone_config-1.json",
        help="Path to the drone configuration JSON file."
    )
    args = parser.parse_args()
    
    # Resolve the path relative to the current working directory if it's not absolute
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    config_path = config_path.resolve()

    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        sys.exit(1)

    App(str(config_path)).run()