Task: read this analytics screenshot from LinkedIn or X and extract the numbers exactly as shown.

Rules:
- Only report numbers you can read. Never estimate or infer a missing number: leave it null.
- "1.2K" means 1200. Copy the post's opening words from the screenshot into text_snippet so it can be matched to a post.
- LinkedIn: impressions, reactions, comments, reposts, sends, followers gained from the post, profile views from the post, link clicks.
- X: views → impressions, likes → reactions, replies → comments, reposts plus quotes → reposts, follows → followers_gained, profile visits → profile_views, link clicks.
- If the screenshot shows account-level totals (followers, profile views for a period), put them under "account".
- confidence: 0 to 1, how sure you are that the numbers are read correctly.

These recent posts may appear (for context only; don't copy numbers from here):
<input>
{{input_json}}
</input>

Reply with JSON only:
{"platform": "linkedin|x", "kind": "post_analytics|post_view|content_list|account", "posts": [{"text_snippet": "…", "posted_date": "YYYY-MM-DD or null", "impressions": null, "reactions": null, "comments": null, "reposts": null, "sends": null, "followers_gained": null, "profile_views": null, "link_clicks": null, "confidence": 0.9}], "account": {"followers": null, "profile_views": null}}
