Task: review how {{display_name}}'s LinkedIn and X posts are performing, from their own analytics, and say what to do about it. Today is {{today}}.

The input has:
- "summary": numbers already worked out from the analytics, per platform: how many posts, median impressions and engagement rate, the best and weakest posts, days of the week, and (for posts PBS drafted) formats and topics. Trust these numbers; don't recompute them.
- "posts": every post with its numbers. "source" is "pbs" for posts PBS drafted (with the opening, format, topic, length and hour) and "history" for posts from the export that PBS didn't draft (often only a date, a link and numbers).
- "followers", "days" (daily or weekly impressions and engagements), "audience" (who sees the posts) and "totals", when the exports had them.
- "goals": what {{display_name}} wants from posting.

Write like a sharp analyst who has read every row, for someone busy:
- "headline": one sentence: the single most useful thing the numbers say.
- "findings": 3 to 6 findings, the most important first. Each has a short "title", a "detail" of one or two sentences on what it means for {{display_name}}, and "evidence": the numbers behind it, quoted from the input (for example "4 posts on Tuesdays: median 2,140 impressions vs 880 on other days").
- "what_works": up to 4 short lines, each something specific to keep doing.
- "what_doesnt": up to 4 short lines, each something specific to drop or change.
- "try_next": 3 to 5 concrete experiments for the next two weeks (a format, a time, a topic, a hook style), each one line that says what to do and what number would show it worked.
- "audience": one or two sentences on who is reading, if the input has it; "" otherwise.
- "caveats": what the data can't say yet (too few posts, missing text for exported posts, a short period). At most 3.

Rules:
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
