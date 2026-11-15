Repo Wrapped
============

A *Repo Wrapped* card is one year in a repository on a square image, made for
sharing: the year's commits, active days, longest streak, lines changed and
contributors, each set against the year before.

.. code-block:: bash

   gitstats --wrapped .
   gitstats --wrapped --wrapped-theme sunset .      # midnight (default), sunset or clean
   gitstats --wrapped --wrapped-year 2025 .         # the card for another year
   gitstats --wrapped --wrapped-output card.svg .   # write it to another file

The card is written next to the report as ``wrapped-<year>.svg``, 1080 by 1080.

What is on the card
-------------------

Every number on the card is for one year, the current one by default: its
commits, active days, longest streak, lines changed, contributors and releases
(or new contributors, in a year without a release), the busiest month and
weekday, the top contributor, the part of the day most of the commits were
made in, and the commits of each month. Nothing on it is an all-time number. A
year without commits gets no card: ``gitstats`` says so and names the last
year that has any.

Compared with the year before
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Next to each of the six numbers the card says how it moved from the year
before: commits and lines by a percentage (``+12%``, and by a factor from ten
times on, ``12x``), days, people and releases by a difference (``+3``).

* A card for a year that is **over** is compared with the whole year before.
* A card for the year **under way** is compared with the same days of the year
  before: made on December 5, it sets January 1 to December 5 of this year
  against January 1 to December 5 of last year, not against all of it. The
  card says so under its numbers.

In the chart, the months of the year before stand as narrow bars beside this
year's: beside the months that are over only, as the month under way is not
yet what the whole month of a year ago was.

A repository in its first year has nothing to be compared with, and its card
shows the year alone. Bots' commits are counted, like everywhere in the
report; a bot is not a new contributor, and it is the top contributor only of
a year nobody else committed in.

What comes with the card
------------------------

A card written into the report directory comes with:

``wrapped.html``
   A page of the report, in its nav as *Wrapped*: the card, the year's
   numbers in a table beside those of the year before, a button that saves
   the card as a PNG (drawn in the browser: most places that take an image do
   not take an SVG), and a line to post with it.

``wrapped-<year>.json``
   The card's numbers as data, described below.

``wrapped-card.html``
   The share card of the page, 1200 by 630: what a link to ``wrapped.html``
   shows where it is posted, when the report is published with ``site_url``
   and ``share_card`` (see :doc:`configuration`) and the card is rendered as
   ``wrapped-card.png``.

The Badges page shows the card with a snippet to put it in a README, and the
History page links to it from its year. With several repositories, each one
gets all of this in its own report directory. A card written elsewhere with
``--wrapped-output`` is the image alone.

``wrapped-<year>.json``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "schema_version": 1,
     "generated_by": "gitstats 2.13.0",
     "generated_at": "2026-12-05T09:00:00+00:00",
     "card": "wrapped-2026.svg",
     "theme": "midnight",
     "year": 2026,
     "project_name": "gitstats",
     "commits": 170,
     "active_days": 73,
     "longest_streak": 5,
     "lines_changed": 52827,
     "contributors": 8,
     "new_contributors": 5,
     "releases": 9,
     "top_author": "Xianpeng Shen",
     "top_author_commits": 133,
     "monthly_commits": [4, 10, 10, 6, 15, 4, 18, 15, 31, 53, 4, 0],
     "busiest_month": "October",
     "busiest_weekday": "Friday",
     "day_part": {"name": "Evening Coder", "start": 18, "end": 24, "share": 0.42},
     "through": "2026-12-05",
     "complete": false,
     "previous": {
       "year": 2025,
       "through": "2025-12-05",
       "commits": 77,
       "active_days": 44,
       "longest_streak": 4,
       "lines_changed": 5529,
       "contributors": 6,
       "new_contributors": 3,
       "releases": 7,
       "monthly_commits": [22, 3, 7, 14, 12, 2, 5, 3, 2, 5, 2, 9]
     }
   }

