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

**Copying and opening the app.** **Copy draft**, under the editor, copies just the draft text. **Copy** in the
bottom bar copies the whole post, with your hashtags at the end. On a computer, **Open LinkedIn** and **Open X**
open a new post with the text already in it. On a phone, **Open X** does the same. **Open LinkedIn** opens the
share sheet instead (the LinkedIn app ignores links that carry text): pick **LinkedIn** and the post arrives in a
new LinkedIn post. It's copied too, so if LinkedIn ever opens empty, paste it.

**Bihar, history to now.** One X card a day is kept for a story that isn't today's news, marked *Story, history
to now*: an era, a person, a place, a tradition or a present-day institution in Bihar, from ancient Magadha to
today's Bihar. It's drafted from the Wikipedia article (about 140 of them, a few a day, in
`pbs/defaults/story_pools.yaml`), and it stays for about a week. Bihar news still comes as usual.
`affairs.stories_per_day` in the settings changes the number (0 lets stories compete with the news on their own).

**What people are talking about, not only the news.** Besides news sites and papers, the *Buzz* scout (Sources →
Buzz) reads tech communities (Reddit's top posts of the day, Ask HN and the most-discussed Hacker News stories,
Techmeme, Lobsters, Product Hunt, GitHub trending), odd and funny tech news (The Register, 404 Media, Futurism,
Gizmodo, Ars Technica, Hackaday, Slashdot, Engadget, Google News searches for bizarre, viral and AI-blunder stories)
and what's trending (Google Trends for India, Australia and the US, Mastodon's trending links). How much a story is
discussed (comments, upvotes, shares, searches) lifts it, and the card's note says so ("5,400 upvotes and 900
comments on Reddit"). Words trending on X (trends24) and Bluesky lift the stories that mention them for a day and a
half. Cards are badged *People are talking*, *Bizarre* or *Trending on X*, and **Read what people are saying** opens
the thread. Reddit and trends24 often refuse GitHub's servers: those are best effort, and the doctor lists them.

**What's working on LinkedIn and X.** Once a day the morning run searches Google (through Gemini) for public
LinkedIn and X posts on your topics: the conversations taking off and why they work. The best reach the board marked
*Trending on LinkedIn* or *Trending on X*, with why posts about them are working, and the draft is written with
that in mind. **Insights → What's working** lists the week's. PBS never logs in to or scrapes LinkedIn or X. When
you see a post you like in their apps, share it to **PBS Desk** (Studio, above). Pause it on Sources → Buzz
(*Social pulse*); `pulse` in the settings turns it off or changes how many a platform.

**Funny posts.** Every morning has at least one funny card on LinkedIn, and X mixes them in as the ranking learns.
They're about real stories (the bizarre, the funny, what people are arguing about), not generic premises (the premise
pool is off: `pools.humor`). Each is written in a *writers' room*: six versions in different styles, then a critic
that keeps the best and throws out clichés, explained jokes, jokes that punch down and anything the story doesn't
support. The card shows the critic's verdict and the next two versions (**Use** swaps one in); when the critic
says *weak*, rewrite it or skip it. Skip a joke as **Not funny** and the critic learns from it. `humor.examples` in
the settings takes funny posts you like (the taste to aim for) and `humor.cliches` the jokes to never use; drafts
that lean on one are flagged. On X, the *Quotes, excerpts and thoughts* lane still brings a quote checked word for
word on Wikiquote, a line worth quoting from the day's material, or one sharp thought.

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
**Insights → Proposals** and approve or reject each one (a proposal that only asks you to look at something has
**Got it** instead); the rest of the learning needs nothing from you.

**Once a month (5 minutes).** The first run of the month reads recent coverage of how LinkedIn and X show posts
and proposes changes to the platform guide the drafts follow, each citing its articles. Approve or reject them
under **Insights → Proposals**; **Insights → Playbook** shows the current guide and has **Research now**.

