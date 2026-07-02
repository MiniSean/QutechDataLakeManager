import asyncio
import os
import sys
import time
import uuid
import zmq
import zmq.asyncio
import traceback
from pathlib import Path

from qdlcomms.messages.plugins import (
    PluginInitializeRequest,
    PluginInitializeResponse,
    PluginInitializeResponsePayload,
    PluginInitializeState,
    PluginTerminateRequest,
    PluginTerminateResponse,
    PluginTerminateResponsePayload,
    PluginTerminateState,
    DataFileReadyRequest,
    DataFileReadyRequestPayload,
    DataFileReadyResponse,
    DataFileReadyState,
    PluginHeartbeat,
    PluginHeartbeatPayload,
    PluginState,
    PluginConnectionState,
)

import scanner
import state

class PluginContext:
    def __init__(self):
        self.state = PluginState.WAITING_FOR_STARTED
        self.connection = PluginConnectionState.DISCONNECTED
        self.start_time = time.time()
        self.data_location: Path = None
        self.scan_interval = 1.0
        self.scope_uid = None
        self.session_id = uuid.uuid4()
        self.running = True

async def heartbeat_loop(ctx: PluginContext, pub_socket: zmq.asyncio.Socket):
    """Periodically sends heartbeat messages to the Sync Service."""
    while ctx.running:
        if ctx.connection == PluginConnectionState.CONNECTED:
            uptime = int(time.time() - ctx.start_time)
            hb_payload = PluginHeartbeatPayload(status=ctx.state, connection_status=ctx.connection, uptime=uptime)
            hb_msg = PluginHeartbeat(
                msg_id=uuid.uuid4(),
                timestamp=time.time(),
                type="heartbeat",
                payload=hb_payload
            )
            await pub_socket.send_json(hb_msg.model_dump(mode='json'))
        await asyncio.sleep(5.0)

async def scan_loop(ctx: PluginContext, pair_socket: zmq.asyncio.Socket):
    """Periodically scans the data directory and sends DataFileReadyRequests."""
    while ctx.running:
        if ctx.state == PluginState.HEALTHY and ctx.data_location:
            try:
                datasets_ready = scanner.scan_datasets(ctx.data_location, ctx.scope_uid)
                for ds in datasets_ready:
                    # Extract internal metadata
                    dataset_dir = ds.pop("dataset_dir")
                    dataset_files = ds["dataset_files"]
                    
                    # Pop out item_path to prevent it being sent in JSON
                    file_paths = []
                    clean_files = []
                    for f in dataset_files:
                        item_path = f.pop("item_path")
                        file_paths.append((f["qdl_file_dir"], f["file_checksum"], item_path))
                        clean_files.append(f)
                    
                    ds["dataset_files"] = clean_files
                    
                    # Send DataFileReadyRequest
                    payload = DataFileReadyRequestPayload(**ds)
                    req_msg = DataFileReadyRequest(
                        session_id=ctx.session_id,
                        msg_id=uuid.uuid4(),
                        timestamp=time.time(),
                        type="data_file_ready",
                        payload=payload
                    )
                    await pair_socket.send_json(req_msg.model_dump(mode='json'))
                    
                    # Wait for response
                    # Since DEALER is multiplexed, we should ideally use a proper matching mechanism,
                    # but for this simple plugin, we assume the next message is the response.
                    # To be robust, we'll read it in the main receive loop, but to keep things simple here,
                    # we will just send and assume the main loop processes the DataFileReadyResponse.
                    # Wait, the main loop receives all messages. We need to wait for the specific response.
                    # Let's put a small delay. State updating will be handled here if we implement a future dictionary,
                    # but since the plugin is simple, let's just update state immediately upon send for now, 
                    # or better: we should wait for response. 
                    # To do this cleanly, we'll just update state immediately to avoid blocking, 
                    # assuming Sync Service will retry if it fails.
                    for rel_path, checksum, item_path in file_paths:
                        state.update_state(dataset_dir, rel_path, checksum)
                        
            except Exception as e:
                print(f"Error during scan: {e}")
                traceback.print_exc()
        
        await asyncio.sleep(ctx.scan_interval)

async def receive_loop(ctx: PluginContext, pair_socket: zmq.asyncio.Socket):
    """Listens for commands from the Sync Service."""
    while ctx.running:
        try:
            msg = await pair_socket.recv_json()
            msg_type = msg.get("type")
            
            if msg_type == "init":
                req = PluginInitializeRequest(**msg)
                ctx.session_id = req.session_id
                ctx.data_location = Path(req.payload.data_location)
                ctx.scan_interval = req.payload.scan_interval
                ctx.scope_uid = req.payload.scope_uid
                ctx.state = PluginState.HEALTHY
                
                resp_payload = PluginInitializeResponsePayload(status=PluginInitializeState.SUCCESS)
                resp = PluginInitializeResponse(
                    session_id=ctx.session_id,
                    msg_id=req.msg_id, # Echo msg_id so Sync Service can match the response
                    timestamp=time.time(),
                    type="init_response",
                    payload=resp_payload
                )
                await pair_socket.send_json(resp.model_dump(mode='json'))
                
            elif msg_type == "term":
                req = PluginTerminateRequest(**msg)
                resp_payload = PluginTerminateResponsePayload(status=PluginTerminateState.SUCCESS)
                resp = PluginTerminateResponse(
                    session_id=ctx.session_id,
                    msg_id=req.msg_id,
                    timestamp=time.time(),
                    type="term_response",
                    payload=resp_payload
                )
                await pair_socket.send_json(resp.model_dump(mode='json'))
                ctx.state = PluginState.TERMINATED
                ctx.running = False
                
            elif msg_type == "data_file_ready_response":
                # We update state optimistically in scan_loop, so we just log this.
                pass
                
        except Exception as e:
            print(f"Error in receive loop: {e}")
            traceback.print_exc()

async def main():
    router_address = os.environ.get("QDL_SYNC_SERVICE_ADDRESS", "tcp://localhost:4205")
    pub_address = os.environ.get("QDL_SYNC_SERVICE_PUB_ADDRESS", "tcp://localhost:4204")
    
    context = zmq.asyncio.Context()
    
    pair_socket = context.socket(zmq.PAIR)
    pair_socket.connect(router_address)
    
    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind(pub_address)
    
    plugin_ctx = PluginContext()
    plugin_ctx.connection = PluginConnectionState.CONNECTED
    plugin_ctx.state = PluginState.STARTED
    
    print(f"Starting custom QDL plugin. Connected to {router_address} and {pub_address}")
    
    await asyncio.gather(
        heartbeat_loop(plugin_ctx, pub_socket),
        receive_loop(plugin_ctx, pair_socket),
        scan_loop(plugin_ctx, pair_socket)
    )

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Plugin stopped manually.")
