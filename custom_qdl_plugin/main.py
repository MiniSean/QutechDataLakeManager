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
from collections import defaultdict


MAX_DATASETS_PER_BATCH = 30

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
        self.pending_acks = set()

import logging

logging.basicConfig(
    filename='plugin_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

async def heartbeat_loop(ctx: PluginContext, pub_socket: zmq.asyncio.Socket):
    """Periodically sends heartbeat messages to the Sync Service."""
    logger.debug("Heartbeat loop started")
    while ctx.running:
        logger.debug(f"Heartbeat tick. State: {ctx.state}, Connection: {ctx.connection}")
        if ctx.connection == PluginConnectionState.CONNECTED:
            uptime = int(time.time() - ctx.start_time)
            hb_payload = PluginHeartbeatPayload(status=ctx.state, connection_status=ctx.connection, uptime=uptime)
            hb_msg = PluginHeartbeat(
                msg_id=uuid.uuid4(),
                timestamp=time.time(),
                type="heartbeat",
                payload=hb_payload
            )
            logger.debug("Sending heartbeat...")
            await pub_socket.send_json(hb_msg.model_dump(mode='json'))
            logger.debug("Heartbeat sent.")
        await asyncio.sleep(5.0)
    logger.debug("Heartbeat loop exiting")

async def scan_loop(ctx: PluginContext, pair_socket: zmq.asyncio.Socket):
    """Periodically scans the data directory and sends DataFileReadyRequests."""
    logger.debug("Scan loop started")
    while ctx.running:
        if ctx.state == PluginState.HEALTHY and ctx.data_location:
            try:
                logger.debug(f"Starting to scan datasets at {ctx.data_location}")
                valid_folders = await asyncio.to_thread(scanner.find_valid_dataset_folders, ctx.data_location)
                logger.debug(f"Found {len(valid_folders)} valid dataset folders to process.")
                
                # Group folders by date
                date_groups = defaultdict(list)
                for folder in valid_folders:
                    date_groups[folder.parent.name].append(folder)
                
                processed_count = 0
                total_folders = len(valid_folders)
                
                for date, folders_in_date in date_groups.items():
                    if not ctx.running:
                        break
                    
                    # Chunk by max_datasets_per_batch
                    for i in range(0, len(folders_in_date), MAX_DATASETS_PER_BATCH):
                        if not ctx.running:
                            break
                        batch = folders_in_date[i:i+MAX_DATASETS_PER_BATCH]
                        ctx.pending_acks.clear()
                        
                        for dataset_dir in batch:
                            processed_count += 1
                            logger.debug(f"Processing dataset {processed_count}/{total_folders} for date: {date}, dataset: {dataset_dir.name}")
                            ds = await asyncio.to_thread(scanner.process_single_dataset, dataset_dir, ctx.scope_uid)
                            
                            if ds:
                                # Extract internal metadata
                                dataset_dir_from_ds = ds.pop("dataset_dir")
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
                                logger.debug(f"Sending DataFileReadyRequest for {dataset_dir_from_ds}")
                                await pair_socket.send_json(req_msg.model_dump(mode='json'))
                                ctx.pending_acks.add(str(req_msg.msg_id))
                                
                                for rel_path, checksum, item_path in file_paths:
                                    state.update_state(dataset_dir_from_ds, rel_path, checksum)
                        
                        # Wait for backpressure
                        while len(ctx.pending_acks) > 0 and ctx.running:
                            await asyncio.sleep(0.1)
                            
                logger.debug("Scan pass completed.")
                        
            except Exception as e:
                logger.error(f"Error during scan: {e}", exc_info=True)
                print(f"Error during scan: {e}")
                traceback.print_exc()
        
        await asyncio.sleep(ctx.scan_interval)
    logger.debug("Scan loop exiting")

async def receive_loop(ctx: PluginContext, pair_socket: zmq.asyncio.Socket):
    """Listens for commands from the Sync Service."""
    logger.debug("Receive loop started")
    while ctx.running:
        try:
            msg = await pair_socket.recv_json()
            msg_type = msg.get("type")
            logger.debug(f"Received message of type: {msg_type}")
            
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
                logger.debug("Sending init_response")
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
                logger.debug("Sending term_response and stopping plugin...")
                await pair_socket.send_json(resp.model_dump(mode='json'))
                ctx.state = PluginState.TERMINATED
                ctx.running = False
                
            elif msg_type == "data_file_ready_response":
                # We update state optimistically in scan_loop, so we just log this.
                logger.debug("Received data_file_ready_response")
                pass
                
            elif msg_type == "data_ready_ack":
                msg_id = str(msg.get("msg_id"))
                if msg_id in ctx.pending_acks:
                    ctx.pending_acks.remove(msg_id)
                logger.debug(f"Received data_ready_ack for {msg_id}")
                
        except Exception as e:
            logger.error(f"Error in receive loop: {e}", exc_info=True)
            print(f"Error in receive loop: {e}")
            traceback.print_exc()
    logger.debug("Receive loop exiting")

async def main():
    router_address = os.environ.get("QDL_SYNC_SERVICE_ADDRESS", "tcp://localhost:4205")
    pub_address = os.environ.get("QDL_SYNC_SERVICE_PUB_ADDRESS", "tcp://localhost:4204")
    
    logger.info(f"Starting custom QDL plugin. Router: {router_address}, Pub: {pub_address}")
    
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
    logger.info("Main gather finished.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Plugin stopped manually.")
        print("Plugin stopped manually.")
