# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others (see doc/AUTHOR)
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
    p = subprocess.Popen(cmds[0], stdout=subprocess.PIPE, shell=True)
    processes = [p]
    for x in cmds[1:]:
        p = subprocess.Popen(x, stdin=p.stdout, stdout=subprocess.PIPE, shell=True)
        processes.append(p)
    output = p.communicate()[0]
    for p in processes:
        p.wait()
    end = time.time()
    if not quiet:
        if ON_LINUX and os.isatty(1):
            print("\r", end=" ")
        print("[%.5f] >> %s" % (end - start, " | ".join(cmds)))
    exectime_external += end - start
    return output.decode("utf-8").rstrip("\n")


def get_commit_range(defaultrange="HEAD", end_only=False):
    if len(conf["commit_end"]) > 0:
        if end_only or len(conf["commit_begin"]) == 0:
            return conf["commit_end"]
        return "%s..%s" % (conf["commit_begin"], conf["commit_end"])
    return defaultrange


def get_num_of_lines_in_blob(ext_blob):
    """
    Get number of lines in blob
    """
    ext, blob_id = ext_blob
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


# By default, gnuplot is searched from path, but can be overridden with the
# environment variable "GNUPLOT"
gnuplot_cmd = "gnuplot"
if "GNUPLOT" in os.environ:
    gnuplot_cmd = os.environ["GNUPLOT"]
