"""Pytest configuration and fixtures for gitstats tests."""

import os
import tempfile
import shutil
import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_git_repo(temp_dir):
    """Create a mock git repository for testing."""
    repo_path = os.path.join(temp_dir, "test_repo")
    os.makedirs(repo_path)

    # Initialize a git repo
    os.chdir(repo_path)
    os.system("git init")
    os.system('git config user.email "test@example.com"')
    os.system('git config user.name "Test User"')

    # Create initial commit
    with open(os.path.join(repo_path, "README.md"), "w") as f:
        f.write("# Test Repository\n")
    os.system("git add .")
    os.system('git commit -m "Initial commit"')

    yield repo_path


@pytest.fixture
def config_file(temp_dir):
    """Create a test configuration file."""
    config_path = os.path.join(temp_dir, "test.conf")
    with open(config_path, "w") as f:
        f.write("[gitstats]\n")
        f.write("max_domains = 5\n")
        f.write("max_authors = 10\n")
        f.write("processes = 2\n")
    yield config_path
    if os.path.exists(config_path):
        os.remove(config_path)


@pytest.fixture(autouse=True)
def reset_config():
    """Reset global config between tests."""
    import gitstats

    gitstats._config = None
    yield
    gitstats._config = None
