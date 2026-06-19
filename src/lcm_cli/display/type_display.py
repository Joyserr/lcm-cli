"""Display utilities for LCM type diagnostics."""

from __future__ import annotations

from typing import Optional

from rich.table import Table

from lcm_cli.core.lcm_type_builder import TypeRegistry
from lcm_cli.core.lcm_type_parser import LcmStruct
from lcm_cli.protocol import fingerprint_to_hex


def build_type_list_table(
    registry: TypeRegistry,
    package_filter: Optional[str] = None,
    grep_filter: Optional[str] = None,
) -> Table:
    """Build a table listing all registered types."""
    table = Table(
        title="Registered LCM Types",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Type", style="cyan")
    table.add_column("Fingerprint", style="dim")
    table.add_column("Package", style="green")
    table.add_column("Fields", justify="right")

    all_types = registry.all_types

    rows = []
    for full_name, cls in all_types.items():
        parts = full_name.rsplit(".", 1)
        package = parts[0] if len(parts) > 1 else ""

        fp_bytes = cls._get_packed_fingerprint()  # type: ignore[attr-defined]
        fp_int = int.from_bytes(fp_bytes, "big")
        fp_hex = fingerprint_to_hex(fp_int)

        field_count = len(getattr(cls, "__slots__", []))

        if package_filter and package != package_filter:
            continue
        if grep_filter and grep_filter.lower() not in full_name.lower():
            continue

        rows.append((full_name, fp_hex, package, str(field_count)))

    for row in sorted(rows, key=lambda r: r[0]):
        table.add_row(*row)

    table.caption = f"{len(rows)} type(s)"
    return table


def build_type_show_table(struct: LcmStruct, registry: TypeRegistry) -> Table:
    """Build a table showing a type's field structure."""
    fp_hex = fingerprint_to_hex(struct.hash_value)

    table = Table(
        title=f"struct {struct.full_name}  (fingerprint: {fp_hex})",
        show_header=False,
        box=None,
    )
    table.add_column("Field", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Info", style="dim")

    for member in struct.members:
        type_str = member.type_name
        dims_str = ""
        if member.dimensions:
            dims_parts = []
            for dim in member.dimensions:
                dims_parts.append(f"[{dim.size}]")
            dims_str = "".join(dims_parts)

        info = ""
        if not _is_primitive(member.type_name):
            ref_cls = registry._classes_by_name.get(member.type_name)
            if ref_cls:
                ref_fp = int.from_bytes(ref_cls._get_packed_fingerprint(), "big")  # type: ignore[attr-defined]
                info = f"→ {member.type_name} ({fingerprint_to_hex(ref_fp)})"

        table.add_row(member.member_name, f"{type_str}{dims_str}", info)

    if struct.constants:
        table.add_row("", "", "")
        for const in struct.constants:
            table.add_row(f"const {const.name}", const.type_name, f"= {const.value_str}")

    return table


def _is_primitive(type_name: str) -> bool:
    return type_name in {
        "byte", "boolean", "int8_t", "int16_t", "int32_t", "int64_t",
        "float", "double", "string",
    }
