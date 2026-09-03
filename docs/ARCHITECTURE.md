# Architecture

Where every piece of data comes from, which network calls the app makes, and
which files it reads. This is the *runtime* half of Diana — for how the
`data/*.json` files are produced in the first place, see
[DEVELOPER.md](DEVELOPER.md).

---

## 1. The shape of the system

Diana has **no backend of its own**. It is a static site: HTML, CSS and JS in
one file (`web/index.html`), plus three small JSON files it reads at load
time, plus a handful of third-party endpoints it calls directly from the
visitor's browser.

```
                         ┌─────────────────────────┐
                         │   visitor's browser      │
                         │                          │
                         │   web/index.html         │
                         │   (map, screens, logic)  │
                         └────────────┬─────────────┘
                                      │
        ┌─────────────────┬──────────┼──────────────┬───────────────────┐
        ▼                 ▼          ▼               ▼                   ▼
 data/onff.geojson  tiles.openfreemap  spots.wwff.co  docs.google.com   api.github.com
 data/onff-index    .org (map tiles)   (spots, agenda,  (gviz CSV,       (Admin panel
 data/meta.json     from this repo's   self-spot POST,  activation       only — see
 (same repo,        published gh-pages  ref validation)  history sheet)  ADMIN.md)
  no API needed)
```

Nothing here needs a server Diana controls. The service worker
(`web/sw.js`) adds an offline cache on top of exactly these same requests —
it does not introduce a new data source.

---

## 2. Where the app's own data comes from

| File | Size (approx.) | Read by | Contents |
|---|---|---|---|
| `data/onff.geojson` | 3.7 MB (≈1 MB gzipped) | the map, on load | one `MultiPolygon` per ONFF reference, with name, province, area, and whatever attributes the source KMZ provided |
| `data/onff-points.geojson` | small | the map, on load (optional — a missing file is not an error) | one `Point` per reference that exists on the ONFF list but has **no boundary** in the KMZ |
| `data/onff-activity.json` | 39 kB | the Heatmap, as a fallback | QSO count and last-activation date per reference, taken from the WWFF directory |
| `data/onff-index.json` | 210 kB | **not loaded by the app** — it exists for tooling, reports and anything built alongside Diana | the zone list **without geometry**: reference, name, province, area, centroid, bounding box, plus a `points` array covering the boundary-less references (including those with no known coordinate, which therefore appear in no other file) |
| `data/meta.json` | small | not shown to the user; provenance only | which source KMZ, which release date, which build settings, and how many boundary-less references were placed or left unplaced |

The app builds its own in-memory search index from `onff.geojson` +
`onff-points.geojson` at load time, so `onff-index.json` is a build artefact
rather than a runtime dependency — useful to know before optimising the wrong
file.

The app tries `./data/...` first (published layout, data next to
`index.html`) and falls back to `../data/...` (repository layout, one level
up) — see `loadData()` / `fetchFirst()` in `index.html`. This is what lets
the exact same file work whether you're browsing the published site or a
checkout served from the repo root.

All of Belgium fits in about one megabyte gzipped. That is *why* Diana has no
tile server and no database of its own — the entire reference dataset is
small enough to ship as a static file and hold in memory.

### 2.1 The ONFF KMZ, one layer further back

