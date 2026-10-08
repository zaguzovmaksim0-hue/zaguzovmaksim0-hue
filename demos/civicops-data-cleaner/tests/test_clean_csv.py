"""Native black-box and unit tests using only synthetic examples."""
from __future__ import annotations
import contextlib
import csv
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import clean_csv as tool


class CleanerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        self.input = self.home / "input.csv"
        self.output = self.home / "output.csv"

    def put(self, text: str, encoding: str = "utf-8"):
        self.input.write_text(text, encoding=encoding, newline="")

    def process(self, *args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exit_code = tool.main([str(self.input), str(self.output), *args])
        payload = json.loads(out.getvalue()) if out.getvalue() else None
        return exit_code, payload, err.getvalue()

    def test_trim_and_dedupe(self):
        self.put("ID, name\r\n001, A \r\n001, duplicate\r\n002, B\r\n")
        code, report, _ = self.process("--trim", "--key", "ID")
        self.assertEqual(code, 0)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertEqual(report["records_written"], 2)
        self.assertEqual(self.output.read_text().splitlines(), ["ID,name", "001,A", "002,B"])

    def test_composite_dedupe_only_duplicate_pair(self):
        self.put("id,type,notes\nx,a,1\nx,b,2\nx,a,3\n")
        code, report, _ = self.process("--key", "id", "--key", "type")
        self.assertEqual((code, report["records_written"]), (0, 2))
        self.assertIn("x,b,2", self.output.read_text())

    def test_no_dedupe_when_key_not_set(self):
        self.put("id,n\n1,X\n1,X\n")
        code, report, _ = self.process()
        self.assertEqual(code, 0)
        self.assertEqual(report["records_written"], 2)

    def test_leading_zeros_survive(self):
        self.put("code,phone\n00001,+34 123\n")
        code, report, _ = self.process("--trim")
        self.assertEqual(code, 0)
        self.assertIn("00001,+34 123", self.output.read_text())

    def test_excel_formula_escape(self):
        self.put("id,n\n1,=1+1\n2,+SUM(A1)\n3,-7+8\n4,@A1\n5, hello\n")
        code, report, _ = self.process("--excel-safe")
        self.assertEqual(code, 0)
        self.assertEqual(report["excel_formula_cells_escaped"], 4)
        with self.output.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual([r[1] for r in rows[1:5]], ["'=1+1", "'+SUM(A1)", "'-7+8", "'@A1"])

    def test_formula_escaped_only_when_requested(self):
        self.put("a,b\n1,=4+4\n")
        code, report, _ = self.process()
        self.assertEqual(code, 0)
        self.assertEqual(report["excel_formula_cells_escaped"], 0)
        self.assertIn(",=4+4", self.output.read_text())

    def test_formula_with_whitespace(self):
        self.put("a,b\n1,  =4+4\n")
        code, report, _ = self.process("--excel-safe")
        self.assertEqual(code, 0)
        with self.output.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[1][1], "'  =4+4")

    def test_formula_header_is_escaped(self):
        self.put("=SUM(A1),number\nhello,1\n")
        code, report, _ = self.process("--excel-safe")
        self.assertEqual(code, 0)
        self.assertEqual(report["excel_formula_cells_escaped"], 1)
        self.assertTrue(self.output.read_text().startswith("'=SUM(A1),number"))

    def test_utf8_bom_and_crlf(self):
        self.input.write_bytes(b"\xef\xbb\xbfid,name\r\n1,A\r\n")
        code, report, _ = self.process()
        self.assertEqual(code, 0)
        self.assertEqual(report["records_written"], 1)
        self.assertTrue(self.output.read_text().startswith("id,name"))

    def test_quoted_newline_in_cell(self):
        self.put('id,notes\n1,"hello\nworld"\n')
        code, report, _ = self.process()
        self.assertEqual(code, 0)
        self.assertEqual(report["records_written"], 1)
        with self.output.open(encoding="utf-8", newline="") as f:
            self.assertEqual(list(csv.reader(f))[1][1], "hello\nworld")

    def test_empty_file_rejected(self):
        self.put("")
        code, _, msg = self.process()
        self.assertEqual(code, 2)
        self.assertIn("no header", msg)
        self.assertFalse(self.output.exists())

    def test_duplicate_headers_rejected(self):
        self.put("id,id\n1,2\n")
        code, _, msg = self.process()
        self.assertEqual(code, 2)
        self.assertIn("duplicated", msg)

    def test_duplicate_headers_after_trim_rejected(self):
        self.put(" id ,id\n1,2\n")
        code, _, msg = self.process("--trim")
        self.assertEqual(code, 2)
        self.assertIn("duplicated", msg)

    def test_blank_header_rejected(self):
        self.put("a,\n1,2\n")
        code, _, _ = self.process()
        self.assertEqual(code, 2)

    def test_unknown_key_rejected(self):
        self.put("id,n\n1,2\n")
        code, _, msg = self.process("--key", "other")
        self.assertEqual(code, 2)
        self.assertIn("--key", msg)

    def test_duplicated_key_rejected(self):
        self.put("id,n\n1,2\n")
        code, _, msg = self.process("--key", "id", "--key", "id")
        self.assertEqual(code, 2)
        self.assertIn("Duplicate --key", msg)

    def test_invalid_extra_cells_rejected(self):
        self.put("id,n\n1,2,3\n")
        code, _, msg = self.process()
        self.assertEqual(code, 2)
        self.assertIn("field count", msg)
        self.assertFalse(self.output.exists())

    def test_invalid_missing_cells_rejected(self):
        self.put("id,n\n1\n")
        code, _, _ = self.process()
        self.assertEqual(code, 2)

    def test_invalid_utf8_rejected(self):
        self.input.write_bytes(b"id,n\n1,\xff\n")
        code, _, msg = self.process()
        self.assertEqual(code, 2)
        self.assertIn("encoding", msg.lower())

    def test_bad_csv_quote_rejected(self):
        self.put('id,n\n1,"unclosed\n')
        code, _, _ = self.process()
        self.assertEqual(code, 2)

    def test_large_input_rejected(self):
        self.input.write_bytes(b"a\n" + b"x" * (2 * 1024 * 1024))
        code, _, msg = self.process()
        self.assertEqual(code, 2)
        self.assertIn("exceeds", msg)

    def test_dry_run_never_writes(self):
        self.put("a,b\n1,2\n")
        code, report, _ = self.process("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(report["records_written"], 1)
        self.assertFalse(self.output.exists())

    def test_source_not_mutated(self):
        self.put("a,b\n1,2\n")
        original = self.input.read_bytes()
        code, _, _ = self.process("--trim")
        self.assertEqual(code, 0)
        self.assertEqual(self.input.read_bytes(), original)

    def test_no_overwriting_destination(self):
        self.put("a,b\n1,2\n")
        self.output.write_text("existing", encoding="utf-8")
        code, _, msg = self.process()
        self.assertEqual(code, 2)
        self.assertIn("exists", msg)
        self.assertEqual(self.output.read_text(), "existing")

    def test_no_overwriting_source(self):
        self.put("a,b\n1,2\n")
        original = self.input.read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = tool.main([str(self.input), str(self.input)])
        self.assertEqual(code, 2)
        self.assertEqual(self.input.read_bytes(), original)

    def test_blank_record_ignored(self):
        self.put("a,b\n\n1,2\n\n")
        code, report, _ = self.process()
        self.assertEqual((code, report["records_read"]), (0, 1))

    def test_empty_body_allowed(self):
        self.put("a,b\n")
        code, report, _ = self.process()
        self.assertEqual((code, report["records_written"]), (0, 0))
        self.assertEqual(self.output.read_text().strip(), "a,b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
