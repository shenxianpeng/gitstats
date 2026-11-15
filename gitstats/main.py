# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The gitstats command: its arguments, and a run from one repository, or
several, to the report (see gitstats.collector for what a report is made from).
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import gitstats
from gitstats import check_git_settings, load_config, parse_config_value, time_start, utils
from gitstats.aggregate import (
    AggregateReportCreator,
    _slugify_repo,
    compute_repo_summary,
    write_repo_summary,
)
from gitstats.ai_summarizer import AISummarizer
from gitstats.collector import DataCollector, GitDataCollector
from gitstats.report_creator import HTMLReportCreator
from gitstats.utils import get_version
from gitstats.wrapped import (
    THEMES,
    WrappedCardGenerator,
    remove_wrapped_page,
    write_card_data,
    write_wrapped_page,
)

logger = logging.getLogger("gitstats")

conf = load_config()


def configure_logging(verbose: bool = False, quiet: bool = False) -> None:
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,
    )


def _prepare_output_dir(path: str) -> str:
    """Create an output directory and return its resolved path.

    The directory name is reduced to its basename, re-anchored under its
    parent and checked to stay there before creation, so a crafted value
    cannot escape the intended location.
    """
    base = os.path.dirname(os.path.abspath(path))
    target = os.path.abspath(os.path.join(base, os.path.basename(os.path.abspath(path))))
    if os.path.commonpath([base, target]) != base:
        raise ValueError(f"Refusing to create output directory outside {base}")
    try:
        os.makedirs(target, exist_ok=True)
    except FileExistsError:
        pass  # a file: the caller says it is not a directory
    except OSError as e:
        raise RuntimeError(f"Cannot create the output directory {target}: {e.strerror}") from e
    return target


def _check_output_dir(path: str, json_beside: bool = False) -> None:
    """Fail before the history is read, not after, when the report cannot be
    written: ``path`` is not a directory, or not one gitstats can write to
    (nor, with ``json_beside``, the directory the JSON goes to beside it, or
    that JSON when it is there already).

    Raises:
        RuntimeError: saying which.
    """
    if not os.path.isdir(path):
        raise RuntimeError(f"Output path is not a directory: {path}")
    targets = [path]
    if json_beside:
        # the folder it goes in, and the file when an earlier run left one
        targets.append(os.path.dirname(path))
        if os.path.exists(path + ".json"):
            targets.append(path + ".json")
    for target in targets:
        if not os.access(target, os.W_OK):
            raise RuntimeError(f"Cannot write to {target}: permission denied")


