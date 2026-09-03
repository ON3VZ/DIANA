import re, json, sys
from playwright.sync_api import sync_playwright
BASE = "http://localhost:8011/web/"
fails = []


def ok(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c:
        fails.append(m)


def routes(ctx):
    ctx.route(re.compile(r"https://tiles\.openfreemap\.org/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"version": 8, "sources": {}, "layers": [
            {"id": "bg", "type": "background", "paint": {"background-color": "#e8e4d8"}}]})))
    ctx.route(re.compile(r"https://spots\.wwff\.co/static/spots\.json"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))
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
    pg.wait_for_timeout(3000)   # het echte wwff-world.geojson is ~9 MB, geef het even

    print("\n[1] fabrieksinstelling: wereldwijde laag staat aan")
    default_on = pg.evaluate("() => showWorld")
    ok(default_on is True, f"showWorld default is true (kreeg {default_on})")
    default_filter = pg.evaluate("() => worldFilter")
    ok(default_filter == "all", f"worldFilter default is 'all' (kreeg '{default_filter}')")

    print("\n[2] de wereldwijde puntenlaag is ingeladen en getekend")
    pg.wait_for_function("() => worldLoaded === true", timeout=15000)
    n = pg.evaluate("() => worldPoints.features.length")
    ok(n > 60000, f"meer dan 60.000 punten geladen (kreeg {n})")
    has_onff = pg.evaluate("() => worldPoints.features.some(f => f.properties.ref.startsWith('ONFF'))")
    ok(not has_onff, "geen ONFF-referenties in de wereldwijde laag (dat is de eigen kaartlaag)")
    src_exists = pg.evaluate("() => !!map.getSource('wwff-world')")
    ok(src_exists, "MapLibre-bron 'wwff-world' bestaat")
    # world-cluster-count is een tekstlaag en heeft glyphs nodig — de neptest-stijl
    # heeft die niet (net zomin als np-label die al langer dezelfde 'if(glyphs)'-wacht heeft).
    layers_exist = pg.evaluate(
        "() => ['world-clusters','world-point'].every(l => !!map.getLayer(l))")
    ok(layers_exist, "de cluster- en puntlaag bestaan")

    print("\n[3] filter op één land beperkt de bron")
    pg.evaluate("""() => {
        const sel = document.getElementById('setWorldCountry');
        const opt = [...sel.options].find(o => o.textContent === 'Netherlands');
        sel.value = opt.value; sel.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(300)
    saved_filter = pg.evaluate("() => worldFilter")
    ok(saved_filter == "PAFF", f"worldFilter is 'PAFF' na landkeuze (kreeg '{saved_filter}')")
    filtered_n = pg.evaluate("() => worldFilteredData().features.length")
    all_paff = pg.evaluate(
        "() => worldFilteredData().features.every(f => f.properties.ref.toUpperCase().split('-')[0] === 'PAFF')")
    ok(filtered_n > 0 and all_paff, f"alleen PAFF-referenties in de gefilterde data ({filtered_n} stuks)")

    print("\n[4] keuze overleeft herladen")
    stored = pg.evaluate("() => localStorage.getItem('diana.worldFilter')")
    ok(stored == "PAFF", f"'PAFF' bewaard in localStorage (kreeg '{stored}')")
    pg.reload(wait_until="load")
    pg.wait_for_timeout(3000)
    pg.wait_for_function("() => worldLoaded === true", timeout=15000)
    after_reload = pg.evaluate("() => worldFilter")
    ok(after_reload == "PAFF", f"worldFilter nog steeds 'PAFF' na herladen (kreeg '{after_reload}')")
    sel_after = pg.evaluate("() => document.getElementById('setWorldCountry').value")
    ok(sel_after == "PAFF", "landkeuzelijst toont de bewaarde keuze na herladen")

    print("\n[5] terug naar wereldwijd")
    pg.evaluate("""() => {
        const sel = document.getElementById('setWorldCountry');
        sel.value = ''; sel.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(300)
    back_to_all = pg.evaluate("() => worldFilter")
    ok(back_to_all == "all", f"worldFilter weer 'all' (kreeg '{back_to_all}')")

    print("\n[6] de laag kan uit- en aangezet worden via het lagenpaneel")
    pg.evaluate("() => document.querySelector('.opt[data-layer=\"world\"]').click()")
    pg.wait_for_timeout(200)
    off_vis = pg.evaluate("() => map.getLayoutProperty('world-point','visibility')")
    ok(off_vis == 'none', f"laag verborgen na uitzetten (kreeg '{off_vis}')")
    pg.evaluate("() => document.querySelector('.opt[data-layer=\"world\"]').click()")
    pg.wait_for_timeout(200)
    on_vis = pg.evaluate("() => map.getLayoutProperty('world-point','visibility')")
    ok(on_vis == 'visible', f"laag weer zichtbaar na aanzetten (kreeg '{on_vis}')")

    print("\n[7] embed zonder ?world=1 laat de laag uit")
    pg2 = ctx.new_page()
    pg2.on("pageerror", lambda e: errs.append(str(e)))
    pg2.goto(BASE + "?embed=1", wait_until="load")
    pg2.wait_for_timeout(2000)
    embed_off = pg2.evaluate("() => showWorld")
    ok(embed_off is False, f"showWorld staat uit in een kale embed (kreeg {embed_off})")
    # Spots zijn juist de uitzondering: die horen er altijd op, ook in een embed.
    embed_spots = pg2.evaluate("() => showSpots")
    ok(embed_spots is True, f"showSpots staat wél aan in een embed (kreeg {embed_spots})")
    pg2.close()

    print("\n[8] embed mét ?world=1 zet de laag wél aan")
    pg3 = ctx.new_page()
    pg3.on("pageerror", lambda e: errs.append(str(e)))
    pg3.goto(BASE + "?embed=1&world=1", wait_until="load")
    pg3.wait_for_timeout(3000)
    embed_on = pg3.evaluate("() => showWorld")
    ok(embed_on is True, f"showWorld staat aan met ?world=1 (kreeg {embed_on})")
    pg3.close()

    print("\n[9] geen JS-fouten")
    real = [e for e in errs if "Failed to load resource" not in e]
    ok(not real, "geen page errors: " + (real[0][:160] if real else "ok"))

    br.close()

print("\n" + ("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
