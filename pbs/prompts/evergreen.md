Task: plan next week's interview cards for {{display_name}}. He answers them in his Sunday session, and each draft is written only from his answers.

Propose topics for the interview-mode pillars listed in the material. Tie them to this week's themes where that gives a sharper question; otherwise pick evergreen topics from his work and life. Avoid repeating anything he posted recently.

Each topic gets two or three questions that:
- are specific and answerable in one to three sentences by typing or dictating on a phone;
- never ask for employer, client or colleague details, internal system names, or identifying figures;
- never lead him to a particular view.

Material:
<input>
{{input_json}}
</input>

Reply with JSON only, up to the counts in "want_interview" per platform:
{"topics": [{"platform": "linkedin|x", "pillar": "<interview pillar key>", "mode": "interview", "title": "…", "angle": "…", "questions": [{"q": "…", "why": "…"}]}]}
