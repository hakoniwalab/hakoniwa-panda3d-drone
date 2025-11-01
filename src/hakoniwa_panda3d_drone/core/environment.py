from typing import Optional, Tuple
from pathlib import Path
from panda3d.core import NodePath, Point3
from hakoniwa_panda3d_drone.primitive.render import RenderEntity

class EnvironmentEntity(RenderEntity):
    def __init__(
        self,
        render: NodePath,
        name: str,
        model_path: str,
        pos: Optional[Tuple[float, float, float]] = None,
        hpr: Optional[Tuple[float, float, float]] = None,
        scale: float = 1.0,
        loader=None,
    ):
        # RenderEntity は (render, name) で初期化
        super().__init__(render, name)

        # loader は ShowBase.loader を使う（明示渡しがなければ base.loader）
        if loader is None:
            # ShowBase 継承前提
            from direct.showbase import ShowBase
            loader = ShowBase.ShowBase.loader  # 型的には存在する

        # パス解決（呼び出し元の cwd 依存を避ける）
        p = Path(model_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()

        # モデルロード
        self.load_model(loader, str(p), copy=True)

        # 表裏両面（屋内モデル対策）
        self.np.setTwoSided(True)

        # 姿勢・スケール
        if scale is not None:
            self.np.setScale(scale)
        if pos is not None:
            self.set_pos(*pos)
        if hpr is not None and hasattr(self, "_geom_np"):
            # RenderEntity のジオムノードに HPR を適用する仕様に合わせる
            self._geom_np.setHpr(*hpr)

        # 大きすぎ/小さすぎ補正
        mn, mx = self.np.getTightBounds()
        if mn and mx:
            diag = (mx - mn).length()
            if diag > 1e4:
                self.np.setScale(100.0 / diag)
            elif diag < 1e-2:
                self.np.setScale(100.0 / max(diag, 1e-6))
