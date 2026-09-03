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
    ctx=br.new_context(service_workers="block", viewport={"width":390,"height":844}, has_touch=True); routes(ctx)
    pg=ctx.new_page(); pg.goto(BASE, wait_until="load"); pg.wait_for_timeout(1800)
    pg.evaluate("""() => { const e=new Event('beforeinstallprompt'); e.prompt=()=>{}; 
                           e.userChoice=Promise.resolve({outcome:'dismissed'}); dispatchEvent(e); }""")
    pg.wait_for_timeout(300)
    ok(pg.evaluate("() => getComputedStyle(document.getElementById('instBar')).display")!="none", "balk zichtbaar zonder open paneel")
    pg.evaluate("() => select('ONFF-0953')"); pg.wait_for_timeout(600)
    ok(pg.evaluate("() => getComputedStyle(document.getElementById('instBar')).display")=="none", "balk wijkt voor een open paneel")
    btn = pg.evaluate("""() => { const b=document.getElementById('zoneSpot').getBoundingClientRect();
                                 return {bottom:b.bottom, h:b.height}; }""")
    ok(btn["h"]>10 and btn["bottom"]<844, f"knop in het paneel weer volledig bruikbaar ({btn})")
    pg.screenshot(path="/tmp/shot_fixed.png")
    pg.evaluate("() => closeSheet()"); pg.wait_for_timeout(400)
    ok(pg.evaluate("() => getComputedStyle(document.getElementById('instBar')).display")!="none", "balk komt terug bij sluiten")
    br.close()
print("\n"+("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: "+" | ".join(fails)))
sys.exit(1 if fails else 0)
