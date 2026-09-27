"""Hand-written model replies for the demo world, so the desk demo shows realistic drafts.

External drafts only use facts present in the mock sources (pbs/demo/web.py); nothing here claims an
experience for Ankit. Interview drafts are built from the answers given.
"""

from __future__ import annotations

from typing import Any

from .. import textutil
from ..llm.base import LLMRequest
from ..llm.fake import DEFAULT_HANDLERS
from . import history

# topic keyword -> triage decision
TRIAGE: dict[str, dict[str, Any]] = {
    "agent platform": {"linkedin": ("industry", 5, "Approval steps and audit logs are the real product for regulated back offices"),
                       "x": ("tech", 5, "x_reply", "The permission model is the story, not the agents")},
    "agentbench": {"linkedin": ("research", 5, "41% end to end: why exception handling is where agents fail"),
                   "x": ("tech", 4, "x_thread", "What a back-office benchmark says about agent readiness")},
    "anthropic raises": {"linkedin": ("industry", 3, "Enterprise revenue is 80% of sales: the market has chosen its buyer"),
                         "x": ("tech", 3, "x_single", "Enterprise is where the money is")},
    "uipath adds agentic": {"linkedin": ("receipts", 5, "Mixing bots, agents and people in one governed flow — what that looks like on the ground"),
                            "x": ("tech", 3, "x_quote", "RPA vendors are becoming agent orchestrators")},
    "automation anywhere": {"linkedin": ("industry", 4, "Finance ops is the first real test for vendor AI agents"),
                            "x": ("tech", 3, "x_single", "Finance ops is the proving ground")},
    "show the evals": {"linkedin": ("learning", 4, "Benchmarks vs production: what evals should measure"),
                       "x": ("tech", 4, "x_thread", "Why agent benchmark numbers don't survive production")},
    "small models": {"linkedin": ("research", 3, "Distilled tool use makes small agents viable for on-prem work"),
                     "x": ("tech", 3, "x_single", "A 3B model keeping 90% of the teacher's tool-use accuracy")},
    "exception handling": {"linkedin": ("research", 4, "Exceptions are the real process, and now there's a benchmark for it"),
                           "x": ("none", 1, "x_single", "")},
    "streamable http": {"linkedin": ("learning", 3, "What changed in MCP's Python SDK and why remote servers matter"),
                        "x": ("tech", 2, "x_single", "MCP remote servers get resumable streams")},
    "industrial corridors": {"linkedin": ("none", 1, ""), "x": ("affairs", 5, "x_thread", "Three corridors along the expressways: what's planned and what to watch", "tracker")},
    "chip packaging": {"linkedin": ("none", 1, ""), "x": ("affairs", 4, "x_single", "₹12,000 crore for chip packaging, and Bihar wants in", "tracker")},
    "safety testing": {"linkedin": ("industry", 4, "Pre-deployment testing is becoming the global default for frontier AI"),
                       "x": ("affairs", 3, "x_single", "Twenty-eight countries, one testing framework", "outlook")},
    "stampede": {"linkedin": ("none", 1, ""), "x": ("affairs", 2, "x_single", "What happened and what officials have said", "tracker")},
    "simultaneous elections": {"linkedin": ("none", 1, ""), "x": ("affairs", 3, "x_single", "Where the simultaneous-elections bills stand", "history"), "issue": "one-nation-one-election"},
    "patna metro": {"linkedin": ("none", 1, ""), "x": ("affairs", 3, "x_single", "Patna Metro's priority corridor is almost here", "tracker")},
    "legislative assembly": {"linkedin": ("none", 1, ""), "x": ("affairs", 3, "x_single", "On this day: Bihar's first assembly session", "history")},
    "insurance claims": {"linkedin": ("industry", 3, "Claims automation is where AI startups are finding revenue"),
                         "x": ("startups", 4, "x_single", "4x faster claims is the kind of number buyers ask about")},
    "yc's latest batch": {"linkedin": ("industry", 3, "Two-thirds of a YC batch builds workflow agents"),
                          "x": ("startups", 4, "x_thread", "105 of 160: what the YC batch says about agents")},
}

HINDI_TITLES = {
    "बिहार में एक्सप्रेसवे के किनारे तीन नए औद्योगिक गलियारे बनेंगे": "Bihar to build three new industrial corridors along expressways",
}

