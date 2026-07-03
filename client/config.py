import json
from pathlib import Path
from typing import Any, MutableMapping, Optional

CONFIG_PATH: Path = Path.home() / ".qdl" / "client_config.json"

class ClientConfig:
    # region Class Properties
    @property
    def data_dir(self) -> str:
        return self._config_data.get("data_dir", "D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/")

    @data_dir.setter
    def data_dir(self, value: str) -> None:
        self._config_data["data_dir"] = value

    @property
    def scope(self) -> str:
        return self._config_data.get("scope", "dicarlo-testing")

    @scope.setter
    def scope(self, value: str) -> None:
        self._config_data["scope"] = value

    @property
    def setup(self) -> str:
        return self._config_data.get("setup", "dicarlo")

    @setup.setter
    def setup(self, value: str) -> None:
        self._config_data["setup"] = value

    @property
    def device(self) -> str:
        return self._config_data.get("device", "testing")

    @device.setter
    def device(self, value: str) -> None:
        self._config_data["device"] = value

    @property
    def qdl_bin_dir(self) -> Optional[str]:
        return self._config_data.get("qdl_bin_dir")

    @qdl_bin_dir.setter
    def qdl_bin_dir(self, value: str) -> None:
        self._config_data["qdl_bin_dir"] = value
    # endregion

    # region Class Constructor
    def __init__(self, config_data: MutableMapping[str, Any]) -> None:
        self._config_data: MutableMapping[str, Any] = config_data
    # endregion

    # region Class Methods
    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._config_data, f, indent=2)
    # endregion

    # region Static Class Methods
    @staticmethod
    def load() -> "ClientConfig":
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    return ClientConfig(json.load(f))
            except json.JSONDecodeError:
                pass
        return ClientConfig({})
    # endregion
