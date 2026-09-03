#!/usr/bin/env python3
"""
Diana — ONFF KMZ to GeoJSON pipeline.

Reads an official ONFF Google Earth release (ONFF_YYYYMMDD.kmz) and produces the
static data files the Diana PWA loads:

    data/onff.geojson       zone geometry, one MultiPolygon feature per ONFF reference
    data/onff-index.json    lightweight index (no geometry) for search, lists and
                            "nearest zones" without loading the full geometry file
    data/onff-points.geojson references that exist on the ONFF list but have no
                            polygon in the KMZ, as single Point features
    data/meta.json          provenance: which source file, which release, what settings
    data/wwff-programs.json every WWFF programme in the directory mapped to its country
                            (worldwide, not just ONFF) — lets the app's spots screen offer
                            a "just this country" filter without shipping a hand-kept list
    data/wwff-world.geojson every OTHER active WWFF reference worldwide (not ONFF), as bare
                            Points — ref and name only, never a boundary; this is the "other
                            WWFF areas" layer, off-ONFF-map but still Diana's own data

It also writes a human-readable diff report against the previous index, which the
GitHub Action posts under the pull request and the /admin page renders in plain
language. See "Diana - Technisch plan" §2.

Usage
-----
    python build/kmz2geojson.py --kmz "source/ONFF 20260101.kmz"

Notes
-----
* The ONFF reference number is NOT stored in a data field. It lives in the name of
  the enclosing Document/Folder, as "ONFF-nnnn <name>". Names contain typos and
  duplicates, so we key everything on the number and never on the name.
* The KMZ embeds a Maidenhead grid layer (~32.700 placemarks) which we drop: a grid
  is cheaper to compute in the client than to ship.
* Attribute coverage is uneven (roughly 38% WDPA fields, 7% Flemish fields, 46%
  nothing at all), so every attribute is optional and callers must degrade
  gracefully.
* The ONFF index sheet lists ~965 references; the KMZ contains ~932 polygons. The
  remainder are real references with no boundary. They are emitted as Points (see
  --refs-csv) so they are visible on the map instead of silently absent, but a
  point is explicitly not a boundary: the app must not run "am I inside" on them.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree
from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union

KML_NS = "{http://www.opengis.net/kml/2.2}"
REF_RE = re.compile(r"ONFF[- ]?(\d{4})")
# Elke WWFF-referentie wereldwijd, bv. ONFF-0104, GFF-0231, VKFF-1234.
FF_RE  = re.compile(r"\b[A-Z0-9]{1,3}FF-\d{3,5}\b")
GEOD = Geod(ellps="WGS84")

# Folders in the KMZ that are not ONFF zones.
SKIP_FOLDERS = {"Maidenhead grid by OH2ECG"}

# Extra thematic layers that sit alongside the provinces. Kept out of the main
# output for now; the MVP is ONFF only.
NON_PROVINCE_FOLDERS = {"National parks", "Natura2000", "Ramsar", "Antartica"}

SCRIPT_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# KML reading
# --------------------------------------------------------------------------- #

def _name(el) -> str | None:
    node = el.find(KML_NS + "name")
    return node.text if node is not None and node.text else None


def _ring(linear_ring) -> list[tuple[float, float]]:
    """Parse a KML <LinearRing> into a list of (lon, lat) tuples."""
    text = linear_ring.find(KML_NS + "coordinates").text
    pts = []
    for chunk in text.split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            pts.append((float(parts[0]), float(parts[1])))
    return pts


JUNK_NAMES = {"sql_statement", "naamloos plaatsmarkering", "untitled placemark", ""}


def _clean_name(raw: str) -> str:
    """Strip the reference prefix and any leftover file extension."""
    name = REF_RE.sub("", raw)
    name = re.sub(r"\.(kml|kmz|shp|gpx)$", "", name.strip(), flags=re.I)
    return name.strip(" -–—_")


def _looks_like_filename(name: str) -> bool:
    """'zwinduinen-en-polders' is an import filename, 'Zwinduinen en Polders' is a name."""
    return " " not in name and bool(re.search(r"[a-z0-9]-[a-z0-9]", name))


def pick_name(counts, ref: str) -> str:
    """
    Choose the best display name out of every spelling found in the KMZ.

    Many zones carry three or four variants (typos, capitalisation, and the name of
    the .kml file they were imported from). Preference order: a name that does not
    look like a filename, then the spelling that occurs most often, then the longest.
    """
    candidates = {}
    for raw, hits in counts.items():
        cleaned = _clean_name(raw)
        if cleaned.lower() in JUNK_NAMES:
            continue
        candidates[cleaned] = candidates.get(cleaned, 0) + hits
    if not candidates:
        return ref
    best = max(candidates, key=lambda c: (not _looks_like_filename(c), candidates[c], len(c)))
    if _looks_like_filename(best):
        best = _titlecase(best.replace("-", " ").replace("_", " "))
    return best


# Words that stay lowercase inside a name, in the three languages that occur.
SMALL_WORDS = {"de", "den", "der", "het", "van", "en", "op", "aan", "ter", "te", "'t",
               "du", "des", "la", "le", "les", "et", "aux", "sur", "sous", "of", "the"}


def _titlecase(name: str) -> str:
    """Capitalise a filename-derived name without shouting at the connecting words."""
    words = name.split()
    out = []
    for i, word in enumerate(words):
        if i > 0 and word.lower() in SMALL_WORDS:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def _extended_data(placemark) -> dict[str, str]:
    """Return the SimpleData fields of a placemark, empty values dropped."""
    schema = placemark.find(".//" + KML_NS + "SchemaData")
    if schema is None:
        return {}
    out = {}
    for field in schema.findall(KML_NS + "SimpleData"):
        value = (field.text or "").strip()
        if value and value not in ("Not Reported", "Not Applicable"):
            out[field.get("name")] = value
    return out


def _ref_from_ancestors(placemark) -> tuple[str | None, str | None]:
    """Walk up the tree to find the nearest ONFF-nnnn name. Returns (ref, raw name)."""
    node = placemark
    while node is not None:
        name = _name(node)
        if name:
            match = REF_RE.search(name)
            if match:
                return "ONFF-" + match.group(1), re.sub(r"\.kml$", "", name).strip()
        node = node.getparent()
    return None, None


def extract_kmz(kmz_path: Path, workdir: Path) -> Path:
    """Unpack doc.kml from the KMZ. Returns the path to the extracted KML."""
    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(kmz_path) as archive:
        kml_names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise SystemExit(f"No .kml found inside {kmz_path}")
        # Google Earth always names the main document doc.kml; fall back to the first.
        target = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
        out = workdir / "doc.kml"
        out.write_bytes(archive.read(target))
    return out


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #

def area_hectares(geom) -> float:
    """Geodesic area in hectares (WGS84), sign-independent."""
    area_m2, _ = GEOD.geometry_area_perimeter(geom)
    return round(abs(area_m2) / 10_000.0, 1)


def round_geometry(geom, decimals: int):
    """Round every coordinate. Five decimals is ~1 m, well under GPS accuracy."""
    def _round_coords(coords):
        return [(round(x, decimals), round(y, decimals)) for x, y in coords]

    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    out = []
    for poly in polys:
        shell = _round_coords(poly.exterior.coords)
        holes = [_round_coords(r.coords) for r in poly.interiors]
        try:
            rounded = Polygon(shell, holes)
        except Exception:
            continue
        if rounded.is_valid and not rounded.is_empty:
            out.append(rounded)
        else:
            fixed = rounded.buffer(0)
            if not fixed.is_empty:
                out.append(fixed)
    if not out:
        return None
    merged = unary_union(out)
    return merged if isinstance(merged, MultiPolygon) else MultiPolygon([merged])


# --------------------------------------------------------------------------- #
# Attribute mapping
# --------------------------------------------------------------------------- #

# The KMZ stores the managing authority as an abbreviation. Spelled out here so
# the app can show something a human recognises. Extend via overrides.json.
MANAGER_NAMES = {
    "ANB": "Agentschap Natuur & Bos",
    "DNF": "Département de la Nature et des Forêts",
    "NP": "Natuurpunt",
    "RNOB": "Natagora / RNOB",
}


def attributes_from(data: dict[str, str]) -> dict:
    """Normalise the two competing schemas in the KMZ into one flat dict."""
    out: dict[str, object] = {}

    # WDPA schema (uppercase) — about 38% of polygons.
    if data.get("DESIG_ENG") or data.get("DESIG"):
        out["desig"] = data.get("DESIG") or data.get("DESIG_ENG")
        out["desig_en"] = data.get("DESIG_ENG")
    if data.get("IUCN_CAT"):
        out["iucn"] = data["IUCN_CAT"]
    if data.get("MANG_AUTH"):
        code = data["MANG_AUTH"].strip()
        out["manager"] = MANAGER_NAMES.get(code, code)
        out["manager_code"] = code
    if data.get("STATUS_YR"):
        out["status_year"] = data["STATUS_YR"]
    if data.get("WDPA_PID"):
        out["wdpa_pid"] = data["WDPA_PID"]

    # Flemish schema (lowercase) — about 7%.
    if not out.get("desig") and data.get("desig"):
        out["desig"] = data["desig"]
    if not out.get("iucn") and data.get("iucn_cat"):
        out["iucn"] = data["iucn_cat"]
    if data.get("inspireid"):
        # "NatuurbeheerplanType4-NBP-AN-18-0007G" -> "NBP-AN-18-0007G"
        out["registration"] = data["inspireid"].split("-", 1)[-1] if "-" in data["inspireid"] else data["inspireid"]
        marker = "NBP-"
        if marker in data["inspireid"]:
            out["registration"] = data["inspireid"][data["inspireid"].index(marker):]
    if data.get("sub_loc") and not out.get("region"):
        out["region"] = data["sub_loc"]

    return out


# --------------------------------------------------------------------------- #
# Main conversion
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# The WWFF directory — the authoritative list of references
#
# https://wwff.co/wwff-data/wwff_directory.csv is regenerated daily and holds
# every WWFF reference worldwide (~68.000 rows, 190 programmes), each with a
# status, an official name, coordinates and an IARU locator. For Diana it does
# two jobs the KMZ cannot:
#
#   1. it says which references EXIST (the KMZ only says which have a boundary)
#   2. it gives a position for the ones that have no boundary yet
#
# The two sources are joined on the reference number, and a reference is only
# ever used once: if the KMZ has a polygon for it, that polygon wins and the
# directory row is used only to fill gaps and to cross-check. Otherwise it
# becomes a Point. That is what keeps duplicates out.
#
# Rows with status != active are skipped entirely — the directory keeps deleted
# references around, renamed to "DELETED AREA - …", and putting those on a map
# would be worse than leaving them off. So are null-island rows (0,0 / JJ00AA),
# which is how the directory marks "position unknown".
# --------------------------------------------------------------------------- #

WWFF_DIRECTORY = "https://wwff.co/wwff-data/wwff_directory.csv"

# The columns actually in wwff_directory.csv, in the order it publishes them:
#   reference, status, name, program, dxcc, state, county, continent, iota,
#   iaruLocator, latitude, longitude, IUCNcat, validFrom, validTo, notes,
#   lastMod, changeLog, reviewFlag, specialFlags, website, country, region,
#   dxccEnum, qsoCount, lastAct
# Read by name, never by position, so a new column in the middle is harmless.

# Region codes the directory uses for Belgium. A row can carry more than one
# ("OV,NP-SV" = East Flanders plus a national-park overlay); the first wins.
BE_REGIONS = {
    "AN": "Antwerpen", "LB": "Limburg", "OV": "Oost-Vlaanderen",
    "VB": "Vlaams-Brabant", "WV": "West-Vlaanderen", "BR": "Brussel",
    "BW": "Brabant Wallon", "HT": "Hainaut", "LG": "Liège",
    "LX": "Luxembourg", "NR": "Namur", "ANT": "Antarctica",
}

# "51.2345, 4.5678" in one cell — only used for a CSV that has no lat/lon columns.
PAIR_RE = re.compile(r"(-?\d{1,3}[.,]\d+)\s*[,;/|]\s*(-?\d{1,3}[.,]\d+)")

# Rough envelope of Belgium, used only to tell latitude from longitude apart in
# that fallback. Named columns are trusted as-is — ONFF-0004 sits in Antarctica.
BE_LAT = (49.0, 52.0)
BE_LON = (2.0, 7.0)


def _read_rows(source: str, timeout: int = 120) -> list[dict[str, str]]:
    """Read a CSV from a local path or a URL into a list of dicts."""
    import csv
    import io

    if re.match(r"^https?://", source):
        import urllib.request
        req = urllib.request.Request(source, headers={"User-Agent": "Diana/1.0 (ONFF map build)"})
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            text = fh.read().decode("utf-8", "replace")
    else:
        text = Path(source).read_text(encoding="utf-8", errors="replace")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return []

    # The header is not always the first line — a hand-made sheet often starts
    # with a title row. The header is the row above the first ONFF/xxFF number.
    first_data = next((i for i, row in enumerate(rows[:12])
                       if any(REF_RE.search(cell or "") or FF_RE.search(cell or "") for cell in row)), 1)
    header_at = max(first_data - 1, 0)
    header = [(c or "").strip() for c in rows[header_at]]
    seen: dict[str, int] = {}
    for i, name in enumerate(header):
        key = name or f"col{i}"
        if key in seen:
            seen[key] += 1
            key = f"{key}_{seen[key]}"
        else:
            seen[key] = 0
        header[i] = key

    out = []
    for row in rows[header_at + 1:]:
        if not any((c or "").strip() for c in row):
            continue
        out.append({header[i] if i < len(header) else f"col{i}": (row[i] or "").strip()
                    for i in range(len(row))})
    return out


def _to_float(raw: str) -> float | None:
    raw = (raw or "").strip().replace("°", "")
    if not raw:
        return None
    try:
        return float(raw.replace(",", ".")) if raw.count(",") <= 1 else None
    except ValueError:
        return None


def _orient(a: float, b: float) -> tuple[float, float] | None:
    """Given two numbers from one cell, return (lat, lon) if we can tell which is which."""
    if BE_LAT[0] <= a <= BE_LAT[1] and BE_LON[0] <= b <= BE_LON[1]:
        return a, b
    if BE_LAT[0] <= b <= BE_LAT[1] and BE_LON[0] <= a <= BE_LON[1]:
        return b, a
    return None


def _row_value(row: dict[str, str], *words: str) -> str | None:
    for key, value in row.items():
        if value and value not in ("-", "n/a") and any(w in key.lower() for w in words):
            return value.strip()
    return None


# Hoe de directory "positie onbekend" schrijft: nul-eiland, als coördinaat én
# als locator. JJ00AA rekent netjes om naar (0.02, 0.04) — dus die moet er hier
# uit, vóór de omrekening, anders glipt hij door de nulcontrole heen.
NULL_LOCATOR = {"JJ00AA", "JJ00", "AA00AA", "AA00"}


def locator_to_latlon(loc: str) -> tuple[float, float] | None:
    """Maidenhead locator to the centre of its square. The directory always has
    one, so it is the backstop when latitude/longitude are empty."""
    loc = (loc or "").strip().upper()
    if loc in NULL_LOCATOR:
        return None
    if not re.fullmatch(r"[A-R]{2}[0-9]{2}([A-X]{2})?", loc):
        return None
    lon = (ord(loc[0]) - 65) * 20 - 180
    lat = (ord(loc[1]) - 65) * 10 - 90
    lon += int(loc[2]) * 2
    lat += int(loc[3]) * 1
    if len(loc) >= 6:
        lon += (ord(loc[4]) - 65) * (2 / 24) + (2 / 48)
        lat += (ord(loc[5]) - 65) * (1 / 24) + (1 / 48)
    else:
        lon += 1
        lat += 0.5
    return lat, lon


def _row_latlon(row: dict[str, str]) -> tuple[float, float] | None:
    """Position for one row: the named columns first, then the locator, then a
    coordinate pair squeezed into a single cell. Null island counts as absent."""
    lat = _to_float(row.get("latitude") or "")
    lon = _to_float(row.get("longitude") or "")
    if lat is None or lon is None:                       # other CSV shapes
        for key, value in row.items():
            k = key.lower()
            if not value:
                continue
            if lat is None and "lat" in k:
                lat = _to_float(value)
            elif lon is None and ("lon" in k or "lng" in k):
                lon = _to_float(value)
    if lat is not None and lon is not None and not (abs(lat) < 0.1 and abs(lon) < 0.1):
        return lat, lon

    ll = locator_to_latlon(row.get("iaruLocator") or _row_value(row, "locator", "grid") or "")
    if ll and not (abs(ll[0]) < 0.1 and abs(ll[1]) < 0.1):
        return ll

    for key, value in row.items():
        if not value or not any(w in key.lower() for w in ("coord", "gps", "positi")):
            continue
        m = PAIR_RE.search(value)
        if m:
            a, b = _to_float(m.group(1)), _to_float(m.group(2))
            if a is not None and b is not None:
                return _orient(a, b) or (a, b)
    return None


def _province(row: dict[str, str]) -> str | None:
    code = (row.get("region") or "").split(",")[0].strip()
    return BE_REGIONS.get(code)


def point_refs(source: str | None, programs: list[str], have: set[str],
               overrides: dict, decimals: int):
    """Join the WWFF directory with the polygons we already have.

    Returns (features, index_entries, activity, warnings, stats). Never raises:
    a directory that has moved, or a runner without network, must not break a
    data build — it degrades to "manual points from overrides.json only".
    """
    warnings: list[str] = []
    stats = {"listed": 0, "deleted": 0, "orphan_polygons": [], "renamed": []}
    rows: list[dict[str, str]] = []
    if source:
        try:
            rows = _read_rows(source)
        except Exception as exc:                      # noqa: BLE001 — any failure is non-fatal
            warnings.append(f"WWFF-directory niet gelezen ({type(exc).__name__}): "
                            f"alleen handmatige punten uit overrides.json gebruikt")

    wanted = tuple(p.strip().upper() for p in programs if p.strip())
    listed: dict[str, dict] = {}
    activity: dict[str, dict] = {}
    seen: set[str] = set()          # élke actieve referentie uit de directory

    # Programma → land, over de VOLLEDIGE directory (niet beperkt tot --program):
    # de kaart zelf blijft ONFF-only, maar de spots-app wil wereldwijd op land
    # kunnen filteren, en heeft daarvoor een naam per WWFF-programma nodig. Eén
    # tel per land per programma; het vaakst voorkomende land wint (bijna altijd
    # is dat het enige, op wat schrijfvarianten na).
    programs_seen: dict[str, Counter] = {}
    program_code_re = re.compile(r"^[A-Z0-9]{1,5}FF$")
    for row in rows:
        prog = (row.get("program") or "").strip().upper()
        country = (row.get("country") or "").strip()
        # Een enkele stray kopregel her en der in de export levert "PROGRAM"/
        # "country" als waarden op; een echt programma eindigt altijd op "FF".
        if program_code_re.match(prog) and country and country not in ("-", "n/a"):
            programs_seen.setdefault(prog, Counter())[country] += 1

    for row in rows:
        ref = (row.get("reference") or _row_value(row, "ref", "onff", "nummer") or "").strip().upper()
        if not ref:
            m = REF_RE.search(" ".join(row.values()))
            ref = f"ONFF-{m.group(1)}" if m else ""
        if not ref or (wanted and not ref.startswith(wanted)):
            continue

        status = (row.get("status") or "active").strip().lower()
        if status and status != "active":
            stats["deleted"] += 1
            # Een geschrapte referentie die wij nog wél tekenen is een echt signaal.
            if ref in have:
                warnings.append(f"{ref} staat als '{status}' in de WWFF-directory maar heeft nog "
                                f"een polygoon in het KMZ — nakijken")
            continue

        stats["listed"] += 1
        seen.add(ref)
        name = row.get("name") or _row_value(row, "name", "naam", "nom")
        q = _to_float(row.get("qsoCount") or "")
        last = (row.get("lastAct") or "").strip()
        if ref in have:
            # Alleen kruiscontrole en activiteit — de polygoon blijft leidend.
            if q is not None or last:
                activity[ref] = {"q": int(q or 0), "last": last or None}
            continue

        listed[ref] = {
            "name": name,
            "prov": _province(row),
            "iucn": (row.get("IUCNcat") or "").strip() or None,
            "site": (row.get("website") or "").strip() or None,
            "loc": (row.get("iaruLocator") or "").strip().upper() or None,
            "latlon": _row_latlon(row),
            "src": "wwff",
        }
        if q is not None or last:
            activity[ref] = {"q": int(q or 0), "last": last or None}

    # Een polygoon zonder rij in de directory. Vergelijk met álle geziene
    # referenties — niet met de activiteitstabel, want een referentie zonder
    # QSO-telling staat daar niet in en is daarom nog niet onbekend.
    if rows and stats["listed"]:
        stats["orphan_polygons"] = sorted(have - seen)

    # overrides.json mag een punt zetten of verplaatsen, en wint altijd.
    for ref, ov in overrides.items():
        if ref in have or not isinstance(ov, dict) or "point" not in ov:
            continue
        listed.setdefault(ref, {"name": None, "prov": None, "iucn": None,
                                "site": None, "loc": None, "latlon": None})
        try:
            lon, lat = float(ov["point"][0]), float(ov["point"][1])
            listed[ref]["latlon"] = (lat, lon)
            listed[ref]["src"] = "overrides"
        except (TypeError, ValueError, IndexError):
            warnings.append(f"{ref}: overrides.json 'point' is geen [lon, lat]")

    features, entries, unplaced = [], [], []
    for ref in sorted(listed):
        info = listed[ref]
        ov = overrides.get(ref) if isinstance(overrides.get(ref), dict) else {}
        props = {
            "ref": ref,
            "name": (ov or {}).get("name") or info.get("name") or ref,
            "prov": (ov or {}).get("province") or info.get("prov"),
            "iucn": info.get("iucn"),
            "loc": info.get("loc"),
            "site": info.get("site"),
            "nopoly": True,
            "src": info.get("src"),
        }
        props = {k: v for k, v in props.items() if v not in (None, "", "n/a", "-")}
        if not info.get("latlon"):
            unplaced.append(ref)
            entries.append({**props, "placed": False})
            continue
        lat, lon = (round(v, decimals) for v in info["latlon"])
        features.append({"type": "Feature", "properties": props,
                         "geometry": {"type": "Point", "coordinates": [lon, lat]}})
        entries.append({**props, "lat": lat, "lon": lon, "placed": True})

    if unplaced:
        warnings.append(f"{len(unplaced)} referenties zonder polygoon én zonder bruikbare positie: "
                        + ", ".join(unplaced[:12]) + ("…" if len(unplaced) > 12 else "")
                        + " — te zetten met \"point\": [lon, lat] in overrides.json")
    if stats["orphan_polygons"]:
        warnings.append(f"{len(stats['orphan_polygons'])} polygonen staan niet in de WWFF-directory: "
                        + ", ".join(stats["orphan_polygons"][:12])
                        + ("…" if len(stats["orphan_polygons"]) > 12 else ""))
    programs_map = {prog: counter.most_common(1)[0][0]
                    for prog, counter in programs_seen.items() if counter}

    # Elke actieve referentie buiten --program, als kaal punt: geen naam-per-land,
    # geen provincie, geen IUCN — enkel wat nodig is om een stip te zetten, want
    # dit wordt al gauw tienduizenden features. Nooit een grens: die bestaat voor
    # geen enkel ander land in wat wij hebben. Positie ontbreekt bij een klein
    # deel (~1%); die worden overgeslagen, nooit verzonnen.
    world_features = []
    for row in rows:
        ref = (row.get("reference") or "").strip().upper()
        if not ref or (wanted and ref.startswith(wanted)):
            continue
        status = (row.get("status") or "active").strip().lower()
        if status != "active":
            continue
        latlon = _row_latlon(row)
        if not latlon:
            continue
        lat, lon = (round(v, 4) for v in latlon)
        world_features.append({
            "type": "Feature",
            "properties": {"ref": ref, "name": (row.get("name") or "").strip()},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })

    return features, entries, activity, warnings, stats, programs_map, world_features


def convert(kml_path: Path, tolerance: float, decimals: int, overrides: dict) -> tuple[dict, dict, dict]:
    tree = etree.parse(str(kml_path))
    document = tree.getroot().find(KML_NS + "Document")
    if document is None:
        raise SystemExit("KML has no <Document> root")

    release = None
    desc = document.find(KML_NS + "description")
    if desc is not None and desc.text:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", desc.text)
        if m:
            release = m.group(1)

    polygons: dict[str, list[Polygon]] = defaultdict(list)
    meta: dict[str, dict] = {}
    warnings: list[str] = []
    skipped_no_ref = 0

    for folder in document.findall(KML_NS + "Folder"):
        folder_name = _name(folder)
        if folder_name in SKIP_FOLDERS:
            continue
        province = None if folder_name in NON_PROVINCE_FOLDERS else folder_name
        layer = folder_name if folder_name in NON_PROVINCE_FOLDERS else None

        for placemark in folder.iter(KML_NS + "Placemark"):
            kml_polys = placemark.findall(".//" + KML_NS + "Polygon")
            if not kml_polys:
                continue
            ref, raw_name = _ref_from_ancestors(placemark)
            if not ref:
                skipped_no_ref += 1
                continue

            for kml_poly in kml_polys:
                outer = kml_poly.find(".//" + KML_NS + "outerBoundaryIs/" + KML_NS + "LinearRing")
                if outer is None:
                    continue
                shell = _ring(outer)
                if len(shell) < 4:
                    continue
                holes = []
                for inner in kml_poly.findall(".//" + KML_NS + "innerBoundaryIs/" + KML_NS + "LinearRing"):
                    ring = _ring(inner)
                    if len(ring) >= 4:
                        holes.append(ring)
                try:
                    poly = Polygon(shell, holes)
                except Exception:
                    warnings.append(f"{ref}: onleesbare polygoon overgeslagen")
                    continue
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty:
                    continue
                polygons[ref].append(poly)

            entry = meta.setdefault(ref, {"names": Counter(), "province": province, "layer": layer})
            if raw_name:
                entry["names"][raw_name] += 1
            if entry["province"] is None and province:
                entry["province"] = province
            attrs = attributes_from(_extended_data(placemark))
            for key, value in attrs.items():
                entry.setdefault(key, value)

    if skipped_no_ref:
        warnings.append(f"{skipped_no_ref} polygonen zonder herkenbaar ONFF-nummer overgeslagen")

    features = []
    index = []
    for ref in sorted(polygons):
        merged = unary_union(polygons[ref])
        simplified = merged.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            warnings.append(f"{ref}: geometrie verdween bij vereenvoudigen, ruwe versie gebruikt")
            simplified = merged
        geom = round_geometry(simplified, decimals)
        if geom is None:
            warnings.append(f"{ref}: geen bruikbare geometrie na afronden — overgeslagen")
            continue

        entry = meta.get(ref, {})
        override = overrides.get(ref, {})

        name = override.get("name") or pick_name(entry.get("names") or Counter(), ref)

        props = {
            "ref": ref,
            "name": name,
            "prov": override.get("province", entry.get("province")),
        }
        for key in ("desig", "iucn", "manager", "registration", "status_year", "layer", "region"):
            value = override.get(key, entry.get(key))
            if value:
                props[key] = value

        area = area_hectares(geom)
        props["area_ha"] = area
        centroid = geom.representative_point()
        bounds = geom.bounds

        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
        index.append({
            **props,
            "lat": round(centroid.y, 5),
            "lon": round(centroid.x, 5),
            "bbox": [round(v, 5) for v in bounds],
            "parts": len(geom.geoms),
        })

    geojson = {"type": "FeatureCollection", "features": features}
    index_doc = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release": release,
        "count": len(index),
        "refs": index,
    }
    stats = {
        "release": release,
        "zones": len(index),
        "polygons": sum(len(v) for v in polygons.values()),
        "warnings": warnings,
    }
    return geojson, index_doc, stats


# --------------------------------------------------------------------------- #
# Diff report
# --------------------------------------------------------------------------- #

def diff_report(new_index: dict, prev_path: Path, stats: dict, source_name: str) -> str:
    new_by_ref = {r["ref"]: r for r in new_index["refs"]}
    lines: list[str] = []

    if not prev_path.exists():
        lines.append(f"## Diana — eerste dataset uit `{source_name}`")
        lines.append("")
        lines.append(f"**{len(new_by_ref)} gebieden** ingelezen. Er is nog geen vorige versie om mee te vergelijken.")
    else:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        prev_by_ref = {r["ref"]: r for r in prev.get("refs", [])}

        added = sorted(set(new_by_ref) - set(prev_by_ref))
        removed = sorted(set(prev_by_ref) - set(new_by_ref))
        changed = []
        for ref in sorted(set(new_by_ref) & set(prev_by_ref)):
            old, cur = prev_by_ref[ref], new_by_ref[ref]
            old_area = old.get("area_ha") or 0
            new_area = cur.get("area_ha") or 0
            if old_area and abs(new_area - old_area) / old_area > 0.01:
                changed.append((ref, cur.get("name"), old_area, new_area))

        delta = len(new_by_ref) - len(prev_by_ref)
        sign = f"+{delta}" if delta > 0 else str(delta)
        lines.append(f"## Diana — nieuwe dataset uit `{source_name}`")
        lines.append("")
        lines.append(
            f"**{len(new_by_ref)} gebieden** (was {len(prev_by_ref)}, {sign}) · "
            f"**{len(added)} nieuw** · **{len(removed)} verdwenen** · "
            f"**{len(changed)} gewijzigde grens**"
        )
        lines.append("")

        if added:
            lines.append(f"<details><summary>{len(added)} nieuwe gebieden</summary>")
            lines.append("")
            for ref in added:
                r = new_by_ref[ref]
                lines.append(f"- `{ref}` {r.get('name')} — {r.get('prov') or 'onbekende provincie'}, {r.get('area_ha')} ha")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        if removed:
            lines.append(f"<details><summary>{len(removed)} verdwenen gebieden — nakijken</summary>")
            lines.append("")
            for ref in removed:
                r = prev_by_ref[ref]
                lines.append(f"- `{ref}` {r.get('name')} — stond in de vorige release, nu niet meer")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        if changed:
            lines.append(f"<details><summary>{len(changed)} gewijzigde grenzen (meer dan 1% oppervlakteverschil)</summary>")
            lines.append("")
            for ref, name, old_area, new_area in changed:
                pct = (new_area - old_area) / old_area * 100
                lines.append(f"- `{ref}` {name}: {old_area} ha → {new_area} ha ({pct:+.1f}%)")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    d = stats.get("directory") or {}
    placed = stats.get("points", 0)
    unplaced = stats.get("points_unplaced", 0)
    if d.get("listed") or placed or unplaced:
        lines.append("")
        lines.append("### Kruiscontrole met de WWFF-directory")
        lines.append("")
        lines.append(f"**{d.get('listed', 0)} actieve referenties** in de directory · "
                     f"**{len(new_by_ref)} met een grens** uit het KMZ · "
                     f"**{placed} als punt** op de kaart"
                     + (f" · **{unplaced} zonder positie**" if unplaced else "")
                     + (f" · {d.get('deleted', 0)} geschrapt (niet getoond)" if d.get("deleted") else ""))
        lines.append("")
        lines.append("Elke referentie komt maar één keer voor: staat er een polygoon in het KMZ, "
                     "dan wint die en wordt de directoryrij alleen gebruikt om te controleren.")
        if unplaced:
            lines.append("")
            lines.append("Referenties zonder positie staan wel in de lijst maar niet op de kaart. "
                         "Een coördinaat zetten kan in `overrides.json`: "
                         "`\"ONFF-0123\": { \"point\": [4.47, 50.85] }` (lengte, breedte).")

    if stats["warnings"]:
        lines.append("")
        lines.append(f"<details><summary>⚠️ {len(stats['warnings'])} waarschuwingen</summary>")
        lines.append("")
        for warning in stats["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")
        lines.append("</details>")

    lines.append("")
    lines.append(f"<sub>Release {stats['release'] or 'onbekend'} · {stats['polygons']} bronpolygonen · gegenereerd door kmz2geojson {SCRIPT_VERSION}</sub>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an ONFF KMZ release into Diana's data files.")
    parser.add_argument("--kmz", required=True, type=Path, help="path to ONFF_YYYYMMDD.kmz")
    parser.add_argument("--out", type=Path, default=Path("data"), help="output directory (default: data)")
    parser.add_argument("--overrides", type=Path, default=Path("overrides.json"))
    parser.add_argument("--report", type=Path, default=Path("report.md"))
    parser.add_argument("--tolerance", type=float, default=0.00005,
                        help="simplification tolerance in degrees (default 0.00005 = ~5 m)")
    parser.add_argument("--decimals", type=int, default=5)
    parser.add_argument("--gzip", action="store_true", help="ook een .gz schrijven, om de uitgeleverde grootte te controleren")
    parser.add_argument("--workdir", type=Path, default=Path(".kmz-work"))
    parser.add_argument("--refs-csv", default=WWFF_DIRECTORY,
                        help="the WWFF directory (URL or local path). It decides which "
                             "references exist; the ones without a polygon in the KMZ become "
                             f"Point features. Default: {WWFF_DIRECTORY}")
    parser.add_argument("--program", default="ONFF",
                        help="comma-separated reference prefixes to keep from the directory "
                             "(default ONFF; e.g. 'ONFF,PAFF,DLFF' for a wider map)")
    parser.add_argument("--no-refs", action="store_true",
                        help="skip the directory entirely (offline builds)")
    args = parser.parse_args()

    if not args.kmz.exists():
        raise SystemExit(f"KMZ not found: {args.kmz}")

    overrides = {}
    if args.overrides.exists():
        raw = json.loads(args.overrides.read_text(encoding="utf-8"))
        overrides = raw.get("zones", raw)

    print(f"→ unpacking {args.kmz.name}", file=sys.stderr)
    kml_path = extract_kmz(args.kmz, args.workdir)

    print("→ parsing and converting", file=sys.stderr)
    geojson, index_doc, stats = convert(kml_path, args.tolerance, args.decimals, overrides)

    print("→ WWFF directory", file=sys.stderr)
    have = {r["ref"] for r in index_doc["refs"]}
    programs = args.program.split(",")
    pt_features, pt_entries, activity, pt_warnings, pt_stats, programs_map, world_features = point_refs(
        None if args.no_refs else args.refs_csv, programs, have, overrides, args.decimals)
    stats["warnings"].extend(pt_warnings)
    stats["points"] = len(pt_features)
    stats["points_unplaced"] = sum(1 for e in pt_entries if not e.get("placed"))
    stats["directory"] = pt_stats
    stats["activity"] = len(activity)
    index_doc["points"] = pt_entries
    index_doc["point_count"] = len(pt_features)

    args.out.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "onff-index.json"

    print("→ writing diff report", file=sys.stderr)
    report = diff_report(index_doc, index_path, stats, args.kmz.name)
    args.report.write_text(report + "\n", encoding="utf-8")

    geojson_path = args.out / "onff.geojson"
    geojson_path.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")
    if args.gzip:
        # Alleen voor een lokale maatcontrole: in productie comprimeert de hosting zelf.
        with gzip.open(str(geojson_path) + ".gz", "wb", compresslevel=9) as fh:
            fh.write(geojson_path.read_bytes())
    index_path.write_text(json.dumps(index_doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # Written even when empty, so the app's fetch is a clean 200 rather than a 404.
    (args.out / "onff-points.geojson").write_text(
        json.dumps({"type": "FeatureCollection",
                    "generated": index_doc["generated"],
                    "features": pt_features}, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8")

    # Activiteit per referentie uit de WWFF-directory: aantal QSO's en de datum van
    # de laatste activatie. Klein bestand, en het laat de heatmap werken zonder de
    # Google-sheet — die is van de drie bronnen veruit de kwetsbaarste.
    if activity:
        (args.out / "onff-activity.json").write_text(
            json.dumps({"generated": index_doc["generated"],
                        "source": "wwff_directory.csv",
                        "refs": activity}, separators=(",", ":")), encoding="utf-8")

    # Wereldwijde programma → land-lijst, voor het spots-filter in de app
    # (Instellingen: alleen ONFF / één specifiek land / wereldwijd). Los van
    # --program: die beperkt alleen wélke referenties de kaart zelf tekent.
    if programs_map:
        (args.out / "wwff-programs.json").write_text(
            json.dumps({"generated": index_doc["generated"],
                        "programs": [{"program": p, "country": c}
                                     for p, c in sorted(programs_map.items(),
                                                         key=lambda kv: kv[1])]},
                       separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # De "andere WWFF-gebieden"-laag: elke actieve referentie buiten --program,
    # als kaal punt. Alleen geschreven als de directory echt gelezen kon worden
    # (anders zou dit een leeg of enorm-verouderd bestand overschrijven met iets
    # dat er nog leger uitziet); anders blijft de vorige versie gewoon staan.
    if world_features:
        (args.out / "wwff-world.geojson").write_text(
            json.dumps({"type": "FeatureCollection",
                        "generated": index_doc["generated"],
                        "features": world_features}, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8")

    (args.out / "meta.json").write_text(json.dumps({
        "source_file": args.kmz.name,
        "release": stats["release"],
        "generated": index_doc["generated"],
        "zones": stats["zones"],
        "directory_listed": pt_stats.get("listed"),
        "directory_deleted": pt_stats.get("deleted"),
        "points_no_polygon": stats["points"],
        "points_unplaced": stats["points_unplaced"],
        "activity_refs": len(activity),
        "world_points": len(world_features),
        "source_polygons": stats["polygons"],
        "tolerance_deg": args.tolerance,
        "decimals": args.decimals,
        "script_version": SCRIPT_VERSION,
    }, indent=2), encoding="utf-8")

    size = geojson_path.stat().st_size / 1e6
    note = ""
    if args.gzip:
        note = f" ({Path(str(geojson_path) + '.gz').stat().st_size / 1e6:.2f} MB gzipped)"
    pts = ""
    if stats["points"] or stats["points_unplaced"]:
        pts = f" · {stats['points']} punten zonder polygoon"
        if stats["points_unplaced"]:
            pts += f" (+{stats['points_unplaced']} zonder coordinaat)"
    world_note = f" · {len(world_features)} wereldwijde WWFF-punten" if world_features else ""
    print(f"✓ {stats['zones']} zones · {size:.2f} MB{note}{pts}{world_note}", file=sys.stderr)
    if stats["warnings"]:
        print(f"⚠ {len(stats['warnings'])} warnings — see {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
