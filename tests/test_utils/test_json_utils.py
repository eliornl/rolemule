"""Tests for utils/json_utils.py."""

import json
import uuid
from datetime import datetime, timezone

from utils.json_utils import CustomJSONEncoder, serialize_object_for_json


def test_custom_json_encoder_uuid_and_datetime() -> None:
    uid = uuid.uuid4()
    dt = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    out = json.dumps({"id": uid, "at": dt}, cls=CustomJSONEncoder)
    parsed = json.loads(out)
    assert parsed["id"] == str(uid)
    assert parsed["at"] == dt.isoformat()


def test_custom_json_encoder_unsupported_type() -> None:
    with __import__("pytest").raises(TypeError):
        json.dumps({"x": object()}, cls=CustomJSONEncoder)


def test_serialize_object_for_json_primitives() -> None:
    uid = uuid.uuid4()
    dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert serialize_object_for_json(uid) == str(uid)
    assert serialize_object_for_json(dt) == dt.isoformat()
    assert serialize_object_for_json(b"hello") == "hello"
    assert serialize_object_for_json(42) == 42


def test_serialize_object_for_json_nested() -> None:
    data = {"items": [{"id": uuid.uuid4()}], "tags": ("a", "b")}
    result = serialize_object_for_json(data)
    assert isinstance(result["items"][0]["id"], str)
    assert isinstance(result["tags"], tuple)


def test_serialize_object_for_json_circular_reference() -> None:
    d: dict = {}
    d["self"] = d
    result = serialize_object_for_json(d)
    assert result["self"] == "<circular reference>"


def test_serialize_object_for_json_circular_list() -> None:
    items: list = []
    items.append(items)
    result = serialize_object_for_json(items)
    assert result[0] == "<circular reference>"


def test_serialize_object_for_json_max_depth() -> None:
    nested = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}
    # Force depth limit by patching is not needed — 50 levels
    deep = nested
    for i in range(55):
        deep = {"n": deep}
    result = serialize_object_for_json(deep)
    # Walk until max depth marker appears
    cur = result
    found = False
    for _ in range(60):
        if cur == "<max depth exceeded>":
            found = True
            break
        if isinstance(cur, dict) and "n" in cur:
            cur = cur["n"]
        else:
            break
    assert found
