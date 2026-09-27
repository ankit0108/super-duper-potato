"""Prompt templates in pbs/prompts/*.md with {{placeholders}}. Each template has a short version hash
that is recorded on every card, so the system report can compare prompt versions by edit ratio."""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Any

from .ids import short_hash

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


@cache
def template(name: str) -> str:
    return resources.files("pbs.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")


def version(*names: str) -> str:
    return short_hash("".join(template(n) for n in names), 7)


def render(name: str, **values: Any) -> str:
    text = template(name)

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f"prompt {name} needs '{key}'")
        v = values[key]
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False, indent=1)
        return "" if v is None else str(v)

    rendered = _VAR_RE.sub(sub, text)
    # Collapse runs of blank lines left by empty optional sections.
    return re.sub(r"\n{3,}", "\n\n", rendered).strip() + "\n"


def input_block(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)
