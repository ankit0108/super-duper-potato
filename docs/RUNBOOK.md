# Runbook

## The routine

**Every morning (10–15 minutes).** Open the desk. *Today's picks* is ranked best first. Open a card, tweak the
draft (swap or edit an opening, trim, use the thread tools), keep or drop the suggested hashtags, tap **Copy**,
then **Open LinkedIn/X**, post it, and post the **First comment** (the source link) right after it. Come back and
tap **Posted**. The hashtags you keep are added at the end of what you copy, and they don't count as edits. Skip
what you won't use, with a reason: it's the most useful signal you can give the ranker. "Other" asks you to say
why in a line, and any skip can get a reason afterwards (**Add why** on the toast). The next morning's ranking
reads your reasons; **Insights → Learning** lists the ones in use. Cards you don't touch expire when the next
morning's set arrives, and that's fine.

**If a sentence sounds like AI.** The card's **Checks** tab lists *Sounds like AI* as you type ("It's not X, it's
Y", "Here's why:", em dashes, emoji bullets, filler, every sentence the same length), and the tile shows a robot
icon when the delivered draft still has one. Rewrite it in your own words. Before you see a draft, an editor pass
has already rewritten what it could; **Details → Editor pass** says what it fixed, or why it kept the draft as
written. A pattern you take out of three drafts becomes a rule; one you keep adding yourself is left alone.

**A visual (optional).** On a card, **Visual → Create visual** (or pick a kind: carousel, flowchart,
comparison, numbered list, big number, quote card, or an **AI image**; tick **Add an AI background** for a picture
behind a carousel cover, big number or quote, once AI images are set up: SETUP, "AI images"). It starts a run straight away; one to three minutes later
it's drawn from the post and its sources, in your style, and a "ready · Open" note pops up. Flip through it, **Edit text** if a word is off, then **Download PDF** (a carousel: on
LinkedIn, add a document to the post and upload it) or **Download PNG** / **Copy image**, and paste the alt text.
When you tap **Posted**, keep **Posted with the visual** ticked: Insights compares posts with and without one.

**Right topic, other platform.** On a card, **Also for X** (or **Also for LinkedIn**) makes a version for the
other platform and keeps both; **Skip → Move to X instead** makes it and skips this one as "wrong platform". The
new card arrives in one to three minutes ("Your X version … is ready · Open"), rewritten for that platform, on top
of Today's picks, and links back to the original. Both teach the ranking which topics suit which platform.

**When a card has questions.** Firsthand and learning-in-public cards arrive already drafted from recent
sources, with one or two optional questions under **Make it yours**. Post the draft as it is, or answer a
question in a sentence or two (typing or dictation): one to three minutes later the draft is rewritten from your
answers plus the sources. A card with no recent sources waits for your answers.

**Sunday (15 minutes).** Metrics: upload the week's LinkedIn and X analytics screenshots, confirm anything the
review queue flags, do the follower check-in. Then **System → Run weekly review**. Monday morning, look at
**Insights → Proposals** and approve or reject each one; the rest of the learning needs nothing from you.

**Once a month (5 minutes).** The first run of the month reads recent coverage of how LinkedIn and X show posts
and proposes changes to the platform guide the drafts follow, each citing its articles. Approve or reject them
under **Insights → Proposals**; **Insights → Playbook** shows the current guide and has **Research now**.

**Want more posts today?** **Get fresh posts** at the top of the board (also on System): pick the platforms and
how many, and a new set is scouted, ranked against what you've already seen today and drafted, in two to four
minutes. It lands on top of Today's picks as a *Fresh set*; the morning set follows it.

**Anytime.** Requests: any topic, full drafts in a few minutes. The request shows what the search understood
("Understood as: …"); if it's off, say what you mean in the notes and ask again. Stances: record or change a
view; your wording shows under **Your stance** once saved.

## When something's wrong

The desk's banners say what happened; **System** shows every run, its steps and errors, provider usage and the
doctor's checks. Personal content never appears in the Actions logs (they carry counts and IDs only), so the
desk is where to look first.

