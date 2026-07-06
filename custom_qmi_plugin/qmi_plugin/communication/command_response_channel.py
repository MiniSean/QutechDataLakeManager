import time
import uuid
from typing import Callable, Coroutine
from uuid import UUID

from qdlcomms.channels.simple_channel import PairClientChannel
from qdlcomms.core.logging import get_logger
from qdlcomms.messages.plugins import (
    DataFileReadyRequest,
    DataFileReadyResponse,
    PluginInitializeRequest,
    PluginInitializeRequestPayload,
    PluginInitializeResponse,
    PluginInitializeResponsePayload,
    PluginTerminateRequest,
    PluginTerminateRequestPayload,
    PluginTerminateResponse,
    PluginTerminateResponsePayload,
)

logger = get_logger()

InitializeCallbackT = Callable[
    [UUID, PluginInitializeRequestPayload], Coroutine[None, None, PluginInitializeResponsePayload]
]

TerminateCallbackT = Callable[
    [UUID, PluginTerminateRequestPayload], Coroutine[None, None, PluginTerminateResponsePayload]
]


class CommandResponseChannel(
    PairClientChannel[  # type: ignore
        PluginInitializeRequest | PluginTerminateRequest | DataFileReadyResponse,
        PluginInitializeResponse | PluginTerminateResponse | DataFileReadyRequest,
    ]
):
    _initialize_request_handler: InitializeCallbackT
    _terminate_request_handler: TerminateCallbackT

    async def _initialize(self, request: PluginInitializeRequest) -> PluginInitializeResponse:
        """Callback method for handling PluginInitializeRequest.

        The registered init handler callback is called.

        Returns:
            PluginInitializeResponse as acknowledgement
        """
        logger.info("QMI-plugin: Received initialize request", session_id=request.session_id)
        payload = await self._initialize_request_handler(request.session_id, request.payload)
        response = PluginInitializeResponse(
            session_id=request.session_id, msg_id=uuid.uuid4(), timestamp=time.time(), type="init_ack", payload=payload
        )
        logger.info("QMI-plugin: Initialize request completed", response=response)
        return response

    async def _terminate(self, request: PluginTerminateRequest) -> PluginTerminateResponse:
        """Callback method for handling PluginTerminateRequest.

        The registered term handler callback is called.

        Returns:
            PluginTerminateResponse as acknowledgement
        """
        logger.info("QMI-plugin: Received terminate request", session_id=request.session_id)
        payload = await self._terminate_request_handler(request.session_id, request.payload)
        response = PluginTerminateResponse(
            session_id=request.session_id, msg_id=uuid.uuid4(), timestamp=time.time(), type="term_ack", payload=payload
        )
        logger.info("QMI-plugin: Terminate request completed", response=response)
        return response

    def __init__(
        self,
        address: str,
        zmq_timeout: float,
        init_handler: InitializeCallbackT,
        term_handler: TerminateCallbackT,
    ) -> None:
        super().__init__(address, zmq_timeout)
        self.register_request_handler(PluginInitializeRequest, self._initialize)
        self._initialize_request_handler = init_handler
        self.register_request_handler(PluginTerminateRequest, self._terminate)
        self._terminate_request_handler = term_handler
