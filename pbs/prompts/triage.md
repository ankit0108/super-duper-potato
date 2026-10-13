Task: triage today's candidate topics for {{display_name}}'s LinkedIn and X. For each topic decide, per platform, whether it fits a pillar or lane, how much angle potential it has for him specifically, and propose one sharp angle.

LinkedIn pillars (key: label — what it covers [mode]):
{{linkedin_pillars}}

X lanes (key: label — what it covers [mode]):
{{x_lanes}}

X affairs post types: history (history behind the news), tracker (what actually changed, with data), outlook (where it is heading and what would change that), opinion (only when the topic touches a recorded stance below), story (a story from history to now that isn't today's news: an era, a person, a place, an achievement, a tradition; topics whose why_now says "not today's news" are always this type). Bihar topics can be any of these: its story runs from ancient Magadha to today, not only this week's headlines.

Post types in the humour and ideas lanes (post_type):
- funny_take (humour lanes, any topic that genuinely invites a smile: a launch that overpromises, a name, a hype cycle, a familiar pattern at work): a light joke whose facts all come from the topic. On LinkedIn only tech, AI, startup and work topics.
- excerpt (ideas lane, X): the sources hold a striking line worth quoting word for word (a paper's key sentence, an essay, a speech, a long read).
- thought (ideas lane, X): the topic prompts one sharp idea that stands on its own without the news.
Humour is never about tragedies, violence, disasters, communal incidents, religion, caste, gender, a region or community, someone's appearance, a private person, or partisan politics. A sensitive topic never goes to a humour lane.

Recorded stances (issue key: his position):
{{stances}}

His recent feedback on suggestions (why he skipped them, and what he moved or copied to the other platform; his own words first):
{{feedback}}

How to judge:
- Learn from his feedback: a topic like one he skipped gets a lower angle_potential, or "none" on that platform, for the reason he gave. His own words say most about what he wants. A topic like one he moved to the other platform belongs there; one he wanted on both platforms suits both.
- angle_potential 1–5: is there something specific and non-generic to say about it? 5 = a sharp, well-grounded take few people will post. 1 = generic news anyone could repost.
- The angle fits the story itself: the technology, the business, the market, the people it affects, the policy, or the history behind it. His automation work is one possible lens, used only when the story is about automating work; never bend a chip, model, funding, policy or research story toward enterprise or process automation. Across the set, vary the lens.
- For a humour lane, the angle is the joke's premise in one line; for the ideas lane, the line to quote or the idea. Most topics are best as analysis: use the humour and ideas lanes only where the topic really suits them.
- Use "none" when a topic doesn't fit a platform. Affairs belong on X; on LinkedIn only where affairs meet tech (for example {{linkedin_affairs}}), under the industry pillar.
- Interview-mode pillars and lanes (firsthand, learning in public, life) need his own experience: the angle must be a link to his work worth asking him about, never a claim.
- X format: x_reply for big announcements where large accounts will post (replying is how a small account gets seen); x_thread only when there is enough substance for 3+ posts; x_quote when there is a specific post or article to react to; otherwise x_single.
- sensitive = true for tragedies, violence, communal incidents, or disasters with casualties.
- issue_key: the key of a recorded stance issue the topic touches, otherwise null.
- summary_en: one neutral English sentence (translate if the topic is in Hindi).

Topics:
<input>
{{input_json}}
</input>

Reply with JSON only, one entry per topic id:
{"topics": [{"id": "T1", "summary_en": "…", "sensitive": false, "sensitive_reason": "", "issue_key": null,
  "linkedin": {"pillar": "{{linkedin_keys}}|none", "angle_potential": 3, "angle": "…", "format_note": "", "post_type": "funny_take|null"},
  "x": {"lane": "{{x_keys}}|none", "angle_potential": 3, "angle": "…", "format": "x_single|x_thread|x_quote|x_reply", "affairs_type": "history|tracker|outlook|opinion|null", "post_type": "funny_take|excerpt|thought|null"}}]}
