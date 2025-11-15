import xml.etree.ElementTree as ET
from typing import List, Tuple, cast
from panda3d.core import Vec3, Vec4, NodePath

from .polygon import Cube
from .render import RenderEntity

class BuildingData:
    """MJCFから抽出した建物の情報を格納するデータクラス"""
    def __init__(self, name: str, size: Tuple[float, float, float], pos: Vec3, hpr: Vec3, color: Tuple[float, float, float, float]):
        self.name = name
        self.size = size
        self.pos = pos
        self.hpr = hpr
        self.color = color

def _parse_vector(s: str) -> List[float]:
    """スペース区切りの文字列をfloatのリストに変換する"""
    return [float(x) for x in s.split()]

def load_buildings_from_mjcf(filepath: str) -> List[BuildingData]:
    """
    MuJoCo MJCFファイルを解析し、建物の情報を抽出してリストとして返す。
    この際、MuJoCoの座標系からPanda3Dの座標系への変換も行う。

    :param filepath: MJCFファイルのパス
    :return: BuildingDataオブジェクトのリスト
    """
    tree = ET.parse(filepath)
    root = tree.getroot()
    buildings: List[BuildingData] = []

    for geom in root.findall(".//geom"):
        name = geom.get("name")
        if name and name.startswith("geom_bldg_"):
            size_str = geom.get("size")
            pos_str = geom.get("pos")
            euler_str = geom.get("euler")
            rgba_str = geom.get("rgba")

            if not all([size_str, pos_str, euler_str, rgba_str]):
                continue

            # 属性をパース
            size_mj = _parse_vector(size_str)
            pos_mj = _parse_vector(pos_str)
            euler_mj = _parse_vector(euler_str)  # degrees
            color = cast(Tuple[float, float, float, float], tuple(_parse_vector(rgba_str)))

            # --- サイズ変換 ---
            size_pd = (size_mj[1] * 2, size_mj[0] * 2, size_mj[2] * 2)

            # --- 位置変換 ---
            # MuJoCo: x=前, y=左, z=上
            # Panda3D: x=右, y=前, z=上
            pos_pd = Vec3(pos_mj[1], -pos_mj[0], pos_mj[2])

            # --- 回転変換 ---
            hpr_pd = Vec3(euler_mj[2], euler_mj[1], euler_mj[0])

            green_color = (0.0, 1.0, 0.0, 1.0)
            building_data = BuildingData(
                name=name,
                size=size_pd,
                pos=pos_pd,
                hpr=hpr_pd,
                color=green_color
            )
            buildings.append(building_data)

    return buildings

def create_building_renders(parent_np: NodePath, building_data_list: List[BuildingData]) -> List[RenderEntity]:
    """
    BuildingDataのリストからRenderEntityを生成し、シーンに配置する。

    :param parent_np: 親となるNodePath
    :param building_data_list: 建物のデータリスト
    :return: 生成されたRenderEntityのリスト
    """
    renders: List[RenderEntity] = []
    for data in building_data_list:
        # Cubeは頂点カラーで色付けするため、8頂点全てに同じ色を設定
        vertex_colors = [data.color] * 8

        # Cubeジオメトリを生成
        cube = Cube(size=data.size, vertex_colors=vertex_colors)

        # RenderEntityを生成してシーンに配置
        entity = RenderEntity(parent_np, name=data.name)
        entity.set_polygon(cube)
        entity.set_pos(data.pos.x, data.pos.y, data.pos.z)
        entity.set_hpr(data.hpr.x, data.hpr.y, data.hpr.z)
        renders.append(entity)
    
    return renders
