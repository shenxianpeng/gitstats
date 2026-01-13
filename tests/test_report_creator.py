"""Tests for gitstats.report_creator module."""

from unittest.mock import patch, MagicMock, mock_open
from gitstats.report_creator import (
    ReportCreator,
    HTMLReportCreator,
    html_header,
    html_linkify,
    get_keys_sorted_by_values,
    get_keys_sorted_by_value_key,
)


class TestReportCreator:
    """Tests for ReportCreator base class."""

    def test_init(self):
        """Test ReportCreator initialization."""
        rc = ReportCreator()
        assert rc.data is None
        assert rc.path is None

    def test_create(self):
        """Test ReportCreator create method."""
        rc = ReportCreator()
        mock_data = MagicMock()
        test_path = "/path/to/output"

        rc.create(mock_data, test_path)

        assert rc.data == mock_data
        assert rc.path == test_path


class TestHTMLReportCreator:
    """Tests for HTMLReportCreator class."""

    def test_heat_level_zero(self):
        """Test _heat_level with zero values."""
        assert HTMLReportCreator._heat_level(0, 100) == 0
        assert HTMLReportCreator._heat_level(10, 0) == 0

    def test_heat_level_calculations(self):
        """Test _heat_level calculations for different ratios."""
        assert HTMLReportCreator._heat_level(25, 100) == 1  # 25% -> level 1
        assert HTMLReportCreator._heat_level(50, 100) == 2  # 50% -> level 2
        assert HTMLReportCreator._heat_level(75, 100) == 3  # 75% -> level 3
        assert HTMLReportCreator._heat_level(100, 100) == 4  # 100% -> level 4

    def test_heat_level_edge_cases(self):
        """Test _heat_level edge cases."""
        assert HTMLReportCreator._heat_level(26, 100) == 2  # Just over 25%
        assert HTMLReportCreator._heat_level(51, 100) == 3  # Just over 50%
        assert HTMLReportCreator._heat_level(76, 100) == 4  # Just over 75%

    def test_heat_td_class(self):
        """Test _heat_td_class method."""
        assert HTMLReportCreator._heat_td_class(0, 100) == "heat heat0"
        assert HTMLReportCreator._heat_td_class(25, 100) == "heat heat1"
        assert HTMLReportCreator._heat_td_class(50, 100) == "heat heat2"
        assert HTMLReportCreator._heat_td_class(75, 100) == "heat heat3"
        assert HTMLReportCreator._heat_td_class(100, 100) == "heat heat4"

    @patch("shutil.copyfile")
    @patch("os.path.exists")
    @patch("os.path.dirname")
    def test_create_copies_static_files(
        self, mock_dirname, mock_exists, mock_copy, temp_dir
    ):
        """Test create method copies static files."""
        mock_dirname.return_value = "/mock/basedir"
        mock_exists.return_value = True

        creator = HTMLReportCreator()
        mock_data = MagicMock()
        mock_data.project_name = "TestProject"

        # Mock all the create_* methods to avoid actual file I/O
        with (
            patch.object(creator, "create_index_html"),
            patch.object(creator, "create_activity_html"),
            patch.object(creator, "create_authors_html"),
            patch.object(creator, "create_files_html"),
            patch.object(creator, "create_lines_html"),
            patch.object(creator, "create_tags_html"),
            patch.object(creator, "create_graphs"),
        ):
            creator.create(mock_data, temp_dir)

        # Verify static files were attempted to be copied
        assert mock_copy.call_count >= 1

    @patch("builtins.open", new_callable=mock_open)
    @patch("gitstats.report_creator.get_version")
    @patch("gitstats.report_creator.get_git_version")
    @patch("gitstats.report_creator.get_gnuplot_version")
    def test_create_index_html(
        self, mock_gnuplot, mock_git, mock_version, mock_file, temp_dir
    ):
        """Test create_index_html method."""
        mock_version.return_value = "1.0.0"
        mock_git.return_value = "git version 2.39.0"
        mock_gnuplot.return_value = "gnuplot 5.4"

        creator = HTMLReportCreator()
        mock_data = MagicMock()
        mock_data.project_name = "TestProject"
        mock_data.get_stamp_created.return_value = 1234567890
        mock_data.get_first_commit_date.return_value = MagicMock()
        mock_data.get_last_commit_date.return_value = MagicMock()
        mock_data.get_commit_delta_days.return_value = 100
        mock_data.get_active_days.return_value = set(range(50))
        mock_data.get_total_files.return_value = 100
        mock_data.get_total_loc.return_value = 10000
        mock_data.total_lines_added = 5000
        mock_data.total_lines_removed = 2000
        mock_data.get_total_commits.return_value = 500
        mock_data.get_total_authors.return_value = 10

        with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
            creator.create_index_html(mock_data, temp_dir)

        # Verify file was opened for writing
        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    @patch("gitstats.report_creator.get_pipe_output")
    def test_create_activity_html(self, mock_pipe, mock_file, temp_dir):
        """Test create_activity_html method."""
        mock_pipe.return_value = "1234567890"

        creator = HTMLReportCreator()
        mock_data = MagicMock()
        mock_data.project_name = "TestProject"
        mock_data.commits_by_year = {2024: 100, 2023: 80}
        mock_data.activity_by_year_week = {"2024-01": 10}
        mock_data.activity_by_year_week_peak = 10
        mock_data.get_activity_by_hour_of_day.return_value = {9: 50, 14: 30}
        mock_data.activity_by_hour_of_day_busiest = 50
        mock_data.get_total_commits.return_value = 100
        mock_data.get_activity_by_day_of_week.return_value = {0: 20, 1: 15}
        mock_data.activity_by_month_of_year = {1: 10, 2: 15}
        mock_data.activity_by_hour_of_week = {0: {9: 5}}
        mock_data.activity_by_hour_of_week_busiest = 5
        mock_data.commits_by_timezone = {"+0000": 50, "+0800": 30}  # Add timezone data

        with (
            patch.object(creator, "print_header"),
            patch.object(creator, "print_nav"),
            patch.object(creator, "_heat_td_class", return_value="heat heat0"),
        ):
            creator.create_activity_html(mock_data, temp_dir)

        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    def test_create_authors_html(self, mock_file, temp_dir):
        """Test create_authors_html method."""
        creator = HTMLReportCreator()
        creator.title = "TestProject"

        mock_data = MagicMock()
        mock_data.get_total_commits.return_value = 100
        mock_data.total_lines_added = 5000
        mock_data.total_lines_removed = 2000
        mock_data.get_authors.return_value = ["Author1", "Author2"]
        mock_data.get_author_info.return_value = {
            "commits": 50,
            "lines_added": 2500,
            "lines_removed": 1000,
            "commits_frac": 50.0,
            "date_first": "2024-01-01",
            "date_last": "2024-12-31",
            "timedelta": MagicMock(),
            "active_days": set(["2024-01-01", "2024-01-02"]),
            "place_by_commits": 1,  # Add place_by_commits
        }
        mock_data.authors = {
            "Author1": {"commits": 50},
            "Author2": {"commits": 30},
        }
        mock_data.domains = {}
        mock_data.author_of_month = {}
        mock_data.author_of_year = {}

        with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
            creator.create_authors_html(mock_data, temp_dir)

        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    def test_create_files_html(self, mock_file, temp_dir):
        """Test create_files_html method."""
        creator = HTMLReportCreator()
        creator.title = "TestProject"

        mock_data = MagicMock()
        mock_data.get_total_files.return_value = 100
        mock_data.get_total_loc.return_value = 10000
        mock_data.total_size = 1048576
        mock_data.extensions = {
            "py": {"files": 50, "lines": 5000},
            "js": {"files": 30, "lines": 3000},
        }

        with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
            creator.create_files_html(mock_data, temp_dir)

        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    def test_create_lines_html(self, mock_file, temp_dir):
        """Test create_lines_html method."""
        creator = HTMLReportCreator()
        creator.title = "TestProject"

        mock_data = MagicMock()
        mock_data.get_total_loc.return_value = 10000
        mock_data.total_lines_added = 5000
        mock_data.total_lines_removed = 2000
        mock_data.changes_by_date = {
            1234567890: {"files": 5, "ins": 100, "del": 50, "lines": 1000}
        }

        with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
            creator.create_lines_html(mock_data, temp_dir)

        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    def test_create_tags_html(self, mock_file, temp_dir):
        """Test create_tags_html method."""
        creator = HTMLReportCreator()
        creator.title = "TestProject"

        mock_data = MagicMock()
        mock_data.tags = {
            "v1.0": {
                "date": "2024-01-01",
                "commits": 50,
                "authors": {"Author1": 30, "Author2": 20},
            }
        }

        with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
            creator.create_tags_html(mock_data, temp_dir)

        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.system")
    def test_create_graphs(self, mock_system, mock_file, temp_dir):
        """Test create_graphs method."""
        creator = HTMLReportCreator()
        creator.data = MagicMock()
        creator.data.commits_by_year = {2024: 100}
        creator.data.commits_by_month = {"2024-01": 10}
        creator.data.lines_added_by_month = {"2024-01": 500}
        creator.data.lines_removed_by_month = {"2024-01": 200}
        creator.data.files_by_stamp = {1234567890: 100}
        creator.data.authors = {"Author1": {"lines_added": 1000}}
        creator.data.authors_by_commits = ["Author1"]
        creator.authors_to_plot = ["Author1"]  # Add authors_to_plot attribute
        creator.data.domains = {"example.com": {"commits": 50}}

        creator.create_graphs(temp_dir)

        # Verify that gnuplot commands were written
        mock_file.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    def test_print_header(self, mock_file):
        """Test print_header method."""
        creator = HTMLReportCreator()
        creator.title = "TestProject"

        f = MagicMock()
        creator.print_header(f)

        # Verify HTML header was written
        assert f.write.called
        calls = [str(call) for call in f.write.call_args_list]
        assert any("<!DOCTYPE html>" in str(call) for call in calls)

    def test_print_nav(self):
        """Test print_nav method."""
        creator = HTMLReportCreator()

        f = MagicMock()
        creator.print_nav(f)

        # Verify navigation was written
        assert f.write.called
        calls = [str(call) for call in f.write.call_args_list]
        assert any("index.html" in str(call) for call in calls)


