import os
import sys
import json
import shutil
import subprocess
import time
import atexit
from pathlib import Path
from typing import Any, Optional, Mapping, MutableMapping

import click
import qdl

CONFIG_PATH: Path = Path.home() / ".qdl" / "client_config.json"
PLUGIN_TARBALL_NAME: str = "qdl-custom-plugin-windows-1.0.0.tar.gz"

daemon_proc: Optional[subprocess.Popen[Any]] = None
sync_proc: Optional[subprocess.Popen[Any]] = None

class MessageConfig:
    # region Class Constructor
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.data: Mapping[str, Any] = data
    # endregion
        
    # region Class Methods
    def get_text(self, category: str, key: str, **format_kwargs: Any) -> str:
        try:
            val: Any = self.data[category][key]
            if isinstance(val, dict):
                text: str = val.get("text", f"Warning: Echo statement NULL text for key '{category}.{key}'")
            else:
                text = val
            return text.format(**format_kwargs)
        except KeyError:
            return f"Warning: Echo statement NULL for key '{category}.{key}'"

    def echo(self, category: str, key: str, **format_kwargs: Any) -> None:
        try:
            val: Any = self.data[category][key]
            if isinstance(val, dict):
                text: str = val.get("text", f"Warning: Echo statement NULL text for key '{category}.{key}'")
                click.secho(text.format(**format_kwargs), fg=val.get("fg"), bg=val.get("bg"), bold=val.get("bold", False))
            else:
                click.secho(val.format(**format_kwargs))
        except KeyError:
            click.secho(f"Warning: Echo statement NULL for key '{category}.{key}'", fg="red")
            
    def print(self, category: str, key: str, **format_kwargs: Any) -> None:
        print(self.get_text(category, key, **format_kwargs))
        
    def prompt(self, category: str, key: str, default: Optional[str] = None, **format_kwargs: Any) -> str:
        text: str = self.get_text(category, key, **format_kwargs)
        if default is not None:
            return click.prompt(text, default=default)
        return click.prompt(text)
    # endregion

def load_messages() -> MessageConfig:
    # Find messages.json, which might be bundled or in the same dir
    msg_path: Path
    if hasattr(sys, "_MEIPASS"):
        msg_path = Path(sys._MEIPASS) / "messages.json"
    else:
        msg_path = Path(__file__).parent / "messages.json"
        
    if msg_path.exists():
        with open(msg_path, "r") as f:
            return MessageConfig(json.load(f))
    return MessageConfig({"prompts": {}, "info": {}, "warnings": {}, "errors": {}})

msgs: MessageConfig = load_messages()

def cleanup() -> None:
    """Kills the background processes when the CLI exits."""
    global daemon_proc, sync_proc
    if sync_proc and sync_proc.poll() is None:
        msgs.print("info", "stopping_sync")
        sync_proc.terminate()
        try:
            sync_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            sync_proc.kill()
            
    if daemon_proc and daemon_proc.poll() is None:
        msgs.print("info", "stopping_daemon")
        daemon_proc.terminate()
        try:
            daemon_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            daemon_proc.kill()

atexit.register(cleanup)

