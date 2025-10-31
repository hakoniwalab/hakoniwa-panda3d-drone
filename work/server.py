#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import asyncio
import hakopy
from hakoniwa_pdu.service.shm_common import ShmCommon
from hakoniwa_pdu.rpc.shm.shm_pdu_service_server_manager import ShmPduServiceServerManager
from hakoniwa_pdu.pdu_msgs.hako_srv_msgs.pdu_pytype_AddTwoIntsRequest import AddTwoIntsRequest
from hakoniwa_pdu.pdu_msgs.hako_srv_msgs.pdu_pytype_AddTwoIntsResponse import AddTwoIntsResponse
from hakoniwa_pdu.rpc.auto_wire import make_protocol_servers
from hakoniwa_pdu.rpc.protocol_server import ProtocolServerImmediate

async def my_add_handler(req: AddTwoIntsRequest):
    result = AddTwoIntsResponse()
    result.sum = req.a + req.b
    return result

async def main_async():

    asset_name = 'ServiceManager'
    service_config_path = 'service.json'
    pdu_config_path = 'pdu_config.json'
    pdu_offset_path = '/usr/local/share/hakoniwa/offset'
    delta_time_usec = 1000 * 1000

    shm = ShmCommon(service_config_path, pdu_offset_path, delta_time_usec)
    shm.start_conductor()
    shm.initialize()
    shm.start_service()
    server_pdu_manager = ShmPduServiceServerManager(asset_name, pdu_config_path, pdu_offset_path)
    services=[
        {
            "service_name": "Service/Add",
            "srv": "AddTwoInts",
            "max_clients": 1,
        }
    ]
    server_pdu_manager.initialize_services(service_config_path, delta_time_usec=delta_time_usec)
    protocol_server: ProtocolServerImmediate = make_protocol_servers(
        pdu_manager=server_pdu_manager,
        services=services,
        ProtocolServerClass=ProtocolServerImmediate,
    )
    protocol_server.start_services()
    await protocol_server.serve({
        "Service/Add": my_add_handler,
    })

    print("Service server started for Service/Add")

    shm.stop_conductor()
    return 0

def main():
    return asyncio.run(main_async())

if __name__ == "__main__":
    sys.exit(main())
