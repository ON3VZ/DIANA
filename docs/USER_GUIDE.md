# User guide

Diana is a map of Belgium's ONFF nature reserves (Flora & Fauna, part of
WWFF) with live WWFF activation spots layered on top. It runs entirely in
your browser, works offline once loaded, and can be installed like a native
app. This guide covers every screen, how to install it, and — importantly —
what it *doesn't* do.

---

## 1. Supported platforms

Diana is a standard Progressive Web App (PWA): any reasonably modern browser
works, and no app-store install is required.

| Platform | Browser | Works? | Installable as an app? |
|---|---|---|---|
| Android | Chrome, Edge, Samsung Internet | Yes | Yes |
| iOS / iPadOS | Safari | Yes | Yes (via Share → Add to Home Screen) |
| iOS / iPadOS | Chrome, Firefox, etc. | Yes | No — iOS only allows PWA installation from Safari |
| Windows / macOS / Linux | Chrome, Edge, other Chromium browsers | Yes | Yes |
| Windows / macOS / Linux | Firefox, Safari | Yes | Browsing works fully; "install as app" isn't offered by these browsers |

GPS-based features (locate-me, session tracking) need a device with a
location sensor and browser location permission — they degrade gracefully
without it: everything else keeps working.

---

## 2. Installing Diana as an app

Installing just wraps the same web app in its own window and icon — there is
no separate "app version" with different features.

**Android (Chrome):** open Diana, tap the ⋮ menu → **Add to Home screen** (or
look for the "Install app" banner Chrome shows automatically).

**iPhone/iPad (Safari):** open Diana, tap the Share icon (square with an
arrow), scroll down and tap **Add to Home Screen**.

**Desktop (Chrome/Edge):** open Diana, click the install icon in the address
bar (a small monitor-with-arrow icon), or ⋮ menu → **Install Diana…**.

