import os
import shutil
import tarfile
import json
import PyInstaller.__main__

def get_plugin_version() -> str:
    v_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "version.json")
    with open(v_path, "r") as f:
        return json.load(f).get("custom_qdl_plugin_version", "0.1.0")

def build():
    version = get_plugin_version()
    print("Cleaning up old builds...")
    dist_dir = 'custom_qdl_plugin/dist'
    build_dir = 'custom_qdl_plugin/build'
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        
    print("Starting PyInstaller build...")
    # 1. Run Pyinstaller
    PyInstaller.__main__.run([
        'custom_qdl_plugin/main.py',
        '--onefile',
        '--name', 'qdl-custom-plugin',
        '--distpath', 'custom_qdl_plugin/dist/bin',
        '--workpath', 'custom_qdl_plugin/build',
        '--specpath', 'custom_qdl_plugin',
        '--noconfirm'
    ])
    
    print("Generating metadata.json...")
    # 2. Generate metadata.json
    metadata = {
        "name": "custom",
        "version": version,
        "description": "Custom Data Collection Plugin",
        "author": "User",
        "binary": "bin/qdl-custom-plugin.exe",
        "capabilities": ["streaming", "historical"],
        "supported_formats": ["hdf5"]
    }
    
    metadata_path = 'custom_qdl_plugin/dist/metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    print("Creating README.md...")
    # 3. Create README.md
    readme_path = 'custom_qdl_plugin/dist/README.md'
    with open(readme_path, 'w') as f:
        f.write("# Custom QDL Plugin\n\nCustom data acquisition monitor.")
        
    print("Packaging into tarball...")
    # 4. Tarball packaging
    tarball_name = f'qdl-{metadata["name"]}-plugin-windows-{metadata["version"]}.tar.gz'
    with tarfile.open(f'custom_qdl_plugin/{tarball_name}', 'w:gz') as tar:
        tar.add('custom_qdl_plugin/dist/bin', arcname='bin')
        tar.add(metadata_path, arcname='metadata.json')
        tar.add(readme_path, arcname='README.md')
        
    print(f"Successfully packaged into {tarball_name}")

if __name__ == "__main__":
    build()
