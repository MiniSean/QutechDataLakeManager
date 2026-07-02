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

def cleanup():
    """Kills the background processes when the CLI exits."""
    global daemon_proc, sync_proc
    if sync_proc and sync_proc.poll() is None:
        print("Stopping QDL Sync Service...")
        sync_proc.terminate()
        try:
            sync_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            sync_proc.kill()
            
    if daemon_proc and daemon_proc.poll() is None:
        print("Stopping QDL Daemon...")
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
    click.secho(msg, fg="red")
    click.pause(info="Press any key to exit...")
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
            
    click.secho(f"Could not find '{name}' in your PATH.", fg="yellow")
    click.secho("If you are using a Python virtual environment, please provide the path to its 'Scripts' or 'bin' directory.", fg="yellow")
    
    while True:
        bin_dir = click.prompt(f"Directory containing {name} (e.g., C:/path/to/venv/Scripts)")
        exe_path = os.path.join(bin_dir, f"{name}.exe" if sys.platform == "win32" else name)
        if os.path.exists(exe_path):
            config["qdl_bin_dir"] = bin_dir
            save_config(config)
            return exe_path
        click.secho(f"Executable not found in {bin_dir}. Please try again.", fg="red")

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
        print(f"Plugin successfully deployed to {target_path}")
    else:
        print(f"Warning: Bundled plugin not found at {bundled_path}. Sync-service may attempt to download it.")

def ensure_authenticated(config):
    """Validates the local QDL token and initiates a login flow if invalid."""
    try:
        # Try initializing the SDK. If the token is missing/expired, this or a subsequent check would fail.
        qdl_settings = qdl.configure()
        if not getattr(qdl_settings, 'api_token', None):
            raise Exception("No API token found in configuration.")
        click.secho("Authenticated with QDL successfully.", fg="green")
    except Exception as e:
        click.secho("Not authenticated or token missing. Starting login process...", fg="yellow")
        try:
            qdl_exe = get_executable("qdl", config)
            subprocess.run([qdl_exe, "login"], check=True)
            # Re-configure after login
            qdl.configure() 
        except Exception as ex:
            fatal_error(f"Error during login: {ex}")

@click.command()
def main():
    """QDL Client Manager: Configures and runs the QDL data backup process."""
    click.secho("=== QDL Backup Client ===", fg="green", bold=True)
    
    config = load_config()
    
    # Interactive Prompts
    default_dir = config.get("data_dir", "D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/")
    data_dir = click.prompt("Data Directory", default=default_dir)
    # Ensure POSIX formatting for QDL
    data_dir = Path(data_dir).as_posix()
    
    fridge = click.prompt("Fridge Name", default=config.get("fridge", "dicarlo"))
    device = click.prompt("Device Name", default=config.get("device", "testing"))
    
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
    
    click.secho("Starting QDL Daemon...", fg="blue")
    daemon_exe = get_executable("qdl-daemon", config)
    try:
        daemon_proc = subprocess.Popen([daemon_exe], creationflags=creationflags)
    except Exception as e:
        fatal_error(f"Error starting daemon: {e}")
        
    click.secho("Starting QDL Sync Service...", fg="blue")
    sync_exe = get_executable("qdl-sync-service", config)
    try:
        sync_proc = subprocess.Popen([sync_exe], creationflags=creationflags)
    except Exception as e:
        fatal_error(f"Error starting sync service: {e}")
    
    # Allow time for services to boot up before attempting to communicate via CLI
    time.sleep(3)
    
    # Hardcoded scope as requested
    scope_uid = "dicarlo-testing"
    
    click.secho(f"Configuring Custom Plugin Sync for scope: {scope_uid}", fg="yellow")
    qdl_exe = get_executable("qdl", config)
    try:
        subprocess.run([qdl_exe, "sync", "create", "custom", scope_uid, data_dir, "0.1.0"], check=False)
    except Exception as e:
        click.secho(f"Warning: Could not create sync: {e}", fg="yellow")
        
    click.secho("Configuring Sync Service...", fg="green")
    try:
        subprocess.run([qdl_exe, "sync", "update", "--scan_interval", "5"], check=False)
    except Exception as e:
        click.secho(f"Warning: Could not configure sync: {e}", fg="yellow")

    click.secho("Starting Backup Sync...", fg="green")
    try:
        subprocess.run([qdl_exe, "sync", "plugin", "start"], check=False)
    except Exception as e:
        click.secho(f"Warning: Could not start sync: {e}", fg="yellow")
        
    click.secho("\nBackup Services are running in the background.", fg="green", bold=True)
    click.secho("Press Ctrl+C to stop the backup process and exit.", fg="red")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.secho("\nShutting down...", fg="yellow")
        # atexit handler will automatically take care of process cleanup

if __name__ == "__main__":
    main()
