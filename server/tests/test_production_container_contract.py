from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_never_builds_images_on_the_target_server() -> None:
    compose = (REPO_ROOT / "compose.production.yml").read_text(encoding="utf-8")

    assert "build:" not in compose
    assert "dockerfile:" not in compose
    assert "new-drug-intelligence-api:${RELEASE_VERSION:-latest}" in compose
    assert "new-drug-intelligence-web:${RELEASE_VERSION:-latest}" in compose
    assert compose.count("pull_policy: never") == 2


def test_release_deploy_requires_packaged_images_and_disables_builds() -> None:
    deploy = (REPO_ROOT / "deployment" / "intranet" / "deploy.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$ForceBuild" not in deploy
    assert 'Invoke-Compose -Arguments @("build"' not in deploy
    assert (
        'Invoke-Compose -Arguments @("up", "-d", "--pull", "never", "--no-build"'
        in deploy
    )
    assert "production-images.tar" in deploy
    assert "Packaged production images are missing" in deploy


def test_backend_container_uses_headless_browser_only_and_no_curl() -> None:
    dockerfile = (REPO_ROOT / "server" / "Dockerfile").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "compose.production.yml").read_text(encoding="utf-8")

    assert "curl" not in dockerfile
    assert "FROM python:3.11-slim@sha256:" in dockerfile
    assert "playwright install --only-shell chromium" in dockerfile
    assert '["CMD", "python", "-c"' in compose
    assert "urllib.request.urlopen" in compose
    assert "data.get('status') == 'ok'" in compose
    assert "data.get('database') == 'ok'" in compose


def test_build_only_compose_keeps_source_build_configuration_out_of_production() -> None:
    build_compose = (REPO_ROOT / "compose.build.yml").read_text(encoding="utf-8")

    assert "server/Dockerfile" in build_compose
    assert "web/Dockerfile.production" in build_compose
