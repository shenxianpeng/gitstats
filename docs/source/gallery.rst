Gallery data
============

The `GitStats Gallery <https://shenxianpeng.dev/gitstats/gallery/>`_ makes a
gitstats report every Monday for each repository of
`gallery/repos.yml <https://github.com/shenxianpeng/gitstats/blob/main/gallery/repos.yml>`_,
and publishes what it counts as data next to its pages. These files are free
to read from scripts, notebooks and other sites.

Ecosystem rankings
------------------

Each group of ``gallery/repos.yml`` (an *ecosystem*: Python, CNCF graduated,
Apache, …) has a page that ranks its repositories by the share of the last
complete quarter's commits that name an AI coding assistant, and the same
ranking as JSON at the same address:

* ``/gitstats/gallery/ecosystems/<id>.html`` and ``<id>.json``, for example
  `python.html <https://shenxianpeng.dev/gitstats/gallery/ecosystems/python.html>`_
  and `python.json <https://shenxianpeng.dev/gitstats/gallery/ecosystems/python.json>`_;
* ``/gitstats/gallery/ecosystems/index.html`` and ``index.json``: every
  ecosystem side by side.

The ids are those of ``gallery/repos.yml``; an ecosystem's page appears once
one of its repositories has a report. ``/gitstats/gallery/sitemap.xml`` lists
the gallery's pages for search engines.

A commit counts as AI-assisted when it names an assistant as its author, as a
co-author, or in the line the assistant signs with. The counts are lower
bounds: an assistant that leaves no mark in a commit is not counted, and a
mark does not say how much of the commit the assistant wrote. A commit counts
in the quarter it was written (its author date).

``<id>.json``
~~~~~~~~~~~~~

A part of ``python.json``, from a gallery of 24 repositories:

.. code-block:: json

   {
     "schema_version": 1,
     "generated_by": "gitstats 2.12.0",
     "generated_at": "2026-10-26T00:41:07+00:00",
     "ecosystem": {"id": "python", "name": "Python", "title": "Python open source projects"},
     "quarter": {"id": "2026-Q3", "label": "Jul–Sep 2026"},
     "previous_quarter": {"id": "2026-Q2", "label": "Apr–Jun 2026"},
     "summary": {
       "repositories": 6,
       "with_commits": 6,
       "naming": 4,
       "median_share": 0.0115,
       "highest": {"id": "pandas", "name": "pandas", "share": 0.6674}
     },
     "repositories": [
       {
         "rank": 1,
         "id": "pandas",
         "name": "pandas",
         "repository": "pandas-dev/pandas",
         "report": "../pandas/",
         "quarter": {"commits": 947, "ai_assisted": 632, "share": 0.6674},
         "previous_quarter": {"commits": 630, "ai_assisted": 356, "share": 0.5651},
         "commits_last_12mo": 2885,
         "active_authors_12mo": 398,
         "health": "steady",
         "last_commit": "2026-10-18",
         "assistants": ["Claude", "Devin", "GitHub Copilot"]
       }
     ]
   }

``index.json`` has ``schema_version``, ``generated_by``, ``generated_at``,
``quarter``, and ``ecosystems``: for each, its ``id``, ``name``, ``title``,
``page``, ``data`` (the file names of its page and JSON) and its ``summary``,
as above.

Stable fields
~~~~~~~~~~~~~

While ``schema_version`` is ``1``, these fields keep their names, types and
meaning; a change to any of them comes with a new ``schema_version``:

* ``schema_version``;
* ``ecosystem.id``; ``quarter.id`` and ``previous_quarter.id`` (``YYYY-Qn``);
* ``summary.repositories``, ``summary.with_commits``, ``summary.naming``,
  ``summary.median_share``, ``summary.highest`` (``id``, ``name``, ``share``,
  or ``null`` when no repository names an assistant);
* for each of ``repositories``, sorted by ``rank``: ``rank``, ``id``,
  ``repository`` (``owner/name`` on GitHub), ``quarter`` and
  ``previous_quarter`` (``commits``, ``ai_assisted``, ``share``),
  ``commits_last_12mo`` and ``active_authors_12mo``;
* in ``index.json``: ``ecosystems[].id``, ``ecosystems[].data`` and
  ``ecosystems[].summary``.

A share is a fraction from 0 to 1, rounded to four decimals, or ``null`` when
there are no commits to make one of. ``quarter`` (in a repository) is ``null``
when its report does not reach back to that quarter. The ranking: the largest
``quarter.share`` first, then the most commits in the quarter, then the name;
repositories without a share last.

Everything else may change without notice: the display names and titles,
``quarter.label``, ``generated_by``, ``generated_at``, ``report`` (where the
repository's report is, relative to the JSON file), ``health`` (the
repository's pace, as its report's History page labels it), ``last_commit``,
and ``assistants`` (the assistants its commits name most). New fields may be
added at any time.

AI-assisted commits
-------------------

`ai.json <https://shenxianpeng.dev/gitstats/gallery/ai.json>`_ and
`ai.csv <https://shenxianpeng.dev/gitstats/gallery/ai.csv>`_ hold the counts
of the `AI-assisted commits <https://shenxianpeng.dev/gitstats/gallery/ai.html>`_
page, month by month and quarter by quarter, for every repository of the
gallery; ``ai/<YYYY>-Q<n>.json`` keeps each quarter as it was first
published.

Organizations
-------------

`organizations.json <https://shenxianpeng.dev/gitstats/gallery/organizations.json>`_
and `organizations.csv <https://shenxianpeng.dev/gitstats/gallery/organizations.csv>`_
hold the counts of the
`Organizations <https://shenxianpeng.dev/gitstats/gallery/organizations.html>`_
page: commits by the domain of the author's email address, added up across
the gallery's repositories. Domains and counts only, never an address.

``organizations`` lists every organization, the most commits in the last 12
months first: ``organization`` (its domain), ``commits_last_12mo`` (the 12
months that end with each repository's last commit), ``commits`` (all of
them) and ``repositories`` (the names of those it committed to).
``repositories`` lists, for each repository, its ``commits`` of the last four
complete quarters (named in ``quarters``) and ``by_kind``, how they divide
between ``organization``, ``one_person`` (a domain only one person commits
from, most often that person's own), ``personal`` (mail providers anyone can
sign up for), ``hidden`` (code hosts' noreply addresses), ``unknown`` and
``bot``; and ``organizations_last_12mo``, its five organizations with the most
commits in the last 12 months. A domain says where an address is, not who paid
for the work. New fields may be added at any time.

Each of the 200 organizations with the most commits in the last 12 months has
a page, ``orgs/<domain>.html``, with its commits to each repository, and a
badge that is made again with every build: ``orgs/<domain>.svg``, and
``orgs/<domain>.json`` for a `shields.io endpoint badge
<https://shields.io/badges/endpoint-badge>`_. In Markdown:

.. code-block:: markdown

   [![GitStats Gallery](https://shenxianpeng.dev/gitstats/gallery/orgs/google.com.svg)](https://shenxianpeng.dev/gitstats/gallery/orgs/google.com.html)

In ``organizations.json``, each organization's ``by_repository`` lists the
repositories it committed to, each with its ``commits``, ``commits_last_12mo``,
``addresses``, ``first_commit`` and ``last_commit``.
