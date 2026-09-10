#!/usr/bin/env python3
"""
Unit tests for the status / error-log interpretation logic. No device needed.

    python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import errorlog  # noqa: E402


class TestDecodeStatusCQE(unittest.TestCase):
    def test_lba_out_of_range(self):
        d = errorlog.decode_status(0x4080)
        self.assertEqual(d.sct, 0x0)
        self.assertEqual(d.sc, 0x80)
        self.assertEqual(d.sc_name, "LBA Out of Range")
        self.assertTrue(d.dnr)
        self.assertFalse(d.is_success)

    def test_invalid_opcode(self):
        d = errorlog.decode_status(0x4001)
        self.assertEqual((d.sct, d.sc), (0x0, 0x01))
        self.assertEqual(d.sc_name, "Invalid Command Opcode")

    def test_unrecovered_read_error(self):
        d = errorlog.decode_status(0x0281)
        self.assertEqual(d.sct, 0x2)
        self.assertEqual(d.sc, 0x81)
        self.assertEqual(d.sct_name, "Media and Data Integrity Errors")
        self.assertEqual(d.sc_name, "Unrecovered Read Error")
        self.assertIn("ECC", d.root_cause_hint)

    def test_success(self):
        self.assertTrue(errorlog.decode_status(0x0).is_success)

    def test_unknown_sc(self):
        d = errorlog.decode_status(0x00FE)
        self.assertIn("Unknown", d.sc_name)

    def test_compare_failure_has_hint(self):
        d = errorlog.decode_status(0x4285)
        self.assertEqual((d.sct, d.sc), (0x2, 0x85))
        self.assertEqual(d.sc_name, "Compare Failure")
        self.assertIn("miscompare", d.root_cause_hint)
        self.assertTrue(d.dnr)


class TestDecodeStatusErrorLog(unittest.TestCase):
    def test_phase_tag_shift(self):
        # Error-log Status Field: SC in bits 8:1. LBA-out-of-range, DNR, phase=1.
        sf = (0x80 << 1) | (1 << 15) | 0x1
        d = errorlog.decode_error_log_status(sf)
        self.assertEqual(d.sc, 0x80)
        self.assertEqual(d.sct, 0x0)
        self.assertTrue(d.dnr)
        self.assertTrue(d.phase_tag)
        self.assertEqual(d.source, "error-log")


class TestInterpretErrorLogPage(unittest.TestCase):
    def test_skips_empty_slots(self):
        page = {"errors": [
            {"error_count": 0, "status_field": 0},
            {"error_count": 0, "status_field": 0},
        ]}
        self.assertEqual(errorlog.interpret_error_log_page(page), [])

    def test_decodes_real_entry(self):
        # error-log Status Field: phase(0) | SC(8:1) | SCT(11:9)
        sf = (0x2 << 9) | (0x81 << 1) | 0x1   # SCT 2 media, SC 0x81 unrecovered read
        page = {"errors": [{
            "error_count": 7, "sqid": 1, "cmdid": 0x42,
            "status_field": sf,
            "lba": 256, "nsid": 1, "parm_error_location": 0,
        }]}
        entries = errorlog.interpret_error_log_page(page)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.error_count, 7)
        self.assertEqual(e.status.sc_name, "Unrecovered Read Error")
        self.assertEqual(e.lba, 256)
        self.assertIn("LBA 256", e.summary())
        self.assertIn("status", e.as_dict())

    def test_new_entries_diff(self):
        before = {"errors": [{"error_count": 1, "cmdid": 1, "status_field": 0x2}]}
        after = {"errors": [
            {"error_count": 1, "cmdid": 1, "status_field": 0x2},
            {"error_count": 2, "cmdid": 5, "status_field": (0x80 << 1)},
        ]}
        new = errorlog.new_error_log_entries(before, after)
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].error_count, 2)


class TestScenarioMetadata(unittest.TestCase):
    def test_registry_and_expectations(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import scenarios
        self.assertIn("oob_write", scenarios.REGISTRY)
        self.assertEqual(scenarios.get("oob_write").expected_sc, 0x80)
        self.assertEqual(scenarios.get("compare_mismatch").expected_sct, 0x2)
        self.assertEqual(scenarios.get("compare_mismatch").expected_sc, 0x85)
        self.assertEqual(scenarios.get("media_error").expected_sct, 0x2)
        self.assertTrue(scenarios.get("media_error").needs_blkdebug)
        self.assertIn("smart_critical_warning",
                      scenarios.get("smart_warning").device_props)
        # client-side set excludes the ones needing special device config
        self.assertIn("oob_write", scenarios.CLIENT_SIDE)
        self.assertNotIn("media_error", scenarios.CLIENT_SIDE)
        self.assertNotIn("smart_warning", scenarios.CLIENT_SIDE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