def _git(gitpath: str, *args: str) -> subprocess.CompletedProcess[str]:
    """``git <args>`` run in ``gitpath``, its output read as UTF-8."""
    return subprocess.run(
        ["git", *args],
        cwd=gitpath,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git_answer(gitpath: str, *args: str) -> str | None:
    """What ``git <args>`` prints in ``gitpath``, or None when it fails."""
    result = _git(gitpath, *args)
    return result.stdout.strip() if result.returncode == 0 else None


def _top_folder(gitpath: str) -> str:
    """The top folder of the repository ``gitpath`` is a folder of, or
    ``gitpath`` itself (a repository's top, a bare repository, ``.git``)."""
    if _git_answer(gitpath, "rev-parse", "--show-prefix"):
        return _git_answer(gitpath, "rev-parse", "--show-toplevel") or gitpath
    return gitpath


def _repository_root(gitpath: str) -> str:
    """The repository ``gitpath`` is, or is in, checked before its history is read.

    A folder inside a repository gives the repository's top folder, with a
    warning: git reads the history of the whole repository, and a report
    that took its files from the folder and its commits from the whole
    would mix the two.

    Raises:
        RuntimeError: when it is not a git repository, git will not read it
            (with git's reason, such as a repository owned by someone else),
            it has no commits, or the configured commit_end or commit_begin
            is not a commit there.
    """
    try:
        check_git_settings(conf)
    except ValueError as e:
        raise RuntimeError(str(e)) from e
    found = _git(gitpath, "rev-parse", "--git-dir")
    if found.returncode != 0:
        reason = found.stderr.strip()
        if not reason or "not a git repository" in reason:
            raise RuntimeError(f"Not a git repository: {gitpath}")
        raise RuntimeError(f"git cannot read {gitpath}: {reason}")
    top = _top_folder(gitpath)
    if top != gitpath:
        logger.warning(
            f"{gitpath} is a folder of the repository {top}: the report is of the whole repository"
        )
        gitpath = top
    for key in ("commit_end", "commit_begin"):
        value = str(conf.get(key) or "")
        if not value or (key == "commit_begin" and value.isascii() and value.isdigit()):
            continue  # a commit_begin of N is the last N commits
        # The value cannot be taken for an option: check_git_settings()
        # refuses one that starts with "-". No --end-of-options, which
        # rev-parse has only from git 2.30; and the revision is found
        # first, then checked to be a commit, as "<rev>^{commit}" would
        # make ":/<text>" search for "<text>^{commit}".
        found_rev = _git_answer(gitpath, "rev-parse", "--verify", "--quiet", value)
        if found_rev is None or (
            _git_answer(gitpath, "rev-parse", "--verify", "--quiet", found_rev + "^{commit}")
            is None
        ):
            if not _git_answer(gitpath, "rev-list", "-n", "1", "--all"):
                raise RuntimeError(f"No commits to analyze: the repository {gitpath} is empty")
            raise RuntimeError(f"{key} {value!r} is not a commit of {gitpath}")
    return gitpath


def normalize_site_url(url: str) -> str:
    """Check a ``site_url`` and give it a trailing slash; "" stays "".

    Raises:
        ValueError: when it is not an http(s) address of a directory.
    """
    url = url.strip()
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ValueError(
            f"site_url must be an http(s) address like https://example.com/report/, got {url!r}"
        )
    return url.rstrip("/") + "/"


def _generate_ai_summaries(
    data: Any, conf: dict[str, Any], outputpath: str
) -> dict[str, dict[str, Any]]:
    """The AI summaries of the report's pages, page type -> {summary, error}.

    Whatever goes wrong here, the report is still written: without the
    summaries when the provider cannot be set up or the run is interrupted
    (Ctrl-C) while they are being written, and with the reason on the AI
    Insights page for each one that failed.
    """
    logger.info("Generating AI summaries...")
    try:
        summarizer = AISummarizer(conf)
        summarizer.set_cache_dir(os.path.join(outputpath, ".ai_cache"))
        summaries = summarizer.generate_all_summaries(data.__dict__, conf.get("refresh_ai", False))
    except KeyboardInterrupt:
        logger.warning("AI summaries interrupted: the report is written without them")
        return {}
    except Exception as e:
        logger.warning(f"No AI summaries: {e}")
        logger.info("Report will be generated without AI insights")
        return {}
    failed = [page for page, result in summaries.items() if result.get("error")]
    if failed:
        logger.warning(
            f"AI summaries: {len(summaries) - len(failed)} of {len(summaries)} written; "
            f"failed: {', '.join(failed)} (the reason is on the AI Insights page)"
        )
    else:
        logger.info(f"AI summaries: {len(summaries)} of {len(summaries)} written")
    return summaries


def _run_single_repo(
    gitpath: str,
    outputpath: str,
    extra_fmt: str | None = None,
    project_name: str | None = None,
    json_sibling: bool = True,
    site_url: str = "",
    wrapped_config: dict[str, Any] | None = None,
) -> DataCollector:
    """Collect, refine and render the full report for one repository.

    Args:
        gitpath: path to the git repository
        outputpath: directory receiving this repository's report
        extra_fmt: extra output format ("json")
        project_name: overrides the report's project name (multi-repo runs
            ignore the process-global ``project_name`` config, which would
            rename every repository identically)
        json_sibling: write the extra JSON next to the output directory
            (single-repo behavior) instead of inside it
        site_url: the report's public address, ending in "/" ("" if unknown)
        wrapped_config: the Wrapped card to write next to the report, if any
    Returns:
        the populated collector
    """
    if not os.path.isdir(gitpath):
        raise RuntimeError(f"Git path is not a directory: {gitpath}")
    gitpath = _repository_root(gitpath)

    outputpath = _prepare_output_dir(outputpath)
    _check_output_dir(outputpath, json_beside=extra_fmt == "json" and json_sibling)

    logger.info(f"Output path: {outputpath}")
    cachefile = os.path.join(outputpath, "gitstats.cache")

    data = GitDataCollector()
    data.load_cache(cachefile)

    logger.info(f"Git path: {gitpath}")
    prevdir = os.getcwd()
    os.chdir(gitpath)
    try:
        logger.info("Collecting data...")
        data.collect(gitpath)
    finally:
        os.chdir(prevdir)

    if project_name is not None:
        data.project_name = project_name

    logger.info("Refining data...")
    data.save_cache(cachefile)
    data.refine()

    # Generate AI summaries if enabled
    if conf.get("ai_enabled", False):
        data.ai_summaries = _generate_ai_summaries(data, conf, outputpath)
    else:
        data.ai_summaries = {}

    # The card comes first, so the report can show it and link to it
    wrapped_card = None
    if wrapped_config and wrapped_config.get("enabled", False):
        wrapped_card = _write_wrapped_card(data, outputpath, wrapped_config)

    logger.info("Generating report...")
    html_report = HTMLReportCreator()
    html_report.site_url = site_url
    html_report.wrapped_card = wrapped_card
    html_report.create(data, outputpath)
    # the card's own page, with the report's header and nav around it
    if wrapped_card:
        write_wrapped_page(html_report, outputpath, wrapped_card)
    else:
        remove_wrapped_page(outputpath)
    if site_url:
        logger.info(f"README badge: [![GitStats]({site_url}badge.svg)]({site_url})")
        logger.info(f"More badges: {site_url}badges.html")

    if extra_fmt:
        if extra_fmt == "json":
            if json_sibling:
                sibling = os.path.join(gitpath, f"{outputpath}.{extra_fmt}")
                _dump_json_within(os.path.dirname(sibling), os.path.basename(sibling), data)
            else:
                _dump_json_within(outputpath, "gitstats.json", data)
        else:
            raise RuntimeError(f"Unsupported format '{extra_fmt}'")

    return data


def _write_wrapped_card(
    data: DataCollector, outputpath: str, wrapped_config: dict[str, Any]
) -> dict[str, Any] | None:
    """Write the Repo Wrapped card for one repository.

    The card goes into the report directory as ``wrapped-<year>.svg``, or
    to the file ``wrapped_config["output"]`` names, whose directory must
    already exist. The card is an extra: when it cannot be written, or the
    year has no commits to put on it, that is logged and the run carries on
    with the report it has.

    A card in the report directory gets its numbers next to it, as
    ``wrapped-<year>.json``.

    Returns what the report needs to show the card, or None when there is no
    card there: none was written, or it was written elsewhere. ``{"year",
    "theme", "file", "data", "stats", "svg"}``: the names of the card and of
    its data in the report directory, the card's numbers and the card itself.
    """
    logger.info("Generating Wrapped card...")
    try:
        generator = WrappedCardGenerator(
            data=data,
            year=wrapped_config.get("year"),
            theme=wrapped_config.get("theme", "midnight"),
        )
        target = os.path.abspath(
            wrapped_config.get("output")
            or os.path.join(outputpath, f"wrapped-{generator.year}.svg")
        )
        # generate() keeps only the file name and writes it inside base_dir
        written = generator.generate(output_path=target, base_dir=os.path.dirname(target))
    except Exception as e:
        logger.warning(f"Failed to generate Wrapped card: {e}")
        return None
    if os.path.dirname(written) != os.path.abspath(outputpath) or generator.stats is None:
        return None  # written elsewhere: the report has nothing next to it to show
    file = os.path.basename(written)
    return {
        "year": generator.year,
        "theme": generator.theme_name,
        "file": file,
        "data": write_card_data(outputpath, generator.stats, generator.theme_name, file),
        "stats": generator.stats,
        "svg": generator.svg,
    }


def _dump_json_within(directory: str, filename: str, data: DataCollector) -> None:
    """Write the collector dump as JSON inside ``directory``.

    The target is resolved from the basename only and checked to stay under
    ``directory`` before writing, guarding against directory traversal.
    """
    base = os.path.abspath(directory)
    target = os.path.abspath(os.path.join(base, os.path.basename(filename)))
    if os.path.commonpath([base, target]) != base:
        raise ValueError(f"Refusing to write outside output directory: {filename}")
    logger.info(f'Generating JSON file: "{target}"')
    with open(target, "w", encoding="utf-8") as file:
        json.dump(data.__dict__, file, default=str)


def run(
    gitpath: list[str],
    outputpath: str,
    extra_fmt: str | None = None,
    wrapped_config: dict[str, Any] | None = None,
) -> int:
    """Run the gitstats program.

    With one repository path the report lands directly in ``outputpath``
    (the historical layout). With several paths each repository gets its own
    subdirectory plus a ``summary.json``, and an aggregate portfolio page is
    written at ``outputpath/index.html``.

    Args:
        gitpath: list of paths to git repositories
        outputpath: path to the output directory
        extra_fmt: extra format
        wrapped_config: the Wrapped card to write next to each report, if any
    Returns:
        0 if at least one repository was analyzed, 1 otherwise
    """
    rundir = os.getcwd()

    try:
        outputpath = _prepare_output_dir(outputpath)
        _check_output_dir(outputpath)
    except RuntimeError as e:
        logger.error(f"FATAL: {e}")
        return 1

    try:
        site_url = normalize_site_url(str(conf.get("site_url", "") or ""))
    except ValueError as e:
        logger.error(f"FATAL: {e}")
        return 1

    exit_code = 0
    try:
        if len(gitpath) == 1:
            try:
                data = _run_single_repo(
                    gitpath[0],
                    outputpath,
                    extra_fmt,
                    site_url=site_url,
                    wrapped_config=wrapped_config,
                )
            except RuntimeError as e:
                logger.error(f"FATAL: {e}")
                return 1
            write_repo_summary(compute_repo_summary(data, "index.html"), outputpath)
        else:
            exit_code = _run_multi_repo(
                gitpath, outputpath, extra_fmt, site_url=site_url, wrapped_config=wrapped_config
            )
    finally:
        os.chdir(rundir)

    time_end = time.time()
    exectime_internal = time_end - time_start
    # read off the module that adds to it, not a copy made when it was 0
    exectime_external = utils.exectime_external
    logger.info(
        f"Execution time {exectime_internal:.5f} secs, {exectime_external:.5f} secs in "
        "external commands (added up: several run at once)"
    )
    if sys.stdin.isatty():
        logger.info("To view the report, re-run with --serve (see gitstats --help)")

    return exit_code


def _server_urls(host: str, port: int) -> tuple[str, str | None]:
    """Return the (local, network) URLs to show for a bound server.

    ``network`` is None when the server is only reachable from this machine
    (loopback binds). Binding ``0.0.0.0`` probes the machine's LAN address;
    any other address is reachable at that address directly.
    """
    # The preview server intentionally speaks plain HTTP: it serves a static
    # report the user just generated, on an address they chose. Loopback URLs
    # fall under the S5332 exception; the exposed variants are marked NOSONAR.
    if host == "localhost":
        return f"http://localhost:{port}/", None
    if host == "::1":
        return f"http://[::1]:{port}/", None
    if host == "127.0.0.1":
        return f"http://127.0.0.1:{port}/", None
    if host == "0.0.0.0":  # noqa: S104 - user explicitly asked to expose
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("192.0.2.1", 80))  # no traffic sent; picks the outbound iface
                lan_ip = probe.getsockname()[0]
            finally:
                probe.close()
        except OSError:
            lan_ip = socket.gethostname()
        return f"http://127.0.0.1:{port}/", f"http://{lan_ip}:{port}/"  # NOSONAR
    url = f"http://{host}:{port}/"  # NOSONAR
    return url, url


