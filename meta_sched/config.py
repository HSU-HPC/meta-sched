import importlib
import tomllib
import uuid
from os import PathLike
from pathlib import Path
from typing import Any, List, Self, Type

from meta_sched.scheduler.base import Scheduler
from meta_sched.submit.target import Target


class Config:
    def __init__(
        self: Self,
        scheduler_class: Type[Scheduler],
        counter_file: Path,
        targets: List[Target],
    ) -> None:
        self.__scheduler_class = scheduler_class
        self.__counter_file = counter_file
        self.__targets = targets

    @property
    def targets(self: Self) -> List[Target]:
        return self.__targets

    @property
    def scheduler_class(self: Self) -> Type[Scheduler]:
        return self.__scheduler_class

    @property
    def counter_file(self: Self) -> Path:
        return self.__counter_file

    @classmethod
    def load(cls, path: str | PathLike[Any]) -> Self:
        return cls.parse(Path(path).read_text())

    @classmethod
    def parse(cls, config_str: str) -> Self:
        config = tomllib.loads(config_str)

        def require_config(
            config: Any,
            path: List[str | None],
            value_type: Any = None,
            options: List[Any] = [],
            path_str: str = "<root>",
        ) -> None:
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

        require_config(config, ["scheduler_class"], str)
        scheduler_class = Scheduler
        module_name, class_name = config["scheduler_class"].split(".")
        try:
            module = importlib.import_module(
                f"meta_sched.schedule.scheduler.{module_name}"
            )
            scheduler_class = getattr(module, class_name)
        except (ModuleNotFoundError, AttributeError):
            raise ValueError(f'Could not load scheduler "{config["scheduler_class"]}"')
        if not issubclass(scheduler_class, Scheduler):
            raise ValueError(
                f'"{config["scheduler_class"]}" is not a subclass of "{Scheduler.__class__.__qualname__}"'
            )

        require_config(config, ["counter_file"], str)
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
        require_config(config, ["targets", None, "batch"], str, ["slurm"])

        return cls(
            scheduler_class, Path(config["counter_file"]), config["targets"]
        )  # TODO parse targets as targets
