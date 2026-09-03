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
| `data/onff-index.json` | 210 kB | search, lists, "nearest zone", province filters, embed `?prov=` | the same list **without geometry**: reference, name, province, area, centroid, bounding box |
| `data/meta.json` | small | not shown to the user; provenance only | which source KMZ, which release date, which build settings produced this data |

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
  of them (97%) — about 33 references currently have no polygon at all.
- The KMZ also contains a Maidenhead grid overlay of roughly 32,700
  placemarks, which the build script discards: a grid is cheaper to compute
  client-side than to ship as data.

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
| `localStorage` key `diana.lang` | chosen UI language | No |
| `localStorage` key `diana.cfg` (or similar settings keys) | callsign, portable callsign, grid locator, home-view preference | No |
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