def _make_server(outputpath: str, host: str, port: int) -> ThreadingHTTPServer:
    """Build a static file server rooted at the report directory."""
    handler = partial(SimpleHTTPRequestHandler, directory=outputpath)
    return ThreadingHTTPServer((host, port), handler)


def _serve_report(outputpath: str, host: str, port: int) -> int:
    """Serve the generated report until interrupted. Returns an exit code."""
    try:
        server = _make_server(outputpath, host, port)
    except OSError as e:
        logger.error(f"Cannot serve on {host}:{port}: {e}")
        return 1

    bound_port = server.server_address[1]
    local_url, network_url = _server_urls(host, bound_port)
    network_line = network_url or "use --host 0.0.0.0 to expose"
    print(f"\n  gitstats v{get_version()}  report ready\n")
    print(f"  ➜  Local:    {local_url}")
    print(f"  ➜  Network:  {network_line}\n")
    print("  press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        server.server_close()
    return 0


def _run_multi_repo(
    gitpaths: list[str],
    outputpath: str,
    extra_fmt: str | None = None,
    site_url: str = "",
    wrapped_config: dict[str, Any] | None = None,
) -> int:
    """Analyze several repositories and assemble the portfolio page.

    ``site_url`` is the portfolio's address; each repository's report sits
    in its own subdirectory under it. ``wrapped_config`` asks for a Wrapped
    card next to each repository's report.
    """
    summaries = []
    failures = []
    # every folder given out, as compared: a file system may not tell "Foo" from "foo"
    used_slugs: set[str] = set()
    for path in gitpaths:
        try:
            # a folder of a repository is reported, and named, as the repository
            slug = _slugify_repo(_top_folder(path) if os.path.isdir(path) else path)
        except ValueError as e:
            logger.warning(f"Skipping repository {path!r}: {e}")
            failures.append({"name": path, "path": path, "error": str(e)})
            continue
        # "foo", then "foo-2", "foo-3"...: the first that no repository has,
        # "foo-2" of a repository named so among them
        base, count = slug, 1
        while slug.casefold() in used_slugs:
            count += 1
            slug = f"{base}-{count}"
        used_slugs.add(slug.casefold())
        repo_outdir = os.path.join(outputpath, slug)
        try:
            data = _run_single_repo(
                path,
                repo_outdir,
                extra_fmt,
                project_name=slug,
                json_sibling=False,
                site_url=f"{site_url}{slug}/" if site_url else "",
                wrapped_config=wrapped_config,
            )
        except Exception as e:
            logger.warning(f"Skipping repository {path!r}: {e}")
            failures.append({"name": slug, "path": path, "error": str(e)})
            continue
        summary = compute_repo_summary(data, f"{slug}/index.html")
        write_repo_summary(summary, repo_outdir)
        summaries.append(summary)

    if not summaries:
        logger.error("FATAL: No repository could be analyzed")
        return 1

    logger.info("Generating portfolio page...")
    AggregateReportCreator().create(summaries, failures, outputpath, site_url=site_url)
    return 0


def _port(text: str) -> int:
    """A --port: 1 to 65535, or 0 for a free one."""
    try:
        port = int(text)
    except ValueError:
        port = -1
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a port: give 1 to 65535, or 0 for a free one"
        )
    return port


