import os
import shutil
import tarfile
import json
import PyInstaller.__main__

def get_plugin_version() -> str:
    # Use hardcoded 0.1.0 for custom mirror
    return "0.1.0"

def build():
    version = get_plugin_version()
    print("Cleaning up old builds...")
    dist_dir = 'custom_qmi_plugin/dist'
    build_dir = 'custom_qmi_plugin/build'
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        
    print("Starting PyInstaller build...")
    # 1. Run Pyinstaller
    PyInstaller.__main__.run([
        'custom_qmi_plugin/qmi_plugin/main.py',
        '--onefile',
        '--name', 'qdl-custom_qmi-plugin',
        '--distpath', 'custom_qmi_plugin/dist/bin',
        '--workpath', 'custom_qmi_plugin/build',
        '--specpath', 'custom_qmi_plugin',
        '--noconfirm'
    ])
    
    print("Generating metadata.json...")
    # 2. Generate metadata.json
    metadata = {
        "name": "custom_qmi",
        "version": version,
        "description": "Custom mirrored QMI Plugin",
        "author": "User",
        "binary": "bin/qdl-custom_qmi-plugin.exe",
        "capabilities": ["streaming", "historical"],
        "supported_formats": ["hdf5"]
    }
    
    metadata_path = 'custom_qmi_plugin/dist/metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    print("Creating README.md...")
    # 3. Create README.md
    readme_path = 'custom_qmi_plugin/dist/README.md'
    with open(readme_path, 'w') as f:
        f.write("# Custom Mirrored QMI Plugin\n\nCustom data acquisition monitor.")
        
    print("Packaging into tarball...")
    # 4. Tarball packaging
    tarball_name = f'qdl-{metadata["name"]}-plugin-windows-{metadata["version"]}.tar.gz'
    with tarfile.open(f'custom_qmi_plugin/{tarball_name}', 'w:gz') as tar:
        tar.add('custom_qmi_plugin/dist/bin', arcname='bin')
        tar.add(metadata_path, arcname='metadata.json')
        tar.add(readme_path, arcname='README.md')
        
    print(f"Successfully packaged into {tarball_name}")

if __name__ == "__main__":
    build()