LINKEDIN: dict[str, dict[str, Any]] = {
    "agent platform": {
        "text": ("OpenAI's new agent platform isn't really about agents. It's about approval steps and audit logs.\n\n"
                 "The launch lets companies build agents that operate internal tools, scoped to specific tools, with every "
                 "action logged for compliance review. Early customers include banks and insurers piloting back-office "
                 "workflows.\n\n"
                 "That's the right order of priorities. In regulated work, the question was never \"can the model do the "
                 "task?\" It's \"can we prove what it did, and stop it before it does the wrong thing?\"\n\n"
                 "Three things worth watching:\n"
                 "- Where the human approval sits: before the action, or after the fact?\n"
                 "- Whether audit logs are readable by the people who actually get audited, not just engineers.\n"
                 "- How exceptions route. The happy path is the easy 20%.\n\n"
                 "If you run automation in financial services, what would your risk team need to see before an agent "
                 "touches production?"),
        "hooks": [("question", "Would your risk team sign off on an agent that can operate internal tools?"),
                  ("contrarian", "The most important feature in OpenAI's agent launch isn't the agent."),
                  ("observation", "Banks and insurers are piloting agents in the back office, and the audit log is the product.")],
        "claims": [("agents that operate internal tools, with audit logs and approval steps", 0),
                   ("Early customers include banks and insurers piloting back-office workflows", 0)],
        "format_note": "Could work as a 4-slide carousel: what launched, where approvals sit, audit logs, exceptions.",
    },
    "agentbench": {
        "text": ("41%.\n\n"
                 "That's how many back-office tasks the best LLM agent completed end to end in AgentBench-Enterprise, a "
                 "new benchmark of 1,200 tasks from finance and insurance operations.\n\n"
                 "The failures cluster around exception handling. Which is exactly where real automation projects live or "
                 "die: the missing field, the invoice in the wrong currency, the customer record that exists twice.\n\n"
                 "Two takeaways for anyone automating real work:\n"
                 "1. Evaluate agents on your exceptions, not your happy path. A demo that works on clean data tells you "
                 "almost nothing.\n"
                 "2. Design the handoff first. If an agent can't finish, who picks it up, with what context?\n\n"
                 "The number will go up. The question is whether your process is ready to catch the tasks that don't make it."),
        "hooks": [("number", "41% of back-office tasks: the best agent's score on a new enterprise benchmark."),
                  ("question", "What happens to the 59% of tasks an agent can't finish?"),
                  ("how-to", "How to read agent benchmarks if you automate real work:")],
        "claims": [("1,200 tasks from finance and insurance operations", 0), ("best agent completes 41% end to end", 0)],
        "format_note": "",
    },
    "anthropic raises": {
        "text": ("Anthropic raised $5 billion at a $183 billion valuation, and one number in the announcement matters more "
                 "than either: enterprise revenue is 80% of sales.\n\n"
                 "The model race gets the headlines. The buyer has quietly been decided. It's companies paying to put "
                 "models inside real workflows, with the controls that implies.\n\n"
                 "For people building automation, that's good news. Enterprise buyers ask the boring questions: audit, "
                 "access control, cost per task, what happens when it's wrong. Those questions shape the product.\n\n"
                 "Which of those questions does your organisation ask first?"),
        "hooks": [("number", "80% of Anthropic's sales now come from enterprise."),
                  ("observation", "The AI model race has quietly picked its customer."),
                  ("question", "Who is actually paying for AI models? The latest raise answers it.")],
        "claims": [("raised $5 billion", 0), ("valued at $183 billion", 0), ("enterprise revenue 80% of sales", 0)],
        "format_note": "",
    },
    "safety testing": {
        "text": ("Twenty-eight countries signed a framework for testing frontier AI models before they're deployed.\n\n"
                 "For most teams automating everyday work, nothing changes tomorrow. But the direction matters: testing "
                 "before deployment is becoming the expected default, not a nice-to-have.\n\n"
                 "That habit is worth borrowing well below the frontier. Before an automation goes live, can you show what "
                 "you tested, on which cases, and what you decided to leave to a human?\n\n"
                 "Regulators are writing that expectation down for the labs. Auditors will ask the rest of us the same "
                 "question soon enough."),
        "hooks": [("number", "28 countries just agreed on how to test frontier AI before it ships."),
                  ("observation", "Pre-deployment testing is becoming the default, and it won't stay at the frontier."),
                  ("question", "Could you show an auditor what you tested before your last automation went live?")],
        "claims": [("Twenty-eight countries signed a framework for pre-deployment testing of frontier AI models", 0)],
        "format_note": "",
    },
    "insurance claims": {
        "text": ("A Bengaluru startup automating insurance claims just raised $30 million in a Series B, and says claims "
                 "are processed 4x faster.\n\n"
                 "Claims is a revealing place for AI to land. It's document-heavy, rule-bound and full of exceptions, which "
                 "is exactly why RPA struggled there for years.\n\n"
                 "The question buyers should ask isn't \"how fast?\" It's \"4x faster on which claims?\" The simple ones were "
                 "already fast. The value is in the messy middle.\n\n"
                 "If you've evaluated claims automation, what did you measure?"),
        "hooks": [("number", "4x faster claims processing is the headline. The fine print is which claims."),
                  ("observation", "Insurance claims are becoming the proving ground for AI automation startups."),
                  ("question", "4x faster at what, exactly?")],
        "claims": [("raised $30 Mn in a Series B", 0), ("claims processed 4x faster", 0)],
        "format_note": "",
    },
    "yc's latest batch": {
        "text": ("Of 160 companies in Y Combinator's latest batch, roughly 105 build agents for specific business "
                 "workflows.\n\n"
                 "Two-thirds of a batch pointing the same way says something about where founders see revenue: not general "
                 "assistants, but narrow agents that own one workflow end to end.\n\n"
                 "That's also how enterprise automation has always worked. The wins come from depth in one process, not "
                 "breadth across many.\n\n"
                 "The hard part for all 105 will be the same: integration, exceptions, and earning trust from the people "
                 "whose work changes."),
        "hooks": [("number", "105 of 160 companies in YC's latest batch are building workflow agents."),
                  ("observation", "Founders have stopped building assistants and started building workflow owners."),
                  ("question", "What happens when two-thirds of a YC batch builds the same kind of company?")],
        "claims": [("Of 160 companies, roughly 105 build agents for specific business workflows", 0)],
        "format_note": "",
    },
    "automation anywhere": {
        "text": ("Automation Anywhere unveiled AI agents for finance operations, and UiPath is bringing agentic orchestration "
                 "to regulated industries.\n\n"
                 "The RPA vendors aren't being replaced by agents. They're becoming the place agents run.\n\n"
                 "That makes sense. They already own what agents lack: connectors into legacy systems, credential vaults, "
                 "audit trails and the relationships with operations teams.\n\n"
                 "The open question is pricing. Bots were licensed per bot. Agents do variable work. Whoever solves that "
                 "model first will shape how enterprises budget for automation."),
        "hooks": [("contrarian", "Agents aren't replacing RPA vendors. They're moving in."),
                  ("question", "Where will enterprise AI agents actually run?"),
                  ("observation", "Both big RPA vendors shipped agent features in the same week.")],
        "claims": [("Automation Anywhere unveils AI agents for finance operations", 0),
                   ("UiPath brings agentic orchestration to regulated industries", 1)],
        "format_note": "Could work as a poll: who will own enterprise agents: RPA vendors, model labs, or cloud platforms?",
    },
    "exception handling": {
        "text": ("A new paper measures how LLM agents recover from exceptions in invoice, KYC and claims workflows.\n\n"
                 "It's a welcome shift. Most agent evaluations reward finishing the task. Real operations reward knowing "
                 "when not to.\n\n"
                 "Good exception handling means three things: noticing something is off, stopping before the wrong action, "
                 "and handing over with enough context that a person can finish quickly.\n\n"
                 "Benchmarks that score those behaviours will tell us far more about production readiness than another "
                 "leaderboard of clean tasks."),
        "hooks": [("observation", "Finally, a benchmark for the part of automation that actually breaks."),
                  ("question", "Does your agent know when to stop?"),
                  ("how-to", "How to judge an agent in operations: watch what it does when something's wrong.")],
        "claims": [("agents recover from exceptions in invoice, KYC and claims workflows", 0)],
        "format_note": "",
    },
}

