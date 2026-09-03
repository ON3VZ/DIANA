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

    print("\n[A] standaardtaal is Engels, ook met een Nederlandse browser")
    ctx=br.new_context(service_workers="block", locale="nl-BE", viewport={"width":420,"height":860}); routes(ctx)
    pg=ctx.new_page(); pg.goto(BASE, wait_until="load"); pg.wait_for_timeout(1500)
    ok(pg.evaluate("() => lang")=="en", "start in het Engels ondanks locale nl-BE")
    ok(pg.evaluate("() => langPref")=="en", "voorkeur staat op 'en'")

    print("\n[B] taal instellen in Instellingen blijft bewaard")
    pg.evaluate("() => document.querySelector('#nav button[data-view=\"viewSet\"]').click()")
    pg.wait_for_timeout(300)
    pg.evaluate("() => document.querySelector('#setLang .seg[data-lang=\"nl\"]').click()")
    pg.wait_for_timeout(400)
    ok(pg.evaluate("() => lang")=="nl", "taal gewisseld naar NL")
    ok(pg.evaluate("() => localStorage.getItem('diana.lang')")=="nl", "keuze opgeslagen")
    ok("Instellingen" in pg.evaluate("() => document.querySelector('#viewSet h1').textContent"), "scherm ook echt vertaald")
    pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
    ok(pg.evaluate("() => lang")=="nl", "keuze overleeft herladen")

    print("\n[C] 'Volg de browser' doet wat het zegt")
    pg.evaluate("() => document.querySelector('#nav button[data-view=\"viewSet\"]').click()")
    pg.evaluate("() => document.querySelector('#setLang .seg[data-lang=\"auto\"]').click()")
    pg.wait_for_timeout(400)
    ok(pg.evaluate("() => lang")=="nl", "volgt browsertaal nl-BE")
    ok(pg.evaluate("() => localStorage.getItem('diana.lang')")=="auto", "'auto' bewaard, niet de opgeloste taal")
    ctx.close()

    print("\n[D] onbekende browsertaal met 'auto' valt terug op Engels")
    ctx=br.new_context(service_workers="block", locale="pl-PL"); routes(ctx)
    pg=ctx.new_page()
    pg.add_init_script("localStorage.setItem('diana.lang','auto')")
    pg.goto(BASE, wait_until="load"); pg.wait_for_timeout(1200)
    ok(pg.evaluate("() => lang")=="en", "Pools wordt niet ondersteund → Engels")
    ctx.close()

    print("\n[E] installeren: knop verschijnt pas als de browser het aanbiedt")
    ctx=br.new_context(service_workers="block", viewport={"width":420,"height":860}); routes(ctx)
    pg=ctx.new_page(); pg.goto(BASE, wait_until="load"); pg.wait_for_timeout(1500)
    pg.evaluate("() => document.querySelector('#nav button[data-view=\"viewSet\"]').click()")
    pg.wait_for_timeout(200)
    ok(pg.evaluate("() => document.getElementById('instBtn').hidden"), "geen knop zonder aanbod van de browser")
    how = pg.evaluate("() => document.getElementById('instHow').innerText")
    ok(len(how)>10, f"wél een uitleg per platform: “{how[:60]}…”")
    ok(pg.evaluate("() => document.getElementById('instBar').hidden"), "geen balk zonder aanbod")

    print("\n[F] installeren: met een aanbod verschijnt knop én balk, en de prompt loopt")
    pg.evaluate("""() => {
      window.__prompted = 0; window.__choice = null;
      const e = new Event('beforeinstallprompt');
      e.prompt = () => { window.__prompted++; };
      e.userChoice = Promise.resolve({outcome:'accepted', platform:'web'});
      dispatchEvent(e);
    }""")
    pg.wait_for_timeout(300)
    ok(not pg.evaluate("() => document.getElementById('instBtn').hidden"), "knop verschijnt")
    ok(not pg.evaluate("() => document.getElementById('instBar').hidden"), "balk verschijnt")
    pg.evaluate("() => document.getElementById('instBtn').click()")
    pg.wait_for_timeout(400)
    ok(pg.evaluate("() => window.__prompted")==1, "prompt() precies één keer aangeroepen")
    ok(pg.evaluate("() => localStorage.getItem('diana.installed')")=="1", "geïnstalleerd onthouden")
    ok("✓" in pg.evaluate("() => document.getElementById('instHow').innerText"), "toont nu 'is geïnstalleerd'")

    print("\n[G] 'niet nu' vraagt het niet opnieuw")
    pg.evaluate("() => { localStorage.removeItem('diana.installed'); localStorage.removeItem('diana.inst.asked'); }")
    pg.reload(wait_until="load"); pg.wait_for_timeout(1200)
    pg.evaluate("""() => { const e=new Event('beforeinstallprompt'); e.prompt=()=>{}; e.userChoice=Promise.resolve({outcome:'dismissed'}); dispatchEvent(e); }""")
    pg.wait_for_timeout(200)
    ok(not pg.evaluate("() => document.getElementById('instBar').hidden"), "balk staat er")
    pg.evaluate("() => document.getElementById('instBarNo').click()")
    pg.wait_for_timeout(200)
    ok(pg.evaluate("() => document.getElementById('instBar').hidden"), "weggeklikt")
    pg.reload(wait_until="load"); pg.wait_for_timeout(1200)
    pg.evaluate("""() => { const e=new Event('beforeinstallprompt'); e.prompt=()=>{}; e.userChoice=Promise.resolve({outcome:'dismissed'}); dispatchEvent(e); }""")
    pg.wait_for_timeout(300)
    ok(pg.evaluate("() => document.getElementById('instBar').hidden"), "komt niet terug na herladen")

    print("\n[H] iOS: geen loze knop maar de Safari-stappen")
    ctx2=br.new_context(service_workers="block",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        viewport={"width":390,"height":844}); routes(ctx2)
    pg2=ctx2.new_page(); pg2.goto(BASE, wait_until="load"); pg2.wait_for_timeout(1500)
    ok(pg2.evaluate("() => platform()")=="ios", "platform herkend als iOS/Safari")
    pg2.evaluate("() => document.querySelector('#nav button[data-view=\"viewSet\"]').click()")
    pg2.wait_for_timeout(200)
    txt = pg2.evaluate("() => document.getElementById('instHow').innerText")
    ok("Home Screen" in txt or "Add to" in txt, f"toont de Deel→Zet-op-beginscherm-stappen: “{txt[:70]}…”")
    ok(pg2.evaluate("() => document.getElementById('instBtn').hidden"), "geen knop die toch niets kan doen")
    ctx2.close()

    print("\n[I] manifest en iconen zijn echt bereikbaar")
    r1 = pg.request.get("http://localhost:8011/web/manifest.webmanifest")
    r2 = pg.request.get("http://localhost:8011/web/icon-192.png")
    r3 = pg.request.get("http://localhost:8011/web/icon-512.png")
    r4 = pg.request.get("http://localhost:8011/web/apple-touch-icon.png")
    ok(r1.status==200 and r2.status==200 and r3.status==200 and r4.status==200,
       f"manifest {r1.status}, iconen {r2.status}/{r3.status}/{r4.status}")
    mf = r1.json()
    ok(any(i["sizes"]=="512x512" for i in mf["icons"]), "512-icoon staat in het manifest")
    ok(any(i.get("purpose")=="maskable" for i in mf["icons"]), "maskable-variant aanwezig")

    br.close()
print("\n"+("ALLES OK" if not fails else f"{len(fails)} PROBLEMEN: "+" | ".join(fails)))
sys.exit(1 if fails else 0)
