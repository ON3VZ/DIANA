# Developer guide

How to get the repository running on your own machine, how the two GitHub
Actions workflows fit together, and how `data/*.json` actually gets made —
both the automatic way and the manual one.

This is the *build-time* half of Diana. For what happens at *runtime* (the
app itself, its data sources, its APIs) see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Repository layout

```
diana/
├─ source/            official ONFF KMZ releases, as received from BOS groups.io
├─ build/             KMZ → GeoJSON conversion                    ← build-time
│  ├─ kmz2geojson.py
│  ├─ requirements.txt
│  └─ site.sh         assembles the publishable folder (excludes source/)
├─ data/              the output — what the app actually loads
│  ├─ onff.geojson
│  ├─ onff-points.geojson   references with no boundary, as Points
│  ├─ onff-activity.json    QSO count + last activation per reference
│  ├─ wwff-programs.json    every WWFF programme worldwide → its country (for the spots filter)
│  ├─ wwff-world.geojson    every active non-ONFF WWFF reference worldwide, as bare points
│  ├─ onff-index.json
│  └─ meta.json
├─ overrides.json     manual name corrections, keyed by reference number
├─ web/               the web application itself                  ← runtime
│  ├─ index.html      the entire app: markup, styles, logic, one file
│  ├─ manifest.webmanifest
│  ├─ sw.js           service worker (offline cache)
│  └─ vendor/         MapLibre GL JS, vendored locally (not a CDN)
├─ docs/              this documentation set
└─ .github/workflows/
   ├─ build-data.yml  runs the conversion on a pull request
   └─ pages.yml       publishes to GitHub Pages (with PR previews)
```

The split that matters: **`build/` runs on a GitHub-hosted runner and never
reaches a visitor's browser.** `web/` is the only thing a user ever loads.
Nothing in `build/` is shipped as part of the site.

---

