import asyncio
import time
import uuid
from asyncio import Task
from typing import Any, Self

from qdlcomms.core.logging import EventKey, get_logger
from qdlcomms.messages.plugins import (
    PluginConnectionState,
    PluginHeartbeat,
    PluginHeartbeatPayload,
    PluginState,
)

from qmi_plugin.communication.pubsub_channel import PluginHeartbeatChannel
from qmi_plugin.core.config import Settings

logger = get_logger()


class StateManager:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._state = PluginState.STARTED
        self._task: Task[None] | None = None
        self.heartbeat_pub_channel = PluginHeartbeatChannel(str(settings.qdl_sync_service_pub_address))
        self._start_time = time.time()
        self._stop = True

    async def __aenter__(self) -> Self:
        await self.heartbeat_pub_channel.start()
        self._stop = False
        self._task = asyncio.create_task(self._work())
        return self

    async def __aexit__(self, *_: Any) -> None:
        self._stop = True
        assert self._task is not None
        self._task.cancel()
        self._task = None
        await self.heartbeat_pub_channel.stop()

    def state(self) -> PluginState:
        """Return the current state of the plugin."""
        return self._state

    def set_state(self, state: PluginState) -> None:
        """Set/change the current state of the plugin."""
        self._state = state

    async def _work(self) -> None:
        while not self._stop:
            try:
                state = self.state()
                timestamp = time.time()
                uptime = timestamp - self._start_time
                payload = PluginHeartbeatPayload(
                    status=state, connection_status=PluginConnectionState.CONNECTED, uptime=int(uptime)
                )
                message = PluginHeartbeat(msg_id=uuid.uuid4(), timestamp=timestamp, type="heartbeat", payload=payload)

                await self.heartbeat_pub_channel.write(message)
                logger.info("QMI-plugin: Published status", event_key=EventKey.PLUGIN_HEARTBEAT_UPDATE, state=state)
                await asyncio.sleep(self._settings.heartbeat_interval)

            except Exception:
                logger.exception("QMI-plugin: Error in publishing heartbeat")
                raise
