#%%
from qdl import create_token, configure

api_token = create_token("my_token")
configure(api_token=api_token)
print(api_token)

#%%
from qdl import Scope, Dataset

scope = "dicarlo-testing"
name = "test_dataset"

# double check if the scope exists
Scope.get(scope)

# create the dataset
dataset = Dataset(scope_uid=scope, name=name)
dataset.rank = 2
dataset.create()

print(dataset)

#%%
print(dataset.uid)

#%%
uid = dataset.uid
dataset = Dataset.get(scope_uid=scope, uid=uid)
dataset.rank = 3

dataset.update()

#%%
from quantify_core.data.handling import set_datadir, locate_experiment_container, TUID, DATASET_NAME
from pathlib import Path

set_datadir(r"E:\OverflowPHDData")
filepath: Path = Path(locate_experiment_container(tuid=TUID("20260625-130323-271-43db95"))) / DATASET_NAME
print(filepath)

#%%
uid = dataset.uid
dataset = Dataset.get(scope_uid=scope, uid=uid)
# add a file to the root directory of the dataset
dataset.add_file(str(filepath))
dataset.upload()

#%%
from qdl import Collection, Dataset

scope_uid = "dicarlo-testing"
collection_uid = "memory_experiments"
dataset_uid = dataset.uid

collection = Collection(scope_uid=scope_uid, name=collection_uid)
collection.create()

dataset = Dataset.get(scope_uid=scope_uid, uid=dataset_uid)
dataset.add_collection(collection.uid)

dataset.update()

#%%
from qdl import Dataset

scope = "dicarlo-testing"
collection = "memory_experiments"

datasets = Dataset.list(scope_uid=scope, collection_name=[])
print(datasets)

#%%
from qdl import Dataset

scope = "dicarlo-testing"
datasets = Dataset.list(scope_uid=scope, collection_name=[])
print(len(datasets))
# for _dataset in datasets:
#     print(_dataset.to_dict())
#     # print(_dataset.__dict__)

#%%
import os
import sys
import datetime
from dateutil.parser import parse
from quantify_core.data.types import TUID as TUID_
from quantify_core.data.handling import set_datadir, get_datadir
from pathlib import Path

class TUID(TUID_):

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

def get_tuids_containing(
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
    datadir = get_datadir()
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
        expdirs = list(
            filter(
                lambda x: (
                    len(x) > 25
                    and (contains in x)  # label is part of exp_name
                    and TUID.is_valid(x[:26])  # tuid is valid
                    and (t_start <= TUID.datetime_seconds(x) < t_stop)
                ),
                os.listdir(os.path.join(datadir, daydir)),
            ),
        )
        expdirs.sort(reverse=reverse)
        for expname in expdirs:
            # Check for inconsistent folder structure for datasets portability
            if daydir != expname[:8]:
                raise FileNotFoundError(
                    f"Experiment container '{expname}' is in wrong day directory "
                    f"'{daydir}'",
                )
            tuids.append(TUID(expname[:26]))
            if len(tuids) == max_results:
                return tuids
    if len(tuids) == 0:
        raise FileNotFoundError(f"No experiment found containing '{contains}'")
    return tuids


set_datadir(Path(r"E:\OverflowPHDData"))
all_tuids = get_tuids_containing()
print(len(all_tuids))