#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import asyncio
from hakoniwa_pdu.service.shm_common import ShmCommon
from hakoniwa_pdu.service.shm_service_client import ShmServiceClient
from hakoniwa_pdu.pdu_msgs.drone_srv_msgs.pdu_pytype_CameraCaptureImageRequest import CameraCaptureImageRequest
from hakoniwa_pdu.pdu_msgs.drone_srv_msgs.pdu_pytype_CameraCaptureImageResponse import CameraCaptureImageResponse
from hakoniwa_pdu.rpc.auto_wire import make_protocol_clients
from hakoniwa_pdu.rpc.protocol_client import ProtocolClientImmediate
from hakoniwa_pdu.rpc.shm.shm_pdu_service_client_manager import ShmPduServiceClientManager

async def main_async():

    asset_name = None
    pdu_config_path = 'pdu_config.json'
    service_config_path = './service.json'
    pdu_offset_path = '/usr/local/share/hakoniwa/offset'
    delta_time_usec = 1000 * 1000

    shm = ShmCommon(service_config_path, pdu_offset_path, delta_time_usec)
    if shm.initialize() == False:
        print("Failed to initialize shm")
        return 1
    

    client_pdu_manager = ShmPduServiceClientManager(asset_name = asset_name, pdu_config_path=pdu_config_path, offset_path= pdu_offset_path)
    client_pdu_manager.initialize_services(service_config_path, delta_time_usec=delta_time_usec)
    protocol_clients: dict[str, ProtocolClientImmediate] = make_protocol_clients(
        pdu_manager=client_pdu_manager,
        services= [
            {
                "service_name": "DroneService/CameraCaptureImage",
                "client_name": "Client01",
                "srv": "CameraCaptureImage",
            }
        ],
        pkg = "hakoniwa_pdu.pdu_msgs.drone_srv_msgs",
        ProtocolClientClass=ProtocolClientImmediate,
    )
    first_client = next(iter(protocol_clients.values()))
    first_client.start_service(None)
    for client in protocol_clients.values():
        client.register()

    req = CameraCaptureImageRequest()
    req.drone_name = "Drone"
    req.image_type = "png"
    res = protocol_clients["DroneService/CameraCaptureImage"].call(req)
    if res is None:
        print("Failed to get response")
        return 1
    print(f"Response: {res}")
    png_images = res.data
    with open("captured_image.png", "wb") as f:
        f.write(bytearray(png_images))
    print("Image saved to captured_image.png")
    return 0

def main():
    return asyncio.run(main_async())

if __name__ == "__main__":
    sys.exit(main())
