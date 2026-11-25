"""Missing optional date-time validation must fail closed."""
import unittest
from unittest.mock import patch

from jsonschema import FormatChecker

from reference.schema_validation import required_format_checker


class TestRequiredDateTimeChecker(unittest.TestCase):
    def test_checker_is_available(self):
        self.assertIn("date-time", required_format_checker().checkers)

    def test_missing_validator_fails_closed(self):
        with patch.dict(FormatChecker.checkers, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "rfc3339-validator"):
                required_format_checker()


if __name__ == "__main__":
    unittest.main()
