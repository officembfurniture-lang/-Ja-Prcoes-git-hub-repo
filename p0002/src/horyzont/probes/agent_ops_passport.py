from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "horyzont.agent-operations-passport/v0.1"
SOURCE_BASIS = [
    "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
    "https://www.ntia.gov/report/2021/minimum-elements-software-bill-materials-sbom",
]
TRACKED_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "node_modules",
}
SKIP_NAMES = {
    ".env",
    ".env.local",
    "credentials.json",
    "secrets.json",
}
MAX_FILE_BYTES = 2_000_000


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def classify_path(path: Path) -> list[str]:
    value = path.as_posix().lower()
    classes: list[str] = []
    markers = {
        "prompt": ("prompt", "instruction"),
        "model_config": ("model", "provider", "inference"),
        "tool_definition": ("tool", "function", "connector", "mcp"),
        "authority_policy": ("policy", "permission", "authority", "guardrail"),
        "evaluation": ("eval", "test", "benchmark", "metric"),
    }
    for category, tokens in markers.items():
        if any(token in value for token in tokens):
            classes.append(category)
    return classes or ["implementation_or_documentation"]


def iter_candidate_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.name.lower() in SKIP_NAMES or path.suffix.lower() not in TRACKED_SUFFIXES:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        yield path


def build_passport(root: str | Path, generated_at: str | None = None) -> dict[str, Any]:
    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError(f"repository root is not a directory: {base}")

    inventory = []
    category_counts: Counter[str] = Counter()
    for path in iter_candidate_files(base):
        relative = path.relative_to(base).as_posix()
        categories = classify_path(Path(relative))
        category_counts.update(categories)
        content = path.read_bytes()
        inventory.append(
            {
                "path": relative,
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
                "categories": categories,
            }
        )

    required_evidence = {
        "prompt": "A prompt or instruction artifact was not identified by filename.",
        "model_config": "A model/provider configuration artifact was not identified by filename.",
        "tool_definition": "A tool or connector definition was not identified by filename.",
        "authority_policy": "An authority or permission policy was not identified by filename.",
        "evaluation": "An evaluation, test or metric artifact was not identified by filename.",
    }
    gaps = [message for category, message in required_evidence.items() if not category_counts[category]]
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    passport: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": timestamp,
        "repository_label": base.name,
        "file_count": len(inventory),
        "inventory": inventory,
        "category_counts": dict(sorted(category_counts.items())),
        "traceability_evidence_gaps": gaps,
        "source_basis": SOURCE_BASIS,
        "truth_boundary": {
            "legal_compliance_determined": False,
            "file_contents_exported": False,
            "secret_named_files_skipped": True,
            "statement": "This artifact inventories local evidence candidates; it is not legal advice or a conformity assessment.",
        },
    }
    stable_identity = {
        field: passport[field]
        for field in (
            "schema",
            "repository_label",
            "file_count",
            "inventory",
            "category_counts",
            "traceability_evidence_gaps",
            "source_basis",
            "truth_boundary",
        )
    }
    passport["inventory_hash"] = sha256_bytes(
        canonical_json(stable_identity).encode("utf-8")
    )
    passport["passport_hash"] = sha256_bytes(canonical_json(passport).encode("utf-8"))
    return passport


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an Agent Operations Passport")
    parser.add_argument("root", help="Repository directory to scan")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()
    result = build_passport(args.root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
