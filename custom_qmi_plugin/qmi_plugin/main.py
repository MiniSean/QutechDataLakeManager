"""Sync-service entrypoint.

This module is the entrypoint of the sync_service package.
"""

import asyncio
import sys

from qdlcomms.core.logging import configure_logger, filter_message_models, get_logger

from qmi_plugin.core.config import get_settings
from qmi_plugin.worker import Worker

logger = get_logger()


def run() -> None:
    """Entry point for the plugin.

    Starts an asyncio coroutine on the worker, which does all the work.
    """
    settings = get_settings()
    configure_logger(extra_processors=[filter_message_models], logging_level=settings.logging_level)
    logger.info("QMI-plugin started")
    worker = Worker(settings)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # pragma: no cover
    asyncio.run(worker.main())


if __name__ == "__main__":
    # Start the ZMQ application QMI plugin.
    run()
