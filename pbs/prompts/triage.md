Task: triage today's candidate topics for {{display_name}}'s LinkedIn and X. For each topic decide, per platform, whether it fits a pillar or lane, how much angle potential it has for him specifically, and propose one sharp angle.

LinkedIn pillars (key: label — what it covers [mode]):
{{linkedin_pillars}}

X lanes (key: label — what it covers [mode]):
{{x_lanes}}

X affairs post types: history (history behind the news), tracker (what actually changed, with data), outlook (where it is heading and what would change that), opinion (only when the topic touches a recorded stance below).

Recorded stances (issue key: his position):
{{stances}}

His recent feedback on suggestions (why he skipped them, newest and most specific first):
{{feedback}}

How to judge:
- Learn from his feedback: a topic like one he skipped gets a lower angle_potential, or "none" on that platform, for the reason he gave. His own words say most about what he wants.
- angle_potential 1–5: can he add something specific and non-generic, given his profile? 5 = only someone with his background would say this. 1 = generic news anyone could repost.
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
  "linkedin": {"pillar": "{{linkedin_keys}}|none", "angle_potential": 3, "angle": "…", "format_note": ""},
  "x": {"lane": "{{x_keys}}|none", "angle_potential": 3, "angle": "…", "format": "x_single|x_thread|x_quote|x_reply", "affairs_type": "history|tracker|outlook|opinion|null"}}]}
