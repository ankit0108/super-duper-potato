Task: edit this {{platform_label}} {{format_label}} by {{display_name}} so it reads like a person wrote it. Change only what reads as AI-written; keep everything else word for word.

What reads as AI-written in it (fix every one):
{{tells}}

How to fix them:
- Contrast framing ("It's not X, it's Y", "not just X but Y"): say the true part directly ("Trust decides it.").
- A labelled reveal ("Here's why", "The result?", "The catch:") or a summary closer ("In short", "Ultimately"): cut the label and keep the point.
- A stock opener ("In today's…", "Imagine…"): open with the concrete fact or claim instead.
- Em dashes: use a comma, a full stop or brackets; keep at most one dash in the whole post.
- Emoji bullets: plain lines, or a short sentence each.
- Stacked rhetorical questions: keep at most one, or turn them into statements.
- Filler phrases: delete them, or say the specific thing.
- Every sentence the same length: merge two short ones, or split a long one, so the rhythm varies.

Hard rules:
- Keep every fact, figure, date, name and source reference exactly as it is. Add nothing new, and drop no fact.
- Keep the opening line's job (the same kind of hook) and the order of the argument.
- Don't claim experiences or opinions for {{display_name}} that the draft doesn't already state.
- {{format_instructions}}
- Never use: {{avoid}}

Recent posts by {{display_name}} (the voice to match; never reuse their content):
{{examples}}

The draft:
<input>
{{input_json}}
</input>

Reply with JSON only: {"text": "…", "posts": []}. For a thread, put the posts in "posts" (the same number of posts) and leave "text" as "". Otherwise put the whole post in "text" and leave "posts" as [].
