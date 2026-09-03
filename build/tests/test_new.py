import re, json, sys, subprocess, time
from playwright.sync_api import sync_playwright

BASE="http://localhost:8011/web/"
fails=[]
def ok(cond,msg):
    print(("  ✓ " if cond else "  ✗ ")+msg)
    if not cond: fails.append(msg)

def route_all(ctx):
    # geen net in deze container: alles wat naar buiten wil, onderscheppen
    ctx.route(re.compile(r"https://tiles\.openfreemap\.org/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"version":8,"sources":{},"layers":[
            {"id":"bg","type":"background","paint":{"background-color":"#e8e4d8"}}]})))
    ctx.route(re.compile(r"https://spots\.wwff\.co/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))
    ctx.route(re.compile(r"https://docs\.google\.com/.*"), lambda r: r.abort())

with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
                           if __import__('os').path.exists("/opt/pw-browsers/chromium-1194/chrome-linux/chrome") else None)
    ctx = br.new_context(service_workers="block", viewport={"width":420,"height":860})
    route_all(ctx)
    pg = ctx.new_page()
    errs=[]
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console."+m.type+": "+m.text) if m.type=="error" else None)
    pg.goto(BASE, wait_until="load")
    pg.wait_for_timeout(2500)

    print("\n[1] geen JS-fouten bij het laden")
    real = [e for e in errs if "Failed to load resource" not in e]   # ./data 404 is de bedoelde terugval
    ok(not real, "geen page errors: "+ (real[0][:160] if real else "ok"))

    print("\n[2] punten zonder polygoon")
    n = pg.evaluate("() => noPoly.features.length")
    ok(n==16, f"16 punten geladen (kreeg {n})")
    inidx = pg.evaluate("() => index.filter(z=>z.nopoly).length")
    ok(inidx==16, f"16 punten in de zoekindex (kreeg {inidx})")
    lay = pg.evaluate("() => !!map.getLayer('np-dot')")
    ok(lay, "laag np-dot bestaat")
    rendered = pg.evaluate("""() => { map.jumpTo({center:[4.5,50.9],zoom:6});
        return map.queryRenderedFeatures({layers:['np-dot']}).length; }""")
    pg.wait_for_timeout(1600)
    rendered = pg.evaluate("() => map.queryRenderedFeatures({layers:['np-dot']}).length")
    ok(rendered>=14, f"punten renderen echt op de kaart ({rendered} van 16; de 16e ligt op Antarctica)")

    print("\n[3] klikken op een punt geeft het juiste paneel")
    pg.evaluate("() => select('ONFF-0953')")
    pg.wait_for_timeout(400)
    ok(pg.locator("#sheet").get_attribute("class").find("open")>=0, "paneel opent")
    ok("Velpevallei" in pg.locator("#zoneName").inner_text(), "naam klopt")
    note = pg.locator("#zoneNote").inner_text()
    ok("no boundary" in note.lower() or "geen grens" in note.lower(), f"uitleg staat er: {note[:60]}…")
    ok(pg.locator("#badges").inner_text().find("Vlaams-Brabant")>=0, "provincie uit de directory wordt getoond")
    ok("area" not in pg.locator("#facts").inner_text().lower() and " ha" not in pg.locator("#facts").inner_text(),
       "geen verzonnen oppervlakte")

    print("\n[4] GPS-test slaat punten over (mag niet crashen)")
    errs.clear()
    pg.evaluate("() => evaluate(50.84896, 4.90140, 12)")   # exact op een punt zonder polygoon
    pg.wait_for_timeout(300)
    ok(not errs, "geen fout bij evaluate() vlakbij een punt: "+(errs[0][:120] if errs else "ok"))
    st = pg.locator("#status").inner_text()
    ok("outside" in st.lower() or "buiten" in st.lower() or len(st)>0, f"status getoond: {st[:70]}…")

    print("\n[5] melding is wegklikbaar")
    ok(pg.locator("#status").get_attribute("class").find("show")>=0, "melding staat aan")
    pg.locator("#stClose").click()
    pg.wait_for_timeout(200)
    ok(pg.locator("#status").get_attribute("class").find("show")<0, "melding weggeklikt")

    print("\n[6] zoeken vindt een referentie zonder grens")
    pg.evaluate("() => { const s=document.getElementById('search'); s.classList.add('on'); s.style.display='block'; }")
    pg.evaluate("() => { const i=document.getElementById('q'); i.value='0961'; i.dispatchEvent(new Event('input',{bubbles:true})); }")
    pg.wait_for_timeout(400)
    res = pg.evaluate("() => document.getElementById('results').innerText")
    ok("Parkbos" in res, "gevonden in zoekresultaten")
    ok("◌" in res, "gemarkeerd als zonder grens")

    print("\n[7] laagknop voor de punten")
    ok(pg.evaluate("() => !document.getElementById('optNopoly').hidden"), "laagknop vrijgegeven zodra er punten zijn")
    pg.evaluate("""() => { const o=document.querySelector('[data-layer=\\"nopoly\\"]'); o.click(); }""")
    pg.wait_for_timeout(300)
    vis = pg.evaluate("() => map.getLayoutProperty('np-dot','visibility')")
    ok(vis=="none", f"uitzetten werkt (visibility={vis})")
    pg.evaluate("""() => document.querySelector('[data-layer=\\"nopoly\\"]').click()""")
    pg.wait_for_timeout(300)
    ok(pg.evaluate("() => map.getLayoutProperty('np-dot','visibility')")=="visible", "weer aan werkt")

    br.close()

print("\n"+("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: "+ " | ".join(fails)))
sys.exit(1 if fails else 0)
