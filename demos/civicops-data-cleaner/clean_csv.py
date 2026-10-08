#!/usr/bin/env python3
"""Offline CSV cleaning demo — stdlib only; no network, telemetry or input mutation."""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
import tempfile

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
EXCEL_FORMULA_PREFIXES = ("=", "+", "-", "@")


class InputProblem(ValueError):
    """Invalid input or unsupported request; never print row contents."""


def safe_excel_cell(value: str) -> tuple[str, bool]:
    """Escape spreadsheet formula interpretation without deleting the data."""
    if value.lstrip().startswith(EXCEL_FORMULA_PREFIXES):
        return "'" + value, True
    return value, False


def clean_rows(
    source: pathlib.Path,
    *,
    trim: bool,
    dedupe_keys: tuple[str, ...],
    excel_safe: bool,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[list[str], list[list[str]], dict[str, int]]:
    if not source.is_file():
        raise InputProblem("Source file not found")
    if source.stat().st_size > max_bytes:
        raise InputProblem(f"Source exceeds {max_bytes} byte limit")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        try:
            reader = csv.reader(handle, strict=True)
            try:
                original_headers = next(reader)
            except StopIteration:
                raise InputProblem("Source CSV has no header") from None
            headers = [x.strip() if trim else x for x in original_headers]
            if not headers or any(not x for x in headers):
                raise InputProblem("CSV has an empty header name")
            if len(set(headers)) != len(headers):
                raise InputProblem("CSV has duplicated header names")
            if len(set(dedupe_keys)) != len(dedupe_keys):
                raise InputProblem("Duplicate --key supplied")
            if any(key not in headers for key in dedupe_keys):
                raise InputProblem("A --key column is not in the header")
            indices = [headers.index(key) for key in dedupe_keys]
            seen: set[tuple[str, ...]] = set()
            output: list[list[str]] = []
            records_read = 0
            removed = 0
            protected = 0
            for record in reader:
                if not record:  # ordinary blank lines, no phantom records
                    continue
                if len(record) != len(headers):
                    raise InputProblem(f"CSV row ending near line {reader.line_num} has incorrect field count")
                records_read += 1
                values = [cell.strip() if trim else cell for cell in record]
                if indices:
                    key_value = tuple(values[i] for i in indices)
                    if key_value in seen:
                        removed += 1
                        continue
                    seen.add(key_value)
                if excel_safe:
                    escaped = [safe_excel_cell(v) for v in values]
                    protected += sum(int(flag) for _val, flag in escaped)
                    values = [val for val, _flag in escaped]
                output.append(values)
        except (csv.Error, UnicodeError) as exc:
            raise InputProblem(f"CSV parse/encoding error ({type(exc).__name__})") from None
    if excel_safe:
        # A header is also a spreadsheet cell: guard attacker-controlled names.
        guarded_headers = [safe_excel_cell(h) for h in headers]
        protected += sum(int(was_guarded) for _cell, was_guarded in guarded_headers)
        headers = [cell for cell, _flag in guarded_headers]
    return headers, output, {
        "records_read": records_read,
        "records_written": len(output),
        "duplicates_removed": removed,
        "excel_formula_cells_escaped": protected,
    }


def atomic_write(dest: pathlib.Path, headers: list[str], rows: list[list[str]]) -> None:
    if dest.exists():
        raise InputProblem("Destination exists; choose a new output path")
    if not dest.parent.is_dir():
        raise InputProblem("Destination directory not found")
    temporary: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", suffix=".csv.tmp", prefix=".civicops-",
            dir=str(dest.parent), delete=False
        ) as handle:
            temporary = pathlib.Path(handle.name)
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)
        os.replace(temporary, dest)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean small CSV files offline; no analytics, no upload, no paid services."
    )
    parser.add_argument("source", type=pathlib.Path, help="UTF-8 CSV input (up to 2 MiB)")
    parser.add_argument("destination", type=pathlib.Path, help="New output file; never overwrite")
    parser.add_argument("--trim", action="store_true", help="Strip surrounding whitespace from headers/cells")
    parser.add_argument("--key", action="append", default=[], metavar="COLUMN", help="Repeat for composite dedupe key")
    parser.add_argument("--excel-safe", action="store_true", help="Prefix CSV formula-like cells with an apostrophe")
    parser.add_argument("--dry-run", action="store_true", help="Count/validate without writing output")
    args = parser.parse_args(argv)
    try:
        if args.source.resolve() == args.destination.resolve():
            raise InputProblem("Source and destination must differ")
        headers, rows, summary = clean_rows(
            args.source, trim=args.trim, dedupe_keys=tuple(args.key), excel_safe=args.excel_safe
        )
        if not args.dry_run:
            atomic_write(args.destination, headers, rows)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (InputProblem, OSError) as exc:
        # Input path or row contents are never sent to a network destination.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
