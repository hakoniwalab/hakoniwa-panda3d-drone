from panda3d.core import NodePath, Vec3
from hakoniwa_panda3d_drone.primitive.polygon import Polygon
from typing import Optional

class RenderEntity:
    """NodePath を持ち、Polygon から受け取った GeomNode をぶら下げる"""
    def __init__(self, parent, name: str = "entity"):
        self.np = parent.attachNewNode(name)
        self._geom_np: Optional[NodePath] = None  # 子ジオメトリの NodePath
        self.children = []

    def add_child(self, child: 'RenderEntity'):
        """子エンティティをぶら下げる"""
        child.np.reparentTo(self.np)
        self.children.append(child)

    def set_polygon(self, poly: Polygon):
        node = poly.make_geom_node()
        # 既存を差し替え
        if self._geom_np is not None:
            self._geom_np.removeNode()
        self._geom_np = self.np.attachNewNode(node)
        # 裏面が消えるのが気になるなら TwoSided
        self._geom_np.setTwoSided(False) #裏面は描画しない

    # --- 追加: 外部モデル(NodePath)を統合 ---
    def _set_model(self, model_np: NodePath, copy: bool = True):
        """
        model_np をこのエンティティ配下にぶら下げる。
        copy=True: model_np をインスタンス化(copy_to)して共有可
        copy=False: model_np 自体をreparent（所有権を移す）
        """
        if self._geom_np is not None:
            self._geom_np.removeNode()
            self._geom_np = None
        self._geom_np = model_np.copy_to(self.np) if copy else model_np.reparentTo(self.np) or model_np


    def load_model(self, loader, path: str, copy: bool = True):
        """loader.loadModel(path) して set_model までを一手に。"""
        print(f"Loading model from: {path}")
        model_np = loader.loadModel(path, noCache=True)
        self._set_model(model_np, copy=copy)

    def clear(self):
        """現在の子モデル/ジオメトリを外す"""
        if self._geom_np is not None:
            self._geom_np.removeNode()
            self._geom_np = None


    # 位置・姿勢などの薄いAPI（必要に応じて）
    def set_pos(self, x, y, z): 
        self.np.setPos(x, y, z)

    def move(self, dx=0, dy=0, dz=0): 
        self.np.setPos(self.np.getPos() + Vec3(dx, dy, dz))

    def set_hpr(self, h, p, r): 
        self.np.setHpr(h, p, r)

    def rotate(self, dh=0, dp=0, dr=0): 
        h, p, r = self.np.getHpr()
        self.np.setHpr(h + dh, p + dp, r + dr)


    def rotate_child_yaw(self, delta_yaw: float):
        self._geom_np.setH(self._geom_np.getH() + delta_yaw)
