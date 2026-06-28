"""Extract numeric fields from LCM decoded messages recursively."""

from __future__ import annotations

from typing import Any


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_struct(value: Any) -> bool:
    """Check if value is a struct-like object (has __slots__ or non-primitive dict)."""
    if isinstance(value, (str, bytes, list, dict, tuple, bool)):
        return False
    return hasattr(value, "__slots__") or hasattr(value, "__dict__")


def extract_numeric_fields(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Recursively extract all numeric fields into flat dot-notation keys.

    - Primitive numeric values (int/float) become top-level keys
    - Nested structs are flattened with dot notation: ``parent.child.field``
    - Arrays of numbers are expanded by index: ``field[0]``, ``field[1]``, ...
    - Arrays of structs are expanded: ``field[0].sub_field``
    - Bytes, strings, booleans are excluded
    """
    result: dict[str, Any] = {}
    attrs = getattr(obj, "__slots__", None)
    if attrs is None:
        attrs = [k for k in dir(obj) if not k.startswith("_")]
    for attr in attrs:
        try:
            value = getattr(obj, attr)
        except AttributeError:
            continue
        key = f"{prefix}.{attr}" if prefix else attr
        if _is_numeric(value):
            result[key] = value
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                idx_key = f"{key}[{i}]"
                if _is_numeric(item):
                    result[idx_key] = item
                elif _is_struct(item):
                    result.update(extract_numeric_fields(item, idx_key))
        elif _is_struct(value):
            result.update(extract_numeric_fields(value, key))
    return result


def get_field_schema(obj: Any) -> list[dict[str, str]]:
    """Return a list of ``{path, type}`` for all extractable numeric fields."""
    fields = extract_numeric_fields(obj)
    return [{"path": k, "type": "numeric"} for k in sorted(fields.keys())]
