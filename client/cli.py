import os
import sys
import json
import shutil
import subprocess
import time
import atexit
import threading
from pathlib import Path
from typing import Any, Optional, Mapping, MutableMapping, List, Dict

import click
import qdl

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, Button, RichLog, Label, ContentSwitcher
from textual.containers import Container, Horizontal, Vertical, Grid
from textual import work

from client.contribution_heatmap.ui import HeatmapGrid
from client.contribution_heatmap.data_fetcher import get_datasets_per_day
from client.contribution_heatmap.strategy_tuid_extraction import QdlDatasetNameDateExtraction
from client.status_panel.ui import StatusPanel
from rich.console import Group
from rich.align import Align

CONFIG_PATH: Path = Path.home() / ".qdl" / "client_config.json"

def get_plugin_version() -> str:
    if hasattr(sys, "_MEIPASS"):
        v_path = Path(sys._MEIPASS) / "version.json"
    else:
        v_path = Path(__file__).parent.parent / "version.json"
    if v_path.exists():
        with open(v_path, "r") as f:
            return json.load(f).get("custom_qdl_plugin_version", "0.1.0")
    return "0.1.0"

PLUGIN_VERSION: str = get_plugin_version()
PLUGIN_TARBALL_NAME: str = f"qdl-custom-plugin-windows-{PLUGIN_VERSION}.tar.gz"

daemon_proc: Optional[subprocess.Popen[Any]] = None
sync_proc: Optional[subprocess.Popen[Any]] = None

def cleanup() -> None:
    """Kills the background processes when the CLI exits."""
    global daemon_proc, sync_proc
    
    if sync_proc and sync_proc.poll() is None:
        sync_proc.terminate()
        try:
            sync_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            sync_proc.kill()
            sync_proc.wait()
            
        if sync_proc.stdout:
            try:
                sync_proc.stdout.close()
            except Exception:
                pass
            
    if daemon_proc and daemon_proc.poll() is None:
        daemon_proc.terminate()
        try:
            daemon_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon_proc.kill()
            daemon_proc.wait()
            
        if daemon_proc.stdout:
            try:
                daemon_proc.stdout.close()
            except Exception:
                pass

atexit.register(cleanup)

def load_config() -> MutableMapping[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}

