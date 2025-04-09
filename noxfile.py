import nox
import shutil
from pathlib import Path

# Default tag for docker images
TAG = "latest"


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


@nox.session(name="install-deps")
def install_deps(session: nox.Session) -> None:
    """Install gnuplot"""
    session.run("sudo", "apt", "update", "-y", external=True)
    session.run("sudo", "apt", "install", "gnuplot", "-y", external=True)


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
    session.run(
        "python3", "-m", "http.server", "8000", "-d", "test-report", external=True
    )


@nox.session
def docs(session: nox.Session) -> None:
    """Build docs"""
    session.install("--upgrade", "pip")
    session.install("-r", "docs/requirements.txt")
    session.run("sphinx-build", "-b", "html", "docs", "docs/build/html")


@nox.session(name="docs-live")
def docs_live(session: nox.Session) -> None:
    session.install("-r", "docs/requirements.txt", "sphinx-autobuild")
    session.run("sphinx-autobuild", "docs", "docs/build/html")
