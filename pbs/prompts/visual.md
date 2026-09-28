Task: design the content of a visual for {{display_name}}'s {{platform_label}} post below. The desk draws it in his own clean style at {{size}}, so write only the words: no colours, fonts or layout.

{{kind_rule}}

His note: {{note}}

Rules:
- Use only what the post and the sources say. Every figure, name and date must appear in them, written exactly as there; never add a number, a statistic or a quote of your own.
- Say it in his voice, plainly: short, concrete words a colleague would use. No hype, no emoji, no hashtags, no links.
- Nothing that claims an experience or an opinion for him beyond what the post itself says.
- "title" is the headline (at most 70 characters); "subtitle" one short line under it, or "".
- "caption" is the source line, like "Source: AgentBench-Enterprise (Hugging Face papers, Sept 2026)", or "" when there are no sources.
- "alt_text" describes the visual for people using screen readers: what it shows and all of its text, in reading order (at most 500 characters).
- "sources" lists the indexes of the sources it draws on.

Material:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"kind": "carousel|flow|compare|list|stat|quote", "title": "…", "subtitle": "…", "items": [{"title": "…", "body": "…"}], "caption": "…", "alt_text": "…", "sources": [0]}
