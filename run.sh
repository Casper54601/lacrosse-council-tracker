#!/bin/sh
# Nightly job: collect, read packets and budget, test, rebuild the site.
# Needs pdftotext (poppler-utils). Exits non-zero if anything fails.
set -e
cd "$(dirname "$0")"
YEAR="${YEAR:-$(date +%Y)}"
PREV=$((YEAR - 1))

# Current year
python3 collector/collect.py --year "$YEAR" --refresh-days 45
python3 collector/packets.py
python3 collector/budget.py
python3 -m unittest discover tests
SITE_YEAR_LINKS="$PREV=$PREV/index.html" python3 site_builder/build.py

# Previous year, as an archive under site/<year>/
export COUNCIL_DB="data/council-$PREV.sqlite"
python3 collector/collect.py --year "$PREV" --refresh-days 0
python3 collector/packets.py
python3 collector/budget.py
SITE_OUT="site/$PREV" SITE_YEAR_LINKS="$YEAR=../index.html" python3 site_builder/build.py