## 2. Cloning and running locally

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
python3 -m http.server 8000
# open http://localhost:8000/web/
```

Start the server **from the repository root**, not from `web/`. The app
requests `../data/onff.geojson` (repository layout) and falls back to
`./data/onff.geojson` (published layout) — starting the server inside `web/`
puts `data/` outside the server root and both requests 404.

No build step, no `npm install`, no bundler. `web/index.html` is a single
static file; MapLibre GL JS is vendored under `web/vendor/` so the app has no
external runtime dependency and genuinely works offline.

To also regenerate the data locally, see §4.

---

## 3. The two GitHub Actions workflows

### `build-data.yml` — convert KMZ to GeoJSON

| Trigger | What happens |
|---|---|
| Pull request touching `source/**.kmz`, `overrides.json`, or `build/**` | Runs `kmz2geojson.py`, commits the regenerated `data/*.json` to the PR branch, and posts (or updates) one PR comment with a diff report |
| `schedule` — every night at **01:00 UTC** | Runs the same conversion against the newest KMZ already in `source/`, so the only thing that can actually change is whatever the WWFF directory itself changed since yesterday (new/renamed/retired references, updated QSO counts) — never a boundary, since those only come from a KMZ. The script runs with `--strict`, so an unreachable **or truncated** directory aborts the build instead of degrading; a **"Uitvoer controleren"** step then re-checks the *content* (zone count, and how many directory references were actually read) rather than merely whether the files are non-empty. Only past both does it commit — **directly to `main`**, no pull request — bumping the last digit of `APP_VERSION` in the same commit, and retrying the push up to three times with a rebase if `main` moved meanwhile. On failure, cancellation, or a run skipped for a missing KMZ, a **"Melding maken bij een mislukte nachtelijke build"** step opens a GitHub issue (or comments on the existing one) labelled `diana-nachtelijke-build` |
| `workflow_dispatch` | Same conversion, run on demand from the Actions tab |

The nightly run is what makes brand-new WWFF references (and status/QSO
changes) show up without anyone touching the repository, and — unlike a KMZ
upload — it is allowed to publish by itself, since the worst it can do is
place or rename a reference, never draw a wrong boundary. A failed night
raises a GitHub issue rather than failing silently — as does a night that
quietly did nothing at all, because "no KMZ in `source/`" would otherwise look
identical to "nothing to refresh" forever. See
[ADMIN.md §3](ADMIN.md#3-where-the-data-comes-from--and-what-you-actually-have-to-do)
for what that looks like and how GitHub's own notifications get it to you.

The diff report looks like:

> **945 zones** (was 932, +13) · **15 new** · **2 removed** · **7 boundary changed**

with the actual lists collapsed under a `<details>` toggle. A removed zone is
real information — ONFF does retire reference numbers — so it is always
surfaced, never silently applied.

The comment is marker-based (`<!-- diana-preview -->`-style), so pushing a
second commit to the same PR *updates* the existing comment instead of
piling up new ones.

### `pages.yml` — publish to GitHub Pages

Deliberately **not** the standard `actions/deploy-pages` action, because that
action has no concept of a pull-request preview — and without a preview,
merging a new KMZ is a leap of faith.

| Trigger | Result |
|---|---|
| push to `main`/`master` | `build/site.sh` output replaces the live site at the repo root of the `gh-pages` branch |
| pull request opened/updated | published to `.../preview/pr-<number>/`, with the link posted as a PR comment |
| pull request closed | that preview folder is deleted |
| `workflow_run` after `build-data.yml` succeeds | publishes whatever that run committed. **This trigger is load-bearing:** a push made with the default `GITHUB_TOKEN` does not start new workflows, so without it the nightly data commit would land on `main` and never be published, and a PR preview would show the dataset from *before* the build |
| `workflow_dispatch` | same as a push — mainly useful to bootstrap `gh-pages` the very first time, before it exists |

Requires **Settings → Actions → General → Workflow permissions → "Read and
write permissions"**, set *before* the first run — otherwise the push to
`gh-pages` fails with a 403. Full first-time setup and troubleshooting (a
missing `gh-pages` branch, a `.github/` folder silently dropped by a
drag-and-drop upload, etc.) is in [DEPLOY.md](../DEPLOY.md).

`build/site.sh` assembles `_site/` from `web/` plus the three `data/*.json`
files, and **excludes `source/`** — the KMZ never becomes part of the
published site, even though it lives in the repository's git history so the
Action can read it.

```
pull request (new KMZ)
        │
        ▼
 build-data.yml ── regenerates data/*.json, comments the diff
        │
        ▼
   pages.yml ── publishes a PR preview at /preview/pr-<n>/
        │
   (human looks at the preview)
        │
      merge
        │
        ▼
   pages.yml ── publishes to the live site
```

---

## 4. Generating `data/*.json` manually

Same script the Action runs, for when you want to check a KMZ before opening
a pull request, or you're iterating on `overrides.json`.

```bash
pip install -r build/requirements.txt --break-system-packages
python build/kmz2geojson.py --kmz "source/ONFF 20260101.kmz"
```

Takes roughly half a minute for the full Belgian dataset.

| Option | Default | Purpose |
|---|---|---|
| `--kmz` | — | path to the source KMZ (required) |
| `--tolerance` | `0.00005` | polygon simplification, in degrees (≈ 5 m — below typical GPS accuracy) |
| `--decimals` | `5` | coordinate rounding (5 decimals ≈ 1 m) |
| `--out` | `data` | output folder |
| `--overrides` | `overrides.json` | manual name-correction file |
| `--report` | `report.md` | where the diff report is written |
| `--refs-csv` | `https://wwff.co/wwff-data/wwff_directory.csv` | the WWFF directory (URL **or** local path) — the list of which references exist |
| `--program` | `ONFF` | comma-separated reference prefixes to keep from the directory, e.g. `ONFF,PAFF,DLFF` for a wider map |
| `--no-refs` | off | skip the directory entirely — for builds with no network |
| `--strict` | off | exit non-zero if the directory is unreachable **or looks truncated** (fewer rows than expected, or a sharp drop against the previous build) instead of continuing with less data. The nightly run uses this: nothing written beats bad data committed unattended |

The directory is fetched fresh on every build — it is regenerated daily, so
pinning a copy would go stale. Reading is deliberately tolerant: columns are
matched by name (never by position, so a new column in the middle is harmless),
a header row below a title row is found, and a position falls back from
`latitude`/`longitude` to the `iaruLocator` square. If the directory cannot be
read at all, the build **continues** with a warning rather than failing — a
moved file must never block a data release; you just get manual points from
`overrides.json` only that run. In CI the URL can be overridden without touching
code, via a repository variable `ONFF_REFS_CSV`.

### What the script actually does

1. Parses the KML inside the KMZ with `lxml`.
2. Extracts the ONFF reference number from the **folder name**, not a data
   field — placemarks are grouped under folders named `ONFF-nnnn <name>`.
   This is a real quirk of the source data, not a design choice; see
   [ARCHITECTURE.md](ARCHITECTURE.md#31-the-onff-kmz).
3. Merges every polygon under one reference number into a single
   `MultiPolygon` with `shapely.ops.unary_union` — some references (e.g.
   ONFF-0329) consist of dozens of disconnected parcels.
4. Simplifies geometry (`simplify(tolerance, preserve_topology=True)`) and
   computes geodesic area with `pyproj.Geod`.
5. Picks the best of the (often typo'd, duplicated, or filename-derived)
   candidate names per reference, then applies `overrides.json` on top,
   keyed by reference number — **never by name**, so a correction survives
   the next release even if the source spelling changes again.
6. Writes `data/onff.geojson` (full geometry), `data/onff-index.json` (the
   same list without geometry — for search and lists without loading the
   large file), and `data/meta.json` (provenance: source file, release date,
   settings used).
7. Fetches the WWFF directory (`--refs-csv`), keeps the rows for `--program`,
   drops everything whose `status` is not `active`, and joins it to the polygons
   on the reference number. References with no polygon are written to
   `data/onff-points.geojson` as Points — positioned from `overrides.json`
   (`"point": [lon, lat]`, always wins), then the directory's coordinates, then
   its IARU locator. References with none of those are reported, not invented.
   The QSO count and last-activation date of every reference go to
   `data/onff-activity.json`, which the app's heatmap uses when the ONFF sheet
   is unreachable. Separately — over the **whole** directory, ignoring
   `--program` — every programme code is tallied against its most common
   `country` value and written to `data/wwff-programs.json`; and every active
   reference that is *not* ONFF is written to `data/wwff-world.geojson` as a
   bare `{ref, name}` Point (no boundary — same rule as the boundary-less ONFF
   references above). The map's own zones stay ONFF-only regardless; these two
   files feed, respectively, the spots screen's country picker and the
   optional "other WWFF areas" map layer (on by default, see
   [ARCHITECTURE.md §2.1.3](ARCHITECTURE.md#213-other-wwff-areas-worldwide)).
8. Diffs the new output against the previous release and writes
   `report.md` — new zones, removed zones, boundary changes, and how many
   boundary-less references were placed or left unplaced.

### Correcting a name

Edit `overrides.json`, keyed by reference number, with a `_why` note so the
reason is still legible years later:

```json
"ONFF-0599": {
  "name": "Carrière de l'Alouette",
  "_why": "KMZ has \"Carriere de 'Alouttel\" — two typos"
}
```

A pull request against this file alone re-triggers `build-data.yml`, exactly
like a new KMZ would.

---

## 5. Publishing a new ONFF release (short version)

The full walkthrough, with screenshots-worth of detail, is in
[ADMIN.md](ADMIN.md#1-publishing-a-new-onff-release). In short: upload the
new KMZ to `source/` on a branch → open a pull request → `build-data.yml`
comments the diff, `pages.yml` comments a preview link → look at the
preview → merge to publish, or close/revert to discard. No local checkout is
required for this path at all — it can be done entirely from github.com, or
from Diana's own in-app Admin panel (§`ADMIN.md`).
