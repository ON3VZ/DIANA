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

De stijlwisseltest in `test_swipe.py` is de belangrijkste: daar zat de bug waarbij
alle eigen lagen om de beurt verdwenen na `map.setStyle()`.
