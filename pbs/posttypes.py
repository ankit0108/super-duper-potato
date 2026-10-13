"""Kinds of post beyond analysis: what the humour and ideas pillars make (Pillar.post_types holds the labels).

- funny_take: a light take on a news topic (the facts from the sources, the joke in the framing);
- observation: a relatable funny post from a premise in humor_pools.yaml (no facts at all);
- quote: a quote from quote_pools.yaml, found word for word on Wikiquote;
- excerpt: a short passage quoted word for word from a news topic's sources;
- thought: one sharp idea, from a theme in thought_pools.yaml or prompted by a news topic.
"""

from __future__ import annotations

HUMOROUS = frozenset({"funny_take", "observation"})
# Quoted words in these must be in the material word for word; the editor pass leaves them alone.
VERBATIM = frozenset({"quote", "excerpt"})
# What triage can make of a news topic, in order of preference when it doesn't say.
FROM_NEWS = ("funny_take", "thought", "excerpt")
LABELS = {"funny_take": "Funny take", "observation": "Relatable", "quote": "Quote", "excerpt": "Excerpt",
          "thought": "Thought"}
# The angle a card from a pool starts with (the premise, theme or quote is the topic).
POOL_ANGLE = {"observation": "The joke everyone will recognise", "thought": "One sharp idea of your own",
              "quote": "What it means today"}


def for_news(types: dict[str, str], wanted: object) -> str | None:
    """A news topic's post type in a pillar with `types`: what triage asked for when it can come from news,
    otherwise the pillar's first type that can. None for a pillar without post types."""
    if not types:
        return None
    if wanted == "quote":
        wanted = "excerpt"  # only the quote pool's quotes are quotes: from news, it's an excerpt
    elif wanted == "observation":
        wanted = "funny_take"
    if wanted in types and wanted in FROM_NEWS:
        return str(wanted)
    return next((t for t in FROM_NEWS if t in types), None)


def pillar_for(settings: object, platform: str, post_type: str) -> str | None:
    """The first pillar on a platform that makes this kind of post."""
    for key, spec in settings.pillars(platform).items():  # type: ignore[attr-defined]
        if post_type in spec.post_types:
            return key
    return None