X_DRAFTS: dict[str, dict[str, Any]] = {
    "agent platform": {
        "x_reply": {"text": "The interesting part is the permission model: agents get scoped tools and every call is logged. That's what gets this past a bank's risk team, not the model.",
                    "reply_context": "Replies to posts announcing OpenAI's agent platform", "search_terms": ["OpenAI", "agent platform"]},
        "x_single": {"text": "OpenAI's agent platform ships with approval steps and audit logs. For banks and insurers, that's the product. The agent is the easy part."},
    },
    "agentbench": {
        "x_thread": {"posts": ["A new benchmark put LLM agents through 1,200 real back-office tasks from finance and insurance. The best one finished 41% end to end.",
                               "Where they fail: exception handling. The missing field, the duplicate record, the invoice in the wrong currency.",
                               "That's not a footnote. In operations, exceptions are most of the work. The happy path was automated years ago.",
                               "So if you're evaluating agents: test them on your exceptions, and design the handoff to a human before you design the agent."]},
    },
    "anthropic raises": {"x_single": {"text": "Anthropic: $5B raised, $183B valuation, and 80% of sales from enterprise. The AI model race has picked its customer."}},
    "uipath adds agentic": {"x_quote": {"text": "RPA vendors are turning into agent orchestrators: bots, agents and people in one governed workflow. The moat is the connectors and the audit trail, not the model.", "quote_source": 0}},
    "automation anywhere": {"x_single": {"text": "Automation Anywhere and UiPath both shipped agent features for finance and regulated ops this week. Agents aren't replacing RPA vendors. They're moving in."}},
    "show the evals": {"x_thread": {"posts": ["Why agent benchmark numbers don't survive production:",
                                              "Benchmarks use clean inputs. Production is duplicates, missing fields and rules nobody wrote down.",
                                              "Benchmarks reward finishing. Operations reward stopping at the right moment and handing over well.",
                                              "Evaluate on your own exceptions. That's the only number that transfers."]}},
    "small models": {"x_single": {"text": "Distilling tool-use traces into a 3B model recovered 90% of the teacher's accuracy. Small, cheap agents that run on-prem are getting real."}},
    "streamable http": {"x_single": {"text": "MCP's Python SDK v1.20 adds resumable streams and tightens OAuth for remote servers. Boring, and exactly what production MCP needs."}},
    "industrial corridors": {"x_thread": {"posts": ["Bihar plans three new industrial corridors along its expressways, the state's minister says.",
                                                    "The logic: put land, power and road access where freight already moves, instead of scattering industrial areas.",
                                                    "What to watch: land acquisition timelines, power supply commitments, and which industries actually sign up.",
                                                    "Corridors are announced often. Anchor investors are the real signal."]}},
    "chip packaging": {"x_single": {"text": "The Union Cabinet approved ₹12,000 crore in incentives for chip packaging units. Bihar is among the states seeking one. Worth watching who wins, and why."}},
    "safety testing": {"x_single": {"text": "Twenty-eight countries signed a framework for pre-deployment testing of frontier AI. Testing before shipping is becoming the default. Everyone else should borrow the habit."}},
    "stampede": {"x_single": {"text": "Officials say 12 people died and dozens were injured in a stampede at a railway station during the festival rush. Thoughts with the families."}},
    "simultaneous elections": {"x_single": {"text": "A parliamentary committee will hear constitutional experts next week on the simultaneous elections bills. The core question hasn't changed: efficiency vs federal accountability."}},
    "patna metro": {"x_single": {"text": "Patna Metro's priority corridor is set to open to passengers next month. The test comes after launch: frequency, last-mile links, and ridership."}},
    "legislative assembly": {"x_single": {"text": "On this day in 1952, the first session of the Bihar Legislative Assembly was convened in Patna."}},
    "insurance claims": {"x_single": {"text": "A Bengaluru AI startup raised $30M to automate insurance claims and says they're processed 4x faster. The real question: 4x faster on which claims?"}},
    "yc's latest batch": {"x_thread": {"posts": ["Of 160 companies in YC's latest batch, roughly 105 build agents for specific business workflows.",
                                                 "Not assistants. Workflow owners: one process, end to end.",
                                                 "That's how enterprise automation has always won: depth in one process beats breadth across many.",
                                                 "The shared hard part for all 105: integration, exceptions, and trust."]}},
}


