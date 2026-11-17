#!/bin/sh
# Run the pipeline on the MIMIC-IV Clinical Database Demo (100 patients, open
# access): load it, build the views with real item IDs, split bags into
# episodes and fit the size models. Run from the project root:
#
#   tools/mimic_demo.sh
#
# Needs, first:
#   * the demo's hosp/ and icu/ folders in mimic_demo/, from
#     https://physionet.org/content/mimic-iv-demo/2.2/
#   * synth/load_duckdb.sql, written by generate_synthetic_mimic.py (the demo
#     has the same five tables and columns as the synthetic data)
#   * the duckdb command-line client
#
# Writes mimic_demo/mimic_demo.duckdb and mimic_demo/phase2/. To use another
# folder, name it: tools/mimic_demo.sh some/folder
set -e
demo=${1:-mimic_demo}
load=$(pwd)/synth/load_duckdb.sql

(cd "$demo" && duckdb mimic_demo.duckdb < "$load")
mkdir -p "$demo/phase2"
# The Phase 2 SQL as written for the synthetic data, with the real item IDs
# and the demo's export folder swapped in.
sed -e "s#sql/views.sql#sql/views_mimic.sql#" -e "s#'phase2/#'$demo/phase2/#" \
    sql/phase2.sql | duckdb "$demo/mimic_demo.duckdb" > /dev/null
uv run python phase2/fit.py "$demo/phase2"
