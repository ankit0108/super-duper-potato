Task: revise this {{platform_label}} {{format_label}} for {{display_name}} according to his note.

His note: "{{note}}"
{{chips}}
{{target_instructions}}
{{format_instructions}}

Keep every fact tied to the same material and add no new facts. {{mode_rule}}
Hashtags: start from "current_hashtags" (the ones he chose) and change them only if his note asks or they don't suit {{platform_label}}.

Style guide learned from his edits (follow it):
{{style_rules}}
What works on {{platform_label}} now (follow it unless his note or style guide says otherwise):
{{platform_guide}}
Target length: {{length_target}}
Never use: {{avoid}}

Material:
<input>
{{input_json}}
</input>

Reply with JSON only:
{"text": "…", "posts": [], "hook_type": "…", "hooks": [{"type": "…", "text": "…"}, {"type": "…", "text": "…"}, {"type": "…", "text": "…"}], "claims": [{"text": "…", "source": 0}], "hashtags": ["#…"], "first_comment": "…", "format_note": "", "angle": "…"{{extra_fields}}}
Field rules: "posts" only for threads ({{thread_min}}–{{thread_max}} posts of at most {{x_limit}} characters, no numbering); three alternative hooks of different types from: {{hook_types}}; "hashtags": {{hashtag_rule}}; "first_comment": {{first_comment_rule}}.
