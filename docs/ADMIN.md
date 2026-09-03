# Administrator guide

Everything an ONFF/Diana administrator needs: publishing a new KMZ release,
using the in-app Admin panel, and what to do when something doesn't work.
For the one-time repository setup (Pages, permissions), see
[DEPLOY.md](../DEPLOY.md) — this document assumes that's already done and
focuses on the recurring, day-to-day tasks.

---

## 1. Publishing a new ONFF release

There are two equivalent ways to do this. Both end at the same pull
request; pick whichever is more convenient.

### Option A — GitHub's own web interface

1. Download the new `ONFF_YYYYMMDD.kmz` from the BOS groups.io.
2. On github.com, go to the `source/` folder → **Add file → Upload files** →
   drag the file in → at the bottom choose **Create a new branch for this
   commit** → **Propose changes**. (The file is around 17 MB; GitHub's web
   upload limit is 25 MiB, so it fits.)
3. Wait a couple of minutes. Two comments appear under the pull request: the
   diff report (new/removed/changed-boundary zones) and a preview link.
4. Open the preview and actually look at the map before doing anything else.
5. Looks right → **Merge**. That *is* publishing — nothing else to do.
6. Looks wrong → close the pull request without merging, or, if it's
   already merged, use **Revert** on the merge commit to go back to the
   previous version in one click.

### Option B — the in-app Admin panel

Same underlying GitHub API calls, done from inside Diana instead of
github.com — useful if you'd rather not leave the app, or want the
embed-code generator in the same place. See §2 below for the full flow.

Either way, a **removed zone is real information, not an error** — ONFF
does retire reference numbers — so it's always shown in the diff, never
silently applied without you seeing it first.

---

## 2. The in-app Admin panel

### Getting to it

The Admin screen is hidden by default — not for security (see the token
warning below), but so it isn't a source of confusion for ordinary
visitors. Two ways to reveal it:

- open the app with `?admin=1` in the URL, or
- click the Diana logo/wordmark **five times in a row**.

Either one adds an "Admin" entry to the bottom navigation for the rest of
that browser session.

### Connecting to a repository

| Field | What goes in it |
|---|---|
| Repository | `owner/repo`, e.g. `ON3VZ/DIANA` (a full URL is normalised down to this form) |
| Main branch | usually `main` |
| Target path | where the uploaded file should land, e.g. `source/` |
| Access token | a GitHub **fine-grained personal access token** |
| "Remember the token on this device" | see the security note below — unticked by default |

Click **Test the connection** before uploading anything. It fetches the
repository and the branch reference and reports back the current commit and
branch, and warns you if the token doesn't actually have write access —
better to find that out now than after picking a file.

**Creating the token**, if you don't have one yet: on GitHub, go to
Settings → Developer settings → Personal access tokens → Fine-grained
tokens → Generate new token, and scope it as narrowly as possible:

- **Repository access:** only the one repository (never "All repositories")
- **Permissions:** Contents — Read and write, Pull requests — Read and
  write. Nothing else is needed.
- **Expiration:** as short as you're willing to renew — a token that
  expires in 90 days is safer than one that doesn't expire at all.

### Uploading a file

Pick the file, then **Upload and open a pull request**. Diana shows the
same seven steps GitHub's Git Data API actually requires, each one ticking
off as it completes:

1. Reading the base branch
2. Reading the file (in your browser, before sending)
3. Sending the file to GitHub (as a blob)
4. Updating the tree
5. Creating the commit
6. Creating the branch (named `diana-upload-<timestamp>`, so repeated
   uploads never collide)
7. Opening the pull request

If a step fails, that step turns red with GitHub's own error message next
to it, and the upload button becomes usable again so you can fix the
problem (usually the token) and retry — nothing is left half-done, because
each step only starts once the previous one has actually succeeded.

