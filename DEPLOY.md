# Diana online zetten — alles binnen GitHub

Geen Cloudflare, geen externe dienst. Eén repo, GitHub Pages, en één beheerder die
uploadt. Dit document zegt ook eerlijk wat daarbij openbaar wordt en wat niet.

---

## 1. Eerst de vraag die er echt toe doet

> "Nadeel, publiek. Maar data mag niet zomaar te grabbel?"

Er zitten drie verschillende dingen in die vraag, en maar één ervan is een echte keuze.

### De zonegrenzen worden hoe dan ook openbaar

Diana is een statische webapp. De browser van elke bezoeker **downloadt
`onff.geojson`** — dat is hoe de kaart werkt. Wie de app kan openen, kan dat bestand
opslaan. Dat geldt bij GitHub Pages, bij Cloudflare, bij eender welke hosting, en
of de repo nu publiek of privé staat.

Met andere woorden: **de app publiceren ís de grenzen publiceren.** Wil ONFF dat niet,
dan kan Diana als publieke webapp niet bestaan — dan wordt het een besloten app achter
een login, en dat is een heel ander project.

Ter geruststelling: die grenzen staan feitelijk al publiek. Het ONFF-blogspot toont ze
per provincie in ingebedde Google My Maps, zonder login.

### De repo publiek zetten voegt daar één ding aan toe

Namelijk het **oorspronkelijke KMZ-bestand**, als bestand, herdistribueerd op een
tweede kanaal. ONFF verspreidt dat via de BOS-groups.io, achter een lidmaatschap. Dat
is geen geheime data — het is grotendeels een WDPA-export, en WDPA is zelf een open
dataset — maar het is wél Luks werk, verspreid via zijn kanaal.

**Dat is dus geen technische vraag maar een beleefdheidsvraag, en ze is voor Luk.**

Wat je hem kan voorleggen, in één zin: *"Diana wordt open source op GitHub. De
zonegrenzen komen daarmee als databestand online — dat moet, anders werkt de kaart
niet. Mag het bron-KMZ er ook bij, of houden we dat buiten de publieke repo?"*

### En dan zijn er twee wegen

| | Als Luk akkoord is | Als Luk liever niet |
|---|---|---|
| Opzet | **één publieke repo** | **twee repo's**: privé voor de bron, publiek voor de site |
| KMZ | staat in `source/`, publiek | blijft in de private repo |
| Complexiteit | laag | één extra repo en één token |
| Kosten | €0 | €0 (2.000 gratis Action-minuten per maand volstaan ruim) |

Hieronder staat weg 1 volledig uitgewerkt. Weg 2 staat in §5.

---

## 2. Weg 1 — één publieke repo (aanbevolen als Luk akkoord is)

### Instellen, één keer

1. Maak op GitHub een **publieke** repo, bijvoorbeeld `diana`.
2. Zet alles uit `diana-repo.zip` erin, plus `ONFF 20260101.kmz` in `source/`.
3. Repo-instellingen → **Pages** → Source: **Deploy from a branch** → branch
   `gh-pages`, map `/ (root)`. (Die branch bestaat nog niet; hij wordt bij de eerste
   push aangemaakt. Zet dit dus in nadat de eerste workflow gedraaid heeft.)
4. Nodig de beheerder uit als **collaborator** met de rol *Write*. Meer heeft hij niet
   nodig om te uploaden en te mergen.

Je site staat dan op `https://<gebruiker>.github.io/diana/`.

### Wat er automatisch gebeurt

| Wanneer | Wat |
|---|---|
| pull request met een nieuw KMZ | `build-data.yml` zet het om en plakt het verschillenrapport eronder |
| dezelfde pull request | `pages.yml` publiceert een **preview** op `.../preview/pr-12/` en zet die link eronder |
| merge naar `main` | de live site wordt bijgewerkt |
| pull request gesloten | de preview wordt opgeruimd |

Die preview is er met opzet. GitHub Pages heeft dat niet standaard — daarom publiceert
`pages.yml` naar een `gh-pages`-branch in plaats van via de standaard Pages-actie. Zo
kan de beheerder **naar de echte kaart met de nieuwe data kijken vóór hij merget**, en
dat is de enige controle die er is.

### Wat er niet online komt

`build/site.sh` stelt de te publiceren map samen uit `web/` en de drie datafiles, en
laat `source/` er bewust buiten. Het KMZ staat dus wel in de repo-boom (want de Action
leest het), maar wordt niet als website uitgeleverd.

---

## 3. Wat de beheerder doet

De volledige procedure, zonder één commando:

1. Haal de nieuwe `ONFF_YYYYMMDD.kmz` van de BOS-groups.io.
2. Op github.com naar `source/` → **Add file → Upload files** → sleep het bestand erin
   → onderaan **Create a new branch for this commit** → **Propose changes**.
