"""Require real JSON Schema date-time validation (not jsonschema's silent fallback)."""
from jsonschema import FormatChecker


def required_format_checker() -> FormatChecker:
    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        raise RuntimeError(
            "Runtime requires rfc3339-validator for JSON Schema date-time validation"
        )
    return checker
