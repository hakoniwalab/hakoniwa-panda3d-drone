from abc import ABC, abstractmethod
from typing import List, Tuple
from panda3d.core import (
    GeomNode, Geom, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GeomTriangles, Vec3, Vec4
)
Color = Tuple[float, float, float, float]

class Polygon(ABC):
    """形状の抽象：GeomNode を作って返す責務だけを持つ"""
    def make_geom_node(self, name: str = "polygon") -> GeomNode:
        vformat = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData(name, vformat, Geom.UH_static)
        vdata.setNumRows(len(self.vtx))

        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        cw = GeomVertexWriter(vdata, "color")


        # 書き込み
        for p, n, col in zip(self.vtx, self.normals, self.colors):
            vw.addData3f(p)
            nw.addData3f(n)
            cw.addData4f(*col)

        prim = GeomTriangles(Geom.UH_static)
        for a, b, c in self.tris:
            prim.addVertices(a, b, c)
        prim.closePrimitive()

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode(name)
        node.addGeom(geom)
        return node

class Cube(Polygon):
    def __init__(self, size: float = 0.2, vertex_colors: List[Color] | None = None):
        self.size = size
        s = size * 0.5
        # 8頂点
        self.vtx: List[Vec3] = [
            Vec3(-s, -s, -s), Vec3( s, -s, -s), Vec3( s,  s, -s), Vec3(-s,  s, -s),
            Vec3(-s, -s,  s), Vec3( s, -s,  s), Vec3( s,  s,  s), Vec3(-s,  s,  s),
        ]
        # 12三角形（6面×2）
        self.tris: List[Tuple[int,int,int]] = [
            (0,1,2), (0,2,3),     # -Z
            (4,6,5), (4,7,6),     # +Z
            (1,5,6), (1,6,2),     # +X
            (0,3,7), (0,7,4),     # -X
            (3,2,6), (3,6,7),     # +Y
            (0,4,5), (0,5,1),     # -Y
        ]
        if vertex_colors is None:
            white = (1, 1, 1, 1)
            self.colors: List[Color] = [white for _ in range(8)]
        else:
            assert len(vertex_colors) == 8
            self.colors = vertex_colors

        # --- 頂点法線を三角形から集計して求める（スムーズシェーディング） ---
        normals = [Vec3(0, 0, 0) for _ in self.vtx]
        for a, b, c in self.tris:
            pa, pb, pc = self.vtx[a], self.vtx[b], self.vtx[c]
            n = (pb - pa).cross(pc - pa)
            if n.length_squared() > 0:
                n.normalize()
                normals[a] += n; normals[b] += n; normals[c] += n
        for i in range(len(normals)):
            if normals[i].length_squared() > 0:
                normals[i].normalize()
        self.normals = normals

    
class Plane(Polygon):
    """Unity の Plane に相当（XZ 平面・原点中心）。size は一辺の長さ。"""
    def __init__(self, size: float = 2.0, color: Color = (0.2, 0.6, 0.6, 1.0)):
        s = size * 0.5
        # XY平面で Z=0 が床（上方向は +Z）
        self.vtx: List[Vec3] = [
            Vec3(-s, -s, 0),  # 0
            Vec3( s, -s, 0),  # 1
            Vec3( s,  s, 0),  # 2
            Vec3(-s,  s, 0),  # 3
        ]
        self.tris: List[Tuple[int, int, int]] = [
            (0, 1, 2),
            (0, 2, 3),
        ]
        # 4 頂点すべて同色（単色）
        self.colors: List[Color] = [color] * 4

        # 法線は全頂点で上向き
        self.normals: List[Vec3] = [Vec3(0, 0, 1)] * 4



