import abc
from typing import Any, Dict, Self


class Serializable(abc.ABC):
    @abc.abstractmethod
    def to_dict(self: Self) -> Dict[str, Any]:
        raise NotImplementedError()
