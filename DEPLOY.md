# Diana online zetten

Kort antwoord op "alles erin en dan Pages activeren?": **ja, alles erin — maar niet
alles online.** En "Pages" is de plek waar de keuze zit tussen twee wegen die niet
evenveel waard zijn.

---

## 1. Wat er in de repo gaat

Alles uit `diana-repo.zip`, plus het KMZ:

```
source/ONFF 20260101.kmz     ← zelf uploaden, zat niet in de zip (17 MB)
build/    data/    web/    overrides.json    .github/    README.md    DEPLOY.md
```

Het KMZ hoort **wel** in de repo (de Action leest het) maar **niet** online. ONFF
verspreidt dat bestand via een groups.io achter lidmaatschap; het ongevraagd op een
publieke URL zetten is niet aan ons. Daarom publiceren we niet de repo-map zelf, maar
een aparte map die `build/site.sh` samenstelt:

```bash
bash build/site.sh _site
```

Dat zet `web/` en de drie datafiles in `_site/`, en laat `source/` er bewust buiten.
Wat niet in `_site` staat, komt niet online.

---

## 2. Cloudflare Pages of GitHub Pages?

|  | Cloudflare Pages | GitHub Pages |
|---|---|---|
| Private repo op een gratis plan | **ja** | **nee** — vereist GitHub Pro of Team |
| Preview-URL per pull request | **ja**, automatisch | nee |
| Eigen domein, HTTPS | ja | ja |
| De Worker die we later nodig hebben | zelfde account | apart |

Die tweede rij is de reden dat het plan Cloudflare koos. Het adminverhaal draait erop:
Luk uploadt een nieuw KMZ, en kijkt naar de **échte kaart met de nieuwe data** voor hij
op publiceren duwt. Zonder preview per pull request valt die controle weg en wordt
"merge" een sprong in het duister.

**Advies: Cloudflare Pages.** GitHub Pages is prima als je de repo publiek maakt en de
preview niet mist — de workflow daarvoor staat hieronder klaar.

---

## 3. Cloudflare Pages instellen

1. Maak de repo op GitHub. **Private** om te beginnen (zie het plan, §2).
2. Push alles, en upload `ONFF 20260101.kmz` naar `source/`.
3. Cloudflare → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**,
   koppel je GitHub-account en kies de repo.
4. Build-instellingen:

   | Veld | Waarde |
   |---|---|
   | Framework preset | None |
   | Build command | `bash build/site.sh _site` |
   | Build output directory | `_site` |
   | Root directory | *(leeg)* |

5. Deploy. Je krijgt `https://<naam>.pages.dev`.
6. Open een pull request om te controleren dat je een preview-URL krijgt. Dat is de
   controle waar de hele adminmodule op steunt.

Later komt daar de Worker bij (spotsproxy, self-spot, dagelijkse sheet-cron) en
eventueel Cloudflare Access voor `/admin`. Beide op hetzelfde account, beide gratis.

---

## 4. Als je toch GitHub Pages wil

Alleen zinvol met een **publieke** repo, tenzij je Pro of Team hebt. Zet dan
`.github/workflows/pages.yml` aan (staat in de repo, met een `workflow_dispatch` zodat
hij niet ongevraagd draait) en zet in de repo-instellingen **Pages → Source → GitHub
Actions**.

Let op: bij een publieke repo staat ook `source/ONFF 20260101.kmz` publiek in de
repo-boom, ook al publiceren we hem niet als website. Dat is een gesprek met Luk, geen
technische instelling.

---

## 5. Volgorde die ik zou aanhouden

1. Repo aanmaken, alles erin, KMZ erbij → controleer dat de Action groen draait en een
   rapport onder de pull request zet.
2. Cloudflare Pages koppelen → controleer de preview-URL bij een pull request.
3. Op de live URL de app openen en kijken of de **spots** en de **heatmap** laden. Doen
   ze dat, dan hebben we geen proxy nodig. Zeggen ze "CORS", dan is de Worker de
   volgende stap.
4. Pas daarna een eigen domein, en pas daarna `/admin` voor Luk.

Stap 3 is de goedkoopste manier om de laatste open vraag uit het plan te beantwoorden.
