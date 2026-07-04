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
print(datasets[0])
print(len(datasets))
# for _dataset in datasets:
#     print(_dataset.to_dict())
#     # print(_dataset.__dict__)