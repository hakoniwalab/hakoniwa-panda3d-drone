import sys
import time
import asyncio
import threading
from queue import SimpleQueue
import sys
sys.stdout.reconfigure(line_buffering=True)

import hakopy
from hakoniwa_pdu.pdu_manager import PduManager
from hakoniwa_pdu.impl.shm_communication_service import ShmCommunicationService
from hakoniwa_pdu.pdu_msgs.geometry_msgs.pdu_conv_Twist import pdu_to_py_Twist
from hakoniwa_pdu.pdu_msgs.hako_mavlink_msgs.pdu_conv_HakoHilActuatorControls import pdu_to_py_HakoHilActuatorControls
from hakoniwa_pdu.pdu_msgs.hako_msgs.pdu_pytype_GameControllerOperation import GameControllerOperation
from hakoniwa_pdu.pdu_msgs.hako_msgs.pdu_conv_GameControllerOperation import py_to_pdu_GameControllerOperation, pdu_to_py_GameControllerOperation

# --- RPC 関連 ---
from hakoniwa_pdu.service.shm_common import ShmCommon
from hakoniwa_pdu.rpc.shm.shm_pdu_service_server_manager import ShmPduServiceServerManager
from hakoniwa_pdu.pdu_msgs.drone_srv_msgs.pdu_pytype_CameraCaptureImageRequest import CameraCaptureImageRequest
from hakoniwa_pdu.pdu_msgs.drone_srv_msgs.pdu_pytype_CameraCaptureImageResponse import CameraCaptureImageResponse
from hakoniwa_pdu.rpc.auto_wire import make_protocol_servers
from hakoniwa_pdu.rpc.protocol_server import ProtocolServerImmediate

from hakoniwa_panda3d_drone.visualizer import App
from hakoniwa_panda3d_drone.primitive.frame import Frame


def is_hakoniwa_running() -> bool:
    import subprocess
    result = subprocess.run(
        ["hako-cmd", "status"],
        capture_output=True,
        text=True
    )

    output = result.stdout.strip()
    print(output)

    if "status=running" in output:
        print("✅ Hakoniwa is running!")
        return True
    else:
        print("❌ Hakoniwa is NOT running.")
        return False

# === globals ===
delta_time_usec = 0
drone_config_path = ''
service_config_path = ''
pdu_config_path = ''
pdu_offset_path = ''
visualizer_runner: App = None
server_pdu_manager: ShmPduServiceServerManager = None
protocol_server: ProtocolServerImmediate = None

# Panda3D スレッドへ渡す更新/命令
ui_queue: SimpleQueue = SimpleQueue()
# asyncio ループ参照（別スレッド）
async_loop_holder = {"loop": None}

# ========== 非同期 sleep ==========
async def my_sleep_async():
    global delta_time_usec
    # hakopy.usleep はブロッキングなので別スレッドで実行
    ok = await asyncio.to_thread(hakopy.usleep, delta_time_usec)
    if not ok:
        return False
    # シミュレータクロック分だけ await
    await asyncio.sleep(delta_time_usec / 1_000_000.0)
    return True

# ========== 環境制御ループ ==========
async def env_control_loop(stop_event: asyncio.Event):
    global server_pdu_manager
    print("[Visualizer] Start Environment Control (async)")
    while not is_hakoniwa_running():
        print("[Visualizer] Waiting for Hakoniwa to start...")
        await asyncio.sleep(1.0)

    while not stop_event.is_set():
        sys.stdout.flush()
        if not await my_sleep_async():
            break

        server_pdu_manager.run_nowait()

        raw_pose = server_pdu_manager.read_pdu_raw_data('Drone', 'pos')
        pose = pdu_to_py_Twist(raw_pose) if raw_pose else None
        if pose is None:
            continue

        rotor_speed = 0.0
        raw_actuator = server_pdu_manager.read_pdu_raw_data('Drone', 'motor')
        if raw_actuator:
            actuator = pdu_to_py_HakoHilActuatorControls(raw_actuator)
            if len(actuator.controls) >= 4:
                rotor_speed = actuator.controls[0] * 400.0
        else:
            pass
        panda3d_pos, panda3d_orientation = Frame.to_panda3d(pose)
        ui_queue.put(("pose", (panda3d_pos, panda3d_orientation, rotor_speed)))

        try:
            raw_game_ctrl = server_pdu_manager.read_pdu_raw_data('Drone', 'hako_cmd_game')
            game_ctrl = pdu_to_py_GameControllerOperation(raw_game_ctrl) if raw_game_ctrl else None
            if game_ctrl is not None:
                # UI スレッドへ命令を投げる
                ui_queue.put(("game_controller", game_ctrl))
        except Exception as e:
            pass

    print("[Visualizer] Environment Control loop finished")

# ========== RPC: カメラキャプチャ ==========
async def handle_camera_capture(req: CameraCaptureImageRequest) -> CameraCaptureImageResponse:
    """
    非同期ループ側で受けた RPC を Panda3D スレッドに依頼し、結果を await で待つ。
    """
    loop = async_loop_holder["loop"]
    fut: asyncio.Future = loop.create_future()

    # UI スレッドへ要求を投げる（UI 側で画像バイト列を作ってくれる想定）
    ui_queue.put(("capture_request", {
        "drone_name": req.drone_name,
        "image_type": req.image_type,
        "future": fut,  # UI 側が loop.call_soon_threadsafe で set_result する
    }))

    try:
        image_bytes: bytes = await asyncio.wait_for(fut, timeout=5.0)  # 必要なら延長
        # レスポンス生成
        print(f"[RPC] Captured image for drone '{req.drone_name}', type='{req.image_type}', size={len(image_bytes)} bytes")
        res = CameraCaptureImageResponse()
        res.ok = True
        res.data = list(image_bytes)
        res.message = f"Captured type={req.image_type} from {req.drone_name} len={len(res.data)}"
        return res
    except asyncio.TimeoutError:
        res = CameraCaptureImageResponse()
        res.ok = False
        res.data = []
        res.message = "Capture timeout"
        return res