| Symptom | What to do |
| --- | --- |
| No cards by 6:30am | GitHub delays or drops scheduled runs, sometimes by hours, so the morning runs start around 1am with catch-ups at about 4am and 6am. To get them now: **System → Deliver the morning set**. If runs are failing, open the latest run's log from System |
| "The schedule is disabled" | GitHub disables schedules in repos without recent activity. **System → Re-enable** (the Saturday run also keeps it alive) |
| "No model provider is usable" | Run the doctor (**System → Run doctor**). Usually an expired or missing `GEMINI_API_KEY`; add `GROQ_API_KEY` as a fallback |
| "No model has answered today" | Every provider failed with an error, not just quota. **System → Free-tier usage** shows each provider's last error, and the run log has one line per provider (`llm: … switched off for this run: …`). "key rejected" means a new key; "model not available" is handled by itself unless you pinned a model in **Settings → Models** (set it back to `auto:flash`). Tap **Draft this** once it's fixed |
| The run log says `llm: gemini overloaded; using the next provider for the rest of this run` | Normal on busy days: after two calls that only got "server error 503", Gemini goes to the back of the line for that run and Groq answers, instead of each call waiting about 45 seconds. Nothing to do |
| Cards arrive as briefs with **Draft this** | The free model quota ran out (or the providers failed: see the row above). Tap **Draft this** later (quotas reset daily), or add `GROQ_API_KEY`/`OPENROUTER_API_KEY` as extra fallbacks |
| "GitHub rejected the token" | The desk token expired or was revoked. Make a new `pbs-desk` token (SETUP step 3) and paste it in **Settings → Connection** |
| Pipeline run fails at "Check out data" | The error names the problem and quotes GitHub. "can't see (HTTP 404)": the repo name is wrong, or the token isn't allowed to see `pbs-data` (repository access). "can't read" or "can't push": the token needs **Contents: Read and write** on `pbs-data`. "rejected (HTTP 401)": the token expired; create a new one and replace the `PBS_DATA_TOKEN` secret. The same run still checks the models and sources ("Check models and sources anyway") |
| "Your data repo is public" | Make `pbs-data` private again (its Settings → General → Change visibility). The pipeline works the same with a private repo; it never needs it public |
| A news source keeps failing | The doctor's `Sources` line names each failing source with its reason (HTTP 403 is usually a site refusing GitHub's servers). Swap it for a Google News query for the same outlet (`site:example.com when:2d`) on the Sources page |
| A change you made "didn't stick" | **System → Rejected changes** lists anything the pipeline couldn't apply, with the reason. *Changes in flight* shows what's still waiting for a run |
| A card is **Blocked** | It matched your blocklist. Nothing was reworded. Edit the draft by hand or skip it. If the match is a false positive, refine the term in `PBS_BLOCKLIST` |
| Drafts sound like AI | **Insights → Voice** shows AI tells per draft as the model wrote it and as shown to you, week by week, and which ones come up most. The run log has a line per draft, such as `edit: polished a linkedin draft (tells 2→0)` or `edit: kept the original draft of a linkedin card (added a figure the sources don't have)`: the editor never keeps a version that adds or drops a figure, claims an experience, or rewrites more than half the post. `edit: skipped … (budget)` means the run was short on model calls, and drafts come first. Taking the pattern out when you edit teaches the drafter; **Settings → Writing** turns the editor pass off or caps it |
| Drafts suddenly need more editing | **Insights → Weekly report** shows edit ratio by prompt and playbook version. Remove the playbook rule that made things worse (**Insights → Playbook**), or **Settings → Learning → Freeze learning** while you review |
| Want another set today | **Get fresh posts** on the board |
| The desk looks out of date (a fix "isn't there") | The desk checks for a new version whenever you come back to it and reloads by itself when nothing is unsent; otherwise a banner offers **Reload**. **System** shows the desk version and when it was built |
| Something says "Still waiting · Run now" | The work was sent but no run has picked it up for three minutes (GitHub can be slow to start runs). Tap **Run now** |
| Hashtags you never use keep coming | Drop them on the card: after a few posts the drafter stops suggesting the ones you remove (and suggests none on a platform where you remove them all). **Settings → Hashtags** turns them off or changes how many |
| An AI image didn't come, or a visual says "drawn without an AI background" | The card's note says why: no image service set up (SETUP, "AI images"), today's limit or the free allowance used up (it resets at midnight UTC), or the service had an error (ask again). **System → Run doctor** tests each image service with one small image. **System → Free-tier usage** doesn't count images; the doctor's lines and the run log (`images: …`) do |
| A visual says something the post doesn't, or flags a figure | Figures the sources don't contain are listed above the visual: fix them with **Edit text**, or **Make a different one**. A visual that mentioned a blocklist term isn't kept (the card says so) |
| A cross-post didn't appear | It starts a run straight away and usually lands in one to three minutes, on top of Today's picks. If the card shows **Still waiting · Run now**, tap it. If it says **Drafting failed**, open it: the original's text is there to work from, or tap **Rewrite** |
| A guide change made drafts worse | Add your own rule under **Insights → Playbook** saying what you want instead: your rules win over the platform guide. The guide shows each researched rule with the articles behind it, and never changes without your approval, so reject proposals like it |

## Recovering data

All state is plain JSON Lines in `pbs-data`, one commit per run. To undo something, revert the commit on
GitHub (or check out an older `db/` and push it); the next run rebuilds `desk.json` from it. The desk only ever
adds files under `inbox/`, and the pipeline deletes an inbox file only after the state that includes it is
saved, so a crash mid-run can't lose your actions.

## Costs and limits

Everything runs on free tiers: Actions minutes (unlimited on a public repo), Pages, Gemini and Groq, and free
news sources. A normal day uses about 15–25 model calls, with a hard cap of 60 in settings; each cross-post is
one more, as is each visual, each draft the editor pass rewrites (at most 12 a run, and only when the run has
calls to spare), and the monthly platform research one. The one upgrade worth paying for, if drafts
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