def _key_for(text: str, table: dict[str, Any]) -> str | None:
    low = (text or "").casefold()
    for key in table:
        if key in low:
            return key
    return None


def _triage(req: LLMRequest, data: Any) -> Any:
    out = []
    for t in data if isinstance(data, list) else data.get("topics", []):
        title = f"{t.get('title', '')} {t.get('summary', '')}"
        key = _key_for(title, TRIAGE)
        if key is None:
            out.append({"id": t.get("id"), "summary_en": textutil.truncate(t.get("summary") or t.get("title"), 200),
                        "sensitive": False, "issue_key": None,
                        "linkedin": {"pillar": "none", "angle_potential": 1, "angle": ""},
                        "x": {"lane": "none", "angle_potential": 1, "angle": "", "format": "x_single"}})
            continue
        spec = TRIAGE[key]
        li, x = spec["linkedin"], spec["x"]
        out.append({
            "id": t.get("id"),
            "summary_en": textutil.truncate(t.get("summary") or t.get("title"), 200),
            "sensitive": key == "stampede",
            "sensitive_reason": "reports deaths in a stampede" if key == "stampede" else "",
            "issue_key": spec.get("issue"),
            "linkedin": {"pillar": li[0], "angle_potential": li[1], "angle": li[2], "format_note": ""},
            "x": {"lane": x[0], "angle_potential": x[1], "angle": x[3], "format": x[2],
                  "affairs_type": x[4] if len(x) > 4 else None},
        })
    return {"topics": out}


