#!/usr/bin/env python3
"""
Diana — ONFF KMZ to GeoJSON pipeline.

Reads an official ONFF Google Earth release (ONFF_YYYYMMDD.kmz) and produces the
static data files the Diana PWA loads:

    data/onff.geojson    zone geometry, one MultiPolygon feature per ONFF reference
    data/onff-index.json lightweight index (no geometry) for search, lists and
                         "nearest zones" without loading the full geometry file
    data/meta.json       provenance: which source file, which release, what settings

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
    (args.out / "meta.json").write_text(json.dumps({
        "source_file": args.kmz.name,
        "release": stats["release"],
        "generated": index_doc["generated"],
        "zones": stats["zones"],
        "source_polygons": stats["polygons"],
        "tolerance_deg": args.tolerance,
        "decimals": args.decimals,
        "script_version": SCRIPT_VERSION,
    }, indent=2), encoding="utf-8")

    size = geojson_path.stat().st_size / 1e6
    note = ""
    if args.gzip:
        note = f" ({Path(str(geojson_path) + '.gz').stat().st_size / 1e6:.2f} MB gzipped)"
    print(f"✓ {stats['zones']} zones · {size:.2f} MB{note}", file=sys.stderr)
    if stats["warnings"]:
        print(f"⚠ {len(stats['warnings'])} warnings — see {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
