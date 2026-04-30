from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOTS = [ROOT / "tests", ROOT / "src" / "admin-portal" / "src"]
TEST_FILE_RE = re.compile(r"(^test_.*\.py$|.*_test\.py$|.*\.test\.(ts|tsx|js|jsx)$|.*\.spec\.(ts|tsx|js|jsx)$)")
FORBIDDEN_PATTERNS = {
    "python_mock_import": re.compile(r"\b(from\s+unittest\.mock\s+import|import\s+unittest\.mock)\b"),
    "python_mock_class": re.compile(r"\b(MagicMock|AsyncMock|Mock)\s*\("),
    "pytest_monkeypatch_setattr": re.compile(r"\bmonkeypatch\.setattr\s*\("),
    "method_replacement_request_json": re.compile(r"\._request_json\s*="),
    "method_replacement_execute_task": re.compile(r"\.execute_task\s*="),
    "fake_class": re.compile(r"\bclass\s+[_A-Za-z0-9]*(Fake|Stub|Dummy)[_A-Za-z0-9]*\b"),
    "fake_function": re.compile(r"\bdef\s+[_]?(fake|stub|dummy)[_A-Za-z0-9]*\b", re.IGNORECASE),
    "vitest_mock": re.compile(r"\bvi\.(mock|fn|mocked|stubGlobal|spyOn)\s*\("),
    "jest_mock": re.compile(r"\bjest\.(mock|fn|spyOn)\s*\("),
    "fetch_replacement": re.compile(r"\b(globalThis|global)\.fetch\s*="),
    "fetch_mock_name": re.compile(r"\b(mockFetch|fetchMock)\b"),
    "requests_mock": re.compile(r"\brequests_mock\b"),
}


def _test_files() -> list[Path]:
    files: list[Path] = []
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and TEST_FILE_RE.match(path.name):
                files.append(path)
    return sorted(files)


def test_no_mock_or_fake_tests_remain_in_repository() -> None:
    """业务要求：测试必须走真实代码路径，禁止 mock/fake/stub/替换 fetch 或替换方法实现。"""
    violations: list[str] = []
    for path in _test_files():
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in FORBIDDEN_PATTERNS.items():
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                rel_path = path.relative_to(ROOT)
                violations.append(f"{rel_path}:{line_no}: {label}: {match.group(0)!r}")

    assert violations == []
