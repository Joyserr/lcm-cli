"""Export utilities for LCM message data.

Provides field extraction, CSV writing, and JSONL writing for exporting
decoded LCM messages to structured formats suitable for downstream analysis
(pandas, jupyter, ELK, etc.).

Modules:
- FieldPath: Parses field path syntax like "a.b[0:3].c"
- FieldExtractor: Applies FieldPath to decoded objects to extract values
- CsvWriter: Stream-based CSV writer (header determined by first message)
- JsonlWriter: Stream-based JSON Lines writer
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TextIO


# ---------------------------------------------------------------------------
# Field Path Parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PathSegment:
    """A single segment in a field path (either attribute or index)."""
    name: Optional[str] = None  # attribute name (None for root array index)
    index: Optional[int] = None  # array index (None for attribute access)
    is_slice: bool = False  # True if this is a slice like [0:3]
    slice_start: Optional[int] = None
    slice_end: Optional[int] = None


@dataclass
class FieldPath:
    """Parsed representation of a field path like "position[0]" or "imu.accel.x"."""

    original: str
    segments: List[PathSegment] = field(default_factory=list)

    @classmethod
    def parse(cls, path_str: str) -> "FieldPath":
        """Parse a field path string into structured segments.

        Examples:
            "timestamp" -> [PathSegment(name="timestamp")]
            "position[0]" -> [PathSegment(name="position"), PathSegment(index=0)]
            "position[0:3]" -> [PathSegment(name="position"), PathSegment(is_slice=True, ...)]
            "imu.accel.x" -> [PathSegment(name="imu"), PathSegment(name="accel"), PathSegment(name="x")]
        """
        fp = cls(original=path_str)

        # Split by dots first
        parts = path_str.split(".")

        for part in parts:
            # Check for array index or slice
            match = re.match(r'^([a-zA-Z_]\w*)(\[(\d+)?:(\d+)?\]|\[(\d+)\])?$', part)
            if not match:
                raise ValueError(f"Invalid field path syntax: '{path_str}' at '{part}'")

            attr_name = match.group(1)
            fp.segments.append(PathSegment(name=attr_name))

            # Check for slice [start:end]
            if match.group(3) is not None or match.group(4) is not None:
                # Slice notation
                start = int(match.group(3)) if match.group(3) else None
                end = int(match.group(4)) if match.group(4) else None
                # Convert slice to multiple index segments
                fp.segments[-1] = PathSegment(
                    name=attr_name,
                    is_slice=True,
                    slice_start=start,
                    slice_end=end,
                )
            elif match.group(5) is not None:
                # Single index [n]
                idx = int(match.group(5))
                fp.segments.append(PathSegment(index=idx))

        return fp

    def expands_to_multiple(self) -> bool:
        """Check if this path expands to multiple columns (due to slice)."""
        return any(seg.is_slice for seg in self.segments)


# ---------------------------------------------------------------------------
# Field Extraction
# ---------------------------------------------------------------------------

class FieldExtractor:
    """Extract field values from decoded LCM message objects."""

    @staticmethod
    def extract(obj: Any, field_path: FieldPath) -> Any:
        """Extract a value from obj following the field path.

        Returns None if the path doesn't exist (doesn't raise).
        For slices, returns a list of values.
        """
        try:
            return FieldExtractor._traverse(obj, field_path.segments, 0)
        except (AttributeError, IndexError, KeyError, TypeError):
            return None

    @staticmethod
    def _traverse(obj: Any, segments: List[PathSegment], idx: int) -> Any:
        """Recursively traverse object following path segments."""
        if idx >= len(segments):
            return obj

        seg = segments[idx]

        if seg.is_slice:
            # Get the array
            if seg.name is None:
                arr = obj
            else:
                arr = getattr(obj, seg.name)

            if not isinstance(arr, (list, tuple)):
                return None

            # Apply slice
            start = seg.slice_start if seg.slice_start is not None else 0
            end = seg.slice_end if seg.slice_end is not None else len(arr)
            sliced = arr[start:end]

            # If there are more segments, traverse each element
            if idx + 1 < len(segments):
                return [
                    FieldExtractor._traverse(item, segments, idx + 1)
                    for item in sliced
                ]
            return sliced

        # Regular attribute or index access
        if seg.name is not None:
            obj = getattr(obj, seg.name)
        elif seg.index is not None:
            obj = obj[seg.index]

        return FieldExtractor._traverse(obj, segments, idx + 1)

    @staticmethod
    def extract_multiple(obj: Any, field_paths: List[FieldPath]) -> Dict[str, Any]:
        """Extract values for multiple field paths.

        Returns dict mapping field path string to value.
        For slices, expands to multiple keys like "field[0]", "field[1]", etc.
        """
        result = {}
        for fp in field_paths:
            if fp.expands_to_multiple():
                # Handle slice expansion
                expanded = FieldExtractor._extract_with_expansion(obj, fp)
                result.update(expanded)
            else:
                value = FieldExtractor.extract(obj, fp)
                result[fp.original] = value

        return result

    @staticmethod
    def _extract_with_expansion(obj: Any, fp: FieldPath) -> Dict[str, Any]:
        """Extract a field path that contains slices, expanding to multiple keys."""
        result = {}

        # Find the slice segment
        for i, seg in enumerate(fp.segments):
            if seg.is_slice:
                # Get the array
                try:
                    if seg.name is None:
                        arr = obj
                        prefix = ""
                    else:
                        arr = getattr(obj, seg.name)
                        prefix = ".".join(s.name for s in fp.segments[:i+1] if s.name)

                    if not isinstance(arr, (list, tuple)):
                        return {fp.original: None}

                    start = seg.slice_start if seg.slice_start is not None else 0
                    end = seg.slice_end if seg.slice_end is not None else len(arr)

                    for j in range(start, min(end, len(arr))):
                        value = FieldExtractor._traverse(arr[j], fp.segments, i + 1)
                        result[f"{prefix}[{j}]"] = value
                except (AttributeError, IndexError, TypeError):
                    result[fp.original] = None
                break

        return result


# ---------------------------------------------------------------------------
# CSV Writer
# ---------------------------------------------------------------------------

class CsvWriter:
    """Stream-based CSV writer that determines headers from the first message."""

    def __init__(
        self,
        file: TextIO,
        columns: Optional[List[str]] = None,
        field_paths: Optional[List[FieldPath]] = None,
    ) -> None:
        """Initialize CSV writer.

        Args:
            file: Output text stream.
            columns: Explicit column names (for field extraction mode).
            field_paths: Field paths for extraction (determines columns if not provided).
        """
        self.file = file
        self.explicit_columns = columns
        self.field_paths = field_paths
        self.writer: Optional[Any] = None
        self._header_written = False
        self._columns: Optional[List[str]] = None

    def write_row(self, data: Dict[str, Any]) -> None:
        """Write a row of data. Headers are determined on first call.

        Args:
            data: Dict mapping column names to values.
        """
        if not self._header_written:
            if self.explicit_columns:
                self._columns = list(self.explicit_columns)
            else:
                self._columns = list(data.keys())
            self.writer = csv.writer(self.file)
            self.writer.writerow(self._columns)
            self._header_written = True

        if self.writer and self._columns:
            row = [data.get(col, "") for col in self._columns]
            self.writer.writerow(row)
            self.file.flush()

    def close(self) -> None:
        """Close the underlying file."""
        self.file.close()


# ---------------------------------------------------------------------------
# JSONL Writer
# ---------------------------------------------------------------------------

class JsonlWriter:
    """Stream-based JSON Lines writer."""

    def __init__(self, file: TextIO) -> None:
        """Initialize JSONL writer.

        Args:
            file: Output text stream.
        """
        self.file = file

    def write_row(self, data: Dict[str, Any]) -> None:
        """Write a JSON object as a line.

        Args:
            data: Dict to serialize as JSON.
        """
        # Convert non-serializable types
        cleaned = self._clean_for_json(data)
        self.file.write(json.dumps(cleaned) + "\n")
        self.file.flush()

    def _clean_for_json(self, obj: Any) -> Any:
        """Recursively clean object for JSON serialization."""
        if isinstance(obj, dict):
            return {k: self._clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._clean_for_json(item) for item in obj]
        elif isinstance(obj, bytes):
            return obj.hex()
        else:
            return obj

    def close(self) -> None:
        """Close the underlying file."""
        self.file.close()
