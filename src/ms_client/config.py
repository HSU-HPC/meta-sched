"""Module containing the configuration for the Meta Scheduler client."""

import tomllib
from pathlib import Path
from typing import Any, List, Self, Tuple

from pydantic import BaseModel, model_validator

import ms_client.data as data


class TargetAdditionalConfigs(BaseModel):
    """
    Class containing additional user configurations for a target from the Meta Scheduler server.

    Attributes
    ----------
    id : str
        The target ID
    tags : Tuple[str, ...]
        Additional user defined tags to filter this target by
    """

    id: str
    tags: Tuple[str, ...] = ()


class Config(BaseModel):
    """
    Class containing the client configuration

    Attributes
    ----------
    protocol : str
        The protocol ("http" or "https") to use for the connection (default: "http")
    host : str
        The host of the Meta Scheduler server
    port : int
    targets: List[_TargetAdditionalConfigs]
        Additional user configurations for targets from the Meta Scheduler server
    """

    protocol: str = "http"
    host: str
    port: int

    targets: List[TargetAdditionalConfigs]

    @model_validator(mode="after")
    def validate_attributes(cls, config: Any) -> Any:
        """
        Validates an adjusts (!) client config attributes. (Is idempotent.)

        Parameters
        ----------
        config : Any
            The client config to validate and update

        Returns
        -------
        Any
            The validated and updated client config
        """
        if config.protocol not in ["http", "https"]:
            raise ValueError(
                f'Invalid protocol "{config.protocol}". Must be "http" or "https".'
            )
        return config

    @property
    def endpoint(self: Self) -> str:
        """
        Get the full endpoint URL of the Meta Scheduler server.

        Returns
        -------
        str
            The full endpoint URL
        """
        return f"{self.protocol}://{self.host}:{self.port}"

    @classmethod
    def load(cls, raise_on_missing: bool = False) -> Self:
        """
        Load and validate the client configuration.

        Parameter
        ---------
        raise_on_missing : bool
            If true, an error will be raised if the file had to be created.

        Returns
        -------
        Self
            The loaded configuration
        """
        config_path = Path.home() / ".config" / "meta-sched.toml"
        if not config_path.is_file():
            # Write default config to path
            config_path.write_text(data.get_default_config_path().read_text())
            if raise_on_missing:
                raise FileNotFoundError(
                    f'No config file found. (Default was created at "{config_path}", please repeat!)'
                )
        values = tomllib.loads(config_path.read_text())
        config = cls.model_validate(values)
        return config
