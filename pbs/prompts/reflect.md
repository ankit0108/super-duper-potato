Task: the weekly reflection for {{display_name}}'s Personal Brand System. Review what happened this week and improve the drafting playbook.

What you may change directly (drafting guidance only): add, modify or remove playbook rules. Every change needs:
- evidence: the post ids behind it;
- a confidence: low, medium or high;
- a reversal condition: the result that would undo it.

Medium- and high-confidence changes apply automatically. Low-confidence ideas become experiments, tried in exploration slots.

What you may only propose, for {{display_name}} to decide: pillar or lane weights, reward weights and guardrails. Put these under "proposals". A proposal must change something when he approves it, so each one needs either:
- a settings "patch" using only these settings, with these exact keys and one platform at a time:
  - a pillar or lane weight from 0 to 1: {"strategy": {"x": {"affairs": {"weight": 0.25}}}} (lanes and their weights now: {{pillar_keys}});
  - cards a morning: {"platforms": {"linkedin": {"slots": 5}}} (LinkedIn 1 to 6, X 1 to 10);
  - reward weights: {"rewards": {"linkedin": {"comments": 0.3}}};
  - how many hashtags: {"hashtags": {"x": {"max": 1}}};
- or, for a guardrail, a "rule": one instruction for the drafts, written as the rule itself (for example "End with at most one question."), with "platform" set to "linkedin", "x" or null.

Anything that fits neither (a suggestion to look at something, a new source, a model change) goes under "advice", not "proposals".

Be conservative:
- With fewer than five posts in the week, prefer no changes or low-confidence experiments.
- Never add a rule that conflicts with the non-negotiables (no fabrication, no employer or client details, no engagement bait).
- Don't duplicate existing rules.

Current playbook rules:
{{rules}}

Active experiments:
{{experiments}}

Drafts that read as AI-written cost {{display_name}} editing time. "ai_tells_in_draft" lists the kinds of AI tell in the draft as shown and "ai_tells_posted" those left in what went out (contrast framing, labelled reveals, stock openers and closers, em dashes, emoji bullets, staccato lines, stacked questions, filler, same-length sentences); "writing" counts them across the week's drafts, before and after the editor pass. A kind that keeps being taken out before posting deserves a rule.

"scout_scores" (when present) gives, per platform, the scouts' average score for the cards he posted and for those he skipped or let expire. If posted cards don't score higher over several cards, say so in a sentence: the scouts' read isn't matching his choices yet. Never a weight change from it.

"editor_order" (when present) counts his posts from the top half and the bottom half of each editor's order. If he keeps posting from the bottom half, say so in a sentence. Never a weight change from it.

A skip with the reason "poorly_written" means the topic was fine but the draft wasn't written well or didn't sound like {{display_name}}: it's about the writing, so learn a playbook rule from it (especially from his note), never a change to pillar weights.

This week (posts with edit ratio and reward, skips with reasons, rewrite notes, pillar mix, writing, scout_scores):
<input>
{{input_json}}
</input>

Reply with JSON only:
{"summary": "two sentences on what worked and what didn't", "changes": [{"op": "add|modify|remove", "rule_id": "r3 (modify/remove only)", "text": "…", "platform": null, "pillar": null, "confidence": "low|medium|high", "evidence": ["pst_…"], "reversal": "…"}], "experiments": [{"platform": "linkedin|x|null", "pillar": null, "instruction": "…", "hypothesis": "…"}], "proposals": [{"kind": "pillar_weights|reward_weights|guardrail|other", "title": "…", "detail": "…", "patch": {}, "rule": null, "platform": null, "evidence": [], "confidence": "medium"}], "advice": [{"title": "…", "detail": "…"}]}
