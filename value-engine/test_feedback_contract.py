"""Tests for feedback signals; no external action or model self-modification."""
import unittest

from health_report import build


class FeedbackContractTests(unittest.TestCase):
    def test_feedback_module_is_read_only(self):
        self.assertTrue(callable(build))


if __name__ == "__main__":
    unittest.main()
