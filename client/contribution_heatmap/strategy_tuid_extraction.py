from abc import ABC, abstractmethod
import datetime
import re
from typing import Mapping, Any, Optional

class DateExtractionStrategy(ABC):
    # region Interface Methods
    @abstractmethod
    def extract_date(self, dataset: Mapping[str, Any]) -> Optional[datetime.date]:
        """Extracts a date from the dataset dictionary."""
        pass
    # endregion

class QdlDatasetNameDateExtraction(DateExtractionStrategy):
    # region Class Specific Properties
    _date_regex = re.compile(r"^(\d{8})-\d{6}")
    # endregion
    
    # region Interface Methods
    def extract_date(self, dataset: Mapping[str, Any]) -> Optional[datetime.date]:
        name: str = dataset.get("name", "")
        if not name:
            return None
            
        match = self._date_regex.match(name)
        if match:
            date_str: str = match.group(1)
            try:
                return datetime.datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                return None
        return None
    # endregion
