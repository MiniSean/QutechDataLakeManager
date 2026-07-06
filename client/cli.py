import os
import sys
import json
import shutil
import subprocess
import time
import atexit
import threading
import logging
from pathlib import Path
from typing import Any, Optional, Mapping, MutableMapping, List, Dict, Callable

# Uncomment the line below to enable debug logging to file for troubleshooting
# logging.basicConfig(filename="client_debug.log", level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

import click
import qdl

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, Button, RichLog, Label, ContentSwitcher, Checkbox
from textual.containers import Container, Horizontal, Vertical, Grid
from textual import work

from client.contribution_heatmap.ui import HeatmapGrid
from client.contribution_heatmap.data_fetcher import get_datasets_per_day, get_tuids_containing, parse_tuids_to_heatmap_data
import datetime
from pathlib import Path
from client.contribution_heatmap.strategy_tuid_extraction import QdlDatasetNameDateExtraction
from client.status_panel.ui import StatusPanel, SyncTimerState
from client.config import ClientConfig
from rich.console import Group
from rich.align import Align


def get_plugin_info() -> tuple[str, str]:
    if hasattr(sys, "_MEIPASS"):
        v_path = Path(sys._MEIPASS) / "version.json"
    else:
        v_path = Path(__file__).parent.parent / "version.json"
    if v_path.exists():
        with open(v_path, "r") as f:
            data = json.load(f)
            return data.get("plugin_name"), data.get("qdl_plugin_version")
    raise Exception("Plugin information not defined")

PLUGIN_NAME, PLUGIN_VERSION = get_plugin_info()
PLUGIN_TARBALL_NAME: str = f"qdl-{PLUGIN_NAME}-plugin-windows-{PLUGIN_VERSION}.tar.gz"

def get_plugin_settings() -> Dict[str, Any]:
    if hasattr(sys, "_MEIPASS"):
        settings_path = Path(sys._MEIPASS) / "plugin_settings.json"
    else:
        settings_path = Path(__file__).parent.parent / "plugin_settings.json"
    if settings_path.exists():
        with open(settings_path, "r") as f:
            return json.load(f)

    raise Exception("Plugin settings not defined")

daemon_proc: Optional[subprocess.Popen[Any]] = None
sync_proc: Optional[subprocess.Popen[Any]] = None

