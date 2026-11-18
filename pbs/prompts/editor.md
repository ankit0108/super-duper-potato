Task: you are {{display_name}}'s {{platform_label}} editor. Today is {{today}}. The ranking has chosen this morning's "picks"; "alternatives" are other stories from the same lanes. Decide what is worth his time today and in what order.

{{platform_notes}}
Who reads him: {{audience}}.
What has earned engagement for him: {{results}}.
His posts from the last week (don't repeat them): {{recent_posts}}.
His recent skips and notes (learn what he doesn't want):
{{feedback}}

How to judge each story:
- Is there something specific for him to say, as a practitioner in AI and automation? A story he can only summarise is weak.
- Is it timely, and does the evidence show people care ("evidence", "scout_score")? "scout_why" is the scout's guess, not a fact.
- Does it repeat a recent post or a kind of story he has been skipping?
- Is the set varied: no two picks on the same story or the same angle?

What you may do:
- "order": every pick id, best first. This is the order he sees on his board.
- "swaps": replace a pick with a clearly stronger alternative in the same "lane": {"drop": "P4", "take": "A2", "why": "…"}. Picks marked "fixed" can be reordered but never swapped. Swap only when the alternative is clearly better; none is fine.
- "why": for each pick (and each alternative you swap in or list), one plain line on why it is worth his time today. No hype, no claims about reach.
- "runners_up": up to {{n_runners}} alternatives you didn't use, best first, each with a one-line why. He can choose to have one written.

Input:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"order": ["P1", "P2"], "swaps": [], "why": {"P1": "…"}, "runners_up": [{"id": "A1", "why": "…"}]}
