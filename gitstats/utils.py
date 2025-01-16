# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others (see doc/AUTHOR)
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import os
import sys
import time
import subprocess
from gitstats import ON_LINUX, exectime_external, load_config
from importlib.metadata import version


conf = load_config()


def getversion():
    return version("gitstats")


def getgitversion():
    return getpipeoutput(["git --version"]).split("\n")[0]


def getgnuplotversion():
    output = getpipeoutput(["%s --version" % gnuplot_cmd]).split("\n")[0]
    return output if output else None


def getpipeoutput(cmds, quiet=False):
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


def getcommitrange(defaultrange="HEAD", end_only=False):
    if len(conf["commit_end"]) > 0:
        if end_only or len(conf["commit_begin"]) == 0:
            return conf["commit_end"]
        return "%s..%s" % (conf["commit_begin"], conf["commit_end"])
    return defaultrange


# By default, gnuplot is searched from path, but can be overridden with the
# environment variable "GNUPLOT"
gnuplot_cmd = "gnuplot"
if "GNUPLOT" in os.environ:
    gnuplot_cmd = os.environ["GNUPLOT"]
