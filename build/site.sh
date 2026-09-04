#!/bin/bash
set -e

# Vind de meest recent geupload .kmz file in source/
KMZ=$(ls -t source/*.kmz 2>/dev/null | head -1)

if [ -z "$KMZ" ]; then
    echo "Fout: geen .kmz file gevonden in source/" >&2
    exit 1
fi

echo "Verwerking: $KMZ" >&2

python3 build/kmz2geojson.py \
    --kmz "$KMZ" \
    --out data \
    --report report.md \
    --refs-csv https://wwff.co/wwff-data/wwff_directory.csv \
    --overrides overrides.json

# Website samenstellen: web/ + data/ → _site/
SITE="${1:-./_site}"
mkdir -p "$SITE"
cp -r web/* "$SITE/"
cp data/*.json "$SITE/"
cp data/*.geojson "$SITE/"
touch "$SITE/.nojekyll"

echo "✓ Klaar" >&2
