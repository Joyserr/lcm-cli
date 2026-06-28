"""FieldExtractor tests."""

from lcm_cli.dashboard.field_extractor import extract_numeric_fields, get_field_schema


def test_flat_numeric_fields():
    msg = type("Msg", (), {"speed": 1.5, "count": 42, "name": "robot"})()
    fields = extract_numeric_fields(msg)
    assert fields == {"speed": 1.5, "count": 42}


def test_nested_struct_fields():
    inner = type("Inner", (), {"x": 1.0, "y": 2.0})()
    msg = type("Msg", (), {"pos": inner, "label": "test"})()
    fields = extract_numeric_fields(msg)
    assert fields == {"pos.x": 1.0, "pos.y": 2.0}


def test_array_fields():
    msg = type("Msg", (), {"data": [10.0, 20.0, 30.0]})()
    fields = extract_numeric_fields(msg)
    assert fields == {"data[0]": 10.0, "data[1]": 20.0, "data[2]": 30.0}


def test_deep_nested():
    leaf = type("Leaf", (), {"val": 99})()
    mid = type("Mid", (), {"leaf": leaf, "extra": 5.0})()
    msg = type("Msg", (), {"mid": mid})()
    fields = extract_numeric_fields(msg)
    assert fields == {"mid.leaf.val": 99, "mid.extra": 5.0}


def test_field_schema():
    inner = type("P", (), {"x": 0, "y": 0})()
    msg = type("Msg", (), {"speed": 1.5, "pos": inner})()
    schema = get_field_schema(msg)
    assert schema == [
        {"path": "pos.x", "type": "numeric"},
        {"path": "pos.y", "type": "numeric"},
        {"path": "speed", "type": "numeric"},
    ]


def test_boolean_excluded():
    msg = type("Msg", (), {"active": True, "speed": 1.0})()
    fields = extract_numeric_fields(msg)
    assert fields == {"speed": 1.0}


def test_bytes_excluded():
    msg = type("Msg", (), {"raw": b"\x00\x01", "val": 3.14})()
    fields = extract_numeric_fields(msg)
    assert fields == {"val": 3.14}


def test_struct_array():
    item_cls = type("Item", (), {"x": 0, "y": 0})
    items = [item_cls(), item_cls()]
    items[0].x = 1
    items[0].y = 2
    items[1].x = 3
    items[1].y = 4
    msg = type("Msg", (), {"points": items})()
    fields = extract_numeric_fields(msg)
    assert fields == {
        "points[0].x": 1,
        "points[0].y": 2,
        "points[1].x": 3,
        "points[1].y": 4,
    }
