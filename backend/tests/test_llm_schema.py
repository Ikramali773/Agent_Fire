"""Tests for app/llm/schema.py's JSON-schema builder, including the nested
BaseModel/Enum support added for Mixed Use's occupancy_breakdown node."""

from app.llm.schema import build_json_schema
from app.models.case_file import OccupancyBreakdownItem


class TestScalarTypes:
    def test_plain_scalars(self):
        schema = build_json_schema({"name": str, "height_m": float, "floors": int, "flag": bool})
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["properties"]["height_m"] == {"type": "number"}
        assert schema["properties"]["floors"] == {"type": "integer"}
        assert schema["properties"]["flag"] == {"type": "boolean"}

    def test_literal_becomes_string_enum(self):
        from typing import Literal

        schema = build_json_schema({"goal": Literal["a", "b"]})
        assert schema["properties"]["goal"] == {"type": "string", "enum": ["a", "b"]}

    def test_list_of_strings(self):
        schema = build_json_schema({"systems": list[str]})
        assert schema["properties"]["systems"] == {"type": "array", "items": {"type": "string"}}


class TestNestedModelSupport:
    def test_list_of_pydantic_model_becomes_array_of_objects(self):
        schema = build_json_schema({"occupancy_breakdown": list[OccupancyBreakdownItem]})
        item_schema = schema["properties"]["occupancy_breakdown"]
        assert item_schema["type"] == "array"
        props = item_schema["items"]["properties"]
        assert props["floor_range"] == {"type": "string"}
        assert props["floor_area_sqm"] == {"type": "number"}
        # OccupancyType is a str Enum - its members should be listed, not
        # collapsed to a bare string.
        assert props["type"]["type"] == "string"
        assert "Residential" in props["type"]["enum"]
        assert "Mixed Use" in props["type"]["enum"]
