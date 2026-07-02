import os
import sys
import json
import shutil
import subprocess
import time
import atexit
from pathlib import Path
import click
import qdl

CONFIG_PATH = Path.home() / ".qdl" / "client_config.json"
PLUGIN_TARBALL_NAME = "qdl-custom-plugin-windows-1.0.0.tar.gz"

daemon_proc = None
sync_proc = None

class MessageConfig:
    def __init__(self, data):
        self.data = data
        
    def get_text(self, category, key, **format_kwargs):
        try:
            val = self.data[category][key]
            if isinstance(val, dict):
                text = val.get("text", f"Warning: Echo statement NULL text for key '{category}.{key}'")
            else:
                text = val
            return text.format(**format_kwargs)
        except KeyError:
            return f"Warning: Echo statement NULL for key '{category}.{key}'"

    def echo(self, category, key, **format_kwargs):
        try:
            val = self.data[category][key]
            if isinstance(val, dict):
                text = val.get("text", f"Warning: Echo statement NULL text for key '{category}.{key}'")
                click.secho(text.format(**format_kwargs), fg=val.get("fg"), bg=val.get("bg"), bold=val.get("bold", False))
            else:
                click.secho(val.format(**format_kwargs))
        except KeyError:
            click.secho(f"Warning: Echo statement NULL for key '{category}.{key}'", fg="red")
            
    def print(self, category, key, **format_kwargs):
        print(self.get_text(category, key, **format_kwargs))
        
    def prompt(self, category, key, default=None, **format_kwargs):
        text = self.get_text(category, key, **format_kwargs)
        if default is not None:
            return click.prompt(text, default=default)
        return click.prompt(text)

def load_messages():
    # Find messages.json, which might be bundled or in the same dir
    if hasattr(sys, "_MEIPASS"):
        msg_path = Path(sys._MEIPASS) / "messages.json"
    else:
        msg_path = Path(__file__).parent / "messages.json"
        
    if msg_path.exists():
        with open(msg_path, "r") as f:
            return MessageConfig(json.load(f))
    return MessageConfig({"prompts": {}, "info": {}, "warnings": {}, "errors": {}})

msgs = load_messages()

def cleanup():
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

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def fatal_error(msg):
    msgs.echo("errors", "fatal", msg=msg)
    click.pause(info=msgs.get_text("prompts", "press_any_key"))
    sys.exit(1)

def get_executable(name, config):
    """Finds the executable in PATH or prompts the user for its location."""
    if shutil.which(name):
        return name
        
    bin_dir = config.get("qdl_bin_dir")
    if bin_dir:
        exe_path = os.path.join(bin_dir, f"{name}.exe" if sys.platform == "win32" else name)
        if os.path.exists(exe_path):
            return exe_path
            
    msgs.echo("warnings", "executable_not_in_path", name=name)
    msgs.echo("info", "venv_hint")
    
    while True:
        bin_dir = msgs.prompt("prompts", "bin_dir", name=name)
        exe_path = os.path.join(bin_dir, f"{name}.exe" if sys.platform == "win32" else name)
        if os.path.exists(exe_path):
            config["qdl_bin_dir"] = bin_dir
            save_config(config)
            return exe_path
        msgs.echo("errors", "executable_not_in_dir", bin_dir=bin_dir)

def extract_plugin():
    """Extracts the bundled PyInstaller tarball into the QDL plugins directory."""
    plugins_dir = Path.home() / ".qdl" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    
    # When bundled by PyInstaller, sys._MEIPASS holds the temp extraction directory
    if hasattr(sys, "_MEIPASS"):
        bundled_path = Path(sys._MEIPASS) / PLUGIN_TARBALL_NAME
    else:
        # Development fallback relative to this file
        bundled_path = Path(__file__).parent.parent / "custom_qdl_plugin" / PLUGIN_TARBALL_NAME

    if bundled_path.exists():
        target_path = plugins_dir / PLUGIN_TARBALL_NAME
        shutil.copy2(bundled_path, target_path)
        msgs.print("info", "plugin_deployed", target_path=target_path)
    else:
        msgs.print("warnings", "plugin_not_found", bundled_path=bundled_path)

def ensure_authenticated(config):
    """Validates the local QDL token and initiates a login flow if invalid."""
    try:
        # Try initializing the SDK. If the token is missing/expired, this or a subsequent check would fail.
        qdl_settings = qdl.configure()
        if not getattr(qdl_settings, 'api_token', None):
            raise Exception("No API token found in configuration.")
        msgs.echo("info", "auth_success")
    except Exception as e:
        msgs.echo("info", "starting_login")
        try:
            qdl_exe = get_executable("qdl", config)
            subprocess.run([qdl_exe, "login"], check=True)
            # Re-configure after login
            qdl.configure() 
        except Exception as ex:
            fatal_error(msgs.get_text("errors", "login_error", ex=ex))

@click.command()
def main():
    """QDL Client Manager: Configures and runs the QDL data backup process."""
    msgs.echo("info", "welcome")
    
    config = load_config()
    
    # Interactive Prompts
    default_dir = config.get("data_dir", "D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/")
    data_dir = msgs.prompt("prompts", "data_dir", default=default_dir)
    # Ensure POSIX formatting for QDL
    data_dir = Path(data_dir).as_posix()
    
    fridge = msgs.prompt("prompts", "fridge", default=config.get("fridge", "dicarlo"))
    device = msgs.prompt("prompts", "device", default=config.get("device", "testing"))
    
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
    creationflags = 0
    if sys.platform == 'win32':
        creationflags = 0x00000008 | 0x00000200
    
    msgs.echo("info", "starting_daemon")
    daemon_exe = get_executable("qdl-daemon", config)
    try:
        daemon_proc = subprocess.Popen([daemon_exe], creationflags=creationflags)
    except Exception as e:
        fatal_error(msgs.get_text("errors", "daemon_start_error", e=e))
        
    msgs.echo("info", "starting_sync")
    sync_exe = get_executable("qdl-sync-service", config)
    try:
        sync_proc = subprocess.Popen([sync_exe], creationflags=creationflags)
    except Exception as e:
        fatal_error(msgs.get_text("errors", "sync_start_error", e=e))
    
    # Allow time for services to boot up before attempting to communicate via CLI
    time.sleep(3)
    
    # Hardcoded scope as requested
    scope_uid = "dicarlo-testing"
    
    msgs.echo("info", "configuring_custom_sync", scope_uid=scope_uid)
    qdl_exe = get_executable("qdl", config)
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
