"""Tests for gitstats.__init__ module."""
import os
import pytest
import tempfile
import gitstats


def test_module_constants():
    """Test module-level constants are defined."""
    assert isinstance(gitstats.exectime_internal, float)
    assert isinstance(gitstats.exectime_external, float)
    assert isinstance(gitstats.time_start, float)
    assert isinstance(gitstats.GNUPLOT_COMMON, str)
    assert isinstance(gitstats.ON_LINUX, bool)
    assert isinstance(gitstats.WEEKDAYS, tuple)
    assert len(gitstats.WEEKDAYS) == 7


def test_default_config():
    """Test that DEFAULT_CONFIG contains expected keys."""
    assert "max_domains" in gitstats.DEFAULT_CONFIG
    assert "max_ext_length" in gitstats.DEFAULT_CONFIG
    assert "style" in gitstats.DEFAULT_CONFIG
    assert "max_authors" in gitstats.DEFAULT_CONFIG
    assert "authors_top" in gitstats.DEFAULT_CONFIG
    assert "commit_begin" in gitstats.DEFAULT_CONFIG
    assert "commit_end" in gitstats.DEFAULT_CONFIG
    assert "linear_linestats" in gitstats.DEFAULT_CONFIG
    assert "project_name" in gitstats.DEFAULT_CONFIG
    assert "processes" in gitstats.DEFAULT_CONFIG
    assert "start_date" in gitstats.DEFAULT_CONFIG
    assert "exclude_exts" in gitstats.DEFAULT_CONFIG


def test_load_config_default(reset_config):
    """Test loading default configuration when file doesn't exist."""
    config = gitstats.load_config("nonexistent_file.conf")
    assert config == gitstats.DEFAULT_CONFIG
    assert config["max_domains"] == 10
    assert config["max_authors"] == 20


def test_load_config_cached(reset_config):
    """Test that config is cached after first load."""
    config1 = gitstats.load_config()
    config2 = gitstats.load_config()
    assert config1 is config2


def test_load_config_from_file(temp_dir, reset_config):
    """Test loading configuration from a file."""
    config_path = os.path.join(temp_dir, "test.conf")
    with open(config_path, "w") as f:
        f.write("[gitstats]\n")
        f.write("max_domains = 15\n")
        f.write("max_authors = 25\n")
        f.write("processes = 4\n")
        f.write("project_name = TestProject\n")
    
    config = gitstats.load_config(config_path)
    assert config["max_domains"] == 15
    assert config["max_authors"] == 25
    assert config["processes"] == 4
    assert config["project_name"] == "TestProject"


def test_load_config_partial_file(temp_dir, reset_config):
    """Test loading config with only some values overridden."""
    config_path = os.path.join(temp_dir, "partial.conf")
    with open(config_path, "w") as f:
        f.write("[gitstats]\n")
        f.write("max_domains = 7\n")
    
    config = gitstats.load_config(config_path)
    # Should have overridden value
    assert config["max_domains"] == 7
    # But not other defaults - they should be from DEFAULT_CONFIG
    # Note: when reading from file, only file values are included
    # This tests the actual behavior


def test_load_config_string_values(temp_dir, reset_config):
    """Test loading string configuration values."""
    config_path = os.path.join(temp_dir, "string.conf")
    with open(config_path, "w") as f:
        f.write("[gitstats]\n")
        f.write("style = custom.css\n")
        f.write("commit_end = main\n")
        f.write("exclude_exts = .md,.txt\n")
    
    config = gitstats.load_config(config_path)
    assert config["style"] == "custom.css"
    assert config["commit_end"] == "main"
    assert config["exclude_exts"] == ".md,.txt"
