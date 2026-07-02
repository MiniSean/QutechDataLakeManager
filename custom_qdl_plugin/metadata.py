from pathlib import Path
from typing import Dict, Any, List

def extract_metadata(dataset_dir: Path) -> Dict[str, Any]:
    """
    Extracts metadata from the dataset directory structure.
    - Extracts TUID and experiment name from the dataset directory name.
    - Extracts labels from 'analysis_<Name>' subdirectories.
    """
    metadata: Dict[str, Any] = {}
    
    # Extract TUID from dataset directory name (format: <TUID>_<experiment_name>)
    dir_name = dataset_dir.name
    parts = dir_name.split('_', 1)
    if len(parts) > 1:
        metadata["TUID"] = parts[0]
        metadata["experiment_name"] = parts[1]
    else:
        # Fallback if no underscore is found
        metadata["TUID"] = dir_name
    
    # Extract labels from analysis_ folders
    labels: List[str] = []
    try:
        for item in dataset_dir.iterdir():
            if item.is_dir() and item.name.startswith("analysis_"):
                label_name = item.name[len("analysis_"):]
                if label_name:
                    labels.append(label_name)
    except OSError:
        # Ignore errors if directory is inaccessible
        pass
        
    if labels:
        metadata["labels"] = labels
        
    return metadata