The result is a normal pull request against your repository, which then
goes through exactly the same `build-data.yml` → diff comment →
`pages.yml` → preview comment sequence described in
[DEVELOPER.md](DEVELOPER.md#3-the-two-github-actions-workflows) — merging
it is still a deliberate, separate step, whether you got there via the
Admin panel or by hand.

### A plain warning about the token

Anything written to `localStorage` — which is what "remember the token on
this device" does — is readable by anyone with access to that browser
profile, and by any script that runs on that page. That is simply what
`localStorage` is; Diana doesn't and can't change that. This is exactly why:

- the checkbox is **off by default** — the token is only kept in memory for
  that browser tab unless you explicitly ask Diana to remember it
- the token should be fine-grained, scoped to this one repository, with
  contents + pull-request permissions only, nothing broader
- give it a short expiration and renew it rather than issuing one that
  never expires
- never tick "remember" on a shared or public computer

### Generating an embed snippet

The same Admin panel has an embed-code generator: fill in a province, a
language, and whether the spots layer and/or the "other WWFF areas" layer
should be on, and it produces a ready-to-paste `<iframe>`. Both layers are
on by default in the app itself but default to **off** inside an embed —
they only appear when their checkbox is ticked here, so an already-published
snippet never changes on its own:

```html
<iframe src="https://<your-domain>/?embed=1&prov=antwerpen&lang=en&spots=1&world=1"
        width="100%" height="600" style="border:0"
        loading="lazy" allow="geolocation"></iframe>
```

`?embed=1` hides Diana's own navigation and header so the map fits cleanly
into someone else's page layout — see
[USER_GUIDE.md §Embedding](USER_GUIDE.md#embedding-diana-on-another-page)
for the full parameter reference and a live example.

---

## 3. Where the data comes from — and what you actually have to do

Diana joins two sources, and they need different amounts of work from you:

| Source | How it arrives | What you do |
|---|---|---|
| **WWFF directory** (`wwff.co/wwff-data/wwff_directory.csv`) — which references exist, their official names, coordinates, QSO counts | **fetched automatically on every data build**, including a build every night at 01:00 UTC. It is regenerated daily at WWFF's end | nothing, normally — see below |
| **ONFF KMZ** — the actual boundaries | **you upload it**, by hand, when ONFF publishes a new release | upload → check the preview → merge (§1) |

So a new *reference* (a park added to WWFF), a renamed one, a retired one, or
updated QSO counts appear by themselves — a scheduled build runs every night
at 01:00 UTC against whatever KMZ is already in the repository. Most nights
this changes nothing (Belgian references don't move every day) and the run
ends quietly with nothing committed.

When the directory *did* change and the build produced good output, that
nightly run **commits straight to `main` by itself** — no pull request, no
waiting for you to click merge. This is a deliberate exception to the
"a human always looks first" rule that governs KMZ uploads: it only ever
touches which references exist, their name, position, or QSO stats — never a
boundary, which still only ever comes from a KMZ you upload by hand — and
only commits when the build hit no errors and every output file actually has
content. If the WWFF directory is unreachable, or the build produces an empty
or missing output file, the run stops **without committing anything**, and
instead opens (or comments on an already-open) GitHub issue labelled
`diana-nachtelijke-build`, so a broken night is a notification you see, not a
silent gap. GitHub notifies whoever watches the repository the same way it
does for any other new issue — as a repository owner you watch your own
repositories by default, so this reaches you as a website notification and,
if you've turned on email for Issues under github.com → Settings →
Notifications, as an email too. A new *boundary*, on the other hand, only
ever appears when you upload a new KMZ — the nightly run never touches
boundaries, and never opens a PR of its own when it succeeds.

If you want the directory refreshed sooner than the next scheduled run, use
**Actions → ONFF-data bouwen → Run workflow** — same result, no upload
needed, and no need to wait for 01:00 UTC.

You can also point the build at a **CSV of your own** instead of the live URL —
set a repository variable `ONFF_REFS_CSV` (Settings → Secrets and variables →
Actions → Variables) to a URL or to a path inside the repository. Use that if
WWFF ever moves the file, or to test a change before it is live. Nothing about
the upload flow changes; it is the same build either way.

## 3.1 A reference with no boundary

16 of ONFF's 948 active references have no polygon in the KMZ. Diana draws them
as a dashed ring at an approximate position instead of hiding them — but it can
only do that if it knows where they are.

Each data build reports the state in the pull-request comment:

> **948 active references** in the directory · **932 with a boundary** from the
> KMZ · **16 as a point** on the map · 16 retired (not shown)

A reference the directory has no position for at all would be searchable but
appear nowhere on the map. To place one, add a coordinate to `overrides.json`:

```json
"ONFF-0123": {
  "point": [4.4700, 50.8500],
  "_why": "no boundary in the KMZ; point set on the reserve entrance"
}
```

The order is `[longitude, latitude]` — GeoJSON order, so the smaller number
usually comes first in Belgium. A point set here always wins over the ONFF index
sheet's own coordinate column, and survives every future release, because the
key is the reference number. Committing that change alone re-runs the build.

Diana never invents a position: a reference with no coordinate from either
source stays off the map deliberately, because a wrong pin in a nature reserve
is worse than no pin.

---

## 4. Troubleshooting

### No `gh-pages` branch appears

That branch is created *by the workflow*, not by hand. Work through this in
order:

1. **Is `.github/` actually in the repository?** By far the most common
   cause: Windows Explorer hides folders that start with a dot, so
   drag-and-dropping extracted files into GitHub's uploader silently leaves
   `.github/` behind. Check on github.com whether
   `.github/workflows/pages.yml` exists. If not, add it with **Add file →
   Create new file**, type the full path as the filename (GitHub creates
   the folders for you), and paste the contents in.
2. **Check the Actions tab.** No runs at all → the workflow file isn't
   there, or your default branch isn't named `main`/`master`. A red run →
   open it and read the failed step.
3. **Red at the "Publiceren"/publish step, with a 403 or "permission
   denied"?** Settings → Actions → General → Workflow permissions → *Read
   and write permissions* → Save, then re-run the workflow with **Run
   workflow** in the Actions tab.
4. **Still nothing?** Actions → the Pages workflow → **Run workflow**
   manually. This creates `gh-pages` without needing a push at all.

Only once `gh-pages` exists can you select it under Settings → Pages.

### The published site shows the wrong thing, or `source/*.kmz` is exposed

This means GitHub's own built-in "pages-build-deployment" ran instead of the
custom `pages.yml` — almost always because `.github/` was missing (see
above), so Settings → Pages was left on "Deploy from a branch: main /
(root)", which publishes the **entire repository root**, KMZ included. Fix:
add the workflow file properly (via "Create new file", not drag-and-drop),
let it run once, then repoint Settings → Pages to the `gh-pages` branch.

### A pull request doesn't get a diff report or preview link

Check that the PR actually touches `source/**.kmz`, `overrides.json`, or
`build/**` — those are the only paths `build-data.yml` watches. A PR that
only touches, say, `docs/` won't trigger a data rebuild, by design.

---

## 5. Before making the repository (or the source KMZ) public

Publishing Diana as a web app necessarily publishes the zone boundaries —
any visitor's browser downloads `onff.geojson`, and that's true regardless
of hosting choice. Making the **repository itself** public additionally
republishes the raw source KMZ file on a second channel outside ONFF's own
groups.io distribution. That second point is a courtesy question for the
ONFF coordinator, not a technical constraint — see
[DEPLOY.md §1](../DEPLOY.md#1-eerst-de-vraag-die-er-echt-toe-doet) and the
data-licensing terms in [LICENSE](../LICENSE) before deciding how open to
make the repository.
