"""Spots staan er altijd op; alleen de lijnen ernaartoe zijn schakelbaar.

En: de kaart opent waar je staat, precies alsof je op de locatieknop drukte —
zonder dat daar nog een instelling voor bestaat.
"""
import re, json, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8011/web/"
fails = []
SPOTS = [{"id": 1, "reference": "ONFF-0001", "activator": "ON4TEST/P", "latitude": 50.85,
          "longitude": 4.35, "frequency_khz": 14285, "mode": "SSB", "spot_time": 9999999999}]


def ok(c, m):
    print(("  \u2713 " if c else "  \u2717 ") + m)
    if not c:
        fails.append(m)


def routes(ctx):
    ctx.route(re.compile(r"https://tiles\.openfreemap\.org/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"version": 8, "sources": {}, "layers": [
            {"id": "bg", "type": "background", "paint": {"background-color": "#e8e4d8"}}]})))
    ctx.route(re.compile(r"https://spots\.wwff\.co/static/spots\.json"), lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SPOTS)))
    ctx.route(re.compile(r"https://spots\.wwff\.co/static/agendas.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))
    ctx.route(re.compile(r"https://docs\.google\.com/.*"), lambda r: r.abort())


with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
                           if __import__("os").path.exists("/opt/pw-browsers/chromium-1194/chrome-linux/chrome") else None)

    print("\n[1] de kaart opent waar je staat, ongevraagd")
    ctx = br.new_context(service_workers="block", viewport={"width": 420, "height": 860},
                         permissions=["geolocation"],
                         geolocation={"latitude": 51.05, "longitude": 3.72})
    routes(ctx)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE, wait_until="load")
    pg.wait_for_timeout(4500)
    c = pg.evaluate("() => { const c = map.getCenter(); return [+c.lng.toFixed(2), +c.lat.toFixed(2), Math.round(map.getZoom())]; }")
    ok(abs(c[0] - 3.72) < 0.05 and abs(c[1] - 51.05) < 0.05, f"gecentreerd op de GPS-positie {c}")
    ok(c[2] >= 12, f"ingezoomd zoals de locatieknop doet (zoom {c[2]})")
    ok(pg.evaluate("() => !!here"), "'here' gezet, dus de booglijnen kunnen getekend worden")
    ok(pg.evaluate("() => !!document.querySelector('.maplibregl-marker')"), "positiemarker staat op de kaart")

    print("\n[2] er valt niets meer te kiezen in Instellingen")
    ok(pg.evaluate("() => !document.getElementById('setView')"), "de startweergave-kaart bestaat niet meer")

    print("\n[3] spots zijn niet uit te zetten")
    ok(pg.evaluate("() => showSpots === true"), "showSpots staat aan")
    ok(pg.evaluate("() => !document.querySelector('[data-layer=spots]')"),
       "geen spots-schakelaar meer in het lagenpaneel")

    print("\n[4] de lijnen ernaartoe wel, en die keuze blijft bewaard")
    pg.wait_for_timeout(1200)
    ok(pg.evaluate("() => map.getLayoutProperty('spot-arcs-line','visibility')") == "visible",
       "lijnen staan standaard aan")
    pg.evaluate("() => document.querySelector('.opt[data-layer=arcs]').click()")
    pg.wait_for_timeout(300)
    ok(pg.evaluate("() => map.getLayoutProperty('spot-arcs-line','visibility')") == "none", "lijnen uit")
    ok(pg.evaluate("() => map.getLayoutProperty('spots-icon','visibility')") == "visible",
       "de spots zelf blijven staan")
    pg.reload(wait_until="load")
    pg.wait_for_timeout(4500)
    ok(pg.evaluate("() => showArcs === false"), "lijnen nog steeds uit na herladen")
    ok(pg.evaluate("() => showSpots === true"), "spots staan na herladen gewoon weer aan")
    real = [e for e in errs if "Failed to load resource" not in e]
    ok(not real, "geen JS-fouten: " + (real[0][:140] if real else "ok"))
    ctx.close()

    print("\n[5] locatie geweigerd: geen klacht, gewoon een bruikbare kaart")
    ctx = br.new_context(service_workers="block", viewport={"width": 420, "height": 860})
    routes(ctx)
    pg = ctx.new_page()
    pg.goto(BASE, wait_until="load")
    pg.wait_for_timeout(4500)
    ok(not pg.evaluate("() => { const r = document.getElementById('status').getBoundingClientRect(); return r.width > 0 && r.height > 0; }"),
       "geen foutmelding in beeld")
    ok(pg.evaluate("() => map.getZoom()") > 5, "kaart staat op de gebieden, niet op een lege wereldbol")
    br.close()

print("\n" + ("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