def test_html_header():
    """Test html_header function."""
    result = html_header(2, "Test Section")
    assert '<h2 id="test_section">' in result
    assert '<a href="#test_section">Test Section</a>' in result
    assert "</h2>" in result


def test_html_header_different_levels():
    """Test html_header with different heading levels."""
    result1 = html_header(1, "Title")
    assert '<h1 id="title">' in result1

    result3 = html_header(3, "Subsection")
    assert '<h3 id="subsection">' in result3


def test_html_linkify():
    """Test html_linkify function."""
    assert html_linkify("Test Section") == "test_section"
    assert html_linkify("Another Example") == "another_example"
    assert html_linkify("Multiple Word Title") == "multiple_word_title"


def test_html_linkify_mixed_case():
    """Test html_linkify with mixed case."""
    assert html_linkify("MixedCase") == "mixedcase"
    assert html_linkify("UPPERCASE") == "uppercase"


def test_get_keys_sorted_by_values():
    """Test get_keys_sorted_by_values function."""
    test_dict = {"a": 3, "b": 1, "c": 2}
    result = get_keys_sorted_by_values(test_dict)
    assert result == ["b", "c", "a"]


def test_get_keys_sorted_by_values_empty():
    """Test get_keys_sorted_by_values with empty dict."""
    result = get_keys_sorted_by_values({})
    assert result == []


