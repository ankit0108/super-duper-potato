Task: revise this {{platform_label}} {{format_label}} for {{display_name}} according to his note.

His note: "{{note}}"
{{chips}}
{{target_instructions}}
{{format_instructions}}

Keep every fact tied to the same material and add no new facts. {{mode_rule}}

Style guide learned from his edits (follow it):
{{style_rules}}
Target length: {{length_target}}
Never use: {{avoid}}

Material:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"text": "…", "posts": [], "hook_type": "…", "hooks": [{"type": "…", "text": "…"}, {"type": "…", "text": "…"}, {"type": "…", "text": "…"}], "claims": [{"text": "…", "source": 0}], "format_note": "", "angle": "…"{{extra_fields}}}
Field rules: "posts" only for threads ({{thread_min}}–{{thread_max}} posts of at most {{x_limit}} characters, no numbering); three alternative hooks of different types from: {{hook_types}}.
