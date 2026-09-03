# Browsertests

Playwright-tests die de app in een echte (headless) browser draaien, met alle
externe hosts onderschept — er is dus geen netwerk voor nodig.

```bash
pip install playwright --break-system-packages
python3 -m http.server 8011          # vanuit de repo-root
python3 build/tests/test_new.py      # enz.
```

| Bestand | Wat het bewaakt |
|---|---|
| `test_new.py` | punten zonder grens: laden, tekenen, paneel, zoeken, laagknop, en dat de GPS-test ze overslaat |
| `test_more.py` | taalkeuze (standaard Engels, "volg de browser", bewaard blijven) en de installatiestroom per platform |
| `test_swipe.py` | naar beneden vegen om panelen te sluiten, en of alle eigen lagen zes stijlwissels overleven |
| `test_final.py` | dat de installatiebalk wijkt voor een open paneel |
| `test_splash.py` | startscherm, versienummer, de 16 punten, en of de onderbalk uitgelijnd staat |
| `test_heat.py` | heatmap uit de sheet én de terugval op de WWFF-directory |
| `test_worldpoints.py` | wereldwijde WWFF-gebieden: standaard aan, clustering, filteren op één land, laag uit/aan, en dat een embed hem uit laat tenzij `?world=1` |
| `test_spotsalways.py` | dat de kaart ongevraagd opent waar je staat, dat spots niet uit te zetten zijn, en dat alleen de lijnen ernaartoe schakelbaar zijn (en bewaard blijven) |
| `test_directory.py` | de bouwstap zelf (geen browser): onmogelijke coördinaten, lekken tussen de lagen, en of `--strict` bij een onbereikbare of afgebroken directory écht niets overschrijft |
| `test_spotsfilter.py` | spots-filter: standaard wereldwijd, ONFF-only, één land via `wwff-programs.json`, en dat het snelle filter en Instellingen gesynchroniseerd blijven en de herlaadbeurt overleven |

De stijlwisseltest in `test_swipe.py` is de belangrijkste: daar zat de bug waarbij
alle eigen lagen om de beurt verdwenen na `map.setStyle()`.
