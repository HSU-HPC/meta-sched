import tomllib
from pathlib import Path
from typing import Self

import ms_client.data as data


class Config:
    """
    Class containing the client configuration
    """

    def __init__(self: Self) -> None:
        """
        Config objects can NOT be created using the constructor.
        (Use Config.load() instead to load the default/current user config!)
        """
        # "Declare" properties of the class
        self.endpoint = ""
        raise RuntimeError(f"Cannot instantiate {self.__class__.__name__} directly.")

    class Error(RuntimeError):
        """
        Class for representing errors during parsing of the configuration.
        """

        pass

    @classmethod
    def load(cls) -> Self:
        """
        Load and validate the client configuration.

        Returns
        -------
        Self
            The loaded configuration
        """
        config_path = Path.home() / ".config" / "meta-sched.toml"
        if not config_path.is_file():
            # Write default config to path
            config_path.write_text(data.get_default_config_path().read_text())
        values = tomllib.loads(config_path.read_text())

        config = super().__new__(cls)
        if "host" not in values or not isinstance(values["host"], str):
            raise Config.Error('Config file must contain key "host" (string)')
        if "port" in values and not isinstance(values["port"], int):
            raise Config.Error('Config file key "port" must be an integer')
        protocols = ["http", "https"]
        if values.get("protocol", protocols[0]) not in protocols:
            protocols_fmtd = " or ".join([f'"{s}"' for s in protocols])
            raise Config.Error(
                f'Value of config file key "protocol" must be {protocols_fmtd}'
            )
        config.endpoint = f"{values.get('protocol', 'http')}://{values['host']}:{values.get('port', 80)}"

        return config
