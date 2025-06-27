"""Module for parsing config files."""

import importlib
import importlib.util
import tomllib
import uuid
from os import PathLike
from pathlib import Path
from typing import Any, List, Self, Tuple, Type

from ms_common.target import Target

from ms_server.scheduling import Policy


# TODO refactor to use pydantic BaseModel for parsing and validation
class Config:
    """Class holding the configuration for the meta scheduler."""

    def __init__(
        self: Self,
        host: str,
        port: int,
        scheduler_class: Type[Policy],
        targets: List[Target],
    ) -> None:
        """
        Create a new instance of the meta scheduler configuration.

        Parameters
        ----------
        host : The host of the API
        port : The port of the API
        scheduler_class : Type[Scheduler]
            The scheduling policy to be applied
        targets : List[Target]
            All targets available to execute jobs
        """
        self.__host = host
        self.__port = port
        self.__scheduler_class = scheduler_class
        self.__targets = targets

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
    def endpoint(self: Self) -> Tuple[str, int]:
        """
        Get the endpoint consisting of host and port for the API.

        Returns
        -------
        Tuple[str, int]
            The host and port for the API
        """
        return self.__host, self.__port

    @property
    def targets(self: Self) -> List[Target]:
        """
        Get all targets which jobs may be assigned to.

        Returns
        -------
        List[Target]
            The list of all targets which jobs may be assigned to
        """
        return self.__targets

    @property
    def scheduler_class(self: Self) -> Type[Policy]:
        """
        Get the scheduling policy to be applied.

        Returns
        -------
        Type[Scheduler]
            The type of scheduling policy to be applied
        """
        return self.__scheduler_class

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
        return cls.parse(Path(path).read_text())

    @classmethod
    def parse(cls, config_str: str) -> Self:
        """
        Parse the raw contents of a configuration file.

        Parameters
        ----------
        config_str : str
            The raw contents of the configuration file

        Returns
        -------
        Self
            The parsed configuration
        """
        config = tomllib.loads(config_str)

        def require_config(
            config: Any,
            path: List[str | None],
            value_type: Any = None,
            options: List[Any] = [],
            path_str: str = "<root>",
        ) -> None:
            """
            Assert that a certain configuration value is present in the configuration.

            Parameters
            ----------
            config : Any
                The current configuration
            path : List[str | None]
                Property path of the configuration value in the configuration
            value_type : Any
                Expected type of the configuration value, but if None (default) the no type is enforced
            options : List[Any]
                Possible values for the configuration value, but if empty (default) any value is allowed
            path_str : str
                Property path for debugging purposes (<root> by default)

            Raises
            ------
            ValueError
                The error encountered when trying to verify the specified configuration value
            """
            if len(path) == 0:
                if value_type and not isinstance(config, value_type):
                    raise ValueError(
                        f'Required config "{path_str} must be of type {value_type.__qualname__}"'
                    )
                if len(options) > 0 and config not in options:
                    raise ValueError(
                        f'Required config "{path_str} can only have these values: {options}"'
                    )
            else:
                keys: Any = path[:1]
                if isinstance(config, dict):
                    keys = config.keys() if keys[0] is None else keys
                elif isinstance(config, list):
                    keys = range(len(config)) if keys[0] is None else keys
                else:
                    raise ValueError(f'Required dict/list config "{path_str}"')
                for k in keys:
                    path_str = f"{path_str}/{k}"
                    try:
                        value = config[k]
                    except Exception:
                        raise ValueError(f'Required config "{path_str}"')
                    require_config(value, path[1:], value_type, options, path_str)

        require_config(config, ["host"], str)
        require_config(config, ["port"], int)

        require_config(config, ["scheduler_class"], str)
        scheduler_class = Policy

        module_filename, class_name = config["scheduler_class"].split(":")
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
                f'"{config["scheduler_class"]}" is not a subclass of "{Policy.__class__.__qualname__}"'
            )

        require_config(config, ["targets", None, "id"], str)
        for i in range(len(config["targets"])):
            id = config["targets"][i]["id"]
            try:
                uuid.UUID(id)
            except ValueError:
                raise ValueError(f'Target id must be a valid UUID ("{id}" is not)')
            if id in [t["id"] for t in config["targets"][i + 1 :]]:
                raise ValueError(
                    f"Targets must have unique ids, but found multiple occurances of {id}"
                )
        require_config(config, ["targets", None, "host"], str)
        require_config(
            config, ["targets", None, "batch_system"], str, ["slurm", "pbs", "none"]
        )
        targets = [Target.model_validate(o) for o in config["targets"]]

        return cls(
            config["host"],
            config["port"],
            scheduler_class,
            targets,
        )
