from typing import Any
import time
from enum import Enum, auto

from rich.text import Text
from rich.table import Table

class SyncTimerState(Enum):
    AWAITING_INPUT = auto()
    AWAITING_SYNC = auto()
    ACTIVE = auto()

class StatusPanel:
    # region Class Constructor
    def __init__(self) -> None:
        self.credentials_status: str = "Pending"
        self.daemon_status: str = "Pending"
        self.sync_status: str = "Pending"
        self.datasets_synced: str = "100%"
        self.time_since_sync: float = 0.0
        self.sync_interval: float = 5.0
        self.spinner_chars: list[str] = ['|', '/', '-', '\\']
        self.spinner_idx: int = 0
        self.sync_timer_state: SyncTimerState = SyncTimerState.AWAITING_INPUT
        
        self.scope_name: str = "N/A"
        self.setup_name: str = "N/A"
        self.device_name: str = "N/A"
    # endregion

    # region Class Methods
    def update_config_info(self, scope: str, setup: str, device: str) -> None:
        """Update config names for display."""
        self.scope_name = scope
        self.setup_name = setup
        self.device_name = device
    
    def update_state(self, credentials: str = None, daemon: str = None, sync: str = None, datasets: str = None) -> None:
        """Update backend statuses."""
        if credentials:
            self.credentials_status = credentials
        if daemon:
            self.daemon_status = daemon
        if sync:
            self.sync_status = sync
        if datasets:
            self.datasets_synced = datasets

    def update_sync_time(self, time_since: float, interval: float = 5.0) -> None:
        """Update time since last sync."""
        self.time_since_sync = time_since
        self.sync_interval = interval

    def tick_spinner(self) -> None:
        """Advance the spinner animation frame."""
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)

    def render(self) -> Text:
        """Render the status block as Rich Text."""
        self.tick_spinner()
        
        def format_status(status: str) -> str:
            if status == "Pass":
                return "[bold green]Pass[/bold green]"
            elif status == "Failed":
                return "[bold red]Failed[/bold red]"
            elif status == "Pending":
                return "[bold yellow]Pending[/bold yellow]"
            return status

        text = Text.from_markup("Client status:\n")
        text.append_text(Text.from_markup(f"| - Credentials \\[{format_status(self.credentials_status)}]\n"))
        text.append_text(Text.from_markup(f"| - QDL Daemon \\[{format_status(self.daemon_status)}]\n"))
        text.append_text(Text.from_markup(f"| - QDL Sync Service \\[{format_status(self.sync_status)}]\n"))
        text.append_text(Text.from_markup(f"| - Datasets synced {self.datasets_synced}\n"))
        
        spinner = self.spinner_chars[self.spinner_idx]
        if self.sync_timer_state == SyncTimerState.AWAITING_INPUT:
            text.append_text(Text.from_markup(f"\\[{spinner}] Awaiting user input...\n"))
        elif self.sync_timer_state == SyncTimerState.AWAITING_SYNC:
            text.append_text(Text.from_markup(f"\\[{spinner}] Awaiting sync action...\n"))
        elif self.sync_timer_state == SyncTimerState.ACTIVE:
            text.append_text(Text.from_markup(f"\\[{spinner}] Time since last sync {int(self.time_since_sync)}/{int(self.sync_interval)} \\[s]\n"))

        if self.sync_timer_state != SyncTimerState.AWAITING_INPUT:
            text.append_text(Text.from_markup(f"\\[scope] {self.scope_name} \\[setup] {self.setup_name} \\[device] {self.device_name}"))

        return text
    # endregion