def _translate(req: LLMRequest, data: Any) -> Any:
    items = data if isinstance(data, list) else data.get("items", [])
    return {"items": [{"id": it.get("id"), "title_en": HINDI_TITLES.get(it.get("title", "").split(" - ")[0].strip(),
                                                                       "Bihar news (translated)"),
                       "summary_en": ""} for it in items]}


REQUEST_LINKEDIN = {
    "text": ("MCP servers are moving from demos to production, and the questions have changed.\n\n"
             "Enterprises are weighing MCP gateways to control what AI agents can reach, and remote MCP servers are "
             "adding OAuth support as adoption grows. An open-source gateway with per-tool permissions and audit logs "
             "drew a long discussion on Hacker News.\n\n"
             "The pattern is familiar from every integration wave: connect everything first, then work out who is "
             "allowed to do what.\n\n"
             "What a production MCP setup needs:\n"
             "- Per-tool permissions, not all-or-nothing access\n"
             "- Audit logs a risk team can read\n"
             "- An owner for every server, like any other integration\n\n"
             "If you're connecting agents to internal systems, which of these do you have today?"),
    "hooks": [("observation", "MCP servers are moving from demos to production, and the questions have changed."),
              ("question", "What does it take to run MCP servers in production?"),
              ("how-to", "What a production MCP setup needs, in three lines:")],
    "claims": [("Enterprises are weighing MCP gateways to control what AI agents can reach", 0),
               ("remote MCP servers are adding OAuth support", 1),
               ("An open-source gateway with per-tool permissions and audit logs", 2)],
}
REQUEST_X = {
    "x_single": {"text": "MCP is moving into production, and the questions are the usual ones: which tools can an agent "
                         "call, who approved it, and where's the log? Gateways with per-tool permissions are the next "
                         "layer."},
    "x_thread": {"posts": ["MCP servers are moving from demos to production. The questions have changed.",
                           "Enterprises are weighing gateways that control what agents can reach. Remote servers are "
                           "adding OAuth.",
                           "It's the familiar integration pattern: connect everything first, then work out who may do "
                           "what.",
                           "What a production setup needs: per-tool permissions, readable audit logs, and an owner for "
                           "every server."]},
}
REQUEST_QUERY = "MCP servers in production"


def _line_after(prompt: str, prefix: str) -> str:
    for line in prompt.splitlines():
        if line.strip().startswith(prefix):
            return line.strip()[len(prefix):].strip()
    return ""


def _draft(req: LLMRequest, data: Any) -> Any:
    title = data.get("topic") or ""
    platform, fmt = data.get("platform"), data.get("format")
    answers = data.get("questions_and_answers") or []
    if data.get("current_draft") and "Adapt this" not in req.prompt:
        return _rewrite(req, data)
    if answers:
        return _from_answers(data, answers)
    story = history.BY_TITLE.get(title.casefold())
    if story is not None:
        return history.compose(story, platform or "linkedin", fmt or "li_text", req.prompt)
    if title.casefold() == REQUEST_QUERY.casefold():
        if platform == "linkedin":
            return _li_out(REQUEST_LINKEDIN, data)
        return _x_out(REQUEST_X.get(fmt) or REQUEST_X["x_single"], fmt, REQUEST_LINKEDIN, data)
    topic = f"{title} {' '.join(s.get('title', '') for s in data.get('sources', [])[:2])}"
    if platform == "linkedin":
        key = _key_for(title, LINKEDIN) or _key_for(topic, LINKEDIN)
        if key:
            return _li_out(LINKEDIN[key], data)
    else:
        key = _key_for(title, X_DRAFTS) or _key_for(topic, X_DRAFTS)
        if key:
            variants = X_DRAFTS[key]
            return _x_out(variants.get(fmt) or next(iter(variants.values())), fmt, LINKEDIN.get(key, {}), data)
    return DEFAULT_HANDLERS["draft"](req, data)


