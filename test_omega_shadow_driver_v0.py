import json
import unittest

from omega_shadow_driver_v0 import evaluate


class OmegaShadowDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("omega_shadow_fixtures_v0.json", "r", encoding="utf-8") as f:
            cls.cases = json.load(f)["cases"]

    def test_fixtures(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                verdict = evaluate(case["record"])
                self.assertEqual(verdict.verdict, case["expected_verdict"])


if __name__ == "__main__":
    unittest.main()
