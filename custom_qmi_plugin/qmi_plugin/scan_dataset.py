import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple

import aiofiles
import h5py
from qdlcomms.core.logging import EventKey, get_logger
from qdllib.exceptions import ChecksumException
from qdllib.type_aliases import DictStrAny
from qdllib.utils import get_file_md5sum

logger = get_logger()


def assure_qdl_path(qdl_path: Path) -> None:
    """On Linux/macOS the .qdl directory (relative to the dataset) is hidden by default.

    On Windows this is not working. To hide the directory we set the hidden attribute via os system call.
    """
    if not qdl_path.exists():
        qdl_path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.system(f'attrib +h "{qdl_path}"')
    else:
        if not qdl_path.is_dir():
            log_message = f"QMI-plugin: {qdl_path} is not a directory."
            logger.error(log_message, event_key=EventKey.PLUGIN_SCAN_DATASETS)
            raise ValueError(log_message)


def valid_qmi_date_directory(date_dir: str) -> bool:
    """QMI datastore contains subdirectories for each date.

    The date is formatted as YYYYMMDD. This function checks if the given directory name is valid.
    """
    try:
        datetime.strptime(date_dir, "%Y%m%d")
    except ValueError:
        return False
    return True


def is_valid_tuid(tuid: str) -> bool:
    """Test if tuid is valid. Formatted as YYYYmmDD-HHMMSS-sss-******."""
    if len(tuid) < 26:
        return False
    if tuid[8] != "-" or tuid[15] != "-" or tuid[19] != "-":
        return False
    uid = tuid[20:26]
    if not uid.isalnum():
        return False
    try:
        datetime.strptime(tuid[:19], "%Y%m%d-%H%M%S-%f")
    except ValueError:
        return False
    return True


def find_valid_dataset_folders(data_location: Path) -> List[Path]:
    """
    Scans the data location and returns a list of valid dataset folders.
    A valid dataset folder is a directory under a YYYYMMDD date folder
    that contains a 'dataset.hdf5' file, and whose name passes TUID validation.
    """
    valid_folders: List[Path] = []
    if not data_location.exists() or not data_location.is_dir():
        return valid_folders

    try:
        for date_dir in data_location.iterdir():
            if not date_dir.is_dir() or not valid_qmi_date_directory(date_dir.name):
                continue
            
            for dataset_dir in date_dir.iterdir():
                if not dataset_dir.is_dir():
                    continue
                
                dataset_name = dataset_dir.name
                if not is_valid_tuid(dataset_name[:26]):
                    continue
                    
                if not (dataset_dir / "dataset.hdf5").exists():
                    continue
                
                valid_folders.append(dataset_dir)
    except Exception as e:
        logger.error(f"QMI-plugin: Error scanning datasets: {e}", event_key=EventKey.PLUGIN_SCAN_DATASETS)

    return valid_folders


async def check_md5sum(qmi_file_path: Path, qdl_file: Path) -> Tuple[bool, str | None]:
    """Check if the md5sum of the given dataset file has changed by comparing it against the content of the qdl_file.

    When the md5sum cannot be calculated we handle as if the md5sum is not changed. When md5sum calculation succeeded
    but the content of qdl_file cannot be read we handle this as if md5sum changed.
    """
    md5sum: str | None = None
    try:
        md5sum = await get_file_md5sum(qmi_file_path)
    except ChecksumException as exc:
        # No error handling other than logging.
        logger.error(
            f"QMI-plugin: Datafile checksum calculation failed: {exc}",
            event_key=EventKey.PLUGIN_SCAN_DATASETS,
        )

    md5sum_changed: bool = False
    if qdl_file.exists() and md5sum is not None:
        prev_md5sum: str | None = None
        try:
            async with aiofiles.open(qdl_file, "r") as file:
                prev_md5sum = await file.read()
        except Exception as exc:
            # No error handling other than logging.
            logger.error(
                f"QMI-plugin: Reading checksum failed: {exc}",
                event_key=EventKey.PLUGIN_SCAN_DATASETS,
            )

        md5sum_changed = md5sum != prev_md5sum

    return md5sum_changed, md5sum


def h5py_iterator(file_or_group: h5py.File | h5py.Group, prefix: str = "") -> Any:
    """Iterate over hdf5 file or group and return Group and Dataset objects found recursively.

    A File can contain Groups and Datasets. Group can contain Datasets.

    Returns:
        Generator returning tuples of path and hdf5-Group or Dataset objects.
    """
    for key, item in file_or_group.items():
        path = f"{prefix}/{key}"
        if isinstance(item, h5py.Dataset):
            yield path, item
        elif isinstance(item, h5py.Group):
            yield path, item
            yield from h5py_iterator(item, path)