def get_parser() -> argparse.ArgumentParser:
    """Get the parser for the command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate statistics for a Git repository.",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
    )

    # Optional arguments
    parser.add_argument(
        "-c",
        "--config",
        metavar="key=value",
        action="append",
        default=[],
        # the names only: the values can hold an API key
        help=(
            "Override configuration value. Can be specified multiple times. Keys: "
            + ", ".join(sorted(conf))
        ),
    )

    # Positional arguments
    parser.add_argument(
        "gitpath",
        metavar="<gitpath>",
        nargs="+",
        help=(
            "Path(s) to Git repositories. With two or more positional arguments, "
            "the last one is the output directory. Multiple repositories produce "
            "per-repository reports plus an aggregate portfolio page."
        ),
    )
    parser.add_argument(
        "outputpath",
        metavar="<outputpath>",
        nargs="?",
        default=None,
        help="Path to the output directory (default: gitstats-report)",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["json"],
        required=False,
        help="Generate additional output format",
    )

    parser.add_argument(
        "--site-url",
        metavar="URL",
        help=(
            "Public address of the report, e.g. https://owner.github.io/repo/: fills in "
            "the snippets on the Badges page and prints the README badge"
        ),
    )

    parser.add_argument(
        "--serve",
        action="store_true",
        help="After generating the report, serve it over HTTP until Ctrl+C",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Address to bind the --serve server to (default: 127.0.0.1, local only; use 0.0.0.0 to expose)",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=8000,
        help="Port for the --serve server (default: 8000; 0 picks a free port)",
    )

    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    logging_group.add_argument(
        "--quiet",
        action="store_true",
        help="Only show warnings and errors",
    )

    # AI-powered features
    parser.add_argument(
        "--ai",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable AI-powered summaries in reports (use --ai or --no-ai)",
    )

    parser.add_argument(
        "--ai-provider",
        choices=["openai", "claude", "gemini", "ollama"],
        help="AI provider to use (openai, claude, gemini, ollama)",
    )

    parser.add_argument(
        "--ai-model",
        help="AI model to use (e.g., gpt-4, claude-opus-5-5, gemini-3.5-flash-lite, llama2)",
    )

    parser.add_argument(
        "--ai-language",
        help=(
            "Language of the AI summaries, as a language code: en, zh, ja, ko, es, fr "
            "and de also translate the page's headings"
        ),
    )

    parser.add_argument(
        "--refresh-ai",
        action="store_true",
        help="Force refresh AI-generated summaries (ignore cache)",
    )

    # Repo Wrapped card
    parser.add_argument(
        "--wrapped",
        action="store_true",
        help="Also write a shareable 'Repo Wrapped' SVG card next to the report",
    )
    parser.add_argument(
        "--wrapped-year",
        type=int,
        metavar="YEAR",
        help=(
            "Year the Wrapped card is for (default: the current year); "
            "a year without commits gets no card"
        ),
    )
    parser.add_argument(
        "--wrapped-theme",
        choices=list(THEMES),
        default="midnight",
        help="Color theme of the Wrapped card (default: midnight)",
    )
    parser.add_argument(
        "--wrapped-output",
        metavar="PATH",
        help=(
            "File to write the Wrapped card to, in an existing directory "
            "(default: <outputpath>/wrapped-<year>.svg); single repository only"
        ),
    )

    return parser


def _apply_config_from_args(conf: dict[str, Any], args: argparse.Namespace) -> None:
    """Apply config key=value overrides from CLI arguments."""
    for item in args.config:
        try:
            key, value = item.split("=", 1)
        except ValueError:
            raise ValueError("Config must be in the form key=value")
        if key not in conf:
            raise KeyError(f'No such key "{key}" in config')
        # Convert the value the same way as the config file does
        conf[key] = parse_config_value(value, key)


def _apply_ai_args(conf: dict[str, Any], args: argparse.Namespace) -> None:
    """Apply AI-related CLI arguments (take precedence over config)."""
    if args.ai is not None:
        conf["ai_enabled"] = args.ai
    if args.ai_provider:
        conf["ai_provider"] = args.ai_provider
    if args.ai_model:
        conf["ai_model"] = args.ai_model
    if args.ai_language:
        conf["ai_language"] = args.ai_language
    conf["refresh_ai"] = args.refresh_ai if hasattr(args, "refresh_ai") else False


def main() -> int:
    parser = get_parser()
    args = parser.parse_args()
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    if gitstats.config_errors:
        # what could not be read from gitstats.conf, before anything is done with it
        parser.error("; ".join(gitstats.config_errors))

    # Resolve positional arguments: gitpath (nargs='+') consumes all positional args.
    # If outputpath is None and more than one arg was given, move the last arg from
    # gitpath to outputpath.
    if args.outputpath is None:
        if len(args.gitpath) > 1:
            *repo_paths, args.outputpath = args.gitpath
            args.gitpath = repo_paths
        else:
            args.outputpath = "gitstats-report"

    gitpath = args.gitpath
    outputpath = os.path.abspath(args.outputpath)
    extra_fmt = args.format

    try:
        _apply_config_from_args(conf, args)
        check_git_settings(conf)
    except (ValueError, KeyError) as e:
        parser.error(str(e))

    # Handle AI CLI arguments (CLI takes precedence over config)
    _apply_ai_args(conf, args)
    if args.site_url is not None:
        conf["site_url"] = args.site_url

    wrapped_config = None
    if args.wrapped:
        if args.wrapped_output and len(gitpath) > 1:
            parser.error(
                "--wrapped-output names one file; with several repositories each "
                "card is written into its repository's report directory"
            )
        wrapped_config = {
            "enabled": True,
            "year": args.wrapped_year,
            "theme": args.wrapped_theme,
            # resolved now, like <outputpath>, before any change of directory
            "output": os.path.abspath(args.wrapped_output) if args.wrapped_output else None,
        }

    exit_code = run(gitpath, outputpath, extra_fmt=extra_fmt, wrapped_config=wrapped_config)
    if exit_code == 0 and args.serve:
        return _serve_report(outputpath, args.host, args.port)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
