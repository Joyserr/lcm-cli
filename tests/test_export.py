"""Unit tests for lcm_cli.export module."""

from __future__ import annotations

import json

import pytest

from lcm_cli.export import (
    CsvWriter,
    FieldExtractor,
    FieldPath,
    JsonlWriter,
)


class TestFieldPath:
    def test_parse_simple_scalar(self):
        fp = FieldPath.parse("timestamp")
        assert len(fp.segments) == 1
        assert fp.segments[0].name == "timestamp"
        assert not fp.expands_to_multiple()

    def test_parse_array_index(self):
        fp = FieldPath.parse("position[0]")
        assert len(fp.segments) == 2
        assert fp.segments[0].name == "position"
        assert fp.segments[1].index == 0
        assert not fp.expands_to_multiple()

    def test_parse_array_slice(self):
        fp = FieldPath.parse("position[0:3]")
        assert len(fp.segments) == 1
        assert fp.segments[0].name == "position"
        assert fp.segments[0].is_slice
        assert fp.segments[0].slice_start == 0
        assert fp.segments[0].slice_end == 3
        assert fp.expands_to_multiple()

    def test_parse_nested_path(self):
        fp = FieldPath.parse("imu.acceleration.x")
        assert len(fp.segments) == 3
        assert fp.segments[0].name == "imu"
        assert fp.segments[1].name == "acceleration"
        assert fp.segments[2].name == "x"
        assert not fp.expands_to_multiple()

    def test_parse_invalid_syntax(self):
        with pytest.raises(ValueError, match="Invalid field path"):
            FieldPath.parse("position[abc]")

    def test_parse_slice_with_open_end(self):
        fp = FieldPath.parse("ranges[:5]")
        assert fp.segments[0].is_slice
        assert fp.segments[0].slice_start is None
        assert fp.segments[0].slice_end == 5


class TestFieldExtractor:
    def test_extract_scalar(self):
        class Obj:
            def __init__(self):
                self.timestamp = 1234567890

        obj = Obj()
        fp = FieldPath.parse("timestamp")
        value = FieldExtractor.extract(obj, fp)
        assert value == 1234567890

    def test_extract_array_index(self):
        class Obj:
            def __init__(self):
                self.position = [1.0, 2.0, 3.0]

        obj = Obj()
        fp = FieldPath.parse("position[1]")
        value = FieldExtractor.extract(obj, fp)
        assert value == 2.0

    def test_extract_nested(self):
        class Inner:
            def __init__(self):
                self.x = 42.0

        class Outer:
            def __init__(self):
                self.imu = Inner()

        obj = Outer()
        fp = FieldPath.parse("imu.x")
        value = FieldExtractor.extract(obj, fp)
        assert value == 42.0

    def test_extract_missing_path_returns_none(self):
        class Obj:
            def __init__(self):
                self.value = 10

        obj = Obj()
        fp = FieldPath.parse("nonexistent.field")
        value = FieldExtractor.extract(obj, fp)
        assert value is None

    def test_extract_slice(self):
        class Obj:
            def __init__(self):
                self.position = [1.0, 2.0, 3.0, 4.0]

        obj = Obj()
        fp = FieldPath.parse("position[0:3]")
        value = FieldExtractor.extract(obj, fp)
        assert value == [1.0, 2.0, 3.0]

    def test_extract_multiple_fields(self):
        class Obj:
            def __init__(self):
                self.timestamp = 1000
                self.position = [1.0, 2.0, 3.0]

        obj = Obj()
        fps = [FieldPath.parse("timestamp"), FieldPath.parse("position[0]")]
        result = FieldExtractor.extract_multiple(obj, fps)
        assert result["timestamp"] == 1000
        assert result["position[0]"] == 1.0


class TestCsvWriter:
    def test_write_basic_rows(self, tmp_path):
        path = tmp_path / "test.csv"
        with open(path, "w", newline="") as f:
            writer = CsvWriter(f)
            writer.write_row({"timestamp": 1.0, "channel": "A", "value": 10})
            writer.write_row({"timestamp": 2.0, "channel": "B", "value": 20})

        content = path.read_text()
        lines = content.strip().split("\n")
        assert lines[0] == "timestamp,channel,value"
        assert "1.0,A,10" in lines[1]
        assert "2.0,B,20" in lines[2]

    def test_write_with_explicit_columns(self, tmp_path):
        path = tmp_path / "test.csv"
        with open(path, "w", newline="") as f:
            writer = CsvWriter(f, columns=["channel", "timestamp"])
            writer.write_row({"timestamp": 1.0, "channel": "A", "extra": "x"})

        content = path.read_text()
        assert "channel,timestamp" in content


class TestJsonlWriter:
    def test_write_basic_rows(self, tmp_path):
        path = tmp_path / "test.jsonl"
        with open(path, "w") as f:
            writer = JsonlWriter(f)
            writer.write_row({"timestamp": 1.0, "channel": "A"})
            writer.write_row({"timestamp": 2.0, "channel": "B"})

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        obj1 = json.loads(lines[0])
        assert obj1["channel"] == "A"
        assert obj1["timestamp"] == 1.0

    def test_write_bytes_as_hex(self, tmp_path):
        path = tmp_path / "test.jsonl"
        with open(path, "w") as f:
            writer = JsonlWriter(f)
            writer.write_row({"data": b"\x01\x02\x03"})

        lines = path.read_text().strip().split("\n")
        obj = json.loads(lines[0])
        assert obj["data"] == "010203"
