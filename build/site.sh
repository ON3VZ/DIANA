#!/usr/bin/env bash
# Bouwt de map die gepubliceerd wordt. Alles wat hier niet in staat, komt niet online.
#
# Belangrijk: source/ blijft er bewust buiten. Het ONFF-KMZ wordt door ONFF
# verspreid via een groups.io achter lidmaatschap; dat bestand hoort niet
# ongevraagd op een publieke URL te staan.
set -euo pipefail

OUT="${1:-_site}"
rm -rf "$OUT"
mkdir -p "$OUT/data"

cp -r web/. "$OUT/"
cp data/onff.geojson data/onff-index.json data/meta.json "$OUT/data/"

echo "Gepubliceerd naar $OUT:"
find "$OUT" -type f | sed "s|^$OUT/|  |" | sort
