from pathlib import Path
from typing import Dict, Any, List

import state
import metadata

def scan_datasets(data_location: Path, scope_uid: str) -> List[Dict[str, Any]]:
    """
    Scans the data location for new or updated datasets and files.
    Returns a list of dictionaries containing the payload data for DataFileReadyRequest.
    """
    datasets_ready = []
    
    if not data_location.exists() or not data_location.is_dir():
        return datasets_ready
        
    # Iterate over YYYYMMDD date folders
    for date_dir in data_location.iterdir():
        if not date_dir.is_dir() or len(date_dir.name) != 8 or not date_dir.name.isdigit():
            continue
            
        # Iterate over <TUID>_<experiment> dataset folders
        for dataset_dir in date_dir.iterdir():
            if not dataset_dir.is_dir():
                continue
                
            # A dataset is ready if it contains dataset.hdf5
            if not (dataset_dir / "dataset.hdf5").exists():
                continue
                
            dataset_name = dataset_dir.name
            dataset_files = []
            
            # Walk through all items in the dataset directory
            for item in dataset_dir.rglob("*"):
                # Skip the .qdl state directory
                if ".qdl" in item.parts:
                    continue
                    
                if item.is_file():
                    current_md5 = state.get_md5(item)
                    rel_path = item.relative_to(dataset_dir).as_posix()
                    if state.has_changed(dataset_dir, rel_path, current_md5):
                        dataset_files.append({
                            "file_dir": item.resolve().as_posix(),
                            "is_dir": False,
                            "qdl_file_dir": rel_path,
                            "file_size": str(item.stat().st_size),
                            "file_checksum": current_md5,
                            "item_path": item # Internal use, excluded from final payload if needed
                        })
                elif item.is_dir():
                    current_md5 = "dir"
                    rel_path = item.relative_to(dataset_dir).as_posix()
                    if state.has_changed(dataset_dir, rel_path, current_md5):
                        dataset_files.append({
                            "file_dir": item.resolve().as_posix(),
                            "is_dir": True,
                            "qdl_file_dir": rel_path,
                            "file_size": "0",
                            "file_checksum": current_md5,
                            "item_path": item # Internal use
                        })
                        
            if dataset_files:
                meta = metadata.extract_metadata(dataset_dir)
                datasets_ready.append({
                    "scope_uid": scope_uid,
                    "dataset_name": dataset_name,
                    "dataset_files": dataset_files,
                    "metadata": meta,
                    "extra_fields": {},
                    "dataset_dir": dataset_dir # Internal use
                })
                
    return datasets_ready