def cleanup(log_func: Optional[Callable[[str], None]] = None) -> None:
    """Kills the background processes when the CLI exits."""
    global daemon_proc, sync_proc
    
    def log(msg: str) -> None:
        logging.debug(msg)
        if log_func:
            log_func(msg)

    log("[CLIENT] cleanup() called")
    
    if sync_proc and sync_proc.poll() is None:
        log("[CLIENT] Terminating sync_proc...")
        if sys.platform == "win32":
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(sync_proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            sync_proc.terminate()
        try:
            sync_proc.wait(timeout=3)
            log("[CLIENT] sync_proc terminated gracefully")
        except subprocess.TimeoutExpired:
            log("[CLIENT] sync_proc terminate timed out, killing...")
            if sys.platform != "win32":
                sync_proc.kill()
            sync_proc.wait()
            log("[CLIENT] sync_proc killed")
            
        if sync_proc.stdout:
            try:
                log("[CLIENT] Closing sync_proc.stdout...")
                sync_proc.stdout.close()
                log("[CLIENT] sync_proc.stdout closed")
            except Exception as e:
                log(f"[CLIENT] Error closing sync_proc.stdout: {e}")
            
    if daemon_proc and daemon_proc.poll() is None:
        log("[CLIENT] Terminating daemon_proc...")
        if sys.platform == "win32":
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(daemon_proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            daemon_proc.terminate()
        try:
            daemon_proc.wait(timeout=2)
            log("[CLIENT] daemon_proc terminated gracefully")
        except subprocess.TimeoutExpired:
            log("[CLIENT] daemon_proc terminate timed out, killing...")
            if sys.platform != "win32":
                daemon_proc.kill()
            daemon_proc.wait()
            log("[CLIENT] daemon_proc killed")
            
        if daemon_proc.stdout:
            try:
                log("[CLIENT] Closing daemon_proc.stdout...")
                daemon_proc.stdout.close()
                log("[CLIENT] daemon_proc.stdout closed")
            except Exception as e:
                log(f"[CLIENT] Error closing daemon_proc.stdout: {e}")
    log("[CLIENT] cleanup() finished")

atexit.register(cleanup)
def get_executable(name: str, config: ClientConfig) -> str:
    """Finds the executable in PATH or from config."""
    if shutil.which(name):
        return name
        
    bin_dir: Optional[str] = config.qdl_bin_dir
    if bin_dir:
        exe_path: str = os.path.join(bin_dir, f"{name}.exe" if sys.platform == "win32" else name)
        if os.path.exists(exe_path):
            return exe_path
            
    return name # Fallback if not found

def extract_plugin() -> None:
    """Extracts the bundled PyInstaller tarball into the QDL plugins directory."""
    plugins_dir: Path = Path.home() / ".qdl" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    
    bundled_path: Path
    if hasattr(sys, "_MEIPASS"):
        bundled_path = Path(sys._MEIPASS) / PLUGIN_TARBALL_NAME
    else:
        bundled_path = Path(__file__).parent.parent / "custom_qdl_plugin" / PLUGIN_TARBALL_NAME

    if bundled_path.exists():
        target_path: Path = plugins_dir / PLUGIN_TARBALL_NAME
        shutil.copy2(bundled_path, target_path)

class HeatmapWidget(Static):
    def update_heatmap(self, grid_table: Any, legend_text: Any) -> None:
        group = Group(
            grid_table,
            Align.left(legend_text)
        )
        self.update(group)

class StatusWidget(Static):
    def on_mount(self) -> None:
        self.status_panel = StatusPanel()
        
    def update_render(self) -> None:
        self.update(self.status_panel.render())

class SetupForm(Container):
    def __init__(self, config: ClientConfig, avoid_duplicates: bool, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.avoid_duplicates = avoid_duplicates

    def compose(self) -> ComposeResult:
        default_dir = self.config.data_dir
        yield Label("Data Directory:")
        with Horizontal(id="dir_row"):
            yield Input(value=default_dir, id="input_data_dir")
            yield Button("Browse", id="btn_browse")
        with Horizontal(id="fridge_device_row"):
            with Vertical(classes="flex_col"):
                yield Label("Scope ID:")
                yield Input(value=self.config.scope, id="input_scope")
            with Vertical(classes="flex_col"):
                yield Label("Setup ID:")
                yield Input(value=self.config.setup, id="input_setup")
            with Vertical(classes="flex_col"):
                yield Label("Device ID:")
                yield Input(value=self.config.device, id="input_device")
            with Vertical(classes="flex_col"):
                yield Label("Lazy Sync:")
                yield Checkbox(value=self.avoid_duplicates, id="chk_avoid_duplicates")
        yield Button("Continue", id="btn_start", variant="primary")

class QdlClientApp(App[None]):
    CSS = """
    Screen {
        overflow: hidden hidden;
    }
    #top_panel {
        height: auto;
        layout: vertical;
        border: solid blue;
    }
    #heatmap_container {
        height: auto;
        margin-bottom: 1;
    }
    #status_container {
        height: auto;
    }
    #bottom_panel {
        height: 1fr;
        border: solid green;
        overflow: hidden hidden;
    }
    RichLog {
        overflow-x: hidden;
    }
    SetupForm {
        padding: 0 1;
    }
    SetupForm Label {
        margin-top: 0;
    }
    SetupForm Input, SetupForm Button, SetupForm Checkbox {
        height: 1;
        min-height: 1;
        border: none;
    }
    SetupForm Input {
        background: $boost;
    }
    SetupForm Button {
        padding: 0 2;
    }
    #dir_row {
        height: auto;
        margin-bottom: 1;
    }
    #dir_row Input {
        width: 1fr;
    }
    #dir_row Button {
        margin-left: 1;
    }
    #fridge_device_row {
        height: auto;
        margin-bottom: 1;
    }
    .flex_col {
        width: 1fr;
        height: auto;
    }
    .flex_col Input {
        width: 1fr;
    }
    #btn_start {
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
        ("d", "toggle_daemon", "Toggle Daemon Logs"),
        ("s", "toggle_sync", "Toggle Sync Logs"),
        ("p", "toggle_plugin", "Toggle Plugin"),
        ("end", "scroll_end", "Snap to Bottom"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.qdl_config: ClientConfig = ClientConfig.load()
        self.strategy = QdlDatasetNameDateExtraction()
        
        settings = get_plugin_settings()
        self.sync_interval = float(settings.get("sync_interval"))
        self.scan_interval = float(settings.get("scan_interval"))
        self.manage_services = bool(settings.get("manage_services"))
        self.show_daemon_logs = bool(settings.get("show_daemon_logs"))
        self.show_sync_logs = bool(settings.get("show_sync_logs"))
        self.heatmap_weeks = int(settings.get("heatmap_weeks"))
        self.plugin_enabled = True
        self.shutting_down = False
        self.tuid_states: Dict[str, Dict[str, Any]] = {}
        
    @work(thread=True)
    def action_quit(self) -> None:
        if getattr(self, "shutting_down", False):
            return
        self.shutting_down = True

        def ui_log(msg: str) -> None:
            try:
                self.call_from_thread(self.write_log, msg)
            except Exception:
                pass
                
        ui_log("[CLIENT] action_quit() triggered")
        
        if getattr(self, "plugin_enabled", False):
            ui_log("[CLIENT] Stopping plugin and waiting for daemon to idle...")
            self.plugin_enabled = False
            qdl_exe = get_executable("qdl", self.qdl_config)
            try:
                subprocess.run([qdl_exe, "sync", "plugin", "stop"], check=False)
            except Exception as e:
                ui_log(f"[CLIENT] Error stopping plugin: {e}")
                
        # Start await idle loop
        import urllib.request
        import urllib.error
        
        start_time = time.time()
        timeout = 60.0
        timeout_sleep = 5.0
        daemon_url = "http://127.0.0.1:5500/transfers/data"
        
        while time.time() - start_time < timeout:
            time_remaining_before_timeout = round(timeout - (time.time() - start_time), 0)
            try:
                req = urllib.request.Request(daemon_url)
                with urllib.request.urlopen(req, timeout=1.0) as response:
                    data = json.loads(response.read().decode())
                    metrics = data.get("queue_metrics", [])
                    busy_count = 0
                    for m in metrics:
                        desc = m.get("description", "")
                        if desc in [
                            "Number of queued uploads", 
                            "Number of uploads in progress", 
                            "Number of queued downloads", 
                            "Number of downloads in progress"
                        ]:
                            busy_count += m.get("count", 0)
                    
                    if busy_count == 0:
                        ui_log("[CLIENT] Daemon is idle. Proceeding to exit.")
                        break
                    else:
                        ui_log(f"[CLIENT] Daemon busy ({busy_count} tasks). Waiting {time_remaining_before_timeout} s...")
            except Exception as e:
                ui_log(f"[CLIENT] Daemon not reachable or error ({e}). Proceeding.")
                break
            time.sleep(timeout_sleep)
        else:
            ui_log(f"[CLIENT] Awaiting Daemon idle - force timeout in {timeout} s.")
            
        cleanup(log_func=ui_log)
        self.call_from_thread(self.exit)
        
    def action_scroll_end(self) -> None:
        if self.query(ContentSwitcher) and self.query_one(ContentSwitcher).current == "rich_log":
            self.query_one(RichLog).scroll_end(animate=False)
            
    def action_toggle_daemon(self) -> None:
        self.show_daemon_logs = not self.show_daemon_logs
        self.write_log(f"[bold blue]{'Showing' if self.show_daemon_logs else 'Hiding'} Daemon Logs[/bold blue]")

    def action_toggle_sync(self) -> None:
        self.show_sync_logs = not self.show_sync_logs
        self.write_log(f"[bold blue]{'Showing' if self.show_sync_logs else 'Hiding'} Sync Logs[/bold blue]")
        
    @work(thread=True)
    def action_toggle_plugin(self) -> None:
        if getattr(self, "shutting_down", False):
            return
            
        qdl_exe = get_executable("qdl", self.qdl_config)
        try:
            if getattr(self, "plugin_enabled", False):
                self.call_from_thread(self.write_log, "[bold blue]Stopping Plugin...[/bold blue]")
                subprocess.run([qdl_exe, "sync", "plugin", "stop"], check=False)
                self.plugin_enabled = False
            else:
                self.call_from_thread(self.write_log, "[bold blue]Starting Plugin...[/bold blue]")
                subprocess.run([qdl_exe, "sync", "plugin", "start"], check=False)
                self.plugin_enabled = True
        except Exception as e:
            self.call_from_thread(self.write_log, f"[bold red]Failed to toggle plugin: {e}[/bold red]")
        
    def compose(self) -> ComposeResult:
        with Container(id="top_panel"):
            yield HeatmapWidget(id="heatmap_container")
            yield StatusWidget(id="status_container")
        
        with ContentSwitcher(initial="setup_form", id="bottom_panel"):
            yield SetupForm(self.qdl_config, self.qdl_config.avoid_duplicates, id="setup_form")
            yield RichLog(id="rich_log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.status_widget = self.query_one(StatusWidget)
        self.heatmap_widget = self.query_one(HeatmapWidget)
        self.log_widget = self.query_one(RichLog)
        
        scope_init = self.qdl_config.scope
        self.status_widget.status_panel.update_config_info(scope_init, self.qdl_config.setup, self.qdl_config.device)
        self.status_widget.status_panel.status_scan_interval = self.scan_interval
        
        # Render empty heatmap immediately so it isn't delayed
        heatmap_grid = HeatmapGrid(num_weeks=self.heatmap_weeks, single_color_mode=True)
        grid_table = heatmap_grid.render(available_counts={}, detected_counts={})
        legend_text = heatmap_grid.render_legend()
        self.heatmap_widget.update_heatmap(grid_table, legend_text)
        
        self.set_interval(0.1, self.tick_status)
        self.set_interval(self.scan_interval, self.fetch_heatmap)
        self.set_interval(self.scan_interval, self.check_pending_tuids)
        self.fetch_heatmap()
        self.tuid_tracker_thread()
        
    def tick_status(self) -> None:
        global daemon_proc, sync_proc
        if daemon_proc:
            self.status_widget.status_panel.update_state(daemon="Pass" if daemon_proc.poll() is None else "Failed")
        if sync_proc:
            self.status_widget.status_panel.update_state(sync="Pass" if sync_proc.poll() is None else "Failed")
            
        self.status_widget.status_panel.time_since_plugin_heartbeat += 0.1
        self.status_widget.update_render()
        
    @work(thread=True)
    def fetch_heatmap(self) -> None:
        if self.manage_services:
            global daemon_proc
            if daemon_proc is None or daemon_proc.poll() is not None:
                return  # Wait for daemon to be started and available

        scope_uid = self.qdl_config.scope
        
        # Determine heatmap week bounds
        today = datetime.datetime.now()
        start_date = today - datetime.timedelta(weeks=self.heatmap_weeks)
        
        # Get available counts locally
        all_tuids = get_tuids_containing(
            Path(self.qdl_config.data_dir),
            t_start=start_date,
            t_stop=today
        )
        available_counts = parse_tuids_to_heatmap_data(all_tuids)
        
        # Get detected counts via QDL SDK
        detected_counts = get_datasets_per_day(scope_uid, self.strategy)
        
        heatmap_grid = HeatmapGrid(num_weeks=self.heatmap_weeks, single_color_mode=True)
        grid_table = heatmap_grid.render(available_counts=available_counts, detected_counts=detected_counts)
        legend_text = heatmap_grid.render_legend()
        self.call_from_thread(self.heatmap_widget.update_heatmap, grid_table, legend_text)

    def write_log(self, text: str) -> None:
        at_bottom = self.log_widget.scroll_y >= (self.log_widget.max_scroll_y - 1)
        self.log_widget.write(text, scroll_end=at_bottom)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.submit_form()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_start":
            self.submit_form()
        elif event.button.id == "btn_browse":
            self.browse_directory()

    def submit_form(self) -> None:
        self.qdl_config.data_dir = self.query_one("#input_data_dir", Input).value
        self.qdl_config.scope = self.query_one("#input_scope", Input).value
        self.qdl_config.setup = self.query_one("#input_setup", Input).value
        self.qdl_config.device = self.query_one("#input_device", Input).value
        self.qdl_config.avoid_duplicates = self.query_one("#chk_avoid_duplicates", Checkbox).value
        self.qdl_config.save()
        
        scope_uid = self.qdl_config.scope
        self.status_widget.status_panel.update_config_info(scope_uid, self.qdl_config.setup, self.qdl_config.device)
        
        self.query_one(ContentSwitcher).current = "rich_log"
        self.query_one(RichLog).focus()
        self.start_auth_and_daemons()

    @work(thread=True)
    def browse_directory(self) -> None:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder_path = filedialog.askdirectory(title="Select Data Directory")
        root.destroy()
        
        if folder_path:
            # We can't update UI directly from a thread, must use call_from_thread
            def update_ui_input():
                self.query_one("#input_data_dir", Input).value = folder_path
            self.call_from_thread(update_ui_input)

    @work(thread=True)
    def start_auth_and_daemons(self) -> None:
        global daemon_proc, sync_proc
        
        self.call_from_thread(self.write_log, "[bold yellow][Await] user login[/bold yellow]")
        self.call_from_thread(self.status_widget.status_panel.update_state, credentials="Pending")
        
        try:
            qdl_settings: Any = qdl.configure()
            if not getattr(qdl_settings, 'api_token', None):
                raise Exception("No API token found")
            self.call_from_thread(self.write_log, "[bold green]Login succeeded[/bold green]")
            self.call_from_thread(self.status_widget.status_panel.update_state, credentials="Pass")
        except Exception as e:
            self.call_from_thread(self.write_log, f"[yellow]Starting login flow... {e}[/yellow]")
            try:
                qdl_exe = get_executable("qdl", self.qdl_config)
                subprocess.run([qdl_exe, "login"], check=True)
                qdl.configure()
                self.call_from_thread(self.write_log, "[bold green]Login succeeded[/bold green]")
                self.call_from_thread(self.status_widget.status_panel.update_state, credentials="Pass")
            except Exception as ex:
                self.call_from_thread(self.write_log, f"[bold red]Login failed. Exit application using Ctrl+C ({ex})[/bold red]")
                self.call_from_thread(self.status_widget.status_panel.update_state, credentials="Failed")
                return

        extract_plugin()
        
        if self.manage_services:
            creationflags = 0
            if sys.platform == 'win32':
                # 0x08000000 = CREATE_NO_WINDOW, 0x00000200 = CREATE_NEW_PROCESS_GROUP
                creationflags = 0x08000000 | 0x00000200
                
            os.environ["QMI_PLUGIN_AVOID_DUPLICATES"] = "1" if self.qdl_config.avoid_duplicates else "0"
                
            self.call_from_thread(self.write_log, "Starting daemon...")
            self.call_from_thread(self.status_widget.status_panel.update_state, daemon="Pending")
            daemon_exe = get_executable("qdl-daemon", self.qdl_config)
            try:
                daemon_proc = subprocess.Popen([daemon_exe], creationflags=creationflags, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.stream_logs(daemon_proc, "[DAEMON]")
            except Exception as e:
                self.call_from_thread(self.write_log, f"[red][DAEMON] Failed to start: {e}[/red]")
                self.call_from_thread(self.status_widget.status_panel.update_state, daemon="Failed")
                
            self.call_from_thread(self.write_log, "Starting sync...")
            self.call_from_thread(self.status_widget.status_panel.update_state, sync="Pending")
            sync_exe = get_executable("qdl-sync-service", self.qdl_config)
            try:
                sync_proc = subprocess.Popen([sync_exe], creationflags=creationflags, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.stream_logs(sync_proc, "[SYNC]")
            except Exception as e:
                self.call_from_thread(self.write_log, f"[red][SYNC] Failed to start: {e}[/red]")
                self.call_from_thread(self.status_widget.status_panel.update_state, sync="Failed")
        else:
            self.call_from_thread(self.write_log, "[blue]Services managed externally. Assuming daemon and sync-service are running.[/blue]")
            self.call_from_thread(self.status_widget.status_panel.update_state, daemon="Pass", sync="Pass")
            
        self.call_from_thread(setattr, self.status_widget.status_panel, "sync_timer_state", SyncTimerState.AWAITING_SYNC)
        time.sleep(2)
        
        scope_uid = self.qdl_config.scope
        qdl_exe = get_executable("qdl", self.qdl_config)
        data_dir = self.qdl_config.data_dir
        
        self.run_and_log([qdl_exe, "sync", "create", "--scan_interval", str(float(self.scan_interval)), PLUGIN_NAME, scope_uid, data_dir, PLUGIN_VERSION])
        self.run_and_log([qdl_exe, "sync", "update", "--sync_interval", str(float(self.sync_interval))])
        self.run_and_log([qdl_exe, "sync", "plugin", "start"])
        
        self.call_from_thread(self.write_log, "Services running! Press Ctrl+C (or Ctrl+Q) to exit.")

    def run_and_log(self, cmd: List[str]) -> None:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.stdout:
            for line in result.stdout.splitlines():
                if line.strip():
                    self.call_from_thread(self.write_log, line.strip())

    @work(thread=True)
    def stream_logs(self, proc: subprocess.Popen[Any], prefix: str) -> None:
        try:
            if proc.stdout:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        stripped = line.strip()
                        if prefix == "[SYNC]" and ("PLUGIN_HEARTBEAT_UPDATE" in stripped or "PLUGIN_SCAN_DATASETS" in stripped):
                            self.call_from_thread(setattr, self.status_widget.status_panel, "sync_timer_state", SyncTimerState.ACTIVE)
                            self.call_from_thread(self.status_widget.status_panel.update_sync_time, 0.0, interval=self.sync_interval)
                            
                        should_log = (prefix == "[DAEMON]" and self.show_daemon_logs) or (prefix == "[SYNC]" and self.show_sync_logs)
                        if should_log:
                            self.call_from_thread(self.write_log, f"{prefix} {stripped}")
                    if proc.poll() is not None:
                        break
        except Exception:
            pass

    @work(thread=True)
    def check_pending_tuids(self) -> None:
        if not getattr(self, "plugin_enabled", False):
            return
        try:
            scope_uid = self.qdl_config.scope
            datasets = qdl.Dataset.list(scope_uid=scope_uid)
            processed_tuids = {d.name for d in datasets}
            now = time.time()
            for tuid, info in list(self.tuid_states.items()):
                if tuid in processed_tuids:
                    if info["state"] != "Processed":
                        info["state"] = "Processed"
                        self.call_from_thread(self.write_log, f"[bold green][TRACKER] TUID {tuid} Processed by Daemon![/bold green]")
                else:
                    if info["state"] == "Submitted" and (now - info["time"] > 120):
                        self.call_from_thread(self.write_log, f"[bold red][WARNING] TUID {tuid} is pending/stuck and has not been processed yet![/bold red]")
                        info["state"] = "Stuck"
        except Exception:
            pass

    @work(thread=True)
    def tuid_tracker_thread(self) -> None:
        import zmq
        ctx = zmq.Context.instance()
        socket = ctx.socket(zmq.SUB)
        socket.bind("tcp://127.0.0.1:4206")
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
        while not getattr(self, "shutting_down", False):
            try:
                if socket.poll(1000):
                    data = socket.recv_json()
                    if data.get("type") == "tuid_event":
                        tuid = data.get("tuid")
                        self.tuid_states[tuid] = {"state": "Submitted", "time": time.time()}
                        self.call_from_thread(self.write_log, f"[bold blue][TRACKER] Plugin Found & Submitted TUID: {tuid}[/bold blue]")
            except Exception:
                pass

@click.command()
def main() -> None:
    app = QdlClientApp()
    app.run()

if __name__ == "__main__":
    main()
