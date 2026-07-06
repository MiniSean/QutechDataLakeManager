from qdlcomms.channels.publish_channel import PublishChannel
from qdlcomms.messages.plugins import PluginHeartbeat


class PluginHeartbeatChannel(PublishChannel[PluginHeartbeat]):  # type: ignore[misc]
    """The channel for publishing the heartbeat for the plugin.

    The constructor takes the address.
    """
