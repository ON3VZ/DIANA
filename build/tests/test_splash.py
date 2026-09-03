import re, json, sys
from playwright.sync_api import sync_playwright
BASE="http://localhost:8011/web/"
fails=[]
def ok(c,m):
    print(("  ✓ " if c else "  ✗ ")+m)
    if not c: fails.append(m)
def routes(ctx):
    ctx.route(re.compile(r"https://tiles\.openfreemap\.org/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"version":8,"sources":{},"layers":[{"id":"bg","type":"background","paint":{"background-color":"#e8e4d8"}}]})))
    ctx.route(re.compile(r"https://spots\.wwff\.co/.*"), lambda r: r.fulfill(status=200, content_type="application/json", body="[]"))
    ctx.route(re.compile(r"https://docs\.google\.com/.*"), lambda r: r.abort())

with sync_playwright() as p:
    br=p.chromium.launch()
    ctx=br.new_context(service_workers="block", viewport={"width":390,"height":844}); routes(ctx)
    pg=ctx.new_page(); errs=[]
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE, wait_until="commit")

    print("\n[1] startscherm staat er meteen")
    pg.wait_for_selector("#splash", timeout=3000)
    pg.wait_for_timeout(450)
    vis = pg.evaluate("() => { const e=document.getElementById('splash'); if(!e) return null; const s=getComputedStyle(e); return {disp:s.display, op:s.opacity, bg:s.backgroundImage.slice(0,60)}; }")
    print("   ", vis)
    ok(vis and vis["disp"]!="none" and float(vis["op"])>0.5, "zichtbaar bij het laden")
    ok(vis and "start.jpg" in vis["bg"], "de tekening staat erop")
    ok(pg.evaluate("() => (document.getElementById('splashVer')||{}).textContent||''").startswith("v"),
       "versienummer staat erop: " + pg.evaluate("() => (document.getElementById('splashVer')||{}).textContent||''"))
    txt = pg.evaluate("() => (document.getElementById('splashTxt')||{}).textContent||''")
    ok(len(txt)>3, f"laadtekst: “{txt}”")
    anim = pg.evaluate("""() => { const s=document.querySelector('.splash .sweep'); const t=document.querySelector('.splash .tx i');
        return {sweep:getComputedStyle(s).animationName, tx:getComputedStyle(t).animationName}; }""")
    ok(anim["sweep"]=="dsweep" and anim["tx"]=="dtx", f"signaalanimaties lopen: {anim}")
    pg.screenshot(path="/tmp/shot_splash.png")
    pg.wait_for_timeout(1200); pg.screenshot(path="/tmp/shot_splash2.png")

    print("\n[2] verdwijnt vanzelf zodra de kaart er staat")
    pg.wait_for_function("() => !document.getElementById('splash')", timeout=12000)
    ok(True, "startscherm is weg")
    ms = pg.evaluate("() => performance.now()")
    print(f"    (na {ms/1000:.1f}s)")
    ok(ms < 11000, "binnen een redelijke tijd")
    ok(pg.evaluate("() => !!map.getLayer('onff-fill')"), "de kaartlaag staat er dan ook echt")

    print("\n[3] de 16 echte punten uit de WWFF-directory")
    n = pg.evaluate("() => noPoly.features.length")
    ok(n==16, f"16 punten geladen (kreeg {n})")
    ok(pg.evaluate("() => index.filter(z=>z.nopoly).length")==16, "alle 16 in de zoekindex")
    dup = pg.evaluate("""() => { const seen={}, dups=[];
        for(const z of index){ if(seen[z.ref]) dups.push(z.ref); seen[z.ref]=1; } return dups; }""")
    ok(not dup, f"geen dubbele referenties in de index ({dup[:4]})")
    pg.evaluate("() => select('ONFF-0951')"); pg.wait_for_timeout(500)
    ok("Orneau" in pg.evaluate("() => document.getElementById('zoneName').textContent"), "naam uit de directory")

    print("\n[4] onderbalk: alle labels op dezelfde hoogte")
    tops = pg.evaluate("""() => [...document.querySelectorAll('#nav button')].filter(b => b.offsetParent).map(b => {
        const lab = b.querySelector('span:last-child');
        return {v:b.dataset.view, top:Math.round(lab.getBoundingClientRect().top),
                ic:Math.round(b.querySelector('.ic').getBoundingClientRect().top)}; })""")
    for t in tops: print("   ", t)
    labtops = {t["top"] for t in tops}
    ictops  = {t["ic"] for t in tops}
    ok(len(labtops)==1, f"labels op één lijn ({sorted(labtops)})")
    ok(len(ictops)==1, f"iconen op één lijn ({sorted(ictops)})")
    pg.screenshot(path="/tmp/shot_nav.png", clip={"x":0,"y":770,"width":390,"height":74})

    print("\n[5] geen JS-fouten")
    real=[e for e in errs if "Failed to load resource" not in e]
    ok(not real, "geen page errors: "+(real[0][:130] if real else "ok"))
    br.close()
print("\n"+("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: "+" | ".join(fails)))
sys.exit(1 if fails else 0)