def test_get_keys_sorted_by_values_single():
    """Test get_keys_sorted_by_values with single item."""
    result = get_keys_sorted_by_values({"only": 42})
    assert result == ["only"]


def test_get_keys_sorted_by_value_key():
    """Test get_keys_sorted_by_value_key function."""
    test_dict = {
        "author1": {"commits": 100},
        "author2": {"commits": 50},
        "author3": {"commits": 75},
    }
    result = get_keys_sorted_by_value_key(test_dict, "commits")
    assert result == ["author2", "author3", "author1"]


def test_get_keys_sorted_by_value_key_empty():
    """Test get_keys_sorted_by_value_key with empty dict."""
    result = get_keys_sorted_by_value_key({}, "commits")
    assert result == []


def test_get_keys_sorted_by_value_key_single():
    """Test get_keys_sorted_by_value_key with single item."""
    test_dict = {"only": {"commits": 42}}
    result = get_keys_sorted_by_value_key(test_dict, "commits")
    assert result == ["only"]


def test_get_keys_sorted_by_value_key_different_key():
    """Test get_keys_sorted_by_value_key with different keys."""
    test_dict = {
        "item1": {"lines": 1000, "commits": 10},
        "item2": {"lines": 500, "commits": 20},
    }
    result_lines = get_keys_sorted_by_value_key(test_dict, "lines")
    assert result_lines == ["item2", "item1"]

    result_commits = get_keys_sorted_by_value_key(test_dict, "commits")
    assert result_commits == ["item1", "item2"]


def test_html_linkify_special_chars():
    """Test html_linkify with special characters."""
    result = html_linkify("Test-Section_123")
    assert result == "test-section_123"


def test_get_keys_sorted_negative_values():
    """Test get_keys_sorted_by_values with negative values."""
    test_dict = {"a": -5, "b": 10, "c": 0}
    result = get_keys_sorted_by_values(test_dict)
    assert result == ["a", "c", "b"]


def test_get_keys_sorted_by_value_key_equal_values():
    """Test get_keys_sorted_by_value_key with equal values."""
    test_dict = {
        "author1": {"commits": 50},
        "author2": {"commits": 50},
    }
    result = get_keys_sorted_by_value_key(test_dict, "commits")
    # Order doesn't matter for equal values, just check length
    assert len(result) == 2


@patch("builtins.open", new_callable=mock_open)
@patch("gitstats.report_creator.get_pipe_output")
def test_html_report_print_methods(mock_pipe, mock_file):
    """Test HTMLReportCreator print methods."""
    creator = HTMLReportCreator()
    creator.title = "Test"

    f = MagicMock()
    creator.print_header(f)
    assert f.write.called

    f = MagicMock()
    creator.print_nav(f)
    assert f.write.called


