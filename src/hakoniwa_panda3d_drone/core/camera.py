# core/camera.py
from math import sin, cos, radians
from panda3d.core import Point3, Vec3, KeyboardButton
from direct.showbase.ShowBase import ShowBase
from direct.task import Task

class OrbitCamera:
    """
    Unity のシーンビュー風カメラ操作:
      - Alt + 左ドラッグ  : オービット（回転）
      - 中ボタンドラッグ : パン
      - ホイール          : ズーム
      - 右ドラッグ        : 代替のオービット（Alt無し）
    座標系: Panda3D デフォルト (Z: up, -Y: forward)

    使い方:
        cam = OrbitCamera(base, target=Point3(0,0,0))
        cam.enable()
    """
    def __init__(
        self,
        base: ShowBase,
        target: Point3 = Point3(0, 0, 0),
        distance: float = 6.0,
        yaw_deg: float = 45.0,
        pitch_deg: float = 20.0,
    ):
        self.base = base
        self.target = Point3(target)
        self.distance = distance
        self.yaw = yaw_deg
        self.pitch = pitch_deg

        # 制限
        self.min_pitch = -89.0
        self.max_pitch = 89.0
        self.min_distance = 0.5
        self.max_distance = 200.0

        # 感度
        self.rotate_sensitivity = 0.25   # ドラッグ 1px あたりの角度
        self.pan_speed = 0.003           # ドラッグ 1px あたりの距離係数
        self.zoom_speed = 1.08           # ホイール1ノッチで距離を倍率で変更

        # 内部状態
        self._rotating = False
        self._panning = False
        self._last_mouse = None  # (x, y)

        self._task_name = "orbit_camera_update"

        # 入力バインド
        a = self.base.accept
        a("mouse1", self._on_mouse1_down)
        a("mouse1-up", self._on_mouse1_up)
        a("mouse2", self._on_mouse2_down)
        a("mouse2-up", self._on_mouse2_up)
        a("mouse3", self._on_mouse3_down)
        a("mouse3-up", self._on_mouse3_up)
        a("wheel_up", lambda: self.zoom(-1))
        a("wheel_down", lambda: self.zoom(+1))

    # ========== 公開API ==========
    def enable(self):
        self._update_camera_pos()
        # Panda3D は taskMgr（アッパーM）です
        self.base.taskMgr.add(self._update_task, self._task_name)

    def disable(self):
        self.base.taskMgr.remove(self._task_name)

    def set_target(self, p: Point3):
        self.target = Point3(p)
        self._update_camera_pos()

    # ========== 入力ハンドラ ==========
    def _on_mouse1_down(self):
        # Alt + 左ドラッグで回転（Unity風）
        if self._alt_down():
            self._begin_rotate()

    def _on_mouse1_up(self):
        # マウスアップ時は修飾キー状態に依存せず終了させる
        if self._rotating:
            self._end_rotate()

    def _on_mouse2_down(self):
        self._begin_pan()

    def _on_mouse2_up(self):
        self._end_pan()

    def _on_mouse3_down(self):
        # 右ドラッグでも回転できるように（Alt不要）
        self._begin_rotate()

    def _on_mouse3_up(self):
        self._end_rotate()

    # ========== 状態切替 ==========
    def _begin_rotate(self):
        self._rotating = True
        self._snapshot_mouse()

    def _end_rotate(self):
        self._rotating = False
        self._last_mouse = None

    def _begin_pan(self):
        self._panning = True
        self._snapshot_mouse()

    def _end_pan(self):
        self._panning = False
        self._last_mouse = None

    def _snapshot_mouse(self):
        if self.base.mouseWatcherNode.has_mouse():
            m = self.base.win.get_pointer(0)
            self._last_mouse = (m.get_x(), m.get_y())

    # ========== ズーム ==========
    def zoom(self, direction: int):
        # direction: +1でズームイン(近づく)に感じるよう符号を調整
        factor = self.zoom_speed if direction > 0 else (1.0 / self.zoom_speed)
        self.distance = max(self.min_distance, min(self.max_distance, self.distance * factor))
        self._update_camera_pos()
        self._snapshot_mouse()

    # ========== 毎フレーム更新 ==========
    def _update_task(self, task: Task):
        if not self.base.mouseWatcherNode.has_mouse():
            self._last_mouse = None
            return Task.cont

        m = self.base.win.get_pointer(0)
        cur = (m.get_x(), m.get_y())

        if self._last_mouse is None:
            self._last_mouse = cur
            return Task.cont

        dx = cur[0] - self._last_mouse[0]
        dy = cur[1] - self._last_mouse[1]
        self._last_mouse = cur

        if self._rotating and (dx or dy):
            self._apply_rotate(dx, dy)

        if self._panning and (dx or dy):
            self._apply_pan(dx, dy)

        return Task.cont

    # ========== 具体動作 ==========
    def _apply_rotate(self, dx: float, dy: float):
        self.yaw += dx * self.rotate_sensitivity
        self.pitch -= dy * self.rotate_sensitivity
        self.pitch = max(self.min_pitch, min(self.max_pitch, self.pitch))
        self._update_camera_pos()

    def _apply_pan(self, dx: float, dy: float):
        # 画面上のピクセル移動をカメラの右・上ベクトルに変換して平行移動
        right = self.base.camera.get_quat().get_right()   # Vec3
        up = self.base.camera.get_quat().get_up()         # Vec3
        scale = self.distance * self.pan_speed
        delta = right * (-dx * scale) + up * (dy * scale)
        self.target += delta
        self._update_camera_pos()

    def _update_camera_pos(self):
        # 球面→デカルト変換（-Y 前方に合わせる）
        r = max(self.min_distance, min(self.max_distance, self.distance))
        yaw = radians(self.yaw)
        pitch = radians(self.pitch)

        x = r * cos(pitch) * sin(yaw)
        y = -r * cos(pitch) * cos(yaw)   # -Y が前
        z = r * sin(pitch)

        pos = self.target + Vec3(x, y, z)
        self.base.camera.set_pos(pos)
        self.base.camera.look_at(self.target)

    # ========== 修飾キー（Alt判定）==========
    def _alt_down(self) -> bool:
        mods = self.base.mouseWatcherNode.get_modifier_buttons()
        # 左右AltどちらでもOK（macOSのOptionもここで拾える）
        return (
            mods.is_down(KeyboardButton.alt()) or
            mods.is_down(KeyboardButton.lalt()) or
            mods.is_down(KeyboardButton.ralt())
        )
