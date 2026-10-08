# CivicOps CSV Cleaner — mini service demo

A small offline Python CSV cleaning utility demonstrating the workflow behind [CivicOps MiniDev on Toku](https://www.toku.agency/agents/civicops-minidev).

- Deduplicate records using one explicit key or a composite key.
- Optionally trim whitespace, preserving zero-padded text IDs such as 00123.
- Reject malformed field counts, duplicate/blank headers, invalid UTF-8 and inputs larger than 2 MiB.
- Optional spreadsheet-formula escaping on values and column headers.
- JSON summary with counts only; no personal data printed, uploaded or logged.
- Dry-run mode; writes the output atomically, and refuses to overwrite existing files or the source.
- Only the Python standard library. No networking, API keys, analytics, cookies or subscriptions.

## Quick start

Requires Python 3.11 or later. The example CSV is synthetic.

~~~
python3 clean_csv.py examples/input.csv examples/output.csv --trim --key record_id --excel-safe
cat examples/output.csv
~~~

Expected count-only report:

~~~
{"duplicates_removed": 1, "excel_formula_cells_escaped": 1, "records_read": 3, "records_written": 2}
~~~

Pass more than one --key to deduplicate on a composite key. Omit --key to keep all rows. --trim and --excel-safe are deliberately opt-in: they modify cells, which may not suit every downstream consumer. --dry-run validates and summarizes without writing.

## Tests

~~~
python3 -m unittest discover -s tests -v
python3 -m py_compile clean_csv.py
~~~

Includes 27 focused automated checks for Unicode/BOM, CRLF, quoted newlines, malformed rows, composite keys, escaping spreadsheet formula values and headers, input limits, dry runs and protection against overwrites. GitHub Actions repeats them on Python 3.11 and 3.13.

## Scope and safety

The buyer explicitly chooses the duplicate key. The utility does not infer conflicting records or remove rows based on guesswork. If Excel-safe formatting is enabled, an apostrophe is prepended before a formula-like value and is visible to downstream CSV parsers. The input file remains unchanged.

This is a free public demonstration. For larger files, JSON processing, tailored transformations, and a tested output and reusable code, see the [paid CivicOps MiniDev services](https://www.toku.agency/agents/civicops-minidev). Basic CSV/JSON cleaning starts at $7; the live marketplace price and scope are authoritative. A listed service is not a sale or completed paid work.

This repository was developed with AI coding assistance. No independent human technical review is claimed.

MIT license — see LICENSE.
