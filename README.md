# Diana

Kaart-app voor de Belgische ONFF-natuurgebieden (Belgian Flora & Fauna, onderdeel van
WWFF) met live WWFF-spots. Een PWA op een open-source achtergrondkaart, die offline
werkt en embedbaar is op een website.

Code: MIT. Data: niet vrij — zie [LICENSE](LICENSE).

Dit is de repo. Het volledige plan staat in `Diana - Technisch plan v0.6.md`; online zetten staat in [DEPLOY.md](DEPLOY.md).

## Documentatie (Engels)

Uitgebreide documentatie per doelgroep staat in [`docs/`](docs/):

| Document | Voor wie | Inhoud |
|---|---|---|
| [docs/DEVELOPER.md](docs/DEVELOPER.md) | ontwikkelaars | repo clonen, de twee GitHub Actions-workflows, `data/*.json` genereren — automatisch én manueel |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | ontwikkelaars/beheerders | waar elke databron vandaan komt, welke API's er lopen, welke mappen de app inleest |
| [docs/ADMIN.md](docs/ADMIN.md) | beheerders | een nieuwe ONFF-release publiceren, het adminscherm in de app gebruiken, foutopsporing |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | gebruikers | platformen, installeren als app, elk scherm uitgelegd, embedden, en de **beperkingen** (alles lokaal, geen synchronisatie tussen toestellen) |

Deze Nederlandstalige `README.md` en `DEPLOY.md` blijven de kortste weg voor
wie al met de repo vertrouwd is; de `docs/`-map is de volledige, Engelstalige
uitleg voor elk van de vier doelgroepen hierboven.

---

## Wat er in deze repo zit

```
source/           de officiële ONFF KMZ-releases, zoals ze van de BOS-groups.io komen
build/            de omzetting van KMZ naar de datafiles die de app laadt   ← bouwtijd
data/             het resultaat — dit is wat de app ophaalt
overrides.json    handmatige correcties die elke nieuwe release overleven
web/              de webapplicatie zelf                                     ← runtime
_site/            wat er gepubliceerd wordt (gemaakt door build/site.sh, niet in git)
.github/          de Action die dit alles automatisch doet bij een pull request
```

Twee helften die niet door elkaar lopen: `build/` draait op een GitHub-runner en komt
nooit bij een gebruiker; `web/` is wat mensen openen.

## De app draaien

Een statische server volstaat — de app heeft geen backend.

```bash
python3 -m http.server 8000        # vanuit de repo-root, niet vanuit web/
# open http://localhost:8000/web/
```

Vanuit `web/` starten werkt niet: de app haalt `../data/onff.geojson` op, en dat valt
dan buiten de serverroot.

