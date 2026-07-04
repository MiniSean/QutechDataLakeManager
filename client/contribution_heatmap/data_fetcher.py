from __future__ import annotations
import os
import sys
import datetime
from dateutil.parser import parse
from pathlib import Path
from typing import Dict, Any, Sequence, Mapping, Iterable, Type, cast
import qdl
from client.contribution_heatmap.strategy_tuid_extraction import DateExtractionStrategy


py_311_plus = sys.version_info >= (3, 11)


class TUID(str):
    """
    A human readable unique identifier based on the timestamp.
    This class does not wrap the passed in object but simply verifies and returns it.

    A tuid is a string formatted as ``YYYYmmDD-HHMMSS-sss-******``.
    The tuid serves as a unique identifier for experiments in quantify.

    .. seealso:: The. :mod:`~quantify_core.data.handling` module.
    """

    __slots__ = ()  # avoid unnecessary overheads

    def __new__(cls: Type[TUID], value: str) -> TUID:
        assert cls.is_valid(value)
        # NB instead of creating an instance of this class we just return the object
        # This avoids nasty type conversion issues when saving a dataset using the
        # `h5netcdf` engine (which we need to support complex numbers)
        return cast("TUID", value)

    @classmethod
    def datetime(cls, tuid: str) -> datetime.datetime:
        """
        Returns
        -------
        :class:`~python:datetime.datetime`
            object corresponding to the TUID
        """
        if py_311_plus:
            return datetime.datetime.fromisoformat(tuid[:15]) + datetime.timedelta(
                milliseconds=int(tuid[16:19])
            )
        return datetime.datetime.strptime(tuid[:19], "%Y%m%d-%H%M%S-%f")

    @classmethod
    def datetime_seconds(cls, tuid: str) -> datetime.datetime:
        """
        Returns
        -------
        :class:`~python:datetime.datetime`
            object corresponding to the TUID with microseconds discarded
        """
        if py_311_plus:
            return datetime.datetime.fromisoformat(tuid[:15])
        return datetime.datetime.strptime(tuid[:15], "%Y%m%d-%H%M%S")

    @classmethod
    def uuid(cls, tuid: str) -> str:
        """
        Returns
        -------
        str
            the uuid (universally unique identifier) component of the TUID,
            corresponding to the last 6 characters.
        """
        return tuid[20:]

    # region Class Methods
    @classmethod
    def is_valid(cls, tuid: str) -> bool:
        """
        Test if tuid is valid.
        A valid tuid is a string formatted as ``YYYYmmDD-HHMMSS-sss-******``.

        Parameters
        ----------
        tuid : str
            a tuid string

        Returns
        -------
        bool
            True if the string is a valid TUID.

        Raises
        ------
        ValueError
            Invalid format
        """
        try:
            cls.datetime(tuid)  # verify date format
        except ValueError:
            return False

        uid = cls.uuid(tuid)

        if len(uid) != 6:
            raise ValueError(
                f"Invalid format: uid has invalid length {len(uid)} (should be 6)."
            )
        if not uid.isalnum():
            raise ValueError("Invalid format: uid is not alphanumeric.")

        if tuid[8] != "-" or tuid[15] != "-" or tuid[19] != "-":
            raise ValueError(
                "Invalid TUID format: seperator at positions 8, 15 and 19 should be '-'."
            )

        return True
    # endregion

def extract_and_filter_tuids(
    names: Iterable[str],
    contains: str = "",
    t_start: datetime.datetime | None = None,
    t_stop: datetime.datetime | None = None,
) -> Dict[TUID, str]:
    """Filters a list of names for valid TUIDs that match the given criteria.

    Parameters
    ----------
    names
        An iterable of file or directory names.
    contains
        A string that must be contained in the name.
    t_start
        datetime to search from, inclusive.
    t_stop
        datetime to search until, exclusive.

    Returns
    -------
    Mapping[TUID, str]
        A dictionary mapping the valid TUID object to the corresponding name.
    """
    if t_start is None:
        t_start = datetime.datetime(1, 1, 1)
    if t_stop is None:
        t_stop = datetime.datetime.now()

    result: Dict[TUID, str] = {}
    for name in names:
        if (
            len(name) > 25
            and (contains in name)
            and TUID.is_valid(name[:26])
        ):
            try:
                t = TUID.datetime_seconds(name[:26])
                if t_start <= t < t_stop:
                    result[TUID(name[:26])] = name
            except Exception:
                pass
    return result