def save_config(config: Mapping[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def get_executable(name: str, config: MutableMapping[str, Any]) -> str:
    """Finds the executable in PATH or from config."""
    if shutil.which(name):
        return name
        
    bin_dir: Optional[str] = config.get("qdl_bin_dir")
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
            "\n",
            Align.right(legend_text)
        )
        self.update(group)

class StatusWidget(Static):
    def on_mount(self) -> None:
        self.status_panel = StatusPanel()
        
    def update_render(self) -> None:
        self.update(self.status_panel.render())

class SetupForm(Container):
    def __init__(self, config: MutableMapping[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.config = config

    def compose(self) -> ComposeResult:
        default_dir = self.config.get("data_dir", "D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/")
        yield Label("Data Directory:")
        with Horizontal(id="dir_row"):
            yield Input(value=default_dir, id="input_data_dir")
            yield Button("Browse", id="btn_browse")
        with Horizontal(id="fridge_device_row"):
            with Vertical(classes="flex_col"):
                yield Label("Scope:")
                yield Input(value=self.config.get("scope", "dicarlo-testing"), id="input_scope")
            with Vertical(classes="flex_col"):
                yield Label("Setup Name:")
                yield Input(value=self.config.get("setup", "dicarlo"), id="input_setup")
            with Vertical(classes="flex_col"):
                yield Label("Device Name:")
                yield Input(value=self.config.get("device", "testing"), id="input_device")
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
    SetupForm Input, SetupForm Button {
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
        ("end", "scroll_end", "Snap to Bottom"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.qdl_config: MutableMapping[str, Any] = load_config()
        self.strategy = QdlDatasetNameDateExtraction()
        
    def action_quit(self) -> None:
        cleanup()
        self.exit()
        
    def action_scroll_end(self) -> None:
        if self.query(ContentSwitcher) and self.query_one(ContentSwitcher).current == "rich_log":
            self.query_one(RichLog).scroll_end(animate=False)
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="top_panel"):
            yield HeatmapWidget(id="heatmap_container")
            yield StatusWidget(id="status_container")
        
        with ContentSwitcher(initial="setup_form", id="bottom_panel"):
            yield SetupForm(self.qdl_config, id="setup_form")
            yield RichLog(id="rich_log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.status_widget = self.query_one(StatusWidget)
        self.heatmap_widget = self.query_one(HeatmapWidget)
        self.log_widget = self.query_one(RichLog)
        
        scope_init = self.qdl_config.get("scope", "dicarlo-testing")
        self.status_widget.status_panel.update_config_info(scope_init, self.qdl_config.get("setup", "dicarlo"), self.qdl_config.get("device", "testing"))
        
        # Render empty heatmap immediately so it isn't delayed
        heatmap_grid = HeatmapGrid(num_weeks=52)
        grid_table = heatmap_grid.render({})
        legend_text = heatmap_grid.render_legend()
        self.heatmap_widget.update_heatmap(grid_table, legend_text)
        
        self.set_interval(0.1, self.tick_status)
        self.set_interval(5.0, self.fetch_heatmap)
        self.fetch_heatmap()
        
    def tick_status(self) -> None:
        global daemon_proc, sync_proc
        if daemon_proc:
            self.status_widget.status_panel.update_state(daemon="Pass" if daemon_proc.poll() is None else "Failed")
        if sync_proc:
            self.status_widget.status_panel.update_state(sync="Pass" if sync_proc.poll() is None else "Failed")
            
        self.status_widget.status_panel.time_since_sync += 0.1
        self.status_widget.update_render()
        
    @work(thread=True)
    def fetch_heatmap(self) -> None:
        scope_uid = self.qdl_config.get("scope", "dicarlo-testing")
        counts = get_datasets_per_day(scope_uid, self.strategy)
        heatmap_grid = HeatmapGrid(num_weeks=52)
        grid_table = heatmap_grid.render(counts)
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
        self.qdl_config["data_dir"] = self.query_one("#input_data_dir", Input).value
        self.qdl_config["scope"] = self.query_one("#input_scope", Input).value
        self.qdl_config["setup"] = self.query_one("#input_setup", Input).value
        self.qdl_config["device"] = self.query_one("#input_device", Input).value
        save_config(self.qdl_config)
        
        scope_uid = self.qdl_config["scope"]
        self.status_widget.status_panel.update_config_info(scope_uid, self.qdl_config["setup"], self.qdl_config["device"])
        
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
        
        self.status_widget.status_panel.show_sync_timer = True
        
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
        
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = 0x00000008 | 0x00000200
            
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
            
        time.sleep(3)
        
        scope_uid = self.qdl_config.get("scope", "dicarlo-testing")
        qdl_exe = get_executable("qdl", self.qdl_config)
        data_dir = self.qdl_config.get("data_dir")
        
        self.run_and_log([qdl_exe, "sync", "create", "custom", scope_uid, data_dir, PLUGIN_VERSION])
        self.run_and_log([qdl_exe, "sync", "update", "--scan_interval", "5"])
        self.run_and_log([qdl_exe, "sync", "plugin", "start"])
        
        self.call_from_thread(self.write_log, "Services running! Press Ctrl+C to exit.")

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
                        self.call_from_thread(self.write_log, f"{prefix} {stripped}")
                        if prefix == "[SYNC]" and ("PLUGIN_HEARTBEAT_UPDATE" in stripped or "PLUGIN_SCAN_DATASETS" in stripped):
                            self.call_from_thread(self.status_widget.status_panel.update_sync_time, 0.0)
                    if proc.poll() is not None:
                        break
        except Exception:
            pass

@click.command()
def main() -> None:
    app = QdlClientApp()
    app.run()

if __name__ == "__main__":
    main()
