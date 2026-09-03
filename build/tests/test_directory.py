"""Wat de bouwstap met een rammelende WWFF-directory doet.

Geen browser nodig: dit draait kmz2geojson.py zelf, met echte KMZ en echte CSV.
De drie dingen die hier bewaakt worden zijn stuk voor stuk in productie fout
gegaan of hadden dat kunnen gaan:

  1. coördinaten die buiten bereik liggen, omgewisseld zijn of half nul —
     die stonden als stip midden op de oceaan
  2. een afgebroken of onbereikbare directory die stilletjes een half bestand
     wegschreef dat er kerngezond uitzag
  3. --strict, waarop de nachtelijke run vertrouwt om niets te committen

Draaien:  python3 build/tests/test_directory.py [pad/naar/wwff_directory.csv]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "build" / "kmz2geojson.py"
fails = []


def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        fails.append(msg)


def build(out: Path, csv: str, strict: bool = False):
    kmz = sorted((ROOT / "source").glob("*.kmz"))
    if not kmz:
        print("Geen KMZ in source/ — test overgeslagen.")
        sys.exit(0)
    args = [sys.executable, str(SCRIPT), "--kmz", str(kmz[-1]), "--out", str(out),
            "--report", str(out / "report.md"), "--refs-csv", csv,
            "--overrides", str(ROOT / "overrides.json")]
    if strict:
        args.append("--strict")
    return subprocess.run(args, capture_output=True, text=True, cwd=ROOT)


def find_csv() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1]
    for base in (Path("/root/.claude/uploads"), Path("/tmp")):
        if base.exists():
            hits = sorted(base.rglob("*wwff_directory.csv"))
            if hits:
                return str(hits[-1])
    return None


CSV = find_csv()
if not CSV:
    print("Geen lokale wwff_directory.csv gevonden — geef het pad mee als argument.")
    sys.exit(0)

work = Path(tempfile.mkdtemp(prefix="diana-dirtest-"))
good = work / "good"

print("\n[1] gewone build tegen de echte directory")
r = build(good, CSV)
ok(r.returncode == 0, f"exitcode 0 (kreeg {r.returncode})")
world = json.loads((good / "wwff-world.geojson").read_text())["features"]
ok(len(world) > 50000, f"{len(world)} wereldpunten geschreven")

print("\n[2] geen enkele onmogelijke coördinaat")
out_of_range = [f["properties"]["ref"] for f in world
                if not (-90 <= f["geometry"]["coordinates"][1] <= 90
                        and -180 <= f["geometry"]["coordinates"][0] <= 180)]
ok(not out_of_range, f"alles binnen bereik (buiten bereik: {out_of_range[:5]})")

half_zero = [f["properties"]["ref"] for f in world
             if abs(f["geometry"]["coordinates"][0]) < 0.001
             or abs(f["geometry"]["coordinates"][1]) < 0.001]
ok(not half_zero, f"geen half-nul posities (gevonden: {half_zero[:5]})")

junk = [f["properties"]["ref"] for f in world if not f["properties"]["ref"][:1].isalnum()
        or "FF-" not in f["properties"]["ref"]]
ok(not junk, f"geen rommelrijen als referentie (gevonden: {junk[:5]})")

print("\n[3] de twee lagen lekken niet in elkaar")
onff_in_world = [f["properties"]["ref"] for f in world if f["properties"]["ref"].startswith("ONFF")]
ok(not onff_in_world, "geen ONFF in de wereldlaag")
pts = json.loads((good / "onff-points.geojson").read_text())["features"]
ok(all(f["properties"]["ref"].startswith("ONFF") for f in pts),
   "alleen ONFF in de puntenlaag zonder grens")

print("\n[4] ONFF-0004 staat op Antarctica en dat hoort zo")
antarctic = [f["geometry"]["coordinates"] for f in pts if f["properties"]["ref"] == "ONFF-0004"]
ok(bool(antarctic) and antarctic[0][1] < -60,
   f"Prinses Elisabethbasis op het zuidelijk halfrond ({antarctic})")

print("\n[5] onbereikbare directory: --strict stopt, zonder iets te schrijven")
before = (good / "wwff-world.geojson").read_bytes()
r = build(good, "https://example.invalid/weg.csv", strict=True)
ok(r.returncode == 1, f"exitcode 1 (kreeg {r.returncode})")
ok((good / "wwff-world.geojson").read_bytes() == before, "wereldbestand ongemoeid gebleven")

print("\n[6] afgebroken directory wordt herkend aan de val tegenover de vorige build")
trunc = work / "trunc.csv"
raw = Path(CSV).read_bytes()
trunc.write_bytes(raw[: len(raw) // 5])
r = build(good, str(trunc), strict=True)
ok(r.returncode == 1, f"exitcode 1 bij een afgebroken CSV (kreeg {r.returncode})")
ok((good / "wwff-world.geojson").read_bytes() == before, "wereldbestand nog steeds ongemoeid")

print("\n[7] zonder --strict blijven de punten van de vorige build staan")
r = build(good, "https://example.invalid/weg.csv")
ok(r.returncode == 0, f"exitcode 0 zonder --strict (kreeg {r.returncode})")
idx = json.loads((good / "onff-index.json").read_text())
ok(idx["point_count"] == len(pts),
   f"{idx['point_count']} punten behouden in plaats van gewist (was {len(pts)})")
ok(len(json.loads((good / "onff-points.geojson").read_text())["features"]) == len(pts),
   "onff-points.geojson niet leeggeschreven")

print("\n" + ("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
