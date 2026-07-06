import asyncio
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import UUID

from qdlcomms.core.logging import EventKey, get_logger
from qdlcomms.exceptions import (
    CommunicationTimeoutException,
    RequestFailedException,
)
from qdlcomms.messages.plugins import (
    DataFileReadyRequest,
    DataFileReadyRequestPayload,
    DataFileReadyResponse,
    DataFileReadyState,
    PluginInitializeRequestPayload,
    PluginInitializeResponsePayload,
    PluginInitializeState,
    PluginState,
    PluginTerminateRequestPayload,
    PluginTerminateResponsePayload,
    PluginTerminateState,
)
from qdllib.type_aliases import DictStrAny

from qmi_plugin.communication.command_response_channel import CommandResponseChannel
from qmi_plugin.core.config import Settings
from qmi_plugin.scan_dataset import (
    mirror_uploaded_files,
    scan_dataset,
    valid_qmi_date_directory,
)
from qmi_plugin.state_manager import StateManager

logger = get_logger()
SOCKET_RECV_TIMEOUT = 5  # [s]


class Worker:
    """Worker that handles all communication between the plugin and sync-service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stopped = False
        self._session_id = uuid.uuid4()
        self._qmi_datastore = Path("")
        self._qmi_data_format = ""
        self._qmi_ready_date = ""
        self._scan_interval = 1.0
        self._scope_uid = ""
        self._busy_work = False
        self._zmq_timeout = -1  # blocking
        self._state_manager = StateManager(self._settings)
        self._command_response_channel = CommandResponseChannel(
            str(settings.qdl_sync_service_address),
            self._zmq_timeout,
            self._callback_initialize,
            self._callback_terminate,
        )
        
        # --- custom tracking ---
        import zmq.asyncio
        self._tracking_ctx = zmq.asyncio.Context.instance()
        self._tracking_pub = self._tracking_ctx.socket(zmq.PUB)
        self._tracking_pub.connect("tcp://127.0.0.1:4206")
        # -----------------------

    async def _callback_initialize(
        self, _session_id: UUID, payload: PluginInitializeRequestPayload
    ) -> PluginInitializeResponsePayload:
        """Callback method for handling PluginInitializeRequest message."""
        self._state_manager.set_state(PluginState.INITIALIZING)
        self._qmi_datastore = Path(payload.data_location)
        self._qmi_data_format = payload.data_format
        self._scan_interval = payload.scan_interval
        self._scope_uid = payload.scope_uid
        self._qmi_ready_date = payload.extra_fields["qmi_ready_date"]

        if not self._scope_uid:
            log_message = "QMI-plugin: Scope is required in plugin configuration"
            logger.error(log_message, event_key=EventKey.PLUGIN_INITIALIZE_REQUEST)
            raise ValueError(log_message)
        if not self._qmi_datastore.is_dir():
            log_message = f"QMI-plugin: root directory {self._qmi_datastore} not a directory"
            logger.error(log_message, event_key=EventKey.PLUGIN_INITIALIZE_REQUEST)
            raise ValueError(log_message)
        if self._qmi_ready_date and not valid_qmi_date_directory(self._qmi_ready_date):
            log_message = f"QMI-plugin: invalid qmi_ready_date {self._qmi_ready_date}. Must be in form of YYYYMMDD"
            logger.error(log_message, event_key=EventKey.PLUGIN_INITIALIZE_REQUEST)
            raise ValueError(log_message)

        logger.info(f"QMI-plugin: Initialized for polling '{self._qmi_datastore}' every {self._scan_interval} seconds")
        self._state_manager.set_state(PluginState.HEALTHY)
        return PluginInitializeResponsePayload(status=PluginInitializeState.SUCCESS)

    async def _callback_terminate(
        self, _session_id: UUID, payload: PluginTerminateRequestPayload  # pylint: disable = W0613 (unused-argument)
    ) -> PluginTerminateResponsePayload:
        """Callback method for handling PluginTerminateRequest message."""
        logger.info(f"QMI-plugin: Terminating for polling {Path(self._qmi_datastore)}")
        self._state_manager.set_state(PluginState.TERMINATING)

        # Here the plugin must take actions to terminate data acquisition. For QMI none needed.

        self._state_manager.set_state(PluginState.TERMINATED)
        return PluginTerminateResponsePayload(status=PluginTerminateState.SUCCESS)

    async def dataset_file_ready(
        self, dataset_path: Path, files_to_add: List[DictStrAny], metadata: DictStrAny, extra_fields: DictStrAny
    ) -> None:
        """One or more new/changed data files for a single dataset are found and ready to be uploaded to QDL."""
        dataset_name = dataset_path.name
        logger.info("QMI-plugin: Send data file ready to sync-service", event_key=EventKey.DATAFILE_READY_REQUEST)
        
        # --- custom tracking ---
        try:
            self._tracking_pub.send_json({"type": "tuid_event", "action": "submitted", "tuid": dataset_name})
        except Exception as e:
            logger.error(f"Failed to publish tracking event: {e}")
        # -----------------------
        
        try:
            payload = DataFileReadyRequestPayload(
                scope_uid=self._scope_uid,
                dataset_name=dataset_name,
                dataset_files=files_to_add,
                metadata=metadata,
                extra_fields=extra_fields,
            )
            message = DataFileReadyRequest(
                session_id=self._session_id,
                msg_id=uuid.uuid4(),
                timestamp=time.time(),
                type="data_ready",
                payload=payload,
            )
            response = await self._command_response_channel.request(
                data=message, response_type=DataFileReadyResponse, timeout=self._zmq_timeout
            )
            logger.info(
                f"QMI-plugin: Received datafile ready response {response.payload.status}",
                event_key=EventKey.DATAFILE_READY_REQUEST,
            )
            if response.payload.status == DataFileReadyState.SUCCESS:
                await mirror_uploaded_files(dataset_path=dataset_path, uploaded_files=files_to_add)

        except (CommunicationTimeoutException, RequestFailedException) as exc:
            # Set state to FAILED
            logger.error(f"QMI-plugin: Datafile ready request failed: {exc}", event_key=EventKey.DATAFILE_READY_REQUEST)
            self._state_manager.set_state(PluginState.FAILED)

    def stop(self) -> None:
        """Flag to stop the worker."""
        self._stopped = True

    def get_extra_fields(self, dataset_path: Path) -> DictStrAny:
        """See if dataset.collected can be extracted from dataset name."""
        dateset_name = dataset_path.name

        if (date_time := re.search(r"\d{8}-\d{6}-\d{3}", dateset_name)) is not None:
            try:
                # see if the digits are of the form: date-time-milliseconds
                datetime_from_name = datetime.strptime(date_time.group(0), "%Y%m%d-%H%M%S-%f")
                return {"collected": datetime_from_name.strftime("%Y-%m-%d %H:%M:%S.%f")}
            except ValueError:
                pass
        return {}

    async def scan_data_store(self) -> None:
        """Scan qmi datastore and per dataset call sync service when changes are discovered."""
        assert self._state_manager.state() == PluginState.HEALTHY

        for date_path in sorted(self._qmi_datastore.iterdir()):
            if valid_qmi_date_directory(date_path.name) and date_path.is_dir():
                for dataset_path in sorted(date_path.iterdir()):
                    if dataset_path.is_dir():
                        files_to_add, attributes_to_add = await scan_dataset(dataset_path)
                        extra_fields = self.get_extra_fields(dataset_path)
                        if files_to_add:
                            await self.dataset_file_ready(
                                dataset_path=dataset_path,
                                files_to_add=files_to_add,
                                metadata=attributes_to_add,
                                extra_fields=extra_fields,
                            )

    async def work(self) -> None:
        """Coroutine that handles the normal work of the healthy plugin."""
        if self._state_manager.state() != PluginState.HEALTHY or self._busy_work:
            return

        logger.debug("QMI-plugin: work")
        try:
            self._busy_work = True
            await self.scan_data_store()
        except Exception as exc:  # pylint: disable = W0718 (broad-exception-caught)
            log_message = f"QMI-plugin: error while scanning datasets: {exc}"
            logger.error(log_message, event_key=EventKey.PLUGIN_SCAN_DATASETS)
            self._state_manager.set_state(PluginState.FAILED)
        finally:
            self._busy_work = False

    async def main(self) -> None:
        """Gather all relevant coroutines and start execution."""
        logger.info("QMI-plugin: startup data ingest")
        async with self._state_manager:
            async with self._command_response_channel:
                while not self._stopped:
                    # do plugin work
                    await self.work()
                    # check for and handle incoming messages from sync service
                    try:
                        await self._command_response_channel.serve()
                    except (CommunicationTimeoutException, RequestFailedException):
                        # Timeout while sending a response
                        logger.error("QMI-plugin: handle requests from sync_service failed")
                        self._state_manager.set_state(PluginState.FAILED)
                    # wait the polling interval
                    await asyncio.sleep(self._scan_interval)
