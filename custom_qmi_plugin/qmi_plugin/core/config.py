"""qmi_plugin core configuration.

This module contains the configuration for the core functionality of the qmi_plugin package.
"""

import logging

from dotenv import load_dotenv
from pydantic import AnyUrl, NonNegativeFloat, PositiveInt
from qdllib.config import BaseSettings

load_dotenv()


class PluginSettings(BaseSettings):  # type: ignore
    heartbeat_interval: PositiveInt = 10
    scan_interval: NonNegativeFloat = 5.0


class Settings(PluginSettings):
    logging_level: int = logging.INFO
    qdl_sync_service_address: AnyUrl | None = None
    qdl_sync_service_pub_address: AnyUrl | None = None


def get_settings() -> Settings:
    """Get plugin settings.

    Be sure to set the qdl_sync_service_address and qdl_sync_service_pub_address in the .env file (not empty or
    default value None).

    Returns:
        The settings.
    """
    _settings = Settings()
    if not _settings.qdl_sync_service_address:
        raise ValueError("QMI-plugin: qdl_sync_service_address not set.")
    if not _settings.qdl_sync_service_pub_address:
        raise ValueError("QMI-plugin: qdl_sync_service_pub_address not set.")
    return _settings
