Task: you're the writers' room for {{display_name}}'s funny {{platform_label}} {{format_label}} about the topic below. Write {{options}} different versions; an editor will judge them and only the best gets posted.

Pillar: {{pillar_label}} — {{pillar_description}}
A premise to start from (use it or find a better one): {{angle}}
{{format_instructions}}
{{post_type_instructions}}
{{mode_instructions}}
{{sensitive_instructions}}

What makes it funny:
- The joke lives in something specific and true from the material: an exact detail, a number, a name, a quote, or the gap between what was announced and what happened. A joke that would work about any AI or tech story doesn't count.
- Each version uses a different device, one each, in this order: {{devices}}.
- {{shape}}
- The last line lands somewhere the reader didn't see coming. Cut every word the joke doesn't need.
- Plain words, in his voice. No emoji, no hashtags in the text, no "Agree?" or question at the end, no lesson, never explain the joke.
- Never these, everyone has seen them: {{cliches}}.
- Never punch down: no jokes about a person's looks, a community, religion, caste, gender, a region, customers or colleagues. The target is the hype, the situation, the corporate language or the absurdity itself.

Humour he likes (match the taste, never reuse the content):
{{funny_examples}}

Recent posts he actually published (match the voice, never reuse the content):
{{examples}}
Never use: {{avoid}}

Material (the only facts you may use):
<input>
{{input_json}}
</input>

Reply with JSON only:
{"options": [{"device": "…", "text": "…"}], "hashtags": ["#…"], "first_comment": "…"}
- "options": {{options}} versions, each "text" a whole post ready to post.
- "hashtags": {{hashtag_rule}}
- "first_comment": {{first_comment_rule}}
