"""Module containing the configuration for the meta scheduler client."""

import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, model_validator

import ms_client.data as data


class Config(BaseModel):
    """
    Class containing the client configuration

    Attributes
    ----------
    protocol : str
        The protocol ("http" or "https") to use for the connection (default: "http")
    host : str
        The host of the meta scheduler server
    port : int
    """

    protocol: str = "http"
    host: str
    port: int

    @model_validator(mode="after")
    def validate_attributes(cls, config: Any) -> Any:
        if config.protocol not in ["http", "https"]:
            raise ValueError(
                f'Invalid protocol "{config.protocol}". Must be "http" or "https".'
            )
        return config

    @property
    def endpoint(self: Self) -> str:
        """
        Get the full endpoint URL of the meta scheduler server.

        Returns
        -------
        str
            The full endpoint URL
        """
        return f"{self.protocol}://{self.host}:{self.port}"

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
        config = cls.model_validate(values)
        return config