**Want more posts today?** **Get fresh posts** at the top of the board (also on System): pick the platforms and
how many, and a new set is scouted, ranked against what you've already seen today and drafted. Cards are drafted
three at a time and reach the board in batches as they're ready ("Drafting: 4 of 10 ready"): the first in a minute
or two after the run starts, the rest within a few minutes. It lands on top of Today's picks as a *Fresh set*; the
morning set follows it. Topics already judged this morning aren't asked about again, so a fresh set mostly spends
its model calls on drafts.

**Studio: write anything, now.** The **Studio** tab is a chat that answers in seconds. Ask it anything, add
pictures (pick them, take a photo, paste or drag them in), share a link, or tap a quick action: *Post ideas*,
*LinkedIn post*, *X post*, *X thread*, *Carousel*, *Funny post*, *Research it*. It searches Google when a question
needs current facts and lists its sources under the reply. Drafts arrive as post blocks you can edit in place,
with the character count, other openings, hashtag chips, the first comment and the same live checks as a card;
then **Copy**, **Open LinkedIn/X** (on a phone, **Share with pictures** takes the text and your pictures to the
app together) or **Save to board**. Carousels and other visuals are drawn on the spot: flip through them, **Edit
text**, **Download PDF**/**PNG** or **Share**, tick **Put your photo behind it**, and **Write the post for it**.
After a draft, the chips change to *Shorter*, *New opening*, *Funnier*, *More me*, the other platform's version
and *Carousel*.
- **Setup, once per device:** **Settings → Studio**: paste a free Gemini key from
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and tap **Check and save**. Make it in a
  different Google Cloud project from the pipeline's `GEMINI_API_KEY`, so chatting never uses the morning's free
  quota. The key and your chats stay in this browser; your guard terms are replaced with "[redacted]" before
  anything is sent. On the free tier Google may use what you send to improve its models, so don't paste anything
  confidential.
- **It writes like the cards.** Every run exports a *Studio kit* in `desk.json`: the system rules, the style
  learned from your edits, the platform guide, recent posts as examples, your hashtag habits and the kinds of post
  (`pbs/studio.py`, prompt `pbs/prompts/studio.md`). Until the first run after this update, the Studio says it
  will write better after the next run.
- **Save to board** makes a card in Today's picks (*From the Studio*) with the draft, its sources, your chosen
  pictures (kept in `media/studio/` in the data repo) and the visual. Post it and tap **Posted** as usual: it's
  learned from like any other card.
- **Ask Studio** on any card starts a chat about it ("Make it better", ideas, a carousel, the X version).
- **From LinkedIn or X on Android:** with the desk installed (Chrome → **Add to Home screen**), tap **Share** on a
  post (or a screenshot) and pick **PBS Desk**. The Studio opens with it: tap **Why is it working?**, **My take**,
  **Reply** or **Quote-post**. Screenshots work better than links: LinkedIn and X pages can't be read without
  logging in.

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
| The run log says `llm: gemini gemini-…-flash: server error (HTTP 503 UNAVAILABLE); trying the next model`, or `llm: gemini overloaded; using the next provider for the rest of this run` | Normal on busy days. A Gemini model that answers "overloaded" goes to the back. After two such answers in a run, it's asked only when no other model is left, and then only one busy model per call. After two calls where every Gemini model was busy, Groq answers for the rest of the run. A busy morning costs a few slow answers per run, not per call. Nothing to do; adding `GROQ_API_KEY`, if it isn't set, keeps runs fast |
| Cards arrive as briefs with **Draft this** | The free model quota ran out (or the providers failed: see the row above). Tap **Draft this** later (quotas reset daily), or add `GROQ_API_KEY`/`OPENROUTER_API_KEY` as extra fallbacks |
| "GitHub rejected the token" | The desk token expired or was revoked. Make a new `pbs-desk` token (SETUP step 3) and paste it in **Settings → Connection** |
| Pipeline run fails at "Check out data" | The error names the problem and quotes GitHub. "can't see (HTTP 404)": the repo name is wrong, or the token isn't allowed to see `pbs-data` (repository access). "can't read" or "can't push": the token needs **Contents: Read and write** on `pbs-data`. "rejected (HTTP 401)": the token expired; create a new one and replace the `PBS_DATA_TOKEN` secret. The same run still checks the models and sources ("Check models and sources anyway") |
| "Your data repo is public" | Make `pbs-data` private again (its Settings → General → Change visibility). The pipeline works the same with a private repo; it never needs it public |
| Every LinkedIn take turns into a point about automation | Takes now fit each story: the technology, the business, the market, the people or the policy, with automation only when the story is about it. Check **Settings → Profile**: if your profile still says it "explains research for people automating real work", change that line, since the drafter reads it as a fact about you. **Insights → Playbook** shows the rules drafts follow; remove any that pushes every post toward automation |
| A news source keeps failing | The doctor's `Sources` line names each failing source with its reason (HTTP 403 is usually a site refusing GitHub's servers). Swap it for a Google News query for the same outlet (`site:example.com when:2d`) on the Sources page |
| A proposal says **Couldn't apply** | Its change can't be made as written (the reason is on the card: usually a setting that doesn't exist or is out of range). Make the change yourself in Settings and **Dismiss** it, or **Try again** after fixing what it names. A proposal that only asked you to look at something is recorded as *Noted* when you tap **Got it** |
| Fresh posts are slow, or the run log says `no answer within 50s` | A model that doesn't answer within its time limit (`llm.timeouts` in the settings: 50 s for a draft) counts as busy and the next model answers, so one stuck call no longer holds up the set. `rate limited (HTTP 429)` from Groq means its free per-minute allowance is used up: the next Groq model answers, then the run waits briefly. Cards still arrive in batches as they're drafted |
| The Studio says the key isn't valid, or "Gemini refused the key" | Make a new key at aistudio.google.com/apikey and paste it in **Settings → Studio**. A key restricted to certain websites must allow your desk's address |
| The Studio says the free quota is used up | Each model has its own small daily free allowance, and Google Search inside the Studio has a separate, smaller one. The Studio answers without search when only search is used up (the reply says so), waits out short per-minute limits, then moves down its models: the newest Gemini flash models, flash-lite, then Gemma (much larger free limits, no search). A model out of quota is skipped until the reset at midnight US Pacific time (the message says when that is for you). **Settings → Studio** lists the models in order and which are used up. If the key is the pipeline's `GEMINI_API_KEY` or from the same Google Cloud project, the morning run shares its quota: make the Studio's key with **Create API key in new project** |
| A Studio post or carousel "didn't come through cleanly" | The model's block wasn't valid. Tap **Try again** (or **Write it again** under the reply) |
| Share → PBS Desk isn't in Android's share sheet | Install the desk from Chrome (**Add to Home screen**), open it once, then try again. Sharing only works with the installed app |
| A change you made "didn't stick" | **System → Rejected changes** lists anything the pipeline couldn't apply, with the reason. *Changes in flight* shows what's still waiting for a run |
| A card is **Blocked** | It matched your blocklist. Nothing was reworded. Edit the draft by hand or skip it. If the match is a false positive, refine the term in `PBS_BLOCKLIST` |
| No quote cards, or the run log says `quotes: 0 verified, 6 not found on Wikiquote` | The day's quotes weren't found word for word on their Wikiquote pages (a page renamed, or the quote worded differently there), so they were left out, as designed. A few not found each day is normal. If it's every quote, Wikiquote may be refusing GitHub's servers: the doctor's `Sources` line shows the source's error. Fix a quote's wording or `page` in `pbs/defaults/quote_pools.yaml` to match the page |
| Too many or too few funny posts | **Settings → Strategy** sets each lane's share (LinkedIn's *Tech humour* keeps one card a day regardless: `strategy.linkedin.humor.min_per_day` in the settings, 0 to stop that). Skipping funny cards teaches the ranking to show fewer; posting them, more |
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
news sources. A normal day uses about 25–40 model calls (15 drafts, triage in two or three batches, and the editor
pass), with a hard cap of 100 in settings (the Studio uses its own key from your browser, so it doesn't count); each cross-post is
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
