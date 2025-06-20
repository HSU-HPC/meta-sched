"""Module containing base class for serializable objects."""

import abc
from typing import Any, Dict, Self


class Serializable(abc.ABC):
    """Base class for serializable objects."""

    @abc.abstractmethod
    def to_dict(self: Self) -> Dict[str, Any]:
        """
        Create a dictionary representation of the object.

        Returns
        -------
        Dict[str, Any]
            The dictionary representing the object

        Raises
        ------
        NotImplementedError
            Must be implemented by the child classes
        """
        raise NotImplementedError()
