import sys
import time
import hakopy
from hakoniwa_pdu.pdu_manager import PduManager
from hakoniwa_pdu.impl.shm_communication_service import ShmCommunicationService
from hakoniwa_pdu.pdu_msgs.geometry_msgs.pdu_conv_Twist import pdu_to_py_Twist
from hakoniwa_pdu.pdu_msgs.hako_mavlink_msgs.pdu_conv_HakoHilActuatorControls import pdu_to_py_HakoHilActuatorControls
from hakoniwa_panda3d_drone.visualizer import App
from hakoniwa_panda3d_drone.primitive.frame import Frame
import threading

# === globals ===
delta_time_usec = 0
config_path = ''
visualizer_runner: App = None

def my_sleep():
    """箱庭シミュレータのクロックに同期してsleep"""
    global delta_time_usec
    if not hakopy.usleep(delta_time_usec):
        return False
    time.sleep(delta_time_usec / 1_000_000.0)
    return True

# === メイン処理 ===
def run():
    """
    手動タイミング制御ループ。
    各ドローン位置を監視し、環境プロパティから外乱(風/温度/気圧)をPDUに書き戻す。
    """
    global config_path, visualizer_runner
    print("[Visualizer] Start Environment Control")

    pdu = PduManager()
    pdu.initialize(config_path=config_path, comm_service=ShmCommunicationService())
    pdu.start_service_nowait()

    # --- メインループ ---
    while True:
        if not my_sleep():
            break

        pdu.run_nowait()

        raw_pose = pdu.read_pdu_raw_data('Drone', 'pos')
        pose = pdu_to_py_Twist(raw_pose) if raw_pose else None

        if pose is None:
            continue

        raw_actuator = pdu.read_pdu_raw_data('Drone', 'motor')
        rotor_speed = 0.0
        if raw_actuator:
            actuator = pdu_to_py_HakoHilActuatorControls(raw_actuator)
            if len(actuator.controls) >= 4:
                rotor_speed = actuator.controls[0]  # 代表値
                rotor_speed *= 400.0 #適当にスケール

        #print(f"[Visualizer] Drone Position: "
        #      f"x={pose.linear.x:.2f} y={pose.linear.y:.2f} z={pose.linear.z:.2f} | "
        #      f"roll={pose.angular.x:.2f} pitch={pose.angular.y:.2f} yaw={pose.angular.z:.2f} | "
        #      f"rotor_speed={rotor_speed:.2f}")

        if visualizer_runner is not None:
            panda3d_pos, panda3d_orientation = Frame.to_panda3d(pose)
            visualizer_runner.set_pose_and_rotation(panda3d_pos, panda3d_orientation, rotor_speed)

    return 0

def start_run_thread():
    thread = threading.Thread(target=run, name="EnvControlThread", daemon=True)
    thread.start()
    return thread

def stop_run_thread(thread):
    # run() 内で break などの終了条件を監視している前提
    thread.join(timeout=2.0)
    if thread.is_alive():
        print("Warning: run() thread still alive.")

# === エントリポイント ===
def main():
    global delta_time_usec, config_path, visualizer_runner, drone_config_path

    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <config_path> <drone_config_path> <delta_time_msec>")
        return 1

    config_path = sys.argv[1]
    drone_config_path = sys.argv[2]
    delta_time_usec = int(sys.argv[3]) * 1000

    asset_name = 'Visualizer'

    print(f"[Visualizer] Registering asset '{asset_name}'")
    ret = hakopy.init_for_external()
    if not ret:
        print("[ERROR] Failed to register asset")
        return 1

    print("[Visualizer] Start simulation...")
    # thread for run()
    t = start_run_thread()

    visualizer_runner = App(drone_config_path)
    visualizer_runner.run()

    stop_run_thread(t)

    return 0


if __name__ == "__main__":
    sys.exit(main())
