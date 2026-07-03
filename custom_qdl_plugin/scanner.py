from pathlib import Path
from typing import Dict, Any, List

import state
import metadata

def find_valid_dataset_folders(data_location: Path) -> List[Path]:
    """
    Scans the data location and returns a list of valid dataset folders.
    A valid dataset folder is a directory under a YYYYMMDD date folder
    that contains a 'dataset.hdf5' file.
    """
    valid_folders = []

    if not data_location.exists() or not data_location.is_dir():
        return valid_folders

    try:
        for date_dir in data_location.iterdir():
            try:
                if not date_dir.is_dir() or len(date_dir.name) != 8 or not date_dir.name.isdigit():
                    continue

                for dataset_dir in date_dir.iterdir():
                    try:
                        if not dataset_dir.is_dir():
                            continue

                        if not (dataset_dir / "dataset.hdf5").exists():
                            continue
                        
                        valid_folders.append(dataset_dir)
                    except Exception as ds_err:
                        print(f"Skipping dataset {dataset_dir} due to error: {ds_err}")
            except Exception as date_err:
                print(f"Skipping date dir {date_dir} due to error: {date_err}")
    except Exception as loc_err:
        print(f"Error accessing data location {data_location}: {loc_err}")

    return valid_folders

def scan_datasets(data_location: Path, scope_uid: str) -> List[Dict[str, Any]]:
    """
    Scans the data location for new or updated datasets and files.
    Returns a list of dictionaries containing the payload data for DataFileReadyRequest.
    """
    datasets_ready = []

    valid_folders = find_valid_dataset_folders(data_location)

    for dataset_dir in valid_folders:
        try:
            dataset_name = dataset_dir.name
            dataset_files = []

            # Walk through all items in the dataset directory
            for item in dataset_dir.rglob("*"):
                # Skip the .qdl state directory
                if ".qdl" in item.parts:
                    continue

                try:
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
                except Exception as file_err:
                    print(f"Skipping {item} due to error: {file_err}")

            if dataset_files:
                try:
                    meta = metadata.extract_metadata(dataset_dir)
                    datasets_ready.append({
                        "scope_uid": scope_uid,
                        "dataset_name": dataset_name,
                        "dataset_files": dataset_files,
                        "metadata": meta,
                        "extra_fields": {},
                        "dataset_dir": dataset_dir # Internal use
                    })
                except Exception as meta_err:
                    print(f"Skipping metadata extraction for {dataset_dir} due to error: {meta_err}")
        except Exception as ds_err:
            print(f"Skipping dataset {dataset_dir} due to error: {ds_err}")

    return datasets_ready