Once installed, Diana opens in its own window without browser chrome, and
the service worker (see [ARCHITECTURE.md §4](ARCHITECTURE.md#4-offline-behaviour-service-worker))
keeps the map and zone data available even with no signal — handy on
activation, where connectivity is exactly what you won't have.

---

## 3. The screens

Bottom navigation, left to right:

### Map (◈)
The main screen. Four base-map styles, search by name or reference number, a
zone-detail panel showing only whatever attributes that zone actually has
(most zones have far less metadata than you'd expect — see
[ARCHITECTURE.md §2.1](ARCHITECTURE.md#21-the-onff-kmz)), and GPS "am I
inside this zone right now" with a warning when your GPS accuracy is poor
enough that the answer could flip. Zone reference numbers are shown as
labels by default. When a spot or zone panel is open, on a phone-sized
screen only one bottom panel is ever visible at a time — opening one tucks
the other out of the way automatically.

Turning on the **Spots** map layer (toggle on the map screen, or `?spots=1`
in the URL) adds a green pulsing icon for each currently active spot and a
dashed lighter-orange marker for each announced-but-not-yet-active agenda
item, plus an arc line from your own position (GPS, or your saved locator)
to each one, labelled with frequency. **⤢ Zoom to all spots** re-frames the
map to fit everything currently shown, including your own position.

### Spots (((·)))
A list view of the same live spots and agenda, filterable to ONFF-only or
worldwide, refreshed every 30 seconds. Tap a spot for bearing, distance, a
compass heading, and both locators.

### Meld / self-spot (✚)
Spot yourself. Reference number is pre-filled if you came from a zone's
detail panel; callsign and spotter are remembered from your last self-spot.
Validation mirrors WWFF Spotline's own rules exactly (callsign format and
digit requirement, frequency range, minimum reference length, a 100-character
remark limit), plus a live check that the reference you typed actually
exists and is active. A bandplan check warns if your chosen mode doesn't
match the segment your frequency falls in (e.g. SSB on a CW-only segment).
Sending opens Spotline's own confirmation page in a new tab — your spot goes
out exactly the way it would if you'd used Spotline directly.

### Settings (⚙)
Your callsign, portable callsign (e.g. `ON3VZ/P`), Maidenhead grid locator
(with "take it from GPS" and format validation), and a home-view preference
that controls where the map opens: **at your locator**, **at your country**
(derived from your callsign's prefix), or **the whole dataset**. If neither
locator nor a recognised prefix is set, the map falls back to fitting all
currently loaded zones — never a meaningless blank world view. Everything
here is local to this device; see §Limitations.

### Admin (⛭, hidden by default)
For repository maintainers only — publishing new data and generating embed
codes. Hidden until `?admin=1` is used or the Diana logo is tapped five
times. Full documentation: [ADMIN.md](ADMIN.md).

### Session (◉)
Start a tracked activation session: a timer, percentage of time spent inside
the zone, and on finishing, a GPX file (with per-point "inside the zone?"
and GPS-accuracy extensions) plus a text summary — useful as activation
proof. The GPS track is generated and downloaded entirely on your device and
is never uploaded anywhere by Diana.

### Heatmap (▦)
Colours every zone by either recency of last activation or total QSO count,
sourced from the published ONFF activation-history sheet. This colouring
only applies while you're on this screen — leaving it returns the map to its
normal single theme colour, so the Heatmap screen doesn't change what the
Map screen looks like.

### Rules (☰)
The IARU Region 1 bandplan per band, with CW/Digi/SSB/FM segments drawn as a
visual bar, FT8 frequencies marked, and WWFF's own preferred SSB/CW
calling frequencies per band highlighted.

---

## 4. Languages

Diana is available in English, Dutch, French, German, Danish, Italian and
Spanish. Language is chosen, in order: the `?lang=` URL parameter, your
previously saved choice, your browser's language (if it's one of the seven),
otherwise **English by default**. Switching language re-renders every
screen immediately — nothing requires a page reload, and nothing is left in
the old language. Zone names themselves are never translated: they're
official names and belong in activation logs exactly as ONFF publishes them.

---

## 5. Embedding Diana on another page

Diana can be dropped into any web page as an iframe — the ONFF blog, a club
site, anything that accepts HTML.

```html
<iframe src="https://<your-domain>/?embed=1&prov=antwerpen&lang=en&spots=1"
        width="100%" height="600" style="border:0"
        loading="lazy" allow="geolocation"></iframe>
```

| Parameter | Effect |
|---|---|
| `?embed=1` | hides Diana's own navigation and header, so it fits inside someone else's page chrome |
| `?lang=en\|nl\|fr\|de\|da\|it\|es` | forces a language, overriding browser detection |
| `?ref=ONFF-0104` | opens directly zoomed to one zone |
| `?prov=antwerpen` | zooms to one Belgian province |
| `?spots=1` | turns the live-spots map layer on immediately |
| `?admin=1` | reveals the Admin panel (not meaningful in an embed; documented here only for completeness) |

The Admin panel (§Admin above) includes a small form that builds this exact
snippet for you from a province, language and spots choice — see
[ADMIN.md §Generating an embed snippet](ADMIN.md#generating-an-embed-snippet).

---

## 6. Limitations

**Everything is stored on this one device, in this one browser — nothing
syncs.** Your callsign, grid locator, home-view preference, language choice,
and (if you enabled it) a remembered Admin token all live in that browser's
local storage. If you open Diana on your phone and then on your laptop, you
will need to enter your settings again on the laptop — the two are
completely independent, and Diana has no account system to tie them
together. Clearing your browser's site data, or using a private/incognito
window, also clears these settings.

**GPS session tracks are not backed up anywhere.** The GPX file from an
activation session exists only as the download it produces — save it
somewhere you'll keep it.

**Live data depends on third parties Diana doesn't control.** Spots, the
agenda, and the activation-history heatmap all come from WWFF Spotline and a
Google Sheet maintained by the ONFF coordinator (see
[ARCHITECTURE.md §2](ARCHITECTURE.md#2-where-the-apps-own-data-comes-from)).
If either is unavailable or changes shape, the relevant screen says so
rather than showing stale data silently — but there's nothing Diana itself
can do to bring either one back online.

**Not every zone has full details.** Roughly half of the 932 mapped ONFF
zones have no attributes beyond a name and reference number — this is a gap
in the underlying source data, not something the app is hiding.

**Data usage terms.** The zone boundaries and activation figures shown in
Diana come from ONFF, WDPA, Flemish/Walloon government sources, and WWFF
Spotline, and remain their owners' data — Diana's *code* is open source
(MIT), but the *data and content* may not be freely redistributed or reused
elsewhere without permission. See [LICENSE](../LICENSE) for the exact terms
and the honest technical caveat about what a web map necessarily has to send
to a visitor's browser.
