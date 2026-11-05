Task: write a {{platform_label}} {{format_label}} for {{display_name}} about the topic below.

Pillar: {{pillar_label}} — {{pillar_description}}
Angle to develop: {{angle}}
{{format_instructions}}
{{affairs_instructions}}
{{post_type_instructions}}
{{mode_instructions}}
{{sensitive_instructions}}
{{experiment_instructions}}

Style guide learned from his edits (follow it):
{{style_rules}}
What works on {{platform_label}} now (follow it unless his style guide says otherwise):
{{platform_guide}}
Target length: {{length_target}}
Never use: {{avoid}}
Hook types that work best for him on {{platform_label}} (by results, then by what he keeps): {{hook_prefs}}

Recent posts he actually published (match the voice, never reuse the content):
{{examples}}

Material (the only facts you may use; cite sources by index; lead with the newest developments and say when things happened; if "why_now" says what he meant by a request, stay on that meaning):
<input>
{{input_json}}
</input>

Reply with JSON only:
{"text": "…", "posts": [], "hook_type": "…", "hooks": [{"type": "…", "text": "…"}, {"type": "…", "text": "…"}, {"type": "…", "text": "…"}], "claims": [{"text": "…", "source": 0}], "hashtags": ["#…"], "first_comment": "…", "format_note": "", "angle": "…"{{extra_fields}}}

Field rules:
- Make one useful point. Lead with the actual development and its concrete detail. Separate what the source reports from your interpretation; use "could", "suggests" or an explicit open question when the consequence is uncertain.
- Never turn one funding round, launch or earnings report into a claim that the whole market is shifting. Never describe a research benchmark as deployment proof. A source's marketing claim is a claim to attribute, not a verified result.
- Follow evidence_depth and editorial_brief. A headline-only source supports a brief attributed observation, not a long explainer. Prefer a short post over padded advice. Do not force an automation, engineering, or AI lesson onto an unrelated story.
- End when the point is made. No compulsory question, generic advice or repeated summary. On X, remove the headline prefix and use the space for a distinctive observation. On LinkedIn, give the reader a concrete implication or limitation they can assess.
- "text": the full post. For a thread leave it "" and use "posts".
- "posts": threads only: {{thread_min}} to {{thread_max}} posts, each at most {{x_limit}} characters, no "1/" numbering. Otherwise [].
- "hook_type": the type of the opening you used.
- "hooks": exactly three alternative opening lines, each a different type from: {{hook_types}}. A number hook may only use a number from the material.
- "claims": every figure, date or factual claim in the draft with the index of the source that supports it ([] if none).
- "hashtags": {{hashtag_rule}}
- "first_comment": {{first_comment_rule}}
- "format_note": LinkedIn only: if a carousel or poll would work better, say how in one sentence; otherwise "".
- "angle": the angle you actually took, in one line.
