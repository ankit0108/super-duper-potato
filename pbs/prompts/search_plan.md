Task: {{display_name}} asked for posts about the topic below. Plan the news and research search for it.

Read his profile and pillars first: they tell you what he most likely means. Resolve an ambiguous topic toward them. For example, for someone who builds automation for business processes, "AI automation" means automating business and back-office work with AI (RPA, workflow and agent tools, document processing, process orchestration), not factory robots or industrial control systems.

About him:
{{profile}}

His pillars:
{{pillars}}

Rules:
- "interpretation": one sentence saying what he means by the topic.
- "queries": 2 or 3 news search queries (3 to 8 words each), specific enough that the top results are about that meaning. Quotes for exact phrases and OR are fine. No site: filters, no dates.
- "exclude": up to 5 single words that only appear with the wrong meaning (for example: industrial, manufacturing, robotics, factory). Use [] when the topic isn't ambiguous. Never exclude a word from his own query.
- "arxiv": an arXiv API search expression for recent papers on that meaning (fields abs: and ti:, joined with AND/OR, phrases in quotes), or null when papers wouldn't help.
- "recency_days": how recent the news should be: 7 for fast-moving news, 14 by default, 30 or 90 for slower topics.
- "background": true only when encyclopedic background would genuinely help (history, a place, an institution).

Topic (and his notes, if any):
<input>
{{input_json}}
</input>

Reply with JSON only:
{"interpretation": "…", "queries": ["…", "…"], "exclude": [], "arxiv": null, "recency_days": 14, "background": false}
