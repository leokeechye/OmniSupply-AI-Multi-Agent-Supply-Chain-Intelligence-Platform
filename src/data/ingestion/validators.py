"""
Data-quality checks for OmniSupply ingestion.

Stubbed alongside loaders.py — same reason (original src/data/ was .gitignore'd).
Only omnisupply_demo.py exercises this. Streamlit deploy does not need it.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    status: str = "PASSED"  # "PASSED" or "FAILED"
    issues_found: int = 0
    issues: List[str] = field(default_factory=list)


class DataQualityChecker:
    """Runs quality checks on loaded data and returns a per-dataset summary."""

    def check_all(self, data: Dict[str, List[Any]]) -> Dict[str, ValidationResult]:
        raise NotImplementedError(
            "DataQualityChecker.check_all() was not committed to the repo. "
            "Implement before running omnisupply_demo.py."
        )