def get_tuids_containing(
    data_location: Path,
    contains: str = "",
    t_start: datetime.datetime | str | None = None,
    t_stop: datetime.datetime | str | None = None,
    max_results: int = sys.maxsize,
    reverse: bool = False,
) -> list[TUID]:
    """Returns a list of tuids containing a specific label.

    .. tip::

        If one is only interested in the most recent
        :class:`~quantify_core.data.types.TUID`, :func:`~get_latest_tuid` is preferred
        for performance reasons.

    Parameters
    ----------
    data_location
        A Path pointing at data directory to be scanned.
    contains
        A string contained in the experiment name.
    t_start
        datetime to search from, inclusive. If a string is specified, it will be
        converted to a datetime object using :obj:`~dateutil.parser.parse`.
        If no value is specified, will use the year 1 as a reference t_start.
    t_stop
        datetime to search until, exclusive. If a string is specified, it will be
        converted to a datetime object using :obj:`~dateutil.parser.parse`.
        If no value is specified, will use the current time as a reference t_stop.
    max_results
        Maximum number of results to return. Defaults to unlimited.
    reverse
        If False, sorts tuids chronologically, if True sorts by most recent.

    Returns
    -------
    list
        A list of :class:`~quantify_core.data.types.TUID`: objects.

    Raises
    ------
    FileNotFoundError
        No data found.
    """
    datadir = data_location
    if isinstance(t_start, str):
        t_start = parse(t_start)
    elif t_start is None:
        t_start = datetime.datetime(1, 1, 1)
    if isinstance(t_stop, str):
        t_stop = parse(t_stop)
    elif t_stop is None:
        t_stop = datetime.datetime.now()

    # date range filters, define here to make the next line more readable
    d_start = t_start.strftime("%Y%m%d")
    d_stop = t_stop.strftime("%Y%m%d")

    def lower_bound(dir_name: str) -> bool:
        return dir_name >= d_start if d_start else True

    def upper_bound(dir_name: str) -> bool:
        return dir_name <= d_stop if d_stop else True

    daydirs = list(
        filter(
            lambda x: (
                x.isdigit() and len(x) == 8 and lower_bound(x) and upper_bound(x)
            ),
            os.listdir(datadir),
        ),
    )
    daydirs.sort(reverse=reverse)
    if len(daydirs) == 0:
        err_msg = f"There are no valid day directories in the data folder '{datadir}'"
        if t_start or t_stop:
            err_msg += f", for the range {t_start or ''} to {t_stop or ''}"
        raise FileNotFoundError(err_msg)

    tuids = []
    for daydir in daydirs:
        day_items = os.listdir(os.path.join(datadir, daydir))
        filtered_tuids_dict = extract_and_filter_tuids(
            names=day_items,
            contains=contains,
            t_start=t_start,
            t_stop=t_stop
        )
        
        # Sort items based on the experiment name
        sorted_items = sorted(filtered_tuids_dict.items(), key=lambda item: item[1], reverse=reverse)
        for tuid, expname in sorted_items:
            # Check for inconsistent folder structure for datasets portability
            if daydir != expname[:8]:
                raise FileNotFoundError(
                    f"Experiment container '{expname}' is in wrong day directory "
                    f"'{daydir}'",
                )
            tuids.append(tuid)
            if len(tuids) == max_results:
                return tuids
    if len(tuids) == 0:
        raise FileNotFoundError(f"No experiment found containing '{contains}'")
    return tuids


def parse_tuids_to_heatmap_data(tuids: Sequence[TUID | str]) -> Dict[datetime.date, int]:
    """Parses a sequence of TUIDs into a dataset count per day for the contribution heatmap.

    Parameters
    ----------
    tuids
        A sequence of TUID objects or valid TUID strings.

    Returns
    -------
    Dict[datetime.date, int]
        A dictionary mapping dates to the number of datasets (TUIDs) on that day.
    """
    counts: Dict[datetime.date, int] = {}
    for tuid in tuids:
        tuid_str: str = str(tuid)
        if len(tuid_str) >= 8:
            try:
                date_val: datetime.date = datetime.datetime.strptime(tuid_str[:8], "%Y%m%d").date()
                counts[date_val] = counts.get(date_val, 0) + 1
            except ValueError:
                pass
    return counts


def get_datasets_per_day(scope_uid: str, strategy: DateExtractionStrategy) -> Dict[datetime.date, int]:
    """Fetches datasets from the QDL SDK and groups them by date using the provided strategy."""

    datasets: Sequence[qdl.Dataset] = qdl.Dataset.list(scope_uid=scope_uid, collection_name=[])
    dataset_names: List[str] = [dataset.name for dataset in datasets]
    valid_tuid_to_names: Dict[TUID, str] = extract_and_filter_tuids(names=dataset_names)
    counts: Dict[datetime.date, int] = parse_tuids_to_heatmap_data(list(valid_tuid_to_names.values()))
    return counts


if __name__ == '__main__':
    from typing import List
    from client.contribution_heatmap.strategy_tuid_extraction import DateExtractionStrategy

    data_path = Path(r"E:\OverflowPHDData")
    all_tuids = get_tuids_containing(data_path)
    date_map_available: Dict[datetime.date, int] = parse_tuids_to_heatmap_data(all_tuids)
    print(len(all_tuids))
    print(len(date_map_available))

    datasets: Sequence[qdl.Dataset] = qdl.Dataset.list(scope_uid="dicarlo-testing", collection_name=[])
    datasets = list(datasets)
    dataset_names: List[str] = [dataset.name for dataset in datasets]
    valid_tuid_to_names: Dict[TUID, str] = extract_and_filter_tuids(names=dataset_names)
    date_map_detected: Dict[datetime.date, int] = parse_tuids_to_heatmap_data(list(valid_tuid_to_names.values()))
    print(len(datasets))
    print(len(valid_tuid_to_names))
    print(len(date_map_detected))