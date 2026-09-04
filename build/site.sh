#!/bin/bash
set -e

# Vind de meest recent geupload .kmz file in source/
# (using modification time as proxy voor upload moment)
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
    --refs-csv /root/.claude/uploads/wwff_directory.csv \
    --overrides overrides.json

echo "✓ Klaar" >&2
