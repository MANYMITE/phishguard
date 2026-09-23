"""Tests for the terminal UI helpers."""
import unittest
from unittest import mock

from phishguard.cli import build_link, parse_choice, ask_consent
from phishguard.safety import ValidationError, validate_campaign_name


class ChoiceParsing(unittest.TestCase):
    def test_accepts_leading_zeros_and_spaces(self):
        self.assertEqual(parse_choice("01", 10), 1)
        self.assertEqual(parse_choice(" 2 ", 10), 2)
        self.assertEqual(parse_choice("08", 10), 8)
        self.assertEqual(parse_choice("10", 10), 10)

    def test_rejects_garbage_and_out_of_range(self):
        self.assertIsNone(parse_choice("abc", 10))
        self.assertIsNone(parse_choice("", 10))
        self.assertIsNone(parse_choice("11", 10))
        self.assertIsNone(parse_choice("-1", 10))


class LinkBuilding(unittest.TestCase):
    def test_link_shape(self):
        link = build_link(3, 7, "tok123")
        self.assertEqual(link, "http://127.0.0.1:5000/sim/3/7-tok123")


class ConsentGate(unittest.TestCase):
    def test_refuses_without_explicit_yes(self):
        for answer in ("no", "", "y", "yeah", "yes?"):
            with mock.patch("builtins.input", return_value=answer):
                self.assertFalse(ask_consent("Alex"), repr(answer))

    def test_accepts_yes_case_insensitively(self):
        for answer in ("yes", "YES", "Yes ", "  yes"):
            with mock.patch("builtins.input", return_value=answer):
                self.assertTrue(ask_consent("Alex"), repr(answer))

    def test_accepts_exact_yes(self):
        with mock.patch("builtins.input", return_value="yes"):
            self.assertTrue(ask_consent("Alex"))


class CatalogRegistry(unittest.TestCase):
    def test_catalog_has_ten_fictional_portals(self):
        from phishguard.sim import CATALOG, TEMPLATES
        self.assertEqual(len(CATALOG), 10)
        self.assertEqual(len(TEMPLATES), len(CATALOG))
        for entry in CATALOG:
            self.assertIn("key", entry)
            self.assertIn("title", entry)
            self.assertEqual(entry["file"], "sim_portal.html")

    def test_template_keys_are_unique_and_stable(self):
        from phishguard.sim import CATALOG
        keys = [e["key"] for e in CATALOG]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("acme_webmail", keys)  # existing campaigns keep working
    def test_campaign_name_minimum(self):
        with self.assertRaises(ValidationError):
            validate_campaign_name("ab")


if __name__ == "__main__":
    unittest.main()