3. Wacht een paar minuten. Onder de pull request verschijnen twee reacties: het
   verschillenrapport en de preview-link.
4. Open de preview en kijk naar de kaart.
5. Klopt het? **Merge.** Dat is publiceren.
6. Klopt het niet? Sluit de pull request. Of, als er al gemerged is: **Revert** op de
   merge-commit, en de vorige versie staat er weer.

Eén beheerder volstaat. Wil je er later meer, dan is dat een collaborator toevoegen.

---

## 4. Grenzen om te kennen

- **Bestandsgrootte in de browser: 25 MiB.** Het KMZ is 17 MB, dus dat past. Groeit het
  ooit voorbij 25 MiB, dan moet het via git in plaats van via de webinterface.
- **Pages-site: max 1 GB, en zachte limiet van 10 builds per uur.** Wij zitten op zo'n
  5 MB per publicatie en enkele builds per maand.
- **Actions op een publieke repo zijn gratis en onbeperkt.**
- **De repo-historie bewaart elk KMZ voorgoed.** Bij ongeveer 17 MB per release en een
  paar releases per jaar duurt het jaren voor dat ergens tegenaan loopt.

---

## 5. Weg 2 — twee repo's, als het KMZ niet publiek mag

Ook volledig binnen GitHub.

```
diana-source   (privé)  source/ build/ overrides.json  + de conversie-Action
      │  duwt data/ en web/ na een merge naar
      ▼
diana          (publiek)  de site + de data   → GitHub Pages
```

- De beheerder uploadt in de **private** repo. Alles wat hij ziet — het rapport, de
  goedkeuring — blijft daar.
- Een fine-grained token met schrijfrechten op enkel de publieke repo staat als secret
  in de private repo; de Action duwt daarmee de gebouwde site door.
- Private Actions-minuten: 2.000 gratis per maand, en één conversie duurt ongeveer een
  minuut.
- Wat je inlevert: de preview-URL zit dan in de publieke repo, terwijl de goedkeuring
  in de private gebeurt. Werkbaar, maar minder rechtlijnig dan weg 1.

Begin niet hiermee. Begin met de vraag aan Luk.

---

## 6. Als er geen `gh-pages` verschijnt

Die branch wordt door de workflow aangemaakt. Staat hij er niet, dan is de workflow niet
gedraaid of gestrand. Loop dit af, in deze volgorde:

**a. Staat de map `.github` wel in de repo?**
Dit is verreweg de vaakste oorzaak. Windows Verkenner verbergt mappen die met een punt
beginnen, dus wie de uitgepakte bestanden naar de GitHub-webuploader sleept, laat
`.github/` ongemerkt achter — en dan bestaat er dus geen workflow. Kijk op github.com of
je `.github/workflows/pages.yml` ziet staan. Zo niet: maak het bestand aan met
**Add file → Create new file**, typ als naam `.github/workflows/pages.yml` (GitHub maakt
de mappen vanzelf) en plak de inhoud erin.

**b. Staat er iets in het tabblad Actions?**
- *Geen enkele run* → de workflow staat er niet, of hij zit op een andere branch dan
  `main`. Kijk hoe je hoofdbranch heet.
- *Rode run* → open hem en lees de gefaalde stap.

**c. Rood bij "Publiceren", met 403 of "permission denied"?**
Dan staat de tokenrechten-instelling nog op alleen-lezen. Settings → Actions → General →
**Workflow permissions** → *Read and write permissions* → Save. Draai daarna de workflow
opnieuw met **Run workflow** in het Actions-tabblad.

**d. Nog steeds niets?**
De workflow heeft ook een handmatige knop. Actions → "Publiceren naar GitHub Pages" →
**Run workflow**. Dat maakt `gh-pages` aan zonder dat je iets hoeft te pushen.

Pas als `gh-pages` bestaat, verschijnt hij in het menu bij Settings → Pages.

---

## 7. De allereerste keer

1. **Eerst** Settings → Actions → General → Workflow permissions op *Read and write*.
2. Repo aanmaken, alles erin, KMZ in `source/` — en controleer dat `.github/` mee is.
3. Actions → "Publiceren naar GitHub Pages" → **Run workflow**. Nu bestaat `gh-pages`.
4. Settings → Pages → branch `gh-pages`, map `/ (root)` → Save.
5. Eén pull request maken (bijvoorbeeld een kleine wijziging in `overrides.json`) en
   controleren dat je twee reacties krijgt: het rapport en de preview-link.
6. **De live site openen en kijken of de spots en de heatmap laden.** Dat beantwoordt
   in tien seconden de laatste open vraag uit het plan: hebben we ooit een proxy nodig,
   of niet?

Die laatste stap is meteen de goedkoopste test in het hele project.
