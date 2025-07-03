"""Module for parsing config files."""

import importlib
import importlib.util
import tomllib
from os import PathLike
from pathlib import Path
from typing import Any, List, Optional, Self, Type

from ms_common.schemas import Target
from pydantic import BaseModel, model_validator

from ms_server.scheduling import Policy


class Config(BaseModel):
    """
    Class holding the configuration for the Meta Scheduler.

    Attributes
    ----------
    host : str
        The host of the API
    port : int
        The port of the API
    db_url : str
        The connection URL to the Postgres/SQLite database
    scheduler_class : Optional[Type[Policy]]
        The scheduling policy to be applied
    scheduling_loop_interval : float
        The interval period between applying the scheduling policy in seconds
    targets : List[Target]
        All targets available to execute jobs
    """

    host: str
    port: int
    db_url: str
    scheduler_class_name: str
    _scheduler_class: Optional[Type[Policy]] = None
    scheduling_loop_interval: float
    targets: List[Target]

    @classmethod
    def get_config_path(cls) -> Path:
        """
        Get the path to the config file.

        Returns
        -------
        Path
            The absolute path to the config file
        """
        return Path("/") / "etc" / "meta-sched.toml"

    @classmethod
    def get_default_config_path(cls) -> Path:
        """
        Get the path to the default config file.

        Returns
        -------
        Path
            The absolute path to the default config file
        """
        return (Path(__file__).parent / "example.toml").absolute()

    @property
    def scheduler_class(self: Self) -> Type[Policy]:
        """
        Get the scheduling policy to be applied.

        Returns
        -------
        Type[Policy]
            The type of scheduling policy to be applied
        """
        assert self._scheduler_class is not None
        return self._scheduler_class

    @classmethod
    def load(cls, path: str | PathLike[Any]) -> Self:
        """
        Load a configuration from a file.

        Parameters
        ----------
        path : str | PathLike[Any]
            The path to the file containing the configuration

        Returns
        -------
        Self
            The loaded configuration
        """
        values = tomllib.loads(Path(path).read_text())
        return cls.model_validate(values)

    @model_validator(mode="after")
    def validate_attributes(cls, config: Any) -> Any:
        """
        Validates an adjusts (!) server config attributes. (Is idempotent.)

        Parameters
        ----------
        config : Any
            The server config to validate and update

        Returns
        -------
        Any
            The validated and updated server config
        """
        db_url_prefixes = ["sqlite://", "postgresql://"]
        if all(not config.db_url.startswith(p) for p in db_url_prefixes):
            raise ValueError(
                f"Database URL must have one of the following prefixes: {', '.join(db_url_prefixes)}"
            )
        module_filename, class_name = config.scheduler_class_name.split(":")
        try:
            base_path = Path(__file__).parent.parent / "scheduling"
            module_path = (
                Path(module_filename)
                if module_filename.startswith("/")
                else base_path / module_filename
            )
            spec = importlib.util.spec_from_file_location(
                "__scheduling." + module_path.stem, module_path
            )
            assert spec is not None
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            scheduler_class = getattr(module, class_name)
        except (ModuleNotFoundError, AttributeError, AssertionError):
            raise ValueError(f'Could not load scheduler "{config["scheduler_class"]}"')
        if not issubclass(scheduler_class, Policy):
            raise ValueError(
                f'"{config.scheduler_class_name}" is not a subclass of "{Policy.__class__.__qualname__}"'
            )
        config._scheduler_class = scheduler_class
        return config
