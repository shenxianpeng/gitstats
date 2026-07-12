#!/usr/bin/env python3
"""Generate an index.html for the gallery directory."""

import os
import sys
from datetime import datetime, timezone


def generate(gallery_root: str) -> None:
    """Scan gallery/<id>/ subdirectories for index.html and generate an index page."""
    # Resolve to an absolute path and ensure it is a directory
    abs_root = os.path.realpath(gallery_root)
    if not os.path.isdir(abs_root):
        print(f"Error: {gallery_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    repos = []
    for entry in sorted(os.listdir(abs_root)):
        # Prevent path traversal: reject entries with separators or parent refs
        if (
            os.path.sep in entry
            or (os.path.altsep and os.path.altsep in entry)
            or entry in (".", "..")
        ):
            continue
        entry_path = os.path.realpath(os.path.join(abs_root, entry))
        # Ensure the resolved path is still inside the gallery root
        if not entry_path.startswith(abs_root + os.sep):
            continue
        report_path = os.path.join(entry_path, "index.html")
        if os.path.isdir(entry_path) and os.path.isfile(report_path):
            display_name = entry.capitalize()
            # Try to read a friendlier name from a .name file
            name_file = os.path.realpath(os.path.join(entry_path, ".name"))
            if os.path.isfile(name_file):
                with open(name_file) as f:
                    display_name = f.read().strip()
            repos.append({"id": entry, "name": display_name})

    repos.sort(key=lambda r: r["name"].lower())

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitStats Gallery</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f8f9fa;
    color: #1f2937;
    line-height: 1.6;
    padding: 2rem 1rem;
  }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  h1 {{
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}
  h1 a {{ color: inherit; text-decoration: none; }}
  h1 a:hover {{ color: #2563eb; }}
  .subtitle {{
    color: #6b7280;
    margin-bottom: 2rem;
    font-size: 1.1rem;
  }}
  .subtitle a {{ color: #2563eb; text-decoration: none; }}
  .subtitle a:hover {{ text-decoration: underline; }}
  .updated {{ font-size: 0.875rem; color: #9ca3af; margin-bottom: 1.5rem; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
  }}
  .card {{
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1.25rem;
    transition: box-shadow 0.15s, border-color 0.15s;
    text-decoration: none;
    color: inherit;
    display: flex;
    flex-direction: column;
  }}
  .card:hover {{
    border-color: #2563eb;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
  }}
  .card h2 {{ font-size: 1.125rem; font-weight: 600; margin-bottom: 0.25rem; }}
  .card p {{ font-size: 0.875rem; color: #6b7280; }}
  .card .arrow {{ margin-top: auto; align-self: flex-end; font-size: 1.25rem; color: #2563eb; }}
</style>
</head>
<body>
<div class="container">
  <h1><a href=".">📊 GitStats Gallery</a></h1>
  <p class="subtitle">
    Live reports for open-source projects —
    <a href="https://github.com/shenxianpeng/gitstats">GitStats</a>
  </p>
  <p class="updated">Last updated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>
  <div class="grid">
"""
    for repo in repos:
        html += f"""    <a class="card" href="{repo["id"]}/index.html">
      <h2>{repo["name"]}</h2>
      <p>gitstats report</p>
      <span class="arrow">→</span>
    </a>
"""

    html += """  </div>
</div>
</body>
</html>
"""
    index_path = os.path.realpath(os.path.join(abs_root, "index.html"))
    with open(index_path, "w") as f:
        f.write(html)
    print(f"✅ Gallery index generated: {index_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_gallery_index.py <gallery_root>")
        sys.exit(1)
    generate(sys.argv[1])
