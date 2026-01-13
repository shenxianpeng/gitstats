import os
import nox
import shutil
from pathlib import Path

# Default tag for docker images
TAG = "latest"


@nox.session
def lint(session: nox.Session) -> None:
    """Run linter"""
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files", external=True)


@nox.session
def image(session: nox.Session) -> None:
    """Build docker image"""
    session.run("docker", "build", "-t", f"gitstats:{TAG}", ".", external=True)


@nox.session
def publish_image(session: nox.Session) -> None:
    """Publish docker image to ghcr"""
    image(session)  # Build the image first
    session.run(
        "docker",
        "tag",
        f"gitstats:{TAG}",
        f"ghcr.io/shenxianpeng/gitstats:{TAG}",
        external=True,
    )
    session.run("docker", "push", f"ghcr.io/shenxianpeng/gitstats:{TAG}", external=True)


@nox.session
def build(session: nox.Session) -> None:
    """Generate gitstats report and json file"""
    report_dir = Path("test-report")
    if report_dir.exists():
        shutil.rmtree(report_dir)
    session.install("--upgrade", "pip")
    session.install("-e", ".")
    session.run("gitstats", ".", str(report_dir), "-f", "json", external=True)


@nox.session
def preview(session: nox.Session) -> None:
    """Preview gitstats report in local"""
    build(session)  # Generate report first
    python_cmd = "python" if os.name == "nt" else "python3"
    session.run(
        python_cmd, "-m", "http.server", "8000", "-d", "test-report", external=True
    )


@nox.session
def docs(session: nox.Session) -> None:
    """Build docs"""
    session.install("--upgrade", "pip")
    session.install("-e", ".[docs]")
    session.run("sphinx-build", "-b", "html", "docs/source", "docs/build/html")


@nox.session(name="docs-live")
def docs_live(session: nox.Session) -> None:
    session.install("-e", ".[docs]")
    session.run("sphinx-autobuild", "docs/source", "docs/build/html", external=True)


@nox.session
def test(session: nox.Session) -> None:
    """Run tests with pytest"""
    session.install("--upgrade", "pip")
    session.install("-e", ".[test]")
    session.run("pytest", "-v", external=True)


@nox.session
def coverage(session: nox.Session) -> None:
    """Run tests with coverage"""
    session.install("--upgrade", "pip")
    session.install("-e", ".[test]")
    session.run(
        "pytest",
        "--cov=gitstats",
        "--cov-report=term-missing",
        "--cov-report=html",
        "-v",
        external=True,
    )
