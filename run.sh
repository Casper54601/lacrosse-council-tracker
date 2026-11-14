#!/bin/sh
# Nightly job: collect, test, rebuild the site. Exits non-zero if anything fails.
set -e
cd "$(dirname "$0")"
python3 collector/collect.py --year "${YEAR:-$(date +%Y)}" --refresh-days 45
python3 -m unittest discover tests
python3 site_builder/build.py
