import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("audit.py")
SPEC = importlib.util.spec_from_file_location("evidence_lineage_audit", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def item(i, **overrides):
    base = {
        "id": i,
        "operator_control": [f"operator-{i}"],
        "source_lineage": [f"source-{i}"],
        "model_lineage": [f"model-{i}"],
        "data_lineage": [f"data-{i}"],
        "prompt_lineage": [f"prompt-{i}"],
        "toolchain_lineage": [f"tool-{i}"],
    }
    base.update(overrides)
    return base


class AuditTests(unittest.TestCase):
    def test_shared_source_is_correlated_even_with_distinct_operators(self):
        result = mod.audit({
            "evidence": [
                item("a", source_lineage=["same-source"]),
                item("b", source_lineage=["same-source"]),
            ]
        })
        self.assertEqual(result["status"], "CORRELATED_DECLARED_LINEAGE")
        self.assertFalse(result["independence_verified"])

    def test_shared_model_is_correlated(self):
        result = mod.audit({
            "evidence": [
                item("a", model_lineage=["shared-model-family"]),
                item("b", model_lineage=["shared-model-family"]),
            ]
        })
        self.assertEqual(result["status"], "CORRELATED_DECLARED_LINEAGE")

    def test_missing_lineage_is_unresolved_not_independent(self):
        b = item("b")
        b["data_lineage"] = []
        result = mod.audit({"evidence": [item("a"), b]})
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertFalse(result["independence_verified"])

    def test_distinct_declarations_do_not_prove_independence(self):
        result = mod.audit({"evidence": [item("a"), item("b")]})
        self.assertEqual(result["status"], "DISTINCT_DECLARED_LINEAGE")
        self.assertFalse(result["independence_verified"])


if __name__ == "__main__":
    unittest.main()