def get_attribute_values(attributes: DictStrAny, hdf5_file_path: Path) -> None:
    """Get the attributes from a hdf5 file and add the non-empty values to attributes via the inner function
    add_attribute. When more values are added for a key, a list of values is returned, duplicate values are filtered.

    In hdf5, attributes are found in groups and datasets, and at file level.
    https://support.hdfgroup.org/documentation/hdf5/latest/_h5_d_s__u_g.html

    filter_attribute_keys is a static list of predefined hdf5 keywords we don't want to add attributes for.

    The found attributes are added to the attributes parameter (passed by reference), which is a dictionary.
    """
    filter_attribute_keys = [
        "CLASS",
        "NAME",
        "REFERENCE_LIST",
        "SUB_CLASS",
        "DIMENSION_LIST",
        "DIMENSION_LABELLIST",
        "DIMENSION_LABELS",
    ]

    def add_attribute(attributes: DictStrAny, key: str, value: str) -> None:
        """Add attribute key, value pair to the attributes parameter (passed by reference), which is a dictionary.

        When more values are added for a key, a list of values is created. We filter some predefined keys, duplicate
        values, empty values and attributes with too long key/value string length.
        """
        if key not in filter_attribute_keys and len(key) <= 64 and value and len(value) <= 256:
            if key in attributes:
                if isinstance(attributes[key], list):
                    if value not in attributes[key]:
                        attributes[key].append(value)
                elif attributes[key] != value:
                    attributes[key] = [attributes[key], value]
            else:
                attributes[key] = value

    if hdf5_file_path.is_file():
        with h5py.File(hdf5_file_path, "r") as hdf5_file:
            # Top level attributes
            for key, value in hdf5_file.attrs.items():
                add_attribute(attributes, key, str(value))

            # group/dataset attributes
            for _path, group_or_dataset in h5py_iterator(hdf5_file):
                for key, value in group_or_dataset.attrs.items():
                    add_attribute(attributes, key, str(value))


async def scan_dataset(dataset_path: Path, qdl_directory: str = ".qdl") -> Tuple[List[DictStrAny], DictStrAny]:
    """Scan a QMI dataset directory for new files and subdirectories not yet added to QDL.

    The found folder structure is mirrored in folder .qdl in the root of the dataset directory in order to keep track
    of the changes. The .qdl directory is excluded from scanning. Return all files and directories that are found in
    the dataset and not in the .qdl directory. Each file or directory found is returned in files_added including
    some meta information. When a dataset subdirectory or file with suffix .md5 exists in the .qdl directory it was
    already uploaded successfully earlier.

    Returns: Tuple of:
        List of subdirectories (relative to dataset directory) and files not yet mirrored in the .qdl directory.
        Attributes of hdf5 files that are in the added files list.
    """
    files_to_add: List[DictStrAny] = []
    attributes_to_add: DictStrAny = {}
    assure_qdl_path(dataset_path / qdl_directory)

    for root, dataset_subdirectories, files in dataset_path.walk():
        if qdl_directory in dataset_subdirectories:
            dataset_subdirectories.remove(qdl_directory)

        relative_dataset_subpath = root.relative_to(dataset_path)
        qdl_subpath = dataset_path / qdl_directory / relative_dataset_subpath

        # mirror the subdirectory to .qdl directory when it doesn't exist
        if not qdl_subpath.exists():
            qdl_subpath.mkdir(parents=True, exist_ok=True)
            file_to_add = {
                "file_dir": str(root),
                "is_dir": True,
                "qdl_file_dir": str(relative_dataset_subpath),
                "file_size": None,
                "file_checksum": None,
            }
            files_to_add.append(file_to_add)

        # collect the files that should be uploaded from this (sub)directory: file doesn't exist or was changed
        # (md5sum is different).
        for qmi_file in files:
            qmi_file_path = root / qmi_file
            qdl_file = qdl_subpath / (qmi_file + ".md5")

            md5sum_changed, md5sum = await check_md5sum(qmi_file_path, qdl_file)

            if not qdl_file.exists() or md5sum_changed:
                file_to_add = {
                    "file_dir": str(qmi_file_path),
                    "is_dir": False,
                    "qdl_file_dir": str(relative_dataset_subpath / qmi_file),
                    "file_size": qmi_file_path.stat().st_size,
                    "file_checksum": md5sum,
                }
                files_to_add.append(file_to_add)
                if qmi_file_path.suffix == ".hdf5":
                    get_attribute_values(attributes_to_add, qmi_file_path)

    return files_to_add, attributes_to_add


async def mirror_uploaded_files(dataset_path: Path, uploaded_files: List[DictStrAny]) -> None:
    """When a dataset file was uploaded successfully to QDL we create the file in the relative .qdl directory with
    suffix md5 and md5sum of the original file as content."""
    qdl_path = dataset_path / ".qdl"
    for qmi_file_to_add in uploaded_files:
        if not qmi_file_to_add["is_dir"]:
            qdl_file_dir = qmi_file_to_add["qdl_file_dir"]
            qdl_file_path = qdl_path / (qdl_file_dir + ".md5")
            async with aiofiles.open(qdl_file_path, "w") as file:
                await file.write(qmi_file_to_add["file_checksum"])
