"""Module containing the configuration for the Meta Scheduler client."""

from pathlib import Path
from typing import Any, List, Optional, Tuple

import tomli
from pydantic import BaseModel, Field, model_validator

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
    datacenter_api_endpoint : Optional[str]
        HTTP endpoint for the datacenter API of this target
        (Used to fetch additional data about the state of the target)
    datacenter_api_forecast_source_id : Optional[int]
        The ID of the forecast source to use at the datacenter API for this target
    """

    id: str
    tags: Tuple[str, ...] = ()
    datacenter_api_endpoint: Optional[str] = None
    datacenter_api_forecast_source_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_attributes(cls, config: Any) -> Any:
        """
        Validates additional target config attributes.

        Parameters
        ----------
        config : Any
            The additional target config to validate

        Returns
        -------
        Any
            The validated additional target config
        """
        if (
            config.datacenter_api_endpoint is None
            and config.datacenter_api_tenant_id is not None
        ) or (
            config.datacenter_api_endpoint is not None
            and config.datacenter_api_tenant_id is None
        ):
            raise ValueError(
                'Either all or no fields with the prefix "data_center_api_" must be given. (Suffixes: endpoint, tenant_id)'
            )
        return config


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

    targets: List[TargetAdditionalConfigs] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_attributes(cls, config: Any) -> Any:
        """
        Validates and adjusts (!) client config attributes. (Is idempotent.)

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
    def endpoint(self: "Config") -> str:
        """
        Get the full endpoint URL of the Meta Scheduler server.

        Returns
        -------
        str
            The full endpoint URL
        """
        return f"{self.protocol}://{self.host}:{self.port}"

    @classmethod
    def load(cls, raise_on_missing: bool = False) -> "Config":
        """
        Load and validate the client configuration.

        Parameter
        ---------
        raise_on_missing : bool
            If true, an error will be raised if the file had to be created.

        Returns
        -------
        Config
            The loaded configuration
        """
        config_path = Path.home() / ".config" / "meta-sched.toml"
        if not config_path.is_file():
            # Write default config to path
            config_path.parent.mkdir(exist_ok=True, parents=True)
            config_path.write_text(data.get_default_config_path().read_text())
            if raise_on_missing:
                raise FileNotFoundError(
                    f'No config file found. (Default was created at "{config_path}", please repeat!)'
                )
        values = tomli.loads(config_path.read_text())
        config = cls.model_validate(values)
        return config
