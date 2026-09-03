import re, json, sys
from playwright.sync_api import sync_playwright
BASE = "http://localhost:8011/web/"
fails = []


def ok(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c:
        fails.append(m)


SPOTS = [
    {"id": 1, "reference": "ONFF-0001", "activator": "ON1TEST", "latitude": 50.85, "longitude": 4.35,
     "frequency_khz": 14285, "mode": "SSB", "spot_time": 9999999999},
    {"id": 2, "reference": "PAFF-0123", "activator": "PA1TEST", "latitude": 52.1, "longitude": 5.1,
     "frequency_khz": 7130, "mode": "SSB", "spot_time": 9999999999},
    {"id": 3, "reference": "VKFF-0456", "activator": "VK1TEST", "latitude": -35.3, "longitude": 149.1,
     "frequency_khz": 21200, "mode": "SSB", "spot_time": 9999999999},
]


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
                            if __import__('os').path.exists("/opt/pw-browsers/chromium-1194/chrome-linux/chrome") else None)
    ctx = br.new_context(service_workers="block", viewport={"width": 420, "height": 860})
    routes(ctx)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE, wait_until="load")
    pg.wait_for_timeout(2000)

    print("\n[1] fabrieksinstelling: wereldwijd, niet ONFF-only")
    default_filter = pg.evaluate("() => spotFilter")
    ok(default_filter == "all", f"spotFilter default is 'all' (kreeg '{default_filter}')")

    print("\n[2] wwff-programs.json is ingeladen")
    n = pg.evaluate("() => wwffPrograms.length")
    ok(n > 100, f"meer dan 100 programma's geladen (kreeg {n})")
    onff_country = pg.evaluate("() => (wwffPrograms.find(p=>p.program==='ONFF')||{}).country")
    ok(onff_country == "Belgium", f"ONFF → Belgium (kreeg '{onff_country}')")

    print("\n[3] wereldwijd toont alle drie de spots")
    pg.evaluate("() => { showSpots=true; startSpots(); }")
    pg.wait_for_timeout(600)
    vis = pg.evaluate("() => visibleSpots().length")
    ok(vis == 3, f"3 spots zichtbaar bij 'wereldwijd' (kreeg {vis})")

    print("\n[4] ONFF-only laat alleen de Belgische spot zien")
    pg.evaluate("() => document.querySelector('#spotFilter [data-filter=\"onff\"]').click()")
    pg.wait_for_timeout(200)
    vis_onff = pg.evaluate("() => visibleSpots().map(s=>s.reference)")
    ok(vis_onff == ["ONFF-0001"], f"alleen ONFF-0001 (kreeg {vis_onff})")

    print("\n[5] een specifiek land via Instellingen")
    pg.evaluate("""() => {
        const sel = document.getElementById('setSpotCountry');
        const opt = [...sel.options].find(o => o.textContent === 'Netherlands');
        sel.value = opt.value; sel.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(200)
    vis_nl = pg.evaluate("() => visibleSpots().map(s=>s.reference)")
    ok(vis_nl == ["PAFF-0123"], f"alleen de Nederlandse spot (kreeg {vis_nl})")

    print("\n[6] de twee schermen blijven gesynchroniseerd")
    spot_screen_on = pg.evaluate(
        "() => [...document.getElementById('spotFilter').children].some(b=>b.classList.contains('on'))")
    ok(not spot_screen_on, "geen ONFF/Wereldwijd-knop actief zodra een land gekozen is")

    print("\n[7] keuze overleeft herladen")
    saved = pg.evaluate("() => localStorage.getItem('diana.spotFilter')")
    ok(saved == "PAFF", f"'PAFF' bewaard (kreeg '{saved}')")
    pg.reload(wait_until="load")
    pg.wait_for_timeout(2000)
    after_reload = pg.evaluate("() => spotFilter")
    ok(after_reload == "PAFF", f"filter nog steeds 'PAFF' na herladen (kreeg '{after_reload}')")
    sel_after = pg.evaluate("() => document.getElementById('setSpotCountry').value")
    ok(sel_after == "PAFF", "land-keuzelijst toont de bewaarde keuze na herladen")

    print("\n[8] terug naar wereldwijd via het snelle filter")
    pg.evaluate("() => document.querySelector('#spotFilter [data-filter=\"all\"]').click()")
    pg.wait_for_timeout(200)
    country_reset = pg.evaluate("() => document.getElementById('setSpotCountry').value")
    ok(country_reset == "", "land-keuzelijst weer leeg na 'Wereldwijd'")

    print("\n[9] geen JS-fouten")
    real = [e for e in errs if "Failed to load resource" not in e]
    ok(not real, "geen page errors: " + (real[0][:160] if real else "ok"))

    br.close()

print("\n" + ("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
