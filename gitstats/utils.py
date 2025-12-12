# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import os
import re
import sys
import time
import subprocess
from gitstats import ON_LINUX, exectime_external, load_config
from importlib.metadata import version


conf = load_config()


def count_lines_in_text(text):
    """Cross-platform function to count lines in text"""
    if not text or not text.strip():
        return 0
    return len(text.strip().split("\n"))


def filter_lines_by_pattern(text, pattern):
    """Filter out lines matching a pattern (cross-platform grep -v replacement)"""
    if not text or not text.strip():
        return ""
    lines = text.split("\n")
    filtered_lines = [line for line in lines if not re.match(pattern, line)]
    return "\n".join(filtered_lines)


def get_version():
    return version("gitstats")


def get_git_version():
    return get_pipe_output(["git --version"]).split("\n")[0]


def get_gnuplot_version():
    output = get_pipe_output(["%s --version" % gnuplot_cmd]).split("\n")[0]
    return output if output else None


def get_pipe_output(cmds, quiet=False):
    global exectime_external
    start = time.time()
    if not quiet and ON_LINUX and os.isatty(1):
        print(">> " + " | ".join(cmds), end=" ")
        sys.stdout.flush()

    # Handle cross-platform cases
    if len(cmds) == 2 and cmds[1] == "wc -l":
        # Handle line counting cross-platform
        p = subprocess.Popen(cmds[0], stdout=subprocess.PIPE, shell=True)
        output = p.communicate()[0]
        p.wait()
        try:
            text = output.decode("utf-8", errors="replace").rstrip("\n")
        except UnicodeDecodeError:
            # Fallback for binary files
            text = output.decode("latin-1", errors="replace").rstrip("\n")
        line_count = count_lines_in_text(text)
        result = str(line_count)
    elif len(cmds) == 2 and cmds[1].startswith("grep -v"):
        # Handle grep -v cross-platform
        pattern = cmds[1].split("grep -v ")[1]
        p = subprocess.Popen(cmds[0], stdout=subprocess.PIPE, shell=True)
        output = p.communicate()[0]
        p.wait()
        try:
            text = output.decode("utf-8", errors="replace").rstrip("\n")
        except UnicodeDecodeError:
            text = output.decode("latin-1", errors="replace").rstrip("\n")
        result = filter_lines_by_pattern(text, pattern)
    else:
        # Standard pipe behavior for other cases
        p = subprocess.Popen(cmds[0], stdout=subprocess.PIPE, shell=True)
        processes = [p]
        for x in cmds[1:]:
            p = subprocess.Popen(x, stdin=p.stdout, stdout=subprocess.PIPE, shell=True)
            processes.append(p)
        output = p.communicate()[0]
        for p in processes:
            p.wait()
        try:
            result = output.decode("utf-8", errors="replace").rstrip("\n")
        except UnicodeDecodeError:
            result = output.decode("latin-1", errors="replace").rstrip("\n")

    end = time.time()
    if not quiet:
        if ON_LINUX and os.isatty(1):
            print("\r", end=" ")
        print("[%.5f] >> %s" % (end - start, " | ".join(cmds)))
    exectime_external += end - start
    return result


def get_commit_range(defaultrange="HEAD", end_only=False):
    if len(conf["commit_end"]) > 0:
        commit_begin = conf["commit_begin"]

        # Convert commit_begin to string for consistent handling
        commit_begin_str = str(commit_begin)

        # If end_only or no commit_begin specified, return just the end
        if end_only or len(commit_begin_str) == 0:
            return conf["commit_end"]

        # Handle numeric commit_begin as "N commits ago"
        if commit_begin_str.isdigit():
            commit_begin_str = f"{conf['commit_end']}~{commit_begin_str}"

        return "%s..%s" % (commit_begin_str, conf["commit_end"])
    return defaultrange


def get_excluded_extensions():
    """
    Get the set of excluded file extensions from config.
    Returns a set of lowercase extensions.
    """
    exclude_ext_str = conf.get("exclude_exts", "")
    if not exclude_ext_str:
        return set()
    return {ext.strip().lower() for ext in exclude_ext_str.split(",") if ext.strip()}


def should_exclude_file(ext):
    """
    Check if a file should be excluded from line counting based on extension.
    Returns True if the file extension is in the exclude_exts configuration.
    If exclude_exts is empty, no files are excluded (returns False for all).
    """
    # Get excluded extensions from config
    excluded_extensions = get_excluded_extensions()

    # If exclude_exts is empty, don't exclude any files
    if not excluded_extensions:
        return False

    # Check if extension is in the excluded list
    return ext.lower() in excluded_extensions


def get_num_of_lines_in_blob(ext_blob):
    """
    Get number of lines in blob.
    Returns 0 for binary files (detected by null bytes).
    """
    ext, blob_id = ext_blob

    # Skip excluded files
    if should_exclude_file(ext):
        return (ext, blob_id, 0)

    # Check if file is binary by reading first 8192 bytes and looking for null bytes
    try:
        # Here not use get_pipe_output because we need raw bytes
        blob_content = subprocess.check_output(
            ["git", "cat-file", "blob", blob_id], stderr=subprocess.DEVNULL
        )
        # Check first 8KB for null bytes (binary indicator)
        if b"\x00" in blob_content[:8192]:
            return (ext, blob_id, 0)
    except subprocess.CalledProcessError:
        return (ext, blob_id, 0)

    return (
        ext,
        blob_id,
        int(get_pipe_output(["git cat-file blob %s" % blob_id, "wc -l"]).split()[0]),
    )


def get_num_of_files_from_rev(time_rev):
    """
    Get number of files changed in commit
    """
    time, rev = time_rev
    return (
        int(time),
        rev,
        int(
            get_pipe_output(['git ls-tree -r --name-only "%s"' % rev, "wc -l"]).split(
                "\n"
            )[0]
        ),
    )


def get_stat_summary_counts(line):
    numbers = re.findall(r"\d+", line)
    if len(numbers) == 1:
        # neither insertions nor deletions: may probably only happen for "0 files changed"
        numbers.append(0)
        numbers.append(0)
    elif len(numbers) == 2 and line.find("(+)") != -1:
        numbers.append(0)
        # only insertions were printed on line
    elif len(numbers) == 2 and line.find("(-)") != -1:
        numbers.insert(1, 0)
        # only deletions were printed on line
    return numbers


def get_log_range(defaultrange="HEAD", end_only=True):
    commit_range = get_commit_range(defaultrange, end_only)
    if len(conf["start_date"]) > 0:
        return '--since="%s" "%s"' % (conf["start_date"], commit_range)
    return commit_range


# By default, gnuplot from gnuplot-wheel package is used, but can be overridden with the
# environment variable "GNUPLOT"
gnuplot_cmd = os.environ.get("GNUPLOT", "gnuplot")