def _li_out(d: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    n_sources = len(data.get("sources", []))
    return {"text": d["text"], "posts": [], "hook_type": d["hooks"][0][0],
            "hooks": [{"type": t, "text": x} for t, x in d["hooks"]],
            "claims": [{"text": c, "source": min(i, max(0, n_sources - 1))} for c, i in d["claims"]],
            "format_note": d.get("format_note", ""), "angle": data.get("angle") or ""}


def _x_out(d: dict[str, Any], fmt: str | None, li: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    hooks = [{"type": t, "text": textutil.truncate(x, 200)} for t, x in li.get("hooks", [])] or [
        {"type": "observation", "text": textutil.truncate(d.get("text") or d.get("posts", [""])[0], 180)},
        {"type": "question", "text": "What's the part of this most people will miss?"},
        {"type": "number", "text": textutil.truncate(data.get("topic", ""), 120)}]
    out = {"text": d.get("text", ""), "posts": d.get("posts", []), "hook_type": hooks[0]["type"], "hooks": hooks,
           "claims": [], "format_note": "", "angle": data.get("angle") or ""}
    if fmt == "x_thread" and not out["posts"]:
        out["posts"] = textutil.split_sentences(out["text"])[:4]
        out["text"] = ""
    if fmt != "x_thread" and not out["text"] and out["posts"]:
        out["text"] = textutil.truncate(" ".join(out["posts"][:2]), 270)
        out["posts"] = []
    if fmt == "x_reply":
        out["reply_context"] = d.get("reply_context", f"Replies to posts about {data.get('topic')}")
        out["search_terms"] = d.get("search_terms", textutil.sim_tokens(data.get("topic"))[:3])
    if fmt == "x_quote":
        out["quote_source"] = d.get("quote_source", 0)
    return out


def _rewrite(req: LLMRequest, data: dict[str, Any]) -> dict[str, Any]:
    """Revise the current draft the way the note and quick asks say: shorter, a sharper hook, and so on."""
    current = data.get("current_draft") or {}
    asks = f"{_line_after(req.prompt, 'Quick asks:')} {_line_after(req.prompt, 'His note:')}".casefold()
    hooks = [h for h in data.get("current_hooks") or [] if h]
    posts = [p for p in current.get("posts") or [] if p]
    text = current.get("text") or ""
    if posts:
        if "short" in asks and len(posts) > 3:
            posts = posts[:-1]
        if ("hook" in asks or "sharper" in asks) and len(hooks) > 1:
            posts[0] = hooks[1]
    else:
        paras = [p for p in text.split("\n\n") if p.strip()]
        if "short" in asks and len(paras) > 2:
            paras = [p for p in paras if not p.startswith("Bottom line:")]
            paras = [paras[0], *[_shorter(p) for p in paras[1:-1]], paras[-1]] if len(paras) > 3 else paras
        if ("hook" in asks or "sharper" in asks) and len(hooks) > 1:
            paras[0] = hooks[1]
        text = "\n\n".join(paras)
    kinds = ["observation", "question", "number"]
    return {"text": "" if posts else text, "posts": posts, "hook_type": "observation",
            "hooks": [{"type": kinds[i % 3], "text": h} for i, h in enumerate(hooks[:3])] or
                     [{"type": "observation", "text": textutil.opening(text or " ".join(posts))}],
            "claims": [], "format_note": "", "angle": data.get("angle") or ""}


def _shorter(paragraph: str) -> str:
    sentences = textutil.split_sentences(paragraph)
    return " ".join(sentences[:-1]) if len(sentences) > 1 else paragraph


def _from_answers(data: dict[str, Any], answers: list[dict[str, str]]) -> dict[str, Any]:
    said = [a["answer"].strip() for a in answers if a.get("answer", "").strip()]
    platform = data.get("platform")
    if platform == "x":
        text = textutil.truncate(said[0], 270) if said else ""
        return {"text": text, "posts": [], "hook_type": "story", "hooks": [
            {"type": "story", "text": textutil.truncate(said[0], 120) if said else ""},
            {"type": "observation", "text": "A small thing from this week."},
            {"type": "question", "text": "Anyone else?"}], "claims": [], "format_note": "", "angle": ""}
    body = "\n\n".join(said)
    return {"text": body.strip(), "posts": [], "hook_type": "story",
            "hooks": [{"type": "story", "text": textutil.truncate(said[0], 160) if said else ""},
                      {"type": "how-to", "text": "What production teaches about automation:"},
                      {"type": "question", "text": "What broke the first time your automation met real data?"}],
            "claims": [], "format_note": "", "angle": ""}


def _questions(req: LLMRequest, data: Any) -> Any:
    topic = data.get("topic") or ""
    low = topic.casefold()
    if "uipath" in low or "orchestration" in low:
        qs = [("When you've mixed bots and people in one process, where did the handoff go wrong first?",
               "A concrete story makes the post"),
              ("What would you need to see before letting an AI agent handle exceptions instead of a person?",
               "Your bar is the angle")]
    elif "evals" in low or "benchmark" in low:
        qs = [("What's one thing you check in an eval that public benchmarks don't?", "Your practice, not the paper's"),
              ("Have you seen a model look great in testing and struggle in production? What was different?",
               "The contrast carries the post")]
    elif "mcp" in low or "streamable" in low:
        qs = [("Have you wired up an MCP server? What was it for?", "Grounds the post in your build"),
              ("What was harder than the docs made it look?", "The honest detail people share")]
    else:
        qs = [("Where have you seen something like this play out in real work?", "Firsthand grounding"),
              ("What would you tell a team about to try it?", "A practical takeaway")]
    return {"questions": [{"q": q, "why": w} for q, w in qs],
            "angle": f"A practitioner's view on {textutil.truncate(topic, 70)}"}


EVERGREEN_SETS = [
    [("linkedin", "receipts", "The approval step nobody designs",
      "Why the sign-off step decides whether an automation ships",
      ["Think of an automation you shipped that needed a person to approve something. Where did that step slow "
       "things down?", "What would you design differently about that step today?"]),
     ("linkedin", "learning", "Testing an agent on messy data",
      "What happens when an agent meets real inputs instead of clean ones",
      ["What did you test an agent or model on recently, and what surprised you?",
       "What would you tell someone setting up their first eval?"]),
     ("linkedin", "receipts", "When a bot met a real exception",
      "The exception that taught more than the happy path",
      ["Describe an exception that broke an automation. How did the team find out?",
       "What check exists now because of it?"]),
     ("x", "life", "A Melbourne spring weekend", "Something small and real from the weekend",
      ["What did you do this weekend that you'd tell a friend about?"]),
     ("x", "life", "What you're reading this week", "A recommendation, with why",
      ["What are you reading or listening to this week, and why did you pick it?"]),
     ("x", "life", "Cooking from home", "Food, memory and distance",
      ["Did you cook something from home recently? What was it, and who taught you?"])],
    [("linkedin", "receipts", "The metric that changed a business team's mind",
      "One number can move a conversation more than a demo",
      ["Have you shown a business team a number that changed their mind about automation? What was it?",
       "Why did that number land when others didn't?"]),
     ("linkedin", "learning", "Wiring an agent to a real tool",
      "The practical gotchas of giving an agent access to something real",
      ["Have you connected an agent to a real tool or API recently? What broke first?",
       "What guardrail did you add afterwards?"]),
     ("linkedin", "receipts", "Explaining automation to the people whose work it changes",
      "Trust is built in the explanation, not the launch",
      ["How do you explain what a bot or agent does to people whose work it changes?",
       "What question from a business user stayed with you?"]),
     ("x", "life", "The festive season, far from home", "Keeping traditions in a new city",
      ["How do you mark the festive season when you're far from home?"]),
     ("x", "life", "One small habit, a year on", "Small habits, honestly",
      ["What small habit stuck this year, and why do you think it did?"]),
     ("x", "life", "Cricket this week", "A moment from the game",
      ["Did you watch any cricket this week? What moment stayed with you?"])],
]

REFLECTIONS = [
    {"summary": "Openings with a concrete figure were kept and filler lines were cut every time. Threads lost their "
                "recap post before posting.",
     "changes": [{"op": "add", "text": "On X, keep threads to three or four posts; cut the recap post.",
                  "platform": "x", "confidence": "medium", "reversal": "Threads of five or more get picked again."},
                 {"op": "add", "text": "Open LinkedIn research posts with the single most surprising figure from the "
                                       "source.", "platform": "linkedin", "pillar": "research", "confidence": "high",
                  "reversal": "Edit ratio on research posts rises above 35%."}],
     "experiments": [{"platform": "linkedin", "pillar": "industry",
                      "instruction": "End with one specific question for people who run operations, not a general "
                                     "one.", "hypothesis": "Specific questions draw more comments from practitioners."}],
     "proposals": [{"kind": "pillar_weights", "title": "Give X affairs a little more room (30% → 35%)",
                    "detail": "Bihar development posts were picked on most days they were offered.",
                    "patch": {"strategy": {"x": {"affairs": {"weight": 0.35}, "tech": {"weight": 0.3}}}},
                    "confidence": "medium"}]},
    {"summary": "Edits fell sharply once filler and summary lines stopped appearing. Research posts with a figure in "
                "the first line drew the most comments on LinkedIn.",
     "changes": [{"op": "add", "text": "When a post covers a survey, say how many were surveyed in the first two lines.",
                  "platform": "linkedin", "confidence": "medium",
                  "reversal": "Survey posts get skipped two weeks running."}],
     "experiments": [{"platform": "x", "pillar": "affairs",
                      "instruction": "Lead Bihar tracker posts with the next concrete milestone and its date.",
                      "hypothesis": "Milestones get more replies than summaries."}],
     "proposals": [{"kind": "pillar_weights", "title": "Give X affairs a little more room (30% → 35%)",
                    "detail": "Asked again: Bihar tracker posts were picked on most days they were offered and drew "
                              "the most replies of any lane.",
                    "patch": {"strategy": {"x": {"affairs": {"weight": 0.35}, "tech": {"weight": 0.3}}}},
                    "confidence": "high"}]},
    {"summary": "Edit ratio fell for the third week running. Threads now go out as drafted, and LinkedIn edits are "
                "mostly small word changes.",
     "changes": [{"op": "add", "text": "On LinkedIn, keep each paragraph to one idea and at most three sentences.",
                  "platform": "linkedin", "confidence": "medium", "reversal": "Posts start getting longer edits."}],
     "experiments": [{"platform": "linkedin", "pillar": "research",
                      "instruction": "For benchmark results, try a short numbered list of the three key figures.",
                      "hypothesis": "Lists make results easier to scan and save."}],
     "proposals": [{"kind": "slots", "title": "Deliver 5 X cards instead of 6",
                    "detail": "The sixth X card was opened on only 2 of the last 14 days. Fewer, better cards save "
                              "time each morning.",
                    "patch": {"platforms": {"x": {"slots": 5}}}, "confidence": "medium"}]},
]


def _voice(req: LLMRequest, data: Any) -> Any:
    return {"rules": ["Open with the concrete detail, not the context.",
                      "Cut filler sentences that announce importance instead of showing it.",
                      "End on the point or one specific question, never a summary line."],
            "summary": "You cut filler and closing summaries, and you keep openings that lead with a figure."}


def demo_handlers() -> dict[str, Any]:
    """Fresh handlers for one demo build (the weekly batch and reflection rotate through their variants)."""
    calls = {"evergreen": 0, "reflect": 0}

    def evergreen(req: LLMRequest, data: Any) -> Any:
        chosen = EVERGREEN_SETS[calls["evergreen"] % len(EVERGREEN_SETS)]
        calls["evergreen"] += 1
        return {"topics": [{"platform": pl, "pillar": pillar, "title": title, "angle": angle, "mode": "interview",
                            "questions": [{"q": q, "why": "Your own experience is the post"} for q in qs]}
                           for pl, pillar, title, angle, qs in chosen]}

    def reflect(req: LLMRequest, data: Any) -> Any:
        out = REFLECTIONS[min(calls["reflect"], len(REFLECTIONS) - 1)]
        calls["reflect"] += 1
        posts = [p["id"] for p in data.get("posts", [])] if isinstance(data, dict) else []
        changes = [{**c, "evidence": posts[i * 2:i * 2 + 3]} for i, c in enumerate(out["changes"])]
        return {**out, "changes": changes}

    return {"triage": _triage, "translate": _translate, "draft": _draft, "draft_personal": _draft,
            "questions": _questions, "reflect": reflect, "voice": _voice, "evergreen": evergreen}