Zes schermen in de onderbalk: **Kaart** (zones, vier kaartstijlen, zoeken,
gebiedspaneel, GPS met "sta ik in de zone"), **Spots** (wat er nu actief is én de
aangekondigde agenda, met richting en afstand), **Meld** (jezelf spotten via Spotline),
**Sessie** (activatiesessie met GPX-bewijs), **Heatmap** (kleurt de kaart op laatste
activatie of aantal QSO's) en **Regels** (bandplan per mode). Plus NL/FR/EN en een
service worker die alles offline houdt.

Het zelfmeldscherm neemt de validatieregels over uit de eigen paginacode van
`spots.wwff.co/spots/create` (roepteken-patroon, frequentiebereik, referentie van
minstens 7 tekens, opmerking van hoogstens 100 tekens) en controleert de referentie via
hun endpoint `/api/references/validate`. Versturen gebeurt als een **gewone
formulierpost in een nieuw tabblad** — dat mag cross-origin, en de gebruiker ziet de
bevestiging van Spotline zelf. Daardoor is er voor deze functie géén proxy nodig.

Referentienummers staan standaard aan. Ze komen uit een aparte puntenbron met één punt
per referentie: zet je ze op de vlakkenlaag, dan tekent MapLibre een label per
polygoondeel — en ONFF-0329 bestaat uit 67 losse percelen.

**Parameters in de URL** (ook voor de embed op het blogspot):

| Parameter | Wat |
|---|---|
| `?lang=nl\|fr\|en` | taal forceren; standaard volgt de browser |
| `?ref=ONFF-0104` | meteen op één gebied inzoomen |
| `?prov=limburg` | inzoomen op een provincie |
| `?spots=1` | de spotslaag meteen aanzetten |
| `?embed=1` | app-chrome verbergen voor een iframe |
| `?admin=1` | het beheerscherm tonen (ook: vijf keer op het logo tikken) |

```html
<iframe src="https://diana.<domein>/web/?embed=1&prov=antwerpen&lang=nl&spots=1"
        width="100%" height="600" style="border:0" loading="lazy"></iframe>
```

**Twee externe bronnen, allebei met een zichtbare terugval.** De spots komen van
`spots.wwff.co` en de heatmap van de gepubliceerde ONFF-statussheet. Of die twee een
rechtstreekse verbinding vanuit de browser toelaten (CORS), is nog niet vastgesteld;
lukt het niet, dan zegt de app dat met zoveel woorden en is de Worker uit het plan
nodig.

---

## Een nieuwe ONFF-release publiceren

Dit is de hele procedure. Er komt geen commando aan te pas.

1. Haal de nieuwe `ONFF_YYYYMMDD.kmz` van de BOS-groups.io.
2. Ga op github.com naar de map `source/`, klik **Add file → Upload files**, sleep het
   bestand erin, en kies onderaan **Create a new branch for this commit**.
   (Het bestand is ±17 MB; de weblimiet is 25 MiB, dus dat past.)
3. De Action draait automatisch en zet een rapport onder je pull request:

   > **945 gebieden** (was 932, +13) · **15 nieuw** · **2 verdwenen** · **7 gewijzigde grens**

   Met de lijsten uitklapbaar en de waarschuwingen erbij.
4. Klik op de preview-link om de nieuwe kaart écht te bekijken vóór je iets publiceert.
5. Klopt het? **Merge** de pull request. Dat is publiceren.
6. Klopt het niet? Sluit de pull request, of gebruik **Revert** op de merge-commit om
   in één klik terug te gaan naar de vorige versie.

Een verdwenen gebied is geen fout maar echte informatie — ONFF schrapt gebieden. Daarom
staat het in het rapport en wordt het nooit stilzwijgend toegepast.

Bij die pull request verschijnt ook een **preview-link** naar de kaart met de nieuwe
data. Kijk daarnaar vóór je merget — dat is de enige controle die er is. Zie
[DEPLOY.md](DEPLOY.md).

---

## Namen corrigeren

De gebiedsnamen in het KMZ bevatten typfouten en dubbele schrijfwijzen. Het script kiest
automatisch de beste variant, maar niet altijd de juiste. Corrigeer die in
`overrides.json`:

```json
"ONFF-0599": {
  "name": "Carrière de l'Alouette",
  "_why": "KMZ schrijft \"Carriere de 'Alouttel\" — twee typfouten"
}
```

Sleutel is altijd het **nummer**, nooit de naam. Zet er een `_why` bij, zodat over drie
jaar nog te zien is waarom die correctie er staat. Een pull request op dit bestand laat
de Action opnieuw draaien.

---

## Lokaal draaien

```bash
pip install -r build/requirements.txt
python build/kmz2geojson.py --kmz "source/ONFF 20260101.kmz"
```

Duurt ongeveer een halve minuut. Opties:

| Optie | Standaard | Waarvoor |
|---|---|---|
| `--tolerance` | `0.00005` | vereenvoudiging in graden; 0,00005 ≈ 5 m |
| `--decimals` | `5` | afronding van de coördinaten; 5 ≈ 1 m |
| `--out` | `data` | uitvoermap |
| `--overrides` | `overrides.json` | correctiebestand |
| `--report` | `report.md` | waar het verschillenrapport heen gaat |

---

## De datafiles

| Bestand | Grootte | Wat |
|---|---|---|
| `data/onff.geojson` | 3,7 MB (1,0 MB gzip) | één MultiPolygon per referentie, met naam, provincie, oppervlakte en wat er aan attributen bekend is |
| `data/onff-points.geojson` | klein | referenties die wél in de WWFF-directory staan maar géén grens hebben in het KMZ, als punt. De app toont ze als gestippelde ring en doet er bewust géén "sta ik erin"-test op |
| `data/onff-activity.json` | 39 kB | per referentie het aantal QSO's en de datum van de laatste activatie, uit de WWFF-directory. De heatmap gebruikt dit als de ONFF-sheet niet bereikbaar is |
| `data/onff-index.json` | 210 kB | dezelfde lijst zónder geometrie, plus de punten. Wordt níét door de app geladen — die bouwt zijn eigen index uit de twee geojson-bestanden. Bedoeld voor rapporten en gereedschap ernaast |
| `data/meta.json` | klein | herkomst: welk bronbestand, welke release, welke instellingen, en hoeveel referenties zonder grens er geplaatst zijn |

Dat hele België in één megabyte past, is de reden dat Diana geen tile-server nodig heeft
en volledig offline kan werken.

### Wat je niet in de data mag verwachten

De attribuutdekking in het KMZ is ongelijk. Van de 932 gebieden heeft:

- **565** een aanduiding (`desig`), **515** een IUCN-categorie, **445** een beheerder
- **75** een registratienummer, **81** een regiocode
- en ongeveer de helft **niets** buiten naam en nummer

Elk veld is dus optioneel. De app moet lege velden weglaten, niet als streepje tonen.
Wat altijd berekend wordt en er altijd is: oppervlakte, middelpunt, bounding box en
provincie.

### Bekende eigenaardigheden van de bron

- Het referentienummer staat **niet in een veld** maar in de naam van de bovenliggende
  folder, als `ONFF-nnnn <naam>`. Daarom wordt overal op het nummer gewerkt.
- Het KMZ bevat een Maidenhead-gridlaag van ±32.700 placemarks. Die wordt weggegooid —
  een grid is goedkoper te berekenen dan te versturen.
- Onderliggend is het een WDPA-export met de ONFF-laag erbovenop; vandaar de velden met
  hoofdletters (`MANG_AUTH`, `GIS_AREA`, `IUCN_CAT`) naast de Vlaamse in kleine letters
  (`opp_ha`, `inspireid`).
- **Welke referenties bestaan, komt uit de WWFF-directory**
  (`https://wwff.co/wwff-data/wwff_directory.csv`, dagelijks vernieuwd, 68.000
  referenties wereldwijd waarvan 964 ONFF). Het KMZ zegt alleen welke er een
  *grens* hebben. Van de 948 actieve ONFF-referenties hebben er 932 een polygoon;
  de overige 16 komen als **punt** op de kaart, met de coördinaat uit de directory
  of uit `overrides.json` (`"point": [lon, lat]`). Geschrapte referenties worden
  niet getoond. Elke referentie komt precies één keer voor: een polygoon wint
  altijd van een punt. Zie [docs/ADMIN.md](docs/ADMIN.md#3-a-reference-with-no-boundary).
