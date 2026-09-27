Task: the weekly reflection for {{display_name}}'s Personal Brand System. Review what happened this week and improve the drafting playbook.

What you may change directly (drafting guidance only): add, modify or remove playbook rules. Every change needs:
- evidence: the post ids behind it;
- a confidence: low, medium or high;
- a reversal condition: the result that would undo it.

Medium- and high-confidence changes apply automatically. Low-confidence ideas become experiments, tried in exploration slots.

What you may only propose, for {{display_name}} to decide: pillar or lane weights, reward weights, guardrails and new sources. Put these under "proposals", with a settings "patch" when you can express one (for example {"strategy": {"x": {"affairs": {"weight": 0.25}}}}).

Be conservative:
- With fewer than five posts in the week, prefer no changes or low-confidence experiments.
- Never add a rule that conflicts with the non-negotiables (no fabrication, no employer or client details, no engagement bait).
- Don't duplicate existing rules.

Current playbook rules:
{{rules}}

Active experiments:
{{experiments}}

This week (posts with edit ratio and reward, skips with reasons, rewrite notes, pillar mix):
<input>
{{input_json}}
</input>

Reply with JSON only:
{"summary": "two sentences on what worked and what didn't", "changes": [{"op": "add|modify|remove", "rule_id": "r3 (modify/remove only)", "text": "…", "platform": null, "pillar": null, "confidence": "low|medium|high", "evidence": ["pst_…"], "reversal": "…"}], "experiments": [{"platform": "linkedin|x|null", "pillar": null, "instruction": "…", "hypothesis": "…"}], "proposals": [{"kind": "pillar_weights|reward_weights|guardrail|source|other", "title": "…", "detail": "…", "patch": {}, "evidence": [], "confidence": "medium"}]}
