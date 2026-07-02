import PyInstaller.__main__
import os
import shutil
import subprocess
import sys
from pathlib import Path

def build():
    # 1. First run the plugin build to ensure the latest tarball is ready
    print("Building plugin tarball first...")
    
    root_dir = Path(__file__).parent.parent
    plugin_build_script = root_dir / "custom_qdl_plugin" / "build.py"
    
    # We run the build script from the root directory to keep paths correct
    subprocess.run([sys.executable, str(plugin_build_script)], check=True, cwd=str(root_dir))
    
    # 2. Package the client with Pyinstaller
    print("Packaging CLI client...")
    
    tarball_path = root_dir / "custom_qdl_plugin" / "qdl-custom-plugin-windows-1.0.0.tar.gz"
    
    if not tarball_path.exists():
        print(f"Error: Tarball not found at {tarball_path}")
        return

    cli_script = Path(__file__).parent / "cli.py"
    
    PyInstaller.__main__.run([
        str(cli_script),
        '--onefile',
        '--name', 'qdl-client',
        '--distpath', str(Path(__file__).parent / 'dist'),
        '--workpath', str(Path(__file__).parent / 'build'),
        '--specpath', str(Path(__file__).parent),
        f'--add-data={tarball_path};.',
        '--add-data=client/messages.json;.',
        '--noconfirm'
    ])
    
    print("Successfully built client executable at client/dist/qdl-client.exe")

if __name__ == "__main__":
    build()
