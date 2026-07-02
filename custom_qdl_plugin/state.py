import hashlib
from pathlib import Path

def get_md5(file_path: Path) -> str:
    """Computes the MD5 checksum of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_mirror_path(dataset_dir: Path, file_relative_path: str) -> Path:
    """Gets the path to the .md5 mirror file in the .qdl directory."""
    return dataset_dir / ".qdl" / f"{file_relative_path}.md5"

def has_changed(dataset_dir: Path, file_relative_path: str, current_md5: str) -> bool:
    """Checks if the file has changed compared to its last known state in the .qdl mirror."""
    mirror_path = get_mirror_path(dataset_dir, file_relative_path)
    if not mirror_path.exists():
        return True
    
    with open(mirror_path, "r", encoding="utf-8") as f:
        known_md5 = f.read().strip()
    
    return known_md5 != current_md5

def update_state(dataset_dir: Path, file_relative_path: str, md5_hash: str) -> None:
    """Saves the current MD5 checksum to the .qdl mirror, marking the file as successfully synced."""
    mirror_path = get_mirror_path(dataset_dir, file_relative_path)
    mirror_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mirror_path, "w", encoding="utf-8") as f:
        f.write(md5_hash)