async def rpc_server_task(stop_event: asyncio.Event):
    global server_pdu_manager, protocol_server
    """
    箱庭 RPC の起動・待受けを行うタスク。
    """
    print("[RPC] Starting RPC server...")
    while not is_hakoniwa_running():
        print("[RPC] Waiting for Hakoniwa to start...")
        await asyncio.sleep(1.0)


    services = [
        {
            "service_name": "DroneService/CameraCaptureImage",
            "srv": "CameraCaptureImage",
            "max_clients": 1,
        }
    ]

    protocol_server = make_protocol_servers(
        pdu_manager=server_pdu_manager,
        services=services,
        ProtocolServerClass=ProtocolServerImmediate,
        pkg="hakoniwa_pdu.pdu_msgs.drone_srv_msgs"
    )
    protocol_server.start_services()

    print("[RPC] RPC server is running.")
    sys.stdout.flush()
    # serve() はハンドラマップを受け取って待受
    serve_task = asyncio.create_task(protocol_server.serve({
        "DroneService/CameraCaptureImage": handle_camera_capture,
    }))
    print("[RPC] Service server started for DroneService/CameraCaptureImage")

    # 停止指示を待つ
    await stop_event.wait()

    # 終了処理
    serve_task.cancel()
    try:
        await serve_task
    except asyncio.CancelledError:
        pass

    print("[RPC] RPC server stopped")

# ========== Panda3D 側：UI タスク ==========
def panda3d_ui_task(task):
    global visualizer_runner
    from direct.task.Task import cont

    MAX_APPLY = 8
    n = 0
    while n < MAX_APPLY:
        try:
            kind, payload = ui_queue.get_nowait()
        except Exception:
            break

        if kind == "pose" and visualizer_runner is not None:
            pos, orient, rotor_speed = payload
            visualizer_runner.set_pose_and_rotation(pos, orient, rotor_speed)
        elif kind == "game_controller" and visualizer_runner is not None:
            game_ctrl: GameControllerOperation = payload
            visualizer_runner.update_game_controller_ui(game_ctrl)
        elif kind == "capture_request":
            # payload: {drone_name, image_type, future}
            drone_name = payload["drone_name"]
            image_type = payload["image_type"]
            fut: asyncio.Future = payload["future"]
            try:
                image_bytes = visualizer_runner.capture_camera(image_type=image_type, drone_name=drone_name)
                loop = async_loop_holder["loop"]
                if loop is not None and not fut.done():
                    loop.call_soon_threadsafe(fut.set_result, image_bytes)
            except Exception as e:
                loop = async_loop_holder["loop"]
                if loop is not None and not fut.done():
                    loop.call_soon_threadsafe(fut.set_exception, e)

        n += 1

    return cont

# ========== 非同期ランタイム起動（別スレッド） ==========
def start_asyncio_runtime(loop_holder: dict, stop_event: asyncio.Event):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder["loop"] = loop

    # 並列に環境制御と RPC を起動
    tasks = [
        loop.create_task(env_control_loop(stop_event)),
        loop.create_task(rpc_server_task(stop_event)),
    ]

    try:
        loop.run_until_complete(asyncio.gather(*tasks))
    finally:
        loop.stop()
        loop.close()

# ========== エントリポイント ==========
def main():
    global delta_time_usec, drone_config_path
    global service_config_path, pdu_config_path, pdu_offset_path
    global visualizer_runner
    global server_pdu_manager, protocol_server

    if len(sys.argv) != 6:
        print(f"Usage: {sys.argv[0]} <drone_config_path> <delta_time_msec> <service.json> <pdu_config.json> <pdu_offset_dir>")
        return 1

    drone_config_path  = sys.argv[1]
    delta_time_usec    = int(sys.argv[2]) * 1000
    service_config_path = sys.argv[3]
    pdu_config_path     = sys.argv[4]
    pdu_offset_path     = sys.argv[5]

    asset_name = 'Visualizer'
    print(f"[Visualizer] Registering asset '{asset_name}'")
    if not hakopy.init_for_external():
        print("[ERROR] Failed to register asset")
        return 1

    print("[Visualizer] Start simulation...")
    server_pdu_manager = ShmPduServiceServerManager("ServiceManager", pdu_config_path, pdu_offset_path)
    server_pdu_manager.initialize_services(service_config_path, delta_time_usec=delta_time_usec)

    # 非同期ランタイム起動（環境制御 + RPC）
    stop_event = asyncio.Event()
    t_async = threading.Thread(
        target=start_asyncio_runtime,
        args=(async_loop_holder, stop_event),
        name="EnvControl+RPC",
        daemon=True
    )
    t_async.start()

    # Panda3D（メインスレッド）
    visualizer_runner = App(drone_config_path)
    visualizer_runner.taskMgr.add(panda3d_ui_task, "ApplyUIUpdates")
    try:
        visualizer_runner.run()
    finally:
        loop = async_loop_holder.get("loop")
        if loop and loop.is_running():
            loop.call_soon_threadsafe(stop_event.set)
        t_async.join(timeout=3.0)
        if t_async.is_alive():
            print("Warning: asyncio loop thread still alive.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
