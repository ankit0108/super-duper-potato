Task: review how {{display_name}}'s LinkedIn and X posts are performing, from their own analytics, and say what to do about it. Today is {{today}}.

The input has:
- "summary": numbers already worked out from the analytics, per platform: how many posts, median impressions and engagement rate, the best and weakest posts, days of the week, and (for posts PBS drafted) formats and topics. Trust these numbers; don't recompute them.
- "posts": every post with its numbers. "source" is "pbs" for posts PBS drafted (with the opening, format, topic, length and hour) and "history" for posts from the export that PBS didn't draft (often only a date, a link and numbers).
- "followers", "days" (daily or weekly impressions and engagements), "audience" ("followers": who follows him; "viewers": who saw his posts) and "totals", when the exports had them. "published_before_period" marks older posts the export lists because they were still seen in its period.
- "goals": what {{display_name}} wants from posting.
- "posting_window": when {{display_name}} is testing posting (his time), per platform; posts PBS drafted say whether they went out inside it ("in_posting_window"). Once there are posts inside and outside it, say whether the window is doing better, with the numbers; until then, say the test is still running.

Write like a sharp analyst who has read every row, for someone busy:
- "headline": one sentence: the single most useful thing the numbers say.
- "findings": 3 to 6 findings, the most important first. Each has a short "title", a "detail" of one or two sentences on what it means for {{display_name}}, and "evidence": the numbers behind it, quoted from the input (for example "4 posts on Tuesdays: median 2,140 impressions vs 880 on other days").
- "what_works": up to 4 short lines, each something specific to keep doing.
- "what_doesnt": up to 4 short lines, each something specific to drop or change.
- "try_next": 3 to 5 concrete experiments for the next two weeks (a format, a time, a topic, a hook style), each one line that says what to do and what number would show it worked.
- "audience": one or two sentences on who is reading, if the input has it; "" otherwise.
- "caveats": what the data can't say yet (too few posts, missing text for exported posts, a short period). At most 3.

Rules:
- "coverage" shows published, measured and missing posts per platform. Missing measurements are unknown, never zero performance. If a platform has no measurements, do not say what works or fails there.
- Groups marked "insufficient" have fewer than five measured posts. Describe them as early observations and propose a test; never recommend abandoning a day, topic or format on this basis. Even larger groups are observational, not causal evidence.
- Account for exposure: posts of different ages, snapshots taken on different dates, and export-period counts are not equivalent lifetime results. Do not infer that posting time caused the outcome. Compare posting windows only with at least five measured posts both inside and outside; otherwise report that more measurements are needed.
- Distinguish median per-post engagement rate from weighted engagement rate. Missing engagement is excluded, not treated as zero. Raw likes without impressions do not give a rate. Never compare reach or raw engagement counts across platforms.
- A useful experiment specifies one change, a baseline from the data, a collection window and at least five posts per condition. Favor repeatable hooks and subject choices over claims about a platform's secret algorithm.
- Every claim must come from the input. Never invent a number, a post or a reason. When a pattern rests on one or two posts, say so.
- Engagement rate means engagements divided by impressions. Compare like with like: LinkedIn with LinkedIn, X with X.
- Be specific. "Post more consistently" or "use engaging hooks" are not findings.
- Plain words, no emoji, no hype.

Input:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"headline": "…", "findings": [{"title": "…", "detail": "…", "evidence": "…"}], "what_works": ["…"], "what_doesnt": ["…"], "try_next": ["…"], "audience": "…", "caveats": ["…"]}
