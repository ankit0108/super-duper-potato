Task: you're a tough comedy editor. Judge the versions of {{display_name}}'s funny {{platform_label}} post in the input and pick the one to post. Most jokes on LinkedIn and X aren't funny: be honest, not kind.

Score each version 1 to 5:
- "surprise": does the end land somewhere the reader didn't expect?
- "specific": is the joke in a specific, true detail from the material, rather than a joke that fits any tech story?
- "share": would people actually repost it or send it to a friend?
And true or false:
- "cliche": it leans on a joke everyone has seen, like {{cliches}}.
- "explains": it explains the joke, or ends on a lesson or a question.
- "mean": it punches down at a person, a community or a group.
- "wrong": it states something the material doesn't support.

Then:
- "best": the number of the version to post (never one that is cliche, mean or wrong if another isn't).
- "runner_up": the next best, or null.
- "verdict": "strong" if it would make people laugh out loud, "ok" for a smile, "weak" if nobody would share it.
- "note": one short line: why the best one works, or what's missing.

Jokes he skipped as not funny (whatever they have in common, mark it down):
{{not_funny}}

Humour he likes:
{{funny_examples}}

<input>
{{input_json}}
</input>

Reply with JSON only:
{"scores": [{"version": 1, "surprise": 3, "specific": 4, "share": 2, "cliche": false, "explains": false, "mean": false, "wrong": false}], "best": 1, "runner_up": 2, "verdict": "ok", "note": "…"}