`data/onff.geojson` is generated (see [DEVELOPER.md §4](DEVELOPER.md#4-generating-datajson-manually))
from a KMZ released periodically by Belgian Flora & Fauna (ONFF, part of
Belgium Outdoor Shack) through a members-only groups.io. A few things worth
knowing when reasoning about gaps in the data:

- It is, underneath, a **WDPA export** (World Database on Protected Areas)
  with the ONFF layer on top — hence the mixed-case field names
  (`MANG_AUTH`, `GIS_AREA`, `IUCN_CAT` alongside Flemish lowercase fields
  like `opp_ha`, `inspireid`).
- The **reference number is not a data field** — it lives in the name of the
  enclosing KML folder, as `ONFF-nnnn <name>`. Every tool in this pipeline
  therefore keys on the folder-derived number, never on name text.
- Coverage is uneven. Of 932 zones in the KMZ: 565 have a designation
  (`desig`), 515 an IUCN category, 445 a manager, 75 a registration number,
  81 a region code — and roughly half have **nothing beyond name and
  number**. The app treats every attribute as optional and omits empty
  fields rather than showing a placeholder.
- The ONFF index sheet (see §2.2) lists 965 references; the KMZ covers 932
  of them (97%) — exactly 33 reference numbers in the 0001–0965 range have no
  polygon at all. Those become Points rather than disappearing; §2.1.1 covers
  how they are placed.
- The KMZ also contains a Maidenhead grid overlay of roughly 32,700
  placemarks, which the build script discards: a grid is cheaper to compute
  client-side than to ship as data.

### 2.1.1 The WWFF directory — which references exist

`https://wwff.co/wwff-data/wwff_directory.csv` is regenerated daily and lists
**every WWFF reference worldwide** — about 68,000 rows across 190 national
programmes, 964 of them ONFF. Columns: `reference, status, name, program, dxcc,
state, county, continent, iota, iaruLocator, latitude, longitude, IUCNcat,
validFrom, validTo, notes, lastMod, changeLog, reviewFlag, specialFlags,
website, country, region, dxccEnum, qsoCount, lastAct`. The build reads them by
name, never by position.

This is the source of record for **which references exist**; the KMZ only says
which of them have a *boundary*. The two are joined on the reference number:

| Situation | What Diana does |
|---|---|
| in the directory **and** in the KMZ (932) | draws the polygon; the directory row is used only to cross-check and for activity figures |
| in the directory, **not** in the KMZ (16) | draws a Point at the directory's coordinates |
| `status` is not `active` (16) | not shown at all — the directory keeps retired references, renamed "DELETED AREA — …" |
| in the KMZ, **not** in the directory | flagged as a warning in the build report — currently none |

That table is the whole de-duplication rule: **a polygon always wins, so a
reference is drawn once and only once.** 932 + 16 = 948 = exactly the number of
active ONFF references the directory lists.

Two data traps the build guards against, both real: the directory marks "position
unknown" as latitude/longitude `0,0` *and* locator `JJ00AA` (which converts to
0.02, 0.04 — close to but not exactly zero), and one row carries an impossible
`lastAct` year of 1059. Both are filtered rather than plotted or coloured.

Coordinates come from `latitude`/`longitude`, falling back to the centre of the
`iaruLocator` square, falling back to `overrides.json`. `overrides.json` always
wins where set.

### 2.1.2 References with no boundary

A reference on ONFF's list but absent from the KMZ used to be invisible in
Diana. It is now drawn as a **dashed ring with an amber centre** — deliberately
unlike a zone outline, because a point is not a boundary. Consequences that are
enforced in code, not just documented:

- the GPS "am I inside this zone" test skips them entirely — there is no inside
  to be in, and claiming otherwise would be worse than saying nothing
- the detail panel shows no area and no parcel count, and states plainly why
- they are searchable and marked `◌` in results, and can be toggled off as
  their own map layer
- an announced agenda item on such a reference can still be plotted, because
  the point gives it a position

Coordinates come from three places, in this order:

| Source | Notes |
|---|---|
| `overrides.json` → `"point": [lon, lat]` | manual, always wins, survives every new release |
| the directory's `latitude`/`longitude` | filled for every active ONFF row today |
| the centre of its `iaruLocator` square | the backstop; roughly 5 km accuracy, which is fine for "this reference is over there" |

Unplaced references are not silently dropped: they are counted in `meta.json`,
listed in the build's PR comment with an instruction to add a coordinate, and
recorded in `onff-index.json`. As of the current data there are none.

### 2.2 The ONFF activation-history sheet (heatmap)

The Heatmap screen colours zones by recency or QSO count, sourced from a
**published Google Sheet** maintained by the ONFF coordinator (sheet ID
`1MFZzdq6xJtpvTtOHfRob6Pvxeo2_5YOQSHjVE0wAyac`), fetched as CSV through the
`gviz` endpoint — not the `/export` endpoint:

```
https://docs.google.com/spreadsheets/d/<id>/gviz/tq?tqx=out:csv&sheet=<tab>
```

`/export?format=csv` returns `401` for this sheet and is not used. The
`gviz` endpoint also accepts a small query language (e.g.
`&tq=select D, max(A), sum(C) group by D`), which lets the app ask the
sheet to pre-aggregate rather than downloading everything and reducing it
client-side.

If the sheet cannot be reached — it is a published spreadsheet, not an API, and
whether CORS allows a browser to read it is still unconfirmed — the Heatmap
falls back to `data/onff-activity.json`, built from the WWFF directory at data
build time. That fallback is coarser (a total QSO count and one last-activation
date per reference, with no per-year breakdown) but it needs no third party at
all and works offline. The panel says which of the two it is showing.

Relevant tabs: one per year (2013–2026: activation date, activating
callsign, QSO count, ONFF reference, region, low-power/GoGreen flags),
`"Still to go"` (references never activated), and the index tab (965
references with name, municipality, IUCN category, province, manager,
cross-references to Windmill/Lighthouse/SOTA/Castle award programmes).

This is a scrape of a spreadsheet someone else maintains for a different
purpose, not a published API — treat it as the least stable data source in
the system, and expect the app's visible fallback message if it ever moves
or is unpublished.

### 2.3 WWFF Spotline (live spots, agenda, self-spotting)

No API key. Refreshed every 30 seconds while a Spots-related screen is
visible, paused when the browser tab is hidden.

| Endpoint | Used for |
|---|---|
| `GET spots.wwff.co/static/spots.json` | the last ~50 live spots, **with** latitude/longitude |
| `GET spots.wwff.co/static/agendas_active.json` | activations currently announced as starting |
| `GET spots.wwff.co/static/agendas.json` | the full announced agenda |
| `GET spots.wwff.co/api/references/validate?reference=X` | live check while typing a reference in the self-spot form: `{valid, is_active, name}` — an undocumented endpoint found in Spotline's own page source, not in any published API docs |
| `POST spots.wwff.co/spots/store` | submitting your own spot (see below) |

`agendas.json`/`agendas_active.json` carry **no coordinates** — Spotline
doesn't publish where an announced-but-not-yet-active reference is. For ONFF
references, Diana substitutes the centroid of its own polygon from
`onff-index.json`; for anything else it cannot place the item on the map at
all, and counts it in a visible "n without a known location" line rather
than guessing or silently dropping it.

**Self-spotting is a genuine HTML form submission, not a `fetch()` call.**
`web/index.html` builds a real `<form method="post" target="_blank">`
pointing at `/spots/store` and submits it, opening Spotline's own
confirmation page in a new tab. Form submissions are not subject to CORS, so
this is the one Spotline interaction that needs **no proxy regardless of
Spotline's server configuration**. Reading the three static JSON files
above, by contrast, is a normal cross-origin `fetch()` and *could* be
blocked by CORS depending on how `spots.wwff.co` is configured — this has
not yet been confirmed against the live site from outside this development
environment. If it turns out to be blocked, the affected screens say so
explicitly rather than failing silently; the fix at that point would be a
small proxy in front of the three JSON files only (self-spotting would be
unaffected).

The client-side validation mirrored from Spotline's own form (kept in sync
manually, since there's no shared schema):

| Field | Rule |
|---|---|
| Callsign (activator/spotter) | `/^[A-Z0-9/]{3,}$/` **and** at least one digit |
| Frequency | 135.7 – 7,500,000,000 kHz |
| Reference | at least 7 characters, plus the live `/references/validate` check |
| Remarks | max 100 characters; Spotline additionally runs a server-side profanity filter |
| Callsign/spotter/reference | auto-uppercased before sending, matching Spotline's own behaviour |

**Status of the "upcoming API" mentioned on wwff.co/spotline:** Spotline's
site references an API in addition to the three static files above. Diana
currently uses only the static files, which are confirmed working. Kristof
is requesting official API access from WWFF separately; if and when that
access exists, the fetch layer for spots/agenda would be the only part of
the app that needs to change — everything downstream (rendering, filtering,
map layers) is already written against a normalised in-memory shape, not
against the raw JSON structure.

### 2.4 OpenFreeMap (base map)

Vector tiles and styles from `https://tiles.openfreemap.org/styles/<style>`
(`liberty`, `positron`, `bright`, `dark`). No API key, no rate limit,
commercial use permitted. Required attribution, shown in the app:
*"OpenFreeMap © OpenMapTiles Data from OpenStreetMap"*. MapLibre GL JS
itself is vendored into `web/vendor/` rather than loaded from a CDN, so the
only *runtime* network dependency for the base map is the tile host itself
— everything needed to render tiles once fetched is already local.

### 2.5 GitHub REST/Git Data API (Admin panel only)

Used only when a user explicitly opens the Admin panel and uploads a file;
never called during normal browsing. Full flow in [ADMIN.md](ADMIN.md).

---

## 3. What's stored where, and what never leaves the device

| Storage | Contents | Synced across devices? |
|---|---|---|
| `localStorage` key `diana.lang` | language preference: a language code, or `auto` to follow the browser. Absent means English | No |
| `localStorage` keys `diana.call` / `diana.callp` / `diana.grid` / `diana.view` | callsign, portable callsign, grid locator, home-view preference | No |
| `localStorage` keys `diana.installed` / `diana.inst.asked` | whether the app was installed, and whether the install banner has already been dismissed once | No |
| `localStorage` (admin keys) | remembered repository/branch/path, and the GitHub token **only if the "remember" checkbox was ticked** | No |
| Session GPX track (in memory / downloaded file) | an activation session's GPS trace | Not stored at all beyond the download — never uploaded anywhere |
| Cache Storage (service worker) | app shell, the three `data/*.json` files, map tiles (LRU-capped) | No — per browser profile |

There is no account system and no server-side state anywhere in Diana. Every
one of these lives in one browser, on one device. See
[USER_GUIDE.md §Limitations](USER_GUIDE.md#limitations) for what that means
in practice for someone using Diana on more than one device.

---

## 4. Offline behaviour (service worker)

`web/sw.js` applies one rule consistently: **cache-first for anything that's
reviewed and versioned, network-first with a visible fallback for anything
that has to be fresh.**

| Request | Strategy |
|---|---|
| App shell (`index.html`, `manifest.webmanifest`, vendored MapLibre, the three `data/*.json` files, in both possible layouts) | cache-first, refreshed opportunistically |
| Map tiles (`tiles.openfreemap.org`) | cache-first, own cache bucket, roughly LRU-trimmed at 3000 entries (~60 MB) |
| Live data (`spots.wwff.co`, `docs.google.com`) | network-first; falls back to the last cached response only if the network request fails, so a visitor is never shown stale spots without the app having tried for fresh ones first |

Caches are versioned (`diana-v1-shell`, `diana-v1-tiles`); a version bump in
`sw.js` drops every old cache on activation.

---

## 5. Runtime request flow, end to end

```
load index.html
   │
   ├─ loadData() ── data/onff.geojson + onff-index.json + meta.json
   │                (independent of the map — search, rules, session
   │                 screens all work even if the map never loads)
   │
   ├─ map init ── tiles.openfreemap.org (style + vector tiles)
   │              paintZones() once both data AND style are ready
   │
   ├─ startSpots() ── spots.wwff.co/static/{spots,agendas_active,agendas}.json
   │                  polled every 30s while a relevant screen is open
   │
   ├─ Heatmap screen opened ── docs.google.com gviz CSV, on demand
   │
   ├─ self-spot submitted ── real form POST to spots.wwff.co/spots/store
   │                          (bypasses fetch/CORS entirely)
   │
   └─ Admin panel used ── api.github.com, only on explicit user action
```
