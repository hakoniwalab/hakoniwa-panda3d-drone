# core/light.py
from panda3d.core import AmbientLight, DirectionalLight, Vec3, Vec4, NodePath

class LightRig:
    """シンプルな環境光 + 平行光セット"""
    def __init__(self, render: NodePath, shadows: bool = False):
        self.render = render

        # Ambient（明るめに変更）
        self.ambient_np = self._make_ambient(color=Vec4(0.4, 0.4, 0.45, 1.0))

        # Directional（真上から強めに）
        self.key_np = self._make_directional(
            color=Vec4(0.8, 0.8, 0.75, 1.0),
            hpr=Vec3(45, -70, 0),  # 角度を調整
            shadows=shadows
        )

    def _make_ambient(self, color: Vec4) -> NodePath:
        amb = AmbientLight("ambient")
        amb.set_color(color)
        np = self.render.attach_new_node(amb)
        self.render.set_light(np)
        return np

    def _make_directional(self, color: Vec4, hpr: Vec3, shadows: bool=False) -> NodePath:
        d = DirectionalLight("key")
        d.set_color(color)
        if shadows:
            d.set_shadow_caster(True, 2048, 2048)
            # 影のカメラ範囲を設定
            lens = d.get_lens()
            lens.set_film_size(4, 4)  # 影の範囲
            lens.set_near_far(0.1, 10)  # 影を計算する距離範囲

        np = self.render.attach_new_node(d)
        np.set_hpr(hpr)
        self.render.set_light(np)
        return np

    def set_key_dir(self, hpr: Vec3):
        self.key_np.set_hpr(hpr)

    def set_key_intensity(self, scale: float):
        light: DirectionalLight = self.key_np.node()
        c = light.get_color()
        light.set_color((c[0]*scale, c[1]*scale, c[2]*scale, c[3]))

    def toggle(self, on: bool):
        if on:
            self.render.set_light(self.ambient_np)
            self.render.set_light(self.key_np)
        else:
            self.render.clear_light(self.ambient_np)
            self.render.clear_light(self.key_np)