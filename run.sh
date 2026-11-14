#!/bin/sh
# Nightly job: collect, read packets, test, rebuild the site. Needs pdftotext (poppler-utils). Exits non-zero if anything fails.
set -e
cd "$(dirname "$0")"
python3 collector/collect.py --year "${YEAR:-$(date +%Y)}" --refresh-days 45
python3 collector/packets.py
python3 -m unittest discover tests
python3 site_builder/build.py
