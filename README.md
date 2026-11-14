# La Crosse Council Tracker

A plain-English, static website showing what the La Crosse Mayor and Common Council
are doing with tax dollars. Counts and dollars only; every figure links to its source
on the city's Legistar site.

## Run it

Needs Python 3.9 or newer. No packages to install.

    ./run.sh                 # collect, test, build
    python3 -m http.server -d site 8000    # then open http://localhost:8000

Steps on their own:

    python3 collector/collect.py --year 2026    # writes data/council.sqlite
    python3 -m unittest discover tests          # pilot facts as tests
    python3 site_builder/build.py               # writes site/

## How it works

- **Data source.** The Legistar Web API works for La Crosse under the client name
  `cityoflacrosse` (`https://webapi.legistar.com/v1/cityoflacrosse/`). The name
  `lacrosse` returns an error. No HTML scraping is needed.
- **Collector** (`collector/collect.py`). Fetches meetings, agenda items, votes, roll
  calls, item histories, sponsors and office records, four requests at a time. Every
  raw response is cached in `data/cache/`. Meetings older than `--refresh-days` with
  final minutes are read from the cache; newer ones are refetched.
- **Database** (`data/council.sqlite`). Tables: `meetings`, `items`, `actions`,
  `votes`, `attendance`, `people`, `sponsors`, `documents`, `meta`. Actions are keyed
  on Legistar's history row ID, so two motions on one item in one night stay separate.
- **Site** (`site_builder/build.py`). Writes static HTML to `site/`.
- **Nightly job** (`.github/workflows/nightly.yml`). Rebuilds and publishes to GitHub
  Pages once the project is pushed to a GitHub repository.

## Not built yet

1. Dollar amounts from agenda packets and the budget book (PDF extraction). Today
   only amounts stated in item titles are shown, labeled "from title".
2. Plain-English summaries. The `items` table has `plain_summary`, `summary_model`
   and `summary_prompt_version` columns, and the site shows a summary next to the
   official title whenever one is present.
3. 2025 data and meetings of the Board of Estimates and Board of Public Works
   (`--year 2025`, `--bodies 138 139 195 186` already work in the collector; the site
   builds one year at a time).
