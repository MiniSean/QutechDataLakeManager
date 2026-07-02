import datetime
from typing import Dict, Any, Sequence
import qdl
from .strategy_tuid_extraction import DateExtractionStrategy

def get_datasets_per_day(scope_uid: str, strategy: DateExtractionStrategy) -> Dict[datetime.date, int]:
    """Fetches datasets from the QDL SDK and groups them by date using the provided strategy."""
    counts: Dict[datetime.date, int] = {}
    
    try:
        # Using the QDL SDK to get datasets
        datasets: Sequence[qdl.Dataset] = qdl.Dataset.list(scope_uid=scope_uid, collection_name=[])
        for dataset in datasets:
            # We assume qdl.Dataset has a to_dict method or we can extract the 'name' attribute
            dataset_dict: Dict[str, Any] = dataset.to_dict() if hasattr(dataset, "to_dict") else dataset.__dict__
            date_val: datetime.date | None = strategy.extract_date(dataset_dict)
            if date_val:
                counts[date_val] = counts.get(date_val, 0) + 1
    except Exception as e:
        # Depending on the error strategy, we might log it or ignore
        pass
        
    return counts
