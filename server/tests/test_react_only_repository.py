import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent


def _text_files(root: Path) -> list[Path]:
    suffixes = {".cjs", ".js", ".json", ".md", ".mjs", ".ps1", ".py", ".ts", ".tsx", ".yaml", ".yml"}
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes]


def test_repository_has_only_the_react_frontend() -> None:
    retired_frontend = "flut" + "ter"

    assert not (PROJECT_ROOT / "frontend").exists()
    assert not (PROJECT_ROOT / "scripts" / f"{retired_frontend}w.ps1").exists()
    assert not (PROJECT_ROOT / "scripts" / "frontend-build.ps1").exists()

    project_manifest = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    workspace_manifest = json.loads((WORKSPACE_ROOT / "package.json").read_text(encoding="utf-8"))
    for manifest in (project_manifest, workspace_manifest):
        scripts = manifest.get("scripts", {})
        assert f"start:{retired_frontend}" not in scripts
        assert f"stop:{retired_frontend}" not in scripts
        assert "start:react" not in scripts

    scan_paths = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / "package.json",
        PROJECT_ROOT / "docs",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "web" / "README.md",
        PROJECT_ROOT / "web" / "src",
        WORKSPACE_ROOT / "package.json",
    ]
    candidates: list[Path] = []
    for path in scan_paths:
        candidates.extend(_text_files(path) if path.is_dir() else [path])

    violations = [
        str(path.relative_to(WORKSPACE_ROOT))
        for path in candidates
        if retired_frontend in path.read_text(encoding="utf-8", errors="ignore").lower()
        and path.resolve() != Path(__file__).resolve()
    ]
    assert violations == []
