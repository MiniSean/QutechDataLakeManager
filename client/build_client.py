import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import PyInstaller.__main__
import json

def get_plugin_version(root_dir: Path) -> str:
    v_path = root_dir / "version.json"
    with open(v_path, "r") as f:
        return json.load(f).get("custom_qdl_plugin_version", "0.1.0")

def build() -> None:
    print("Cleaning up old builds...")
    dist_dir: str = 'client/dist'
    build_dir: str = 'client/build'
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        
    print("Building plugin tarball first...")
    root_dir: Path = Path(__file__).parent.parent
    plugin_build_script: Path = root_dir / "custom_qdl_plugin" / "build.py"
    
    # We run the build script from the root directory to keep paths correct
    subprocess.run([sys.executable, str(plugin_build_script)], check=True, cwd=str(root_dir))
    
    # 2. Package the client with Pyinstaller
    print("Packaging CLI client...")
    
    version = get_plugin_version(root_dir)
    tarball_path: Path = root_dir / "custom_qdl_plugin" / f"qdl-custom-plugin-windows-{version}.tar.gz"
    
    if not tarball_path.exists():
        print(f"Error: Tarball not found at {tarball_path}")
        return

    cli_script: Path = Path(__file__).parent / "cli.py"
    
    messages_path: Path = root_dir / "client" / "messages.json"
    version_path: Path = root_dir / "version.json"
    plugin_settings_path: Path = root_dir / "plugin_settings.json"
    
    PyInstaller.__main__.run([
        str(cli_script),
        '--onefile',
        '--name', 'qdl-client',
        '--distpath', str(Path(__file__).parent / 'dist'),
        '--workpath', str(Path(__file__).parent / 'build'),
        '--specpath', str(Path(__file__).parent),
        f'--add-data={tarball_path};.',
        f'--add-data={messages_path};.',
        f'--add-data={version_path};.',
        f'--add-data={plugin_settings_path};.',
        '--noconfirm'
    ])
    
    print("Successfully built client executable at client/dist/qdl-client.exe")

if __name__ == "__main__":
    build()
