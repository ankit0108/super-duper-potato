Task: find what's working on LinkedIn and X right now for {{display_name}}, who posts about the topics in the input. Today is {{today}}.

Search Google for public LinkedIn and X posts from the last three days on these topics (for example "site:linkedin.com/posts" or "site:x.com" with a topic), and for coverage of what people on LinkedIn and X are discussing. Find the conversations that are taking off: posts with many reactions, comments or reposts, or the same subject coming up from many people at once. Funny, bizarre and heated conversations count as much as serious ones.

For each conversation:
- "platform": "linkedin" or "x", where it's taking off.
- "topic": the subject in a few specific words, like a headline (not "AI" or "careers").
- "what_people_say": one or two sentences: the takes, the argument or the joke going round.
- "why_it_works": one sentence on what makes posts about it travel: the hook, the format, the angle or the timing.
- "angle": one line {{display_name}} could post that adds something rather than repeating what's out there.
- "examples": up to two links to posts or articles about it, copied exactly from the search results; [] if none.

Rules:
- Only conversations you found in the search results, from the last three days. Never invent a conversation, a figure, a quote or a link.
- At most {{per_platform}} per platform, the most active first.
- Skip party politics, tragedies, anything about a private person, giveaways and "comment YES" engagement bait.

Topics:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"conversations": [{"platform": "linkedin", "topic": "…", "what_people_say": "…", "why_it_works": "…", "angle": "…", "examples": ["https://…"]}]}
