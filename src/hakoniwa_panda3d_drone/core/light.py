# core/light.py
from panda3d.core import AmbientLight, DirectionalLight, Vec3, Vec4, NodePath

class LightRig:
    """環境光 + 平行光。影は安全運転のデフォルト値、必要に応じて自動フィット可。"""
    def __init__(
        self,
        render: NodePath,
        shadows: bool = False,
        # 影のデフォルト設定（あとで auto_fit_shadow() を呼ぶと上書き）
        shadow_film_size: float = 50.0,   # シーンが大きい場合は 100〜300 に
        shadow_near: float = 0.5,
        shadow_far: float = 200.0,
        shadow_bias: float = 0.0015,      # 黒潰れ（アクネ）対策
        shadow_normal_offset: float = 0.5 # 接地面のチラつき対策
    ):
        self.render = render
        self._shadows = shadows

        # Ambient（やや明るめ）
        self.ambient_np = self._make_ambient(color=Vec4(0.35, 0.35, 0.4, 1.0))

        # Directional（斜め上から）
        self.key_np = self._make_directional(
            color=Vec4(0.9, 0.9, 0.85, 1.0),
            hpr=Vec3(45, -60, 0),
            shadows=shadows,
            film_size=shadow_film_size,
            near=shadow_near,
            far=shadow_far,
            bias=shadow_bias,
            normal_offset=shadow_normal_offset,
        )

    def _make_ambient(self, color: Vec4) -> NodePath:
        amb = AmbientLight("ambient")
        amb.setColor(color)
        np = self.render.attachNewNode(amb)
        self.render.setLight(np)
        return np

    def _make_directional(
        self,
        color: Vec4,
        hpr: Vec3,
        shadows: bool=False,
        film_size: float=50.0,
        near: float=0.5,
        far: float=200.0,
        bias: float=0.0015,
        normal_offset: float=0.5,
    ) -> NodePath:
        d = DirectionalLight("key")
        d.setColor(color)

        if shadows:
            # 解像度はまず 2048。必要なら 4096 へ
            d.setShadowCaster(True, 2048, 2048)
            lens = d.getLens()  # OrthographicLens
            lens.setFilmSize(film_size, film_size)
            lens.setNearFar(near, far)
            # バイアス設定（黒い斑点・チラつき軽減）
            d.setShadowBias(bias)
            d.setShadowNormalOffsetScale(normal_offset)

        np = self.render.attachNewNode(d)
        np.setHpr(hpr)
        self.render.setLight(np)
        return np

    # ---- 公開API ----
    def set_key_dir(self, hpr: Vec3):
        self.key_np.setHpr(hpr)

    def set_key_intensity(self, scale: float):
        light: DirectionalLight = self.key_np.node()
        c = light.getColor()
        light.setColor((c[0]*scale, c[1]*scale, c[2]*scale, c[3]))

    def toggle(self, on: bool):
        if on:
            self.render.setLight(self.ambient_np)
            self.render.setLight(self.key_np)
        else:
            self.render.clearLight(self.ambient_np)
            self.render.clearLight(self.key_np)

    def auto_fit_shadow(self, target_np: NodePath, margin: float = 1.3):
        """対象ノードのバウンドに合わせてシャドウカメラの範囲を自動調整."""
        if not self._shadows:
            return
        light = self.key_np.node()
        lens = light.getLens()

        mn, mx = target_np.getTightBounds()
        if not mn or not mx:
            return

        size = (mx - mn)
        w = max(1.0, size.x) * margin
        h = max(1.0, size.y) * margin
        # filmは正方形でOK（回転しても破綻しにくい）
        film = max(w, h)
        lens.setFilmSize(film, film)

        depth = max(1.0, size.z) * margin
        # 平行光のnear/farは“影を落としたい高さ”に合わせる
        lens.setNearFar(0.5, max(50.0, depth * 5.0))
