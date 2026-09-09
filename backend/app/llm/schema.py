"""Converts a plain-Python field-type mapping (as used throughout
dialogue/nodes.py) into a JSON Schema object, so app/llm/client.py can hand
the same schema to any backend regardless of how that provider likes to
receive it.
"""

from __future__ import annotations

import typing
from enum import Enum

from pydantic import BaseModel


def _unwrap_optional(py_type: type) -> type:
    """Optional[X] is Union[X, None] - a node's field can be typed Optional
    (e.g. OccupancyBreakdownItem.floor_area_sqm) without every schema branch
    below needing to special-case Union itself.
    """
    if typing.get_origin(py_type) is typing.Union:
        args = [arg for arg in typing.get_args(py_type) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return py_type


def _schema_for_type(py_type: type) -> dict:
    py_type = _unwrap_optional(py_type)
    origin = typing.get_origin(py_type)

    if origin is typing.Literal:
        return {"type": "string", "enum": list(typing.get_args(py_type))}

    if origin in (list, typing.List):  # noqa: UP006
        args = typing.get_args(py_type)
        item_type = args[0] if args else str
        return {"type": "array", "items": _schema_for_type(item_type)}

    if isinstance(py_type, type) and issubclass(py_type, Enum):
        return {"type": "string", "enum": [member.value for member in py_type]}

    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        # Lets a node ask for a nested structure in one extraction call (e.g.
        # Mixed Use's occupancy_breakdown: list[OccupancyBreakdownItem])
        # instead of the flat field_types every other node uses.
        return {
            "type": "object",
            "properties": {
                name: _schema_for_type(field.annotation)
                for name, field in py_type.model_fields.items()
            },
            "additionalProperties": False,
        }

    return {
        str: {"type": "string"},
        float: {"type": "number"},
        int: {"type": "integer"},
        bool: {"type": "boolean"},
    }.get(py_type, {"type": "string"})


def build_json_schema(field_types: dict[str, type]) -> dict:
    """Every field is optional in the schema - a field the model isn't
    confident about should be omitted, never guessed, so nothing is listed
    under "required".
    """
    return {
        "type": "object",
        "properties": {name: _schema_for_type(typ) for name, typ in field_types.items()},
        "additionalProperties": False,
    }
