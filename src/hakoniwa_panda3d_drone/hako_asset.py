import sys
import time
import asyncio
import threading
from queue import SimpleQueue

import hakopy
from hakoniwa_pdu.pdu_manager import PduManager
from hakoniwa_pdu.impl.shm_communication_service import ShmCommunicationService
from hakoniwa_pdu.pdu_msgs.geometry_msgs.pdu_conv_Twist import pdu_to_py_Twist
from hakoniwa_pdu.pdu_msgs.hako_mavlink_msgs.pdu_conv_HakoHilActuatorControls import pdu_to_py_HakoHilActuatorControls

from hakoniwa_panda3d_drone.visualizer import App
from hakoniwa_panda3d_drone.primitive.frame import Frame

# === globals ===
delta_time_usec = 0
config_path = ''
drone_config_path = ''
visualizer_runner: App = None

# Panda3D スレッドに UI 反映を依頼するためのキュー
ui_queue: SimpleQueue = SimpleQueue()

async def my_sleep_async():
    """箱庭シミュレータのクロックに(できる限り)同期して non-blocking sleep"""
    global delta_time_usec
    # hakopy.usleep はブロッキングなので別スレッドで実行
    ok = await asyncio.to_thread(hakopy.usleep, delta_time_usec)
    if not ok:
        return False
    # シミュレータクロック分だけ await
    await asyncio.sleep(delta_time_usec / 1_000_000.0)
    return True

async def env_control_loop(stop_event: asyncio.Event):
    """
    非同期環境制御ループ。
    各ドローン位置を監視し、必要な値を Panda3D スレッドにキューで渡す。
    """
    print("[Visualizer] Start Environment Control (async)")
    pdu = PduManager()
    pdu.initialize(config_path=config_path, comm_service=ShmCommunicationService())
    pdu.start_service_nowait()

    while not stop_event.is_set():
        if not await my_sleep_async():
            break

        # PDU のポーリングは nowait で軽く
        pdu.run_nowait()

        raw_pose = pdu.read_pdu_raw_data('Drone', 'pos')
        pose = pdu_to_py_Twist(raw_pose) if raw_pose else None
        if pose is None:
            continue

        # モータ回転数の代表値
        rotor_speed = 0.0
        raw_actuator = pdu.read_pdu_raw_data('Drone', 'motor')
        if raw_actuator:
            actuator = pdu_to_py_HakoHilActuatorControls(raw_actuator)
            if len(actuator.controls) >= 4:
                rotor_speed = actuator.controls[0] * 400.0  # 適当なスケール

        panda3d_pos, panda3d_orientation = Frame.to_panda3d(pose)

        # ここでは Panda3D オブジェクトに触らず、UI キューへ積む
        ui_queue.put(("pose", (panda3d_pos, panda3d_orientation, rotor_speed)))

    print("[Visualizer] Environment Control loop finished")

def panda3d_ui_task(task):
    """
    Panda3D の taskMgr から呼ぶ UI 反映タスク。
    別スレッドから積まれた更新を安全に取り出して適用。
    """
    global visualizer_runner
    try:
        # 1 フレームで多すぎる反映は避けるため、上限を決める
        MAX_APPLY = 5
        n = 0
        while n < MAX_APPLY:
            try:
                kind, payload = ui_queue.get_nowait()
            except Exception:
                break
            if kind == "pose" and visualizer_runner is not None:
                pos, orient, rotor_speed = payload
                # ここはメインスレッドなので安全に触れる
                visualizer_runner.set_pose_and_rotation(pos, orient, rotor_speed)
            n += 1
    except Exception as e:
        print(f"[Visualizer] UI task error: {e}")
    return task.cont

def start_asyncio_runtime(loop_holder: dict, stop_event: asyncio.Event):
    """
    別スレッドで asyncio イベントループを起動。
    `loop_holder['loop']` にループインスタンスを格納。
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder['loop'] = loop
    # メインの環境制御コルーチンを起動
    main_task = loop.create_task(env_control_loop(stop_event))
    try:
        loop.run_until_complete(main_task)
    finally:
        loop.stop()
        loop.close()

def main():
    global delta_time_usec, config_path, drone_config_path, visualizer_runner

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

    # --- 非同期ランタイム（別スレッド）を起動 ---
    stop_event = asyncio.Event()  # これは別スレッド内で使われるので箱だけ用意
    # stop_event はループの中で参照されるが、別スレッド生成前に作って渡せば OK
    loop_holder = {}
    t_async = threading.Thread(
        target=start_asyncio_runtime,
        args=(loop_holder, stop_event),
        name="EnvControlAsyncLoop",
        daemon=True
    )
    t_async.start()

    # --- Panda3D アプリ（メインスレッド） ---
    visualizer_runner = App(drone_config_path)
    # UI 反映タスクを登録
    visualizer_runner.taskMgr.add(panda3d_ui_task, "ApplyUIUpdates")

    try:
        visualizer_runner.run()
    finally:
        # ウィンドウを閉じたら async ループへ停止指示
        loop = loop_holder.get('loop')
        if loop and loop.is_running():
            # stop_event.set() をイベントループスレッド側で実行する
            def _set():
                stop_event.set()
            loop.call_soon_threadsafe(_set)

        # スレッド終了待ち
        t_async.join(timeout=2.0)
        if t_async.is_alive():
            print("Warning: asyncio loop thread still alive.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
