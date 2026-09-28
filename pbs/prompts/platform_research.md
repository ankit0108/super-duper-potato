Task: keep {{display_name}}'s platform guide for LinkedIn and X current. Below are the guide's rules and recent articles about how the two platforms show and rank posts, and what is working for people who post there.

Propose a change only where the articles give real evidence of something new or different: an algorithm change, a new or retired format, a documented shift in what gets reach or what gets penalised. Be conservative: most months need no change at all. Rumour, opinion pieces and generic "tips" lists are not evidence. Never propose anything against his non-negotiables: no engagement bait, no fabrication, no automated posting or engagement.

Current guide (id [platform, format]: rule):
{{rules}}

Recent articles:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"summary": "one or two sentences on what changed on the platforms, if anything", "changes": [{"op": "add|modify|remove", "rule_id": "the id of the rule to modify or remove (null for add)", "platform": "linkedin|x", "format": "null for every format, or the one format it applies to (li_text, x_single, x_thread, x_quote, x_reply)", "text": "the rule as it should read, one or two sentences (add and modify)", "why": "one sentence", "evidence": ["A3"], "confidence": "low|medium|high"}]}

"changes" is [] when nothing is well supported. "evidence" lists only ids of the articles above that support the change.
