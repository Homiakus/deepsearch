"""Unit tests for Docker container hardening and Compose profiles (§DS-24)."""

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


def test_dockerfile_hardening():
    """Verify Dockerfile uses multi-stage, non-root user, frozen uv dependencies, and healthcheck."""
    dockerfile_path = WORKSPACE_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist"

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage check
    assert "AS builder" in content
    assert "AS runtime" in content

    # Locked frozen dependency install without editable mode
    assert "uv sync --frozen" in content
    assert "-e ." not in content
    assert "pip install" not in content

    # Non-root unprivileged user check
    assert "useradd" in content
    assert "USER deepsearch" in content

    # Healthcheck presence
    assert "HEALTHCHECK" in content
    assert "/api/v1/health" in content


def test_dockerignore_completeness():
    """Verify .dockerignore ignores development, virtualenv, and secret files."""
    dockerignore_path = WORKSPACE_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist"

    content = dockerignore_path.read_text(encoding="utf-8")

    ignored_items = [".git", "__pycache__", ".venv", ".pytest_cache", "data/", ".env"]
    for item in ignored_items:
        assert item in content, f"Expected '{item}' to be ignored in .dockerignore"


def test_docker_compose_security_and_profiles():
    """Verify docker-compose.yml isolates storage under profile and pins image tags."""
    compose_path = WORKSPACE_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    content = compose_path.read_text(encoding="utf-8")

    # Core scraper-api service
    assert "scraper-api:" in content
    assert "healthcheck:" in content

    # Storage services are profile-gated
    assert "profiles:" in content
    assert "- storage" in content

    # No unpinned 'latest' for databases
    assert "qdrant:latest" not in content
    assert "minio:latest" not in content
    assert "redis:7.4-alpine" in content

    # Storage ports bound to localhost 127.0.0.1
    assert "127.0.0.1:5432:5432" in content
    assert "127.0.0.1:6333:6333" in content
    assert "127.0.0.1:6379:6379" in content
