"""Converts a plain-Python field-type mapping (as used throughout
dialogue/nodes.py) into a JSON Schema object, so app/llm/client.py can hand
the same schema to any backend regardless of how that provider likes to
receive it.
"""

from __future__ import annotations

import typing


def _schema_for_type(py_type: type) -> dict:
    origin = typing.get_origin(py_type)

    if origin is typing.Literal:
        return {"type": "string", "enum": list(typing.get_args(py_type))}

    if origin in (list, typing.List):  # noqa: UP006
        args = typing.get_args(py_type)
        item_type = args[0] if args else str
        return {"type": "array", "items": _schema_for_type(item_type)}

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