While ``schema_version`` is ``1``, these fields keep their names, types and
meaning; a change to any of them comes with a new ``schema_version``:

* ``schema_version``, ``year``, ``card`` (the card's file name, next to this
  file) and ``project_name``;
* ``commits``, ``active_days``, ``longest_streak`` (in days),
  ``lines_changed`` (added and removed), ``contributors``,
  ``new_contributors`` and ``releases``;
* ``monthly_commits``: twelve numbers, January first;
* ``through``, the last day the numbers reach (``YYYY-MM-DD``), and
  ``complete``, whether the year was over when the card was made;
* ``previous``: ``null`` when there is no year before to compare with, or its
  ``year``, its ``through`` and the same seven numbers and
  ``monthly_commits``. Its numbers stop at ``previous.through``; its
  ``monthly_commits`` are whole months.

.. _wrapped-workflow:

Make the card in GitHub Actions
-------------------------------

Copy this workflow into a repository as ``.github/workflows/wrapped.yml``,
then run it from the *Actions* tab: *Repo Wrapped*, *Run workflow*. The card
is in the ``repo-wrapped`` artifact of the run, as SVG and PNG with its
numbers as JSON, and the run's summary says the year in a table.

It only reads the repository: it needs no token, publishes nothing and
changes nothing.

.. code-block:: yaml

   name: Repo Wrapped

   on:
     workflow_dispatch:
       inputs:
         year:
           description: "Year of the card (empty: this year)"
           required: false
           type: string
         theme:
           description: Color theme of the card
           type: choice
           default: midnight
           options: [midnight, sunset, clean]

   permissions:
     contents: read

   jobs:
     wrapped:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v7
           with:
             fetch-depth: 0  # the whole history: a shallow clone has one commit

         - name: Make the card
           env:
             YEAR: ${{ inputs.year }}
             THEME: ${{ inputs.theme }}
           run: |
             pipx run gitstats --wrapped --wrapped-theme "$THEME" \
               ${YEAR:+--wrapped-year "$YEAR"} . report
             mkdir card
             cp report/wrapped-*.svg report/wrapped-*.json card/

         - name: Render it as a PNG
           run: |
             for svg in card/*.svg; do
               google-chrome --headless=new --no-sandbox --hide-scrollbars \
                 --window-size=1080,1080 --screenshot="$PWD/${svg%.svg}.png" "file://$PWD/$svg"
             done

         - name: Say the year in the summary
           run: |
             python3 - >> "$GITHUB_STEP_SUMMARY" <<'PYTHON'
             import glob, json

             card = json.load(open(glob.glob("card/*.json")[0], encoding="utf-8"))
             years = [card] + ([card["previous"]] if card["previous"] else [])
             print(f"### {card['project_name']}: Repo Wrapped {card['year']}\n")
             print("| |" + "".join(f" {year['year']} |" for year in years))
             print("|---|" + "---:|" * len(years))
             for key in ("commits", "contributors", "active_days", "longest_streak", "lines_changed", "releases"):
                 name = key.replace("_", " ").capitalize()
                 print(f"| {name} |" + "".join(f" {year[key]:,} |" for year in years))
             print("\nThe card is in the `repo-wrapped` artifact of this run, as SVG and PNG.")
             PYTHON

         - uses: actions/upload-artifact@v7
           with:
             name: repo-wrapped
             path: card/

To publish the card with the whole report instead, add ``--wrapped`` to the
command of a workflow from :doc:`integration`: the report then has the card's
page, and a link to it can be shared.

In the Gallery
--------------

The `GitStats Gallery <https://shenxianpeng.dev/gitstats/gallery/>`_ makes a
card for each of its projects every week, and a
`page of them all <https://shenxianpeng.dev/gitstats/gallery/wrapped/>`_.
See :doc:`gallery`.
