# Runbook

## The routine

**Every morning (10–15 minutes).** Open the desk. *Today's picks* is ranked best first. Open a card, tweak the
draft (swap an opening, trim, use the thread tools), tap **Copy**, then **Open LinkedIn/X**, post it, come back
and tap **Posted**. Skip what you won't use, with a reason: it's the most useful signal you can give the
ranker. Cards you don't touch expire when the next morning's set arrives, and that's fine.

**When a card asks you questions.** Firsthand and learning-in-public posts are drafted only from your answers.
Answer in a sentence or two (typing or dictation) and the draft arrives in about two minutes.

**Sunday (15 minutes).** Metrics: upload the week's LinkedIn and X analytics screenshots, confirm anything the
review queue flags, do the follower check-in. Then **System → Run weekly review**. Monday morning, look at
**Insights → Proposals** and approve or reject each one; the rest of the learning needs nothing from you.

**Anytime.** Requests: any topic, full drafts in a few minutes. Stances: record or change a view.

## When something's wrong

The desk's banners say what happened; **System** shows every run, its steps and errors, provider usage and the
doctor's checks. Personal content never appears in the Actions logs (they carry counts and IDs only), so the
desk is where to look first.

| Symptom | What to do |
| --- | --- |
| No cards by 6:30am | GitHub delays or drops scheduled runs sometimes; a catch-up run follows about 90 minutes after the first. To get them now: **System → Deliver the morning set**. If runs are failing, open the latest run's log from System |
| "The schedule is disabled" | GitHub disables schedules in repos without recent activity. **System → Re-enable** (the Saturday run also keeps it alive) |
| "No model provider is usable" | Run the doctor (**System → Run doctor**). Usually an expired or missing `GEMINI_API_KEY`; add `GROQ_API_KEY` as a fallback |
| "No model has answered today" | Every provider failed with an error, not just quota. **System → Free-tier usage** shows each provider's last error, and the run log has one line per provider (`llm: … switched off for this run: …`). "key rejected" means a new key; "model not available" is handled by itself unless you pinned a model in **Settings → Models** (set it back to `auto:flash`). Tap **Draft this** once it's fixed |
| Cards arrive as briefs with **Draft this** | The free model quota ran out (or the providers failed: see the row above). Tap **Draft this** later (quotas reset daily), or add `GROQ_API_KEY`/`OPENROUTER_API_KEY` as extra fallbacks |
| "GitHub rejected the token" | The desk token expired or was revoked. Make a new `pbs-desk` token (SETUP step 3) and paste it in **Settings → Connection** |
| Pipeline run fails at "Check out data" | The error names the problem and quotes GitHub. "can't see (HTTP 404)": the repo name is wrong, or the token isn't allowed to see `pbs-data` (repository access). "can't read" or "can't push": the token needs **Contents: Read and write** on `pbs-data`. "rejected (HTTP 401)": the token expired; create a new one and replace the `PBS_DATA_TOKEN` secret. The same run still checks the models and sources ("Check models and sources anyway") |
| "Your data repo is public" | Make `pbs-data` private again (its Settings → General → Change visibility). The pipeline works the same with a private repo; it never needs it public |
| A news source keeps failing | The doctor's `Sources` line names each failing source with its reason (HTTP 403 is usually a site refusing GitHub's servers). Swap it for a Google News query for the same outlet (`site:example.com when:2d`) on the Sources page |
| A change you made "didn't stick" | **System → Rejected changes** lists anything the pipeline couldn't apply, with the reason. *Changes in flight* shows what's still waiting for a run |
| A card is **Blocked** | It matched your blocklist. Nothing was reworded. Edit the draft by hand or skip it. If the match is a false positive, refine the term in `PBS_BLOCKLIST` |
| Drafts suddenly need more editing | **Insights → Weekly report** shows edit ratio by prompt and playbook version. Remove the playbook rule that made things worse (**Insights → Playbook**), or **Settings → Learning → Freeze learning** while you review |
| Want another set today | **System → Get another set** |

## Recovering data

All state is plain JSON Lines in `pbs-data`, one commit per run. To undo something, revert the commit on
GitHub (or check out an older `db/` and push it); the next run rebuilds `desk.json` from it. The desk only ever
adds files under `inbox/`, and the pipeline deletes an inbox file only after the state that includes it is
saved, so a crash mid-run can't lose your actions.

## Costs and limits

Everything runs on free tiers: Actions minutes (unlimited on a public repo), Pages, Gemini and Groq, and free
news sources. A normal day uses about 15–20 model calls, with a hard cap of 60 in settings. The one upgrade worth paying for, if drafts
stay generic after a month, is a stronger drafting model: **Settings → Models**.

## Development

```bash
pip install -e ".[dev]" && pytest && ruff check pbs tests
pbs tick --offline --data .pbs-local     # a full run: mock feeds, fake model, no network, no keys
pbs doctor --offline --data .pbs-local
cd web && npm ci && npm run demo-data && npm run dev
```

Contract changes: edit `pbs/contracts.py`, run `pbs schema` and `cd web && npm run gen:types`, and bump
`DESK_SCHEMA_VERSION` for breaking changes (an older desk shows a warning to reload when the data is newer than it understands).
