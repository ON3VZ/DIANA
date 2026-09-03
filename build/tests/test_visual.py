import re, json, sys
from playwright.sync_api import sync_playwright
BASE="http://localhost:8011/web/"
fails=[]
def ok(c,m):
    print(("  ✓ " if c else "  ✗ ")+m); 
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
    pg=ctx.new_page(); pg.goto(BASE, wait_until="load"); pg.wait_for_timeout(2000)

    print("\n[1] het icoon wordt echt getekend (pixels tellen, niet hopen)")
    pg.evaluate("() => map.jumpTo({center:[5.228,51.062], zoom:11})"); pg.wait_for_timeout(1200)
    pt = pg.evaluate("() => { const p = map.project([5.228,51.062]); return [Math.round(p.x), Math.round(p.y)]; }")
    shot = pg.screenshot(clip={"x":max(0,pt[0]-30),"y":max(0,pt[1]-30),"width":60,"height":60})
    open("/tmp/np_icon.png","wb").write(shot)
    from PIL import Image
    im = Image.open("/tmp/np_icon.png").convert("RGB")
    px = list(im.getdata())
    def near(c, t, tol=26): return all(abs(c[i]-t[i])<=tol for i in range(3))
    green = sum(1 for c in px if near(c,(27,67,50)))
    amber = sum(1 for c in px if near(c,(217,119,6)))
    print(f"    groene ringpixels: {green} · amberkern: {amber}")
    ok(green>40, "gestippelde groene ring zichtbaar")
    ok(amber>4, "amberkleurige kern zichtbaar")

    print("\n[2] installbalk overlapt de onderbalk niet")
    pg.evaluate("""() => { const e=new Event('beforeinstallprompt'); e.prompt=()=>{}; 
                           e.userChoice=Promise.resolve({outcome:'dismissed'}); dispatchEvent(e); }""")
    pg.wait_for_timeout(400)
    box = pg.evaluate("""() => { const b=document.getElementById('instBar').getBoundingClientRect();
                                 const n=document.getElementById('nav').getBoundingClientRect();
                                 return {bBottom:b.bottom, nTop:n.top, bTop:b.top, w:b.width}; }""")
    print("   ", box)
    ok(box["bBottom"] <= box["nTop"]+1, f"balk eindigt boven de nav ({box['bBottom']:.0f} ≤ {box['nTop']:.0f})")
    ok(box["bTop"] > 0 and box["w"] > 200, "balk staat volledig in beeld")
    pg.screenshot(path="/tmp/shot_bar.png")

    print("\n[3] paneel van een punt zonder grens")
    pg.evaluate("() => document.getElementById('instBarNo').click()")
    pg.evaluate("() => select('ONFF-0011')"); pg.wait_for_timeout(800)
    pg.screenshot(path="/tmp/shot_point.png")
    ok(True, "screenshot gemaakt")

    print("\n[4] instellingenscherm met taal + installeren")
    pg.evaluate("() => closeSheet()")
    pg.evaluate("() => document.querySelector('#nav button[data-view=\"viewSet\"]').click()")
    pg.wait_for_timeout(400)
    pg.screenshot(path="/tmp/shot_settings.png", full_page=True)
    ok(True, "screenshot gemaakt")
    br.close()
print("\n"+("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: "+" | ".join(fails)))
sys.exit(1 if fails else 0)
