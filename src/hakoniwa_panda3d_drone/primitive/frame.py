from hakoniwa_pdu.pdu_msgs.geometry_msgs.pdu_pytype_Twist import Twist
from panda3d.core import Vec3
from typing import Tuple
from math import pi

class Frame:
    """
    箱庭式: geometry_msgs/Twist を 姿勢(Position+RPY) として扱う。
    ROS座標系(+X前,+Y左,+Z上) ⇔ Panda3D(+X右,-Y前,+Z上)
    orientation_deg: Panda3DのHPR[deg]
    ROS Twist.angular: RPY[rad]
    """
    @staticmethod
    def to_ros_twist(pos: Vec3, orientation_deg: Vec3) -> Twist:
        twist = Twist()
        twist.linear.x = pos.y
        twist.linear.y = -pos.x
        twist.linear.z = pos.z
        twist.angular.x = orientation_deg.z * pi / 180.0 #Roll
        twist.angular.y = -orientation_deg.y * pi / 180.0 #Pitch
        twist.angular.z = orientation_deg.x * pi / 180.0 #Heading
        return twist

    @staticmethod
    def to_panda3d(ros_twist: Twist) -> Tuple[Vec3, Vec3]:
        pos = Vec3(
            -ros_twist.linear.y, 
            ros_twist.linear.x, 
            ros_twist.linear.z)
        orientation = Vec3(
            ros_twist.angular.z * 180.0 / pi, #heading
            -ros_twist.angular.y * 180.0 / pi, #pitch
            ros_twist.angular.x * 180.0 / pi)  #roll
        return pos, orientation
