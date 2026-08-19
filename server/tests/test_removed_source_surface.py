from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCANNED_ROOTS = (
    PROJECT_ROOT / "server" / "app",
    PROJECT_ROOT / "server" / "tests",
    PROJECT_ROOT / "server" / "storage" / "templates",
    PROJECT_ROOT / "web" / "src",
    PROJECT_ROOT / "frontend" / "lib",
    PROJECT_ROOT / "frontend" / "test",
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "README.md",
)
TEXT_SUFFIXES = {".dart", ".json", ".md", ".py", ".ts", ".tsx"}


def test_retired_social_article_source_has_no_product_residue() -> None:
    forbidden_fragments = (
        "we" + "chat",
        "mp." + "weixin.qq.com",
        "公众" + "号",
        "collect" + "ManualSource",
        "Manual" + "CollectionResult",
        "collect_" + "manual_url",
        "人工" + "登记",
    )
    current_file = Path(__file__).resolve()
    violations: list[str] = []

    for root in SCANNED_ROOTS:
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file() or path.resolve() == current_file:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for fragment in forbidden_fragments:
                if fragment.lower() in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: {fragment}")

    assert violations == []
