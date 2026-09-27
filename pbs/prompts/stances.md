Task: propose up to {{count}} new recurring public issues that {{display_name}} might want a recorded stance on, based on recent affairs coverage (world, India, Bihar). Skip anything already in "existing_issues".

For each issue, lay out two to four main positions people actually hold. Write each position fairly, in the words its supporters would use. Never indicate which position is right, and never pick one.

<input>
{{input_json}}
</input>

Reply with JSON only:
{"issues": [{"key": "short-kebab-id", "issue": "the question, in a few words", "tier": "world|india|bihar|other", "context": "one neutral line of background", "positions": [{"key": "a", "label": "…", "text": "…"}], "keywords": ["…"]}]}