def load_config() -> MutableMapping[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            config: MutableMapping[str, Any] = json.load(f)
            return config
    return {}

def save_config(config: Mapping[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def fatal_error(msg: str) -> None:
    msgs.echo("errors", "fatal", msg=msg)
    click.pause(info=msgs.get_text("prompts", "press_any_key"))
    sys.exit(1)

def get_executable(name: str, config: MutableMapping[str, Any]) -> str:
    """Finds the executable in PATH or prompts the user for its location."""
    if shutil.which(name):
        return name
        
    bin_dir: Optional[str] = config.get("qdl_bin_dir")
    if bin_dir:
        exe_path: str = os.path.join(bin_dir, f"{name}.exe" if sys.platform == "win32" else name)
        if os.path.exists(exe_path):
            return exe_path
            
    msgs.echo("warnings", "executable_not_in_path", name=name)
    msgs.echo("info", "venv_hint")
    
    while True:
        bin_dir_prompt: str = msgs.prompt("prompts", "bin_dir", name=name)
        exe_path = os.path.join(bin_dir_prompt, f"{name}.exe" if sys.platform == "win32" else name)
        if os.path.exists(exe_path):
            config["qdl_bin_dir"] = bin_dir_prompt
            save_config(config)
            return exe_path
        msgs.echo("errors", "executable_not_in_dir", bin_dir=bin_dir_prompt)

def extract_plugin() -> None:
    """Extracts the bundled PyInstaller tarball into the QDL plugins directory."""
    plugins_dir: Path = Path.home() / ".qdl" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    
    bundled_path: Path
    # When bundled by PyInstaller, sys._MEIPASS holds the temp extraction directory
    if hasattr(sys, "_MEIPASS"):
        bundled_path = Path(sys._MEIPASS) / PLUGIN_TARBALL_NAME
    else:
        # Development fallback relative to this file
        bundled_path = Path(__file__).parent.parent / "custom_qdl_plugin" / PLUGIN_TARBALL_NAME

    if bundled_path.exists():
        target_path: Path = plugins_dir / PLUGIN_TARBALL_NAME
        shutil.copy2(bundled_path, target_path)
        msgs.print("info", "plugin_deployed", target_path=target_path)
    else:
        msgs.print("warnings", "plugin_not_found", bundled_path=bundled_path)

def ensure_authenticated(config: MutableMapping[str, Any]) -> None:
    """Validates the local QDL token and initiates a login flow if invalid."""
    try:
        # Try initializing the SDK. If the token is missing/expired, this or a subsequent check would fail.
        qdl_settings: Any = qdl.configure()
        if not getattr(qdl_settings, 'api_token', None):
            raise Exception("No API token found in configuration.")
        msgs.echo("info", "auth_success")
    except Exception as e:
        msgs.echo("info", "starting_login")
        try:
            qdl_exe: str = get_executable("qdl", config)
            subprocess.run([qdl_exe, "login"], check=True)
            # Re-configure after login
            qdl.configure() 
        except Exception as ex:
            fatal_error(msgs.get_text("errors", "login_error", ex=ex))

@click.command()
def main() -> None:
    """QDL Client Manager: Configures and runs the QDL data backup process."""
    msgs.echo("info", "welcome")
    
    config: MutableMapping[str, Any] = load_config()
    
    # Interactive Prompts
    default_dir: str = config.get("data_dir", "D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/")
    data_dir_str: str = msgs.prompt("prompts", "data_dir", default=default_dir)
    # Ensure POSIX formatting for QDL
    data_dir: str = Path(data_dir_str).as_posix()
    
    fridge: str = msgs.prompt("prompts", "fridge", default=config.get("fridge", "dicarlo"))
    device: str = msgs.prompt("prompts", "device", default=config.get("device", "testing"))
    
    # Save preferences
    config.update({
        "data_dir": data_dir,
        "fridge": fridge,
        "device": device
    })
    save_config(config)
    
    # Authenticate and Extract Plugin
    ensure_authenticated(config)
    extract_plugin()
    
    global daemon_proc, sync_proc
    
    # Windows detached process flags
    # 0x00000008 = DETACHED_PROCESS
    # 0x00000200 = CREATE_NEW_PROCESS_GROUP
    creationflags: int = 0
    if sys.platform == 'win32':
        creationflags = 0x00000008 | 0x00000200
    
    msgs.echo("info", "starting_daemon")
    daemon_exe: str = get_executable("qdl-daemon", config)
    try:
        daemon_proc = subprocess.Popen([daemon_exe], creationflags=creationflags)
    except Exception as e:
        fatal_error(msgs.get_text("errors", "daemon_start_error", e=e))
        
    msgs.echo("info", "starting_sync")
    sync_exe: str = get_executable("qdl-sync-service", config)
    try:
        sync_proc = subprocess.Popen([sync_exe], creationflags=creationflags)
    except Exception as e:
        fatal_error(msgs.get_text("errors", "sync_start_error", e=e))
    
    # Allow time for services to boot up before attempting to communicate via CLI
    time.sleep(3)
    
    # Hardcoded scope as requested
    scope_uid: str = "dicarlo-testing"
    
    msgs.echo("info", "configuring_custom_sync", scope_uid=scope_uid)
    qdl_exe: str = get_executable("qdl", config)
    try:
        subprocess.run([qdl_exe, "sync", "create", "custom", scope_uid, data_dir, "0.1.0"], check=False)
    except Exception as e:
        msgs.echo("warnings", "could_not_create_sync", e=e)
        
    msgs.echo("info", "configuring_sync_service")
    try:
        subprocess.run([qdl_exe, "sync", "update", "--scan_interval", "5"], check=False)
    except Exception as e:
        msgs.echo("warnings", "could_not_configure_sync", e=e)

    msgs.echo("info", "starting_backup_sync")
    try:
        subprocess.run([qdl_exe, "sync", "plugin", "start"], check=False)
    except Exception as e:
        msgs.echo("warnings", "could_not_start_sync", e=e)
        
    msgs.echo("info", "services_running")
    msgs.echo("info", "press_ctrl_c")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        msgs.echo("info", "shutting_down")
        # atexit handler will automatically take care of process cleanup

if __name__ == "__main__":
    main()
