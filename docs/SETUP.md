# Setup (about 15 minutes)

You need a GitHub account and a Google account (for a free Gemini API key). Everything below is free.

The design in one line: **this repo holds code and stays public; a new private repo holds your data.** The
pipeline refuses to store personal data in a public repo.

> Replace `<you>` with your GitHub username and `<repo>` with this repo's name (for example
> `ankit0108/super-duper-potato`).

## 1. Make sure this repo has a `main` branch

Scheduled workflows run from the default branch, and the desk triggers the pipeline on `main`. In this repo:
**Settings → General → Default branch**. If it isn't `main`, merge the setup pull request into `main` (or
rename the default branch to `main` there).

## 2. Create the private data repo

[github.com/new](https://github.com/new) → name it `pbs-data` → **Private** → leave it empty (no README) →
**Create repository**. The first pipeline run fills it.

## 3. Create two fine-grained tokens

**Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
(profile menu → Settings, at the bottom of the left menu). Use two tokens so the one stored in your browser
can't be reused by the pipeline and the other way round.

| Token | Repository access | Permissions | Where it goes |
| --- | --- | --- | --- |
| `pbs-pipeline` | Only select repositories: `pbs-data` | Contents: **Read and write** | Secret `PBS_DATA_TOKEN` (step 5) |
| `pbs-desk` | Only select repositories: `pbs-data` and `<repo>` | Contents: **Read and write**; Actions: **Read and write** | Pasted into the desk (step 8) |

Pick an expiry you're comfortable with (up to a year) and set yourself a reminder. When a token expires the
desk says so, and the pipeline's run fails with a clear message.

## 4. Get a Gemini API key

[aistudio.google.com](https://aistudio.google.com) → **Get API key** → **Create API key** → copy it. The free
tier is enough. PBS sends your own words (answers, edits, voice analysis) to GitHub Models first, because it
doesn't train on inputs. Every model call has your blocklist terms redacted.

## 5. Add the secrets

In **this** repo: **Settings → Secrets and variables → Actions → Secrets → New repository secret**.

| Secret | Required | What to put |
| --- | --- | --- |
| `PBS_DATA_TOKEN` | Yes | The `pbs-pipeline` token |
| `GEMINI_API_KEY` | Recommended | The key from step 4. Without it, GitHub Models does everything within its smaller free quota |
| `PBS_BLOCKLIST` | Strongly recommended | One term per line: your employer, clients, colleagues, internal system names and code names, with common variants. Drafts containing a term are blocked (never reworded), and the terms are redacted from every model call |
| `GROQ_API_KEY`, `OPENROUTER_API_KEY` | Optional | Extra free fallbacks when the others run out |
| `PBS_NTFY_TOPIC` | Optional | A long random [ntfy](https://ntfy.sh) topic name for "drafts are ready" pings (content-free) |
| `PBS_TELEGRAM_BOT_TOKEN`, `PBS_TELEGRAM_CHAT_ID` | Optional | The Telegram alternative to ntfy |

GitHub Models needs no key: the workflow uses its built-in token with `models: read`.

## 6. Add the variables

Same page, **Variables** tab → **New repository variable**:

| Variable | Value |
| --- | --- |
| `PBS_DATA_REPO` | `<you>/pbs-data` |
| `PBS_DESK_URL` | `https://<you>.github.io/<repo name>/` (optional: notifications link straight to the desk) |

## 7. Turn on the desk (GitHub Pages)

**Settings → Pages → Build and deployment → Source: GitHub Actions.** Then **Actions → desk → Run workflow**
(it also runs on every push to `main` that changes the desk or the pipeline). The run summary shows the desk's
URL: `https://<you>.github.io/<repo name>/`.

## 8. First run and connecting the desk

1. **Actions → pbs → Run workflow**, hint `doctor`. After about two minutes `pbs-data` has `db/` and
   `desk/desk.json`, and the doctor has checked every secret, model and source.
2. Open the desk URL and fill in **Connect your desk**: data repo `<you>/pbs-data` (branch `main`), pipeline
   repo `<you>/<repo name>` (branch `main`), and the `pbs-desk` token.
3. **System → Deliver the morning set** for your first cards now, or wait for tomorrow morning.
4. On your phone, open the desk URL and add it to the home screen (Safari: Share → Add to Home Screen;
   Chrome: Install app). Connect it the same way; each device keeps its own copy of the token.

## 9. Make it yours (10 minutes, any time in the first week)

- **Settings → Profile**: the only facts about you the drafter may use. Write only what you're happy for a
  model to see; never name your employer or clients.
- **Stances**: ten recurring issues are laid out with their main positions. Pick one, write your own, or leave
  it. Opinion posts on an issue are drafted only once you've recorded a stance.
- **Metrics → Weekly check-in**: today's follower counts, so the growth charts have a baseline.
- **Sources**: pause anything you don't want and add your favourite feeds or Google News queries.

## What runs when (Melbourne time)

| Run | Time |
| --- | --- |
| Morning delivery | About 5:10am (AEDT) / 4:10am (AEST), plus a catch-up run about 90 minutes later |
| Light ticks | Three times a day: desk events, expiry, learning |
| Saturday batch | Saturday evening: the week's interview and evergreen cards |
| Weekly review | When you tap **Run weekly review** after your Sunday screenshots, or Monday morning at the latest |
| Desk actions | Answers, rewrites, requests and "run now" start a run straight away (results in about two minutes) |

GitHub sometimes delays scheduled runs; every run catches up on anything overdue, and the desk warns you if
nothing has run for 30 hours.

## Alternative: one private repo

If you'd rather keep everything in one repo, make this repo private and skip `PBS_DATA_REPO` and
`PBS_DATA_TOKEN`: state then goes to its `data` branch, and the desk connects to this repo with branch `data`.
GitHub Pages on a private repo needs a paid plan, so host the desk elsewhere (for example Cloudflare Pages,
free: build command `npm run build` in `web/`, output `web/dist`).

Something not working? See [RUNBOOK.md](RUNBOOK.md).