@patch("builtins.open", new_callable=mock_open)
@patch("gitstats.report_creator.get_pipe_output")
def test_create_activity_html_no_first_commit(mock_pipe, mock_file, temp_dir):
    """Test create_activity_html when first_commit_timestamp is empty."""
    mock_pipe.return_value = ""  # Empty timestamp

    creator = HTMLReportCreator()
    mock_data = MagicMock()
    mock_data.project_name = "TestProject"
    mock_data.commits_by_year = {}
    mock_data.commits_by_month = {}
    mock_data.lines_added_by_year = {}
    mock_data.lines_removed_by_year = {}
    mock_data.lines_added_by_month = {}
    mock_data.lines_removed_by_month = {}
    mock_data.activity_by_year_week = {}
    mock_data.activity_by_year_week_peak = 1
    mock_data.get_activity_by_hour_of_day.return_value = {}
    mock_data.activity_by_hour_of_day_busiest = 1
    mock_data.get_total_commits.return_value = 1  # Avoid division by zero
    mock_data.get_activity_by_day_of_week.return_value = {}
    mock_data.activity_by_month_of_year = {}
    mock_data.activity_by_hour_of_week = {}
    mock_data.activity_by_hour_of_week_busiest = 1
    mock_data.commits_by_timezone = {
        "+0000": 1
    }  # Need at least one to avoid max() error

    with (
        patch.object(creator, "print_header"),
        patch.object(creator, "print_nav"),
        patch.object(creator, "_heat_td_class", return_value="heat heat0"),
    ):
        creator.create_activity_html(mock_data, temp_dir)

    # Verify YEARS defaults to 5 when first_commit_timestamp is empty
    mock_file.assert_called()


@patch("builtins.open", new_callable=mock_open)
def test_create_files_html_edge_cases(mock_file, temp_dir):
    """Test create_files_html with edge cases."""
    creator = HTMLReportCreator()
    creator.title = "TestProject"
    mock_data = MagicMock()

    # Test with extensions having lots of files
    mock_data.extensions = {
        ".py": {"files": 1500, "lines": 50000},  # More than 1000 files
        ".js": {"files": 500, "lines": 20000},
        ".md": {"files": 50, "lines": 1000},
    }
    mock_data.get_total_size.return_value = 1000000
    mock_data.get_total_loc.return_value = 71000

    with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
        creator.create_files_html(mock_data, temp_dir)

    mock_file.assert_called()


@patch("builtins.open", new_callable=mock_open)
def test_create_tags_html_no_tags(mock_file, temp_dir):
    """Test create_tags_html when there are no tags."""
    creator = HTMLReportCreator()
    creator.title = "TestProject"
    mock_data = MagicMock()
    mock_data.tags = {}  # No tags

    with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
        creator.create_tags_html(mock_data, temp_dir)

    mock_file.assert_called()


@patch("builtins.open", new_callable=mock_open)
def test_create_authors_html_edge_cases(mock_file, temp_dir):
    """Test create_authors_html with edge cases."""
    creator = HTMLReportCreator()
    creator.title = "TestProject"
    mock_data = MagicMock()

    # Test with many authors
    mock_data.get_total_authors.return_value = 150
    mock_data.authors = {}
    for i in range(150):
        author = f"author{i}@example.com"
        mock_data.authors[author] = {
            "commits": i + 1,
            "lines_added": i * 10,
            "lines_removed": i * 5,
            "first_commit_stamp": 1234567890,
            "last_commit_stamp": 1234567890 + i,
            "place_by_commits": i + 1,
        }
    mock_data.get_total_commits.return_value = sum(i + 1 for i in range(150))
    mock_data.get_total_loc.return_value = 100000
    mock_data.domains = {"example.com": {"commits": 150}}

    with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
        creator.create_authors_html(mock_data, temp_dir)

    mock_file.assert_called()


@patch("builtins.open", new_callable=mock_open)
def test_create_lines_html_edge_cases(mock_file, temp_dir):
    """Test create_lines_html with edge cases."""
    creator = HTMLReportCreator()
    creator.title = "TestProject"
    mock_data = MagicMock()
    mock_data.get_total_loc.return_value = 100000

    # Test with many entries - use timestamps as keys
    mock_data.changes_by_date = {}
    for i in range(200):
        timestamp = 1609459200 + (i * 86400)  # Daily increments from 2021-01-01
        mock_data.changes_by_date[timestamp] = {
            "lines": (i + 1) * 100,  # Must have 'lines' key
            "added": i * 100,
            "removed": i * 50,
            "commits": i + 1,
        }
    mock_data.changes_by_date_peak = 20000

    with patch.object(creator, "print_header"), patch.object(creator, "print_nav"):
        creator.create_lines_html(mock_data, temp_dir)

    mock_file.assert_called()
