"""Stories for the demo's past three weeks, and how the demo model drafts them.

The drafts obey what the real pipeline has learned: the demo model reads the avoid list, style rules and
hook preferences from the actual prompt, so as the voice profile and playbook learn from Ankit's edits,
the drafts need fewer edits. That makes the demo's falling edit ratio an honest product of the learning
loop, not a scripted number.

Every figure in a draft appears in the story's `fact` (the source summary), so the unsourced-number check
stays quiet unless something is genuinely wrong. Nothing here claims an experience for Ankit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .. import ids, textutil


@dataclass(frozen=True)
class Story:
    title: str
    fact: str
    publisher: str
    scout: str
    x_lane: str
    li_pillar: str | None = None
    hooks: dict[str, str] = field(default_factory=dict)
    so: str = ""
    ask: str = ""
    x: str = ""
    thread: tuple[str, ...] = ()
    affairs_type: str | None = None
    tier: str | None = None

    @property
    def angle(self) -> str:
        return textutil.truncate(self.so.split(". ")[0].rstrip("."), 110) if self.so else ""


def _full(title: str, fact: str, pub: str, li: str, lane: str, hooks: dict[str, str], so: str, ask: str, x: str,
          thread: tuple[str, ...] = ()) -> Story:
    return Story(title=title, fact=fact, publisher=pub, scout="startups" if lane == "startups" else "tech",
                 x_lane=lane, li_pillar=li, hooks=hooks, so=so, ask=ask, x=x, thread=thread)


def _affairs(title: str, fact: str, pub: str, tier: str, kind: str, x: str, thread: tuple[str, ...] = ()) -> Story:
    return Story(title=title, fact=fact, publisher=pub, scout="affairs", x_lane="affairs", x=x, thread=thread,
                 affairs_type=kind, tier=tier)


def _startup(title: str, fact: str, pub: str, x: str) -> Story:
    return Story(title=title, fact=fact, publisher=pub, scout="startups", x_lane="startups", x=x)


FULL: list[Story] = [
    _full("Open benchmark tests document AI on forms in 14 Indian languages",
          "Researchers released a benchmark of 9,000 scanned forms in 14 Indian languages. The best model extracted "
          "78% of fields correctly, falling to 52% on handwritten entries.",
          "Research Digest", "research", "tech",
          {"number": "52%: how often the best model read handwritten Indian-language forms correctly.",
           "question": "Would your document pipeline survive a handwritten form in two scripts?",
           "observation": "Document AI benchmarks finally look like Indian paperwork."},
          "Most document AI demos use clean, typed English PDFs. Real back offices get handwriting, stamps and "
          "three languages on one page.",
          "If you process forms at scale, which of these cases would break your pipeline first?",
          "A new benchmark of 9,000 scanned forms in 14 Indian languages: the best model gets 78% of fields right, "
          "and 52% on handwriting. Handwriting is the last mile of document AI."),
    _full("Agents that can pause and ask for help make far fewer costly errors, study finds",
          "Researchers compared agents that can pause to ask a person with agents that can't, on 600 simulated "
          "operations tasks. Agents with a pause step made 60% fewer costly errors and asked for help on 1 in 8 tasks.",
          "AI Research Roundup", "research", "tech",
          {"number": "Letting an agent ask for help on 1 in 8 tasks cut its costly errors by 60%.",
           "contrarian": "The most useful agent feature isn't autonomy. It's the pause button.",
           "question": "When should an agent stop and ask?"},
          "The design choice that matters isn't how autonomous an agent is. It's whether it knows when to stop, and "
          "who it hands the task to.",
          "Where would you put the 'ask a person' step in your workflows?",
          "Agents with a 'pause and ask' step made 60% fewer costly errors across 600 operations tasks, while asking "
          "for help on 1 in 8. Knowing when to stop is a feature.",
          ("A study compared agents that can pause to ask a person with agents that can't, across 600 simulated "
           "operations tasks.",
           "Result: the agents with a pause step made 60% fewer costly errors. They asked for help on 1 in 8 tasks.",
           "That's the trade most teams should want: a little human time for a big drop in expensive mistakes.",
           "Design the handoff first. Autonomy is the easy part to add later.")),
    _full("LLM reviewers match human reviewers 81% of the time on process documentation",
          "A study of 1,500 process documents found LLM-based reviewers matched human pass/fail decisions 81% of "
          "the time, but missed most errors in exception-handling sections.",
          "Research Digest", "research", "tech",
          {"number": "LLM reviewers agreed with people 81% of the time. The misses are where the risk lives.",
           "question": "Would you let a model sign off on your process documentation?",
           "observation": "Automated review is good at the routine parts and weak exactly where it matters."},
          "The misses cluster in exception handling, the part of a process document that auditors and operators "
          "actually rely on.",
          "Would you let a model sign off on process documentation, or only pre-screen it?",
          "LLM reviewers matched human decisions on 81% of 1,500 process documents. The misses were concentrated in "
          "exception handling, the part that matters most."),
    _full("A small open model matches much larger ones at invoice matching after fine-tuning",
          "A team fine-tuned a 7B open-weights model on 40,000 invoice-to-purchase-order matches. It reached 94% "
          "accuracy, level with much larger general models, at a fraction of the inference cost.",
          "ML Engineering Weekly", "research", "tech",
          {"number": "A 7B model, 40,000 examples, 94% accuracy on invoice matching.",
           "observation": "For narrow back-office tasks, small tuned models are catching up with the giants.",
           "question": "Which of your automations is narrow enough for a small model?"},
          "For narrow, high-volume back-office work, a small tuned model can match a big general one on accuracy "
          "while costing far less to run.",
          "Which of your automations is narrow enough to try a small model?",
          "A 7B open model fine-tuned on 40,000 invoice matches hit 94% accuracy, level with much larger models, at a "
          "fraction of the cost. Narrow tasks don't need giant models."),
    _full("Benchmark tests how automation copes with changing web interfaces",
          "A new benchmark replays 300 web workflows after interface changes such as moved buttons and renamed "
          "fields. Agents that read the page recovered in 70% of cases; selector-based bots recovered in 12%.",
          "Research Digest", "research", "tech",
          {"number": "Move a button, and selector-based bots recovered only 12% of the time.",
           "question": "How much of your automation budget goes on fixing bots after UI changes?",
           "observation": "The oldest RPA problem just got a benchmark."},
          "This is the classic RPA maintenance problem in new clothes. Recovering from interface changes may be "
          "where agents earn their keep first.",
          "How much of your team's time goes on fixing bots after an application update?",
          "Moved buttons, renamed fields: selector-based bots recovered in 12% of 300 changed workflows. Agents that "
          "read the page recovered in 70%. Maintenance is where agents may win first.",
          ("A new benchmark replays 300 web workflows after the interface changes: moved buttons, renamed fields.",
           "Selector-based bots recovered in 12% of cases. Agents that read the page recovered in 70%.",
           "Anyone who has maintained RPA bots knows why this matters: the build is cheap, the upkeep isn't.",
           "If agents cut the upkeep, that's the business case, more than any demo.")),
    _full("Better retrieval beats bigger models for policy-document Q&A",
          "Across 2,000 questions on insurance policy documents, improving retrieval raised answer accuracy from 64% "
          "to 85%, while switching to a larger model added 3 points.",
          "Applied AI Letter", "research", "tech",
          {"number": "Better retrieval: 64% to 85%. A bigger model: 3 more points.",
           "question": "Is your team tuning the model or the retrieval?",
           "contrarian": "Most RAG projects work on the wrong half of the system."},
          "Most teams reach for a bigger model first. The evidence keeps saying the retrieval layer is where the "
          "accuracy is.",
          "Where does your team spend its time: the model or the retrieval?",
          "On 2,000 insurance-policy questions, better retrieval took accuracy from 64% to 85%. A bigger model added "
          "3 points. Fix the retrieval first."),
    _full("Survey of enterprise agent pilots finds an unclear handoff is the top failure",
          "A survey of 120 enterprise agent pilots grouped failures into five types. An unclear handoff to people was "
          "the most common, cited in 46% of failed pilots.",
          "Enterprise AI Review", "research", "tech",
          {"number": "46% of failed agent pilots had the same problem: nobody owned the handoff.",
           "question": "When your agent gets stuck, who owns the task?",
           "observation": "Agent pilots aren't failing on model quality."},
          "Not model quality, not cost. When the agent gets stuck, nobody knows who owns the task or what context "
          "they'll get.",
          "Who owns the task in your process when an agent gets stuck?",
          "A survey of 120 enterprise agent pilots: the top failure, in 46% of failed pilots, was an unclear handoff "
          "to people. Design the handoff before the agent."),
    _full("Synthetic test data overstates agent accuracy, study finds",
          "Evaluating agents on synthetic data overstated production accuracy by an average of 18 points across 12 "
          "workflows, mostly because synthetic cases lacked duplicates and missing fields.",
          "Research Digest", "research", "tech",
          {"number": "Synthetic test data overstated agent accuracy by 18 points.",
           "question": "Does your test set include your messiest real cases?",
           "observation": "Clean test data measures the demo, not the job."},
          "The gap came from exactly the things real operations are full of: duplicates, missing fields and odd "
          "formats.",
          "Does your evaluation set include your messiest real cases?",
          "Across 12 workflows, synthetic test data overstated agent accuracy by 18 points. The missing ingredient: "
          "duplicates and missing fields. Test on real mess."),
    _full("Long-context models still miss clauses buried in the middle of contracts",
          "Tested on 500 commercial contracts, long-context models found clauses near the start and end reliably but "
          "missed about 1 in 4 clauses placed in the middle.",
          "Legal Tech Review", "research", "tech",
          {"number": "Long-context models missed about 1 in 4 clauses buried mid-contract.",
           "question": "Would you trust one model pass over a long contract?",
           "observation": "A bigger context window isn't the same as careful reading."},
          "A bigger context window isn't the same as careful reading. Chunking, checklists and a second pass still "
          "matter.",
          "Would you trust a single model pass over a long contract?",
          "Tested on 500 contracts, long-context models missed about 1 in 4 clauses in the middle of the document. "
          "Big context windows still need checklists."),
    _full("Tool-calling accuracy drops sharply as agents get more tools",
          "A function-calling benchmark found accuracy fell from 92% with 5 tools available to 61% with 50, as models "
          "picked plausible but wrong tools.",
          "AI Research Roundup", "research", "tech",
          {"number": "92% with 5 tools. 61% with 50.",
           "contrarian": "Giving an agent every tool isn't generous. It's confusing.",
           "question": "How many tools does your agent need?"},
          "Giving an agent every tool isn't generous, it's confusing. Scoping tools per task matters as much as the "
          "model.",
          "How many tools does your agent have, and how many does it need?",
          "Function-calling accuracy: 92% with 5 tools, 61% with 50. Scope your agent's tools per task."),
    _full("Open Hinglish speech benchmark exposes gaps in call-centre transcription",
          "A new open benchmark of 400 hours of Hindi-English call-centre audio found commercial speech models' word "
          "error rate rose from 8% on English to 21% on code-switched speech.",
          "Research Digest", "research", "tech",
          {"number": "Speech models: 8% word error rate in English, 21% on Hinglish.",
           "question": "Does your voice automation understand how customers actually talk?",
           "observation": "Code-switching is the default in Indian customer calls, and models still stumble on it."},
          "Customers don't pick one language per call. Voice automation for Indian markets has to be tested on the "
          "way people actually speak.",
          "Have you tested your voice bots on code-switched speech?",
          "400 hours of Hindi-English call-centre audio: speech models went from 8% word error rate on English to "
          "21% on Hinglish. Test on how people actually talk."),
    _full("Review queues, not models, cap automation throughput, study finds",
          "An analysis of 30 automated workflows found that human review queues caused 70% of end-to-end delays, "
          "while model processing time accounted for under 5%.",
          "Operations Research Notes", "research", "tech",
          {"number": "70% of automation delays came from review queues. Model time: under 5%.",
           "question": "Where does your automation actually wait?",
           "contrarian": "Faster models won't speed up your automation."},
          "Faster models won't fix a process that waits on people. Designing the review step is the throughput "
          "lever.",
          "Have you measured where your automations actually wait?",
          "Across 30 automated workflows, human review queues caused 70% of delays. Model time: under 5%. Design the "
          "review step, not just the model."),
    _full("Most banks are piloting AI agents, but few run them in production",
          "A survey of 210 banks found 62% are piloting AI agents, but only 9% run one in production. Governance "
          "approval was the top blocker.",
          "Banking Technology Survey", "industry", "tech",
          {"number": "62% of banks are piloting AI agents. 9% run one in production.",
           "question": "What's the first document your risk team asks for?",
           "observation": "The gap between pilot and production in banking isn't technical."},
          "The gap isn't technology. It's the approval path: who signs off, on what evidence, and what happens when "
          "the agent is wrong.",
          "What's the first document your risk team asks for?",
          "62% of 210 banks are piloting AI agents. 9% run one in production. The blocker is governance approval, "
          "not the model.",
          ("A survey of 210 banks: 62% are piloting AI agents. Only 9% run one in production.",
           "The top blocker isn't the technology. It's governance approval.",
           "Getting to production means answering unglamorous questions well: who signs off, on what evidence, what "
           "happens when it's wrong.",
           "The teams that write those answers down first will be the ones in production next year.")),
    _full("AI halves claims routing time, but payouts aren't faster, report finds",
          "An industry report on 40 insurers found AI triage cut the time to route claims by half, while average time "
          "to payout barely changed because approvals stayed manual.",
          "Insurance Industry Report", "industry", "tech",
          {"observation": "AI halved claims routing time. Payouts didn't get any faster.",
           "question": "Where's the real bottleneck in your process?",
           "how-to": "How to find the bottleneck before you automate:"},
          "Speeding up one step doesn't speed up the process when the bottleneck is somewhere else. Map the whole "
          "flow first.",
          "Where's the real bottleneck in your process?",
          "Across 40 insurers, AI cut claims routing time by half. Time to payout barely moved, because approvals "
          "stayed manual. Automate the bottleneck, not the easy step."),
    _full("Cloud providers cut batch AI inference prices by up to 50%",
          "Two major cloud providers cut prices for batch, non-real-time AI inference by up to 50%, aimed at "
          "overnight document and data-processing jobs.",
          "Cloud Computing News", "industry", "tech",
          {"number": "Batch AI inference just got up to 50% cheaper.",
           "question": "Which of your AI workloads could run overnight?",
           "observation": "Most back-office AI doesn't need an instant answer."},
          "Most back-office automation doesn't need an instant answer. It needs one by the morning, at the lowest "
          "cost.",
          "Which of your AI workloads could run overnight?",
          "Batch AI inference is now up to 50% cheaper at two major clouds. Most back-office work doesn't need an "
          "instant answer, just one by morning."),
    _full("Enterprise vendors move AI agents to per-task pricing",
          "Several enterprise software vendors announced pricing per resolved task for their AI agents, replacing "
          "per-seat licences in their service products.",
          "Enterprise Software News", "industry", "tech",
          {"observation": "Enterprise AI is moving from per-seat to per-task pricing.",
           "question": "Would per-task pricing change how you budget for automation?",
           "contrarian": "Per-seat pricing never made sense for software that does the work."},
          "Per-task pricing makes the business case easy to compare with the manual cost. It also makes an agent "
          "that doesn't finish tasks hard to hide.",
          "Would per-task pricing change how you budget for automation?",
          "Enterprise vendors are pricing AI agents per resolved task instead of per seat. Easier to compare with "
          "manual cost, and harder to hide an agent that doesn't finish."),
    _full("Companies fold RPA centres of excellence into AI teams",
          "A report on 150 large companies found 38% merged their RPA centre of excellence into a broader AI or data "
          "team in the past year.",
          "Automation Industry Report", "industry", "tech",
          {"number": "38% of large companies folded their RPA centre of excellence into an AI team.",
           "observation": "The RPA centre of excellence is quietly becoming the AI team.",
           "question": "Is your automation team in the AI conversation?"},
          "The skills that made RPA work, process mapping, exception handling and change management, are exactly "
          "what many AI projects are missing.",
          "Is your automation team part of the AI conversation?",
          "38% of 150 large companies merged their RPA centre of excellence into an AI team this year. Process "
          "mapping and exception handling are exactly what AI projects lack."),
    _full("Open-weights model comes within 4 points of the frontier on coding",
          "A new open-weights model scored within 4 points of leading closed models on a popular coding benchmark and "
          "is licensed for commercial use.",
          "AI Model Tracker", "industry", "tech",
          {"number": "An open-weights model is now within 4 points of the frontier on coding.",
           "question": "Does running models in-house change what you'd automate?",
           "observation": "The gap between open and closed models keeps shrinking."},
          "For regulated teams that need to run models in their own environment, the trade-off between control and "
          "capability just got smaller.",
          "Would running models in-house change what you'd automate?",
          "A commercially licensed open-weights model is within 4 points of the best closed models on coding. For "
          "regulated teams, that's the story."),
    _full("Data centres could use about 3% of global electricity by 2030",
          "An energy agency report estimated data centres could use about 3% of global electricity by 2030, with AI "
          "the fastest-growing share of demand.",
          "Energy Policy Report", "industry", "tech",
          {"number": "Data centres could use about 3% of the world's electricity by 2030.",
           "question": "Does energy cost show up in your AI business cases?",
           "observation": "Compute and energy will decide which AI use cases pay off."},
          "Compute cost and energy will shape which AI use cases are worth doing, not just which ones are possible.",
          "Does energy cost show up in your AI business cases yet?",
          "Data centres could use about 3% of global electricity by 2030, with AI growing fastest. Energy is becoming "
          "part of the AI business case."),
    _full("IT leaders report duplicate AI agents doing the same job",
          "A survey of IT leaders found the average large company runs 14 separate AI agent projects, and 41% "
          "reported duplicate agents doing the same job.",
          "CIO Survey", "industry", "tech",
          {"number": "41% of IT leaders found duplicate AI agents doing the same job.",
           "observation": "Agent sprawl is RPA sprawl all over again.",
           "question": "Does anyone in your organisation know how many agents are running?"},
          "Same pattern as early RPA: easy to build, hard to govern. Agent registries and clear ownership come next.",
          "Does anyone in your organisation know how many agents are running?",
          "The average large company runs 14 AI agent projects, and 41% of IT leaders found duplicates doing the same "
          "job. Agent sprawl is RPA sprawl again."),
    _full("Payments network cuts dispute handling time with AI drafts and human sign-off",
          "A payments network said an AI pilot drafts responses to merchant disputes, with staff approving each one. "
          "Approval time fell from 20 minutes to 6.",
          "Payments Industry News", "industry", "tech",
          {"number": "Dispute responses went from 20 minutes to 6, with a person still approving every one.",
           "question": "Where could 'AI drafts, a person approves' work in your team?",
           "observation": "Keeping people in the loop didn't kill the gains. It made them deployable."},
          "Keeping a person in the loop didn't kill the gains. It's what made the pilot deployable in a regulated "
          "business.",
          "Where could 'AI drafts, a person approves' work in your team?",
          "A payments network's AI drafts dispute responses and staff approve each one. Time per dispute: 20 minutes "
          "to 6. Human sign-off made it deployable."),
    _full("Bank uses AI to turn legacy code into readable specifications",
          "A bank reported using AI tools to turn 1.2 million lines of COBOL into readable specifications, cutting a "
          "discovery phase from 9 months to 4.",
          "Banking Technology News", "industry", "tech",
          {"number": "1.2 million lines of COBOL, turned into readable specs.",
           "observation": "The first job for AI in legacy modernisation isn't rewriting code. It's explaining it.",
           "question": "How much of your legacy system is documented?"},
          "The first job for AI in legacy modernisation isn't rewriting the code. It's explaining what the code does, "
          "so people can decide what to keep.",
          "How much of your legacy estate is actually documented?",
          "A bank used AI to turn 1.2 million lines of COBOL into readable specs, cutting discovery from 9 months to "
          "4. Explaining legacy code comes before rewriting it."),
    _full("Browsers add built-in agents that can fill forms",
          "Two major browsers announced built-in agents that can fill web forms and complete purchases after the user "
          "confirms.",
          "Tech Daily", "industry", "tech",
          {"observation": "Form-filling used to be RPA's bread and butter. Now it's a browser feature.",
           "question": "Who's accountable when a browser agent submits the wrong form?",
           "contrarian": "Browser agents are an audit problem before they're a productivity win."},
          "It raises new questions about audit and identity: which person, which session, which data, and who checks "
          "the result.",
          "Who's accountable when a browser agent submits the wrong form?",
          "Two major browsers now ship agents that fill forms and complete purchases after you confirm. Form-filling "
          "was RPA's bread and butter. Audit and identity questions come next."),
    _full("AI lab adds click-by-click audit logs to its computer-use agent",
          "A leading AI lab added audit logs and admin controls to its computer-use agent for enterprise customers, "
          "recording every click and keystroke for review.",
          "Tech Daily", "industry", "tech",
          {"observation": "Every click and keystroke, logged for review.",
           "question": "What would your auditors want to see in an agent's log?",
           "contrarian": "The most important agent feature this month is a log file."},
          "Audit logs are becoming the price of entry for agents in the enterprise, and they're what risk teams have "
          "been asking for.",
          "What would your auditors want to see in an agent's log?",
          "Computer-use agents now come with click-by-click audit logs and admin controls for enterprises. The log is "
          "the feature that gets agents approved."),
    _full("Developers say review is now the bottleneck as AI writes more code",
          "A developer survey of 9,000 respondents found AI tools write about 30% of new code, and 58% said review "
          "has become the bottleneck.",
          "Developer Survey", "industry", "tech",
          {"number": "AI writes about 30% of new code. 58% of developers say review is now the bottleneck.",
           "observation": "Generation got cheap. Verification didn't.",
           "question": "Is review the bottleneck in your team too?"},
          "Generation got cheap. Verification didn't. It's the same pattern in automation: building bots is easy, "
          "trusting them is the work.",
          "Is review the bottleneck in your team too?",
          "Survey of 9,000 developers: AI writes about 30% of new code, and 58% say review is now the bottleneck. "
          "Generation got cheap. Verification didn't."),
    _full("MCP registry launches with over 1,000 tool servers",
          "An open registry for Model Context Protocol servers launched with over 1,000 listed servers and "
          "verification badges for publishers.",
          "Developer News", "industry", "tech",
          {"number": "Over 1,000 MCP servers, now in one registry.",
           "question": "How would you vet an MCP server before connecting it?",
           "observation": "Discovery for agent tools is solved. Trust isn't."},
          "Discovery is solved. Trust isn't: which of these servers would you let near production data, and on whose "
          "say-so?",
          "How would you vet an MCP server before connecting it?",
          "An open MCP registry launched with over 1,000 servers and publisher verification. Finding tools is easy "
          "now. Deciding which to trust is the work."),
    _full("Utilities hand after-hours outage calls to AI voice agents",
          "Two utilities reported AI voice agents now handle after-hours outage calls, resolving 70% without a person "
          "and escalating the rest with a summary.",
          "Utility Industry News", "industry", "tech",
          {"number": "70% of after-hours outage calls, resolved without a person.",
           "observation": "The escalation summary is the underrated part.",
           "question": "What makes a good handoff from an agent to a person?"},
          "The escalation summary is the underrated part: the person who picks up the call doesn't start from zero.",
          "What makes a good handoff from an agent to a person?",
          "Two utilities' AI voice agents now resolve 70% of after-hours outage calls and escalate the rest with a "
          "summary. The summary is the underrated feature."),
    _full("Indian AI startups raise a record $1.1 billion in a quarter",
          "Indian AI startups raised $1.1 billion last quarter, the highest on record, led by enterprise automation "
          "and vertical AI companies.",
          "Startup Funding Tracker", "industry", "startups",
          {"number": "Indian AI startups raised $1.1 billion last quarter, a record.",
           "observation": "The money is going to unglamorous, specific problems.",
           "question": "Which unglamorous problem would you fund?"},
          "The money is going to unglamorous, specific problems like claims, collections and compliance. That's a "
          "healthy sign for the ecosystem.",
          "Which unglamorous problem would you fund?",
          "Indian AI startups raised a record $1.1 billion last quarter, led by enterprise automation and vertical AI. "
          "Specific problems are getting funded."),
    _full("Startup prices its accounts-payable agent at ₹4 per invoice",
          "A startup launched an accounts-payable agent priced at ₹4 per invoice processed, targeting mid-size Indian "
          "companies.",
          "Startup News", "industry", "startups",
          {"number": "₹4 per invoice: AI accounts payable, priced like a utility.",
           "observation": "Per-unit pricing makes the comparison with manual work simple.",
           "question": "What would a finance team need to see before switching?"},
          "Per-unit pricing makes the comparison with manual processing simple. The harder sell is trust in the "
          "exceptions.",
          "What would a finance team need to see before switching?",
          "An accounts-payable agent at ₹4 per invoice, aimed at mid-size Indian companies. Pricing per unit makes "
          "the ROI maths simple. Exceptions are the real sell."),
    _full("Startup open-sources its evaluation suite for support agents",
          "A startup open-sourced the evaluation harness it used internally for 2 years, with 400 test scenarios for "
          "customer-support agents.",
          "Developer News", "industry", "startups",
          {"number": "400 test scenarios for support agents, now open source.",
           "question": "Would you adopt someone else's eval suite, or build your own?",
           "observation": "Evaluation is the moat nobody talks about."},
          "Evaluation is the moat nobody talks about. Sharing it is a confident move, and a useful starting point for "
          "everyone else.",
          "Would you adopt someone else's eval suite, or build your own?",
          "A startup open-sourced its internal eval harness: 400 test scenarios for customer-support agents. Evals are "
          "the moat nobody talks about."),
    _full("Melbourne startup raises A$12 million to automate construction compliance",
          "A Melbourne startup raised A$12 million to automate compliance paperwork for construction firms, reading "
          "permits and inspection reports.",
          "Australian Startup News", "industry", "startups",
          {"number": "A$12 million to automate construction paperwork, from Melbourne.",
           "observation": "Some of the best AI businesses will be in industries nobody calls tech.",
           "question": "Which unglamorous industry is next?"},
          "Some of the best AI businesses will be in industries nobody calls tech, where paperwork is heavy and "
          "margins are thin.",
          "Which unglamorous industry is next?",
          "A Melbourne startup raised A$12 million to read permits and inspection reports for builders. The best AI "
          "businesses may be in industries nobody calls tech."),
    _full("Collections startup reports fewer complaints after adding AI call summaries",
          "A debt-collection software startup said customer complaints fell 30% after its AI began summarising every "
          "call for human agents and flagging hardship cases.",
          "Fintech News", "industry", "startups",
          {"number": "Complaints down 30% after AI started flagging hardship cases.",
           "observation": "The best use of AI in collections might be slowing down.",
           "question": "Where would an early warning flag change outcomes in your process?"},
          "The best use of AI in collections might be knowing when to slow down: flagging hardship early protects "
          "customers and the business.",
          "Where would an early warning flag change outcomes in your process?",
          "A collections startup says complaints fell 30% after its AI began summarising calls and flagging hardship "
          "cases. Sometimes the win is knowing when to slow down."),
    _full("Workflow-specific AI startups close enterprise deals faster than general assistants",
          "A venture firm's analysis of 300 enterprise AI deals found vertical, workflow-specific startups closed "
          "deals 2x faster than horizontal assistant products.",
          "Venture Research", "industry", "startups",
          {"number": "Workflow-specific AI startups closed enterprise deals 2x faster.",
           "observation": "Enterprises are buying outcomes, not assistants.",
           "question": "Would you buy a general assistant or a tool for one workflow?"},
          "Enterprises are buying outcomes in one workflow, not general assistants that need a use case found for "
          "them.",
          "Would your organisation buy a general assistant or a tool for one workflow?",
          "Across 300 enterprise AI deals, workflow-specific startups closed 2x faster than general assistants. "
          "Enterprises buy outcomes."),
    _full("Researchers show prompt injection risks in document-processing agents",
          "Security researchers showed that hidden text in 1 of 20 test invoices could redirect a document-processing "
          "agent to change payment details, unless outputs were validated against source systems.",
          "Security Research", "research", "tech",
          {"observation": "Hidden text in an invoice can redirect a document agent.",
           "question": "Does your agent validate its outputs against the system of record?",
           "how-to": "How to stop a document agent from being redirected:"},
          "Validation against the system of record, not smarter prompts, is what stopped the attack. The old "
          "controls still matter.",
          "Does your agent check its outputs against the system of record?",
          "Researchers hid instructions in 1 of 20 test invoices and redirected a document agent to change payment "
          "details. The fix: validate outputs against the source system."),
    _full("AI meeting notes miss decisions more than action items, study finds",
          "A study of 250 recorded business meetings found AI note-takers captured 90% of action items but only 65% "
          "of decisions and their reasons.",
          "Workplace Research", "research", "tech",
          {"number": "AI note-takers caught 90% of action items, but only 65% of decisions.",
           "observation": "The 'why' is what AI notes miss.",
           "question": "Do your meeting notes record why a decision was made?"},
          "The reasons behind a decision are exactly what teams need later, and exactly what automated notes drop.",
          "Do your meeting notes record why a decision was made?",
          "AI note-takers captured 90% of action items across 250 meetings, but only 65% of decisions and their "
          "reasons. The 'why' is what gets lost."),
    _full("Benchmark measures how well agents follow business rules written in plain English",
          "A benchmark of 1,000 business rules written in plain English found agents followed simple rules 95% of "
          "the time, but only 58% of rules with exceptions such as 'unless' clauses.",
          "Research Digest", "research", "tech",
          {"number": "Agents followed 95% of simple rules, and 58% of rules with an 'unless'.",
           "observation": "'Unless' is the hardest word in business rules.",
           "question": "How many of your business rules have an exception?"},
          "'Unless' is where business rules live. If an agent can't handle exceptions to rules, it can't run the "
          "process.",
          "How many of your business rules come with an 'unless'?",
          "Agents followed 95% of simple plain-English business rules, but 58% of rules with exceptions. 'Unless' is "
          "the hardest word in automation."),
]

AFFAIRS: list[Story] = [
    _affairs("Bihar approves flood-forecasting network with 120 river gauges",
             "The state cabinet approved a flood-forecasting network with 120 automatic river gauges across the Kosi "
             "and Gandak basins, to be installed before next monsoon.", "Bihar Development Watch", "bihar", "tracker",
             "Bihar approved 120 automatic river gauges across the Kosi and Gandak basins, due before next monsoon. "
             "What to watch: installation on time, and whether alerts reach villages early enough.",
             ("Bihar's cabinet approved a flood-forecasting network: 120 automatic river gauges across the Kosi and "
              "Gandak basins.",
              "The target is to install them before next monsoon.",
              "The test isn't the gauges. It's whether warnings reach villages in time to act.",
              "Worth tracking: installation progress by district, and the alert system that goes with it.")),
    _affairs("Patna's new inter-state bus terminal to open with 50 electric buses",
             "Patna's new inter-state bus terminal will open next month, with 50 electric buses on city routes.",
             "Patna City News", "bihar", "tracker",
             "Patna's new inter-state bus terminal opens next month, with 50 electric buses on city routes. The real "
             "test comes after opening: frequency and last-mile links."),
    _affairs("Monsoon ends 8% above average, but Bihar records a 12% deficit",
             "The monsoon season ended with rainfall 8% above the long-period average nationally, while Bihar "
             "recorded a 12% deficit.", "India Weather Desk", "india", "tracker",
             "India's monsoon ended 8% above average. Bihar was 12% short. A national average can hide a hard season "
             "for farmers in one state."),
    _affairs("Bihar's revised startup policy offers seed grants to first-time founders",
             "Bihar's revised startup policy offers seed grants of up to ₹10 lakh to first-time founders and a "
             "single-window registration portal.", "Bihar Development Watch", "bihar", "tracker",
             "Bihar's revised startup policy: seed grants up to ₹10 lakh for first-time founders, plus single-window "
             "registration. Worth tracking how many grants are actually paid out."),
    _affairs("On this day in 1949, the Constituent Assembly adopted Hindi in Devanagari as an official language",
             "On 14 September 1949, the Constituent Assembly adopted Hindi written in Devanagari as an official "
             "language of the Union. The date is marked as Hindi Diwas.", "History Desk", "india", "history",
             "On this day in 1949, the Constituent Assembly adopted Hindi in Devanagari as an official language of "
             "the Union. That's why 14 September is Hindi Diwas."),
    _affairs("Engineers' Day marks M. Visvesvaraya's birth anniversary",
             "India marks Engineers' Day on 15 September, the birth anniversary of M. Visvesvaraya, born in 1860, who "
             "led major irrigation and dam projects.", "History Desk", "india", "history",
             "Engineers' Day in India marks the birth of M. Visvesvaraya on 15 September 1860. He led major "
             "irrigation and dam projects that shaped how India plans water infrastructure."),
    _affairs("Six-lane Ganga bridge near Patna is 90% complete, officials say",
             "Officials said a new six-lane bridge over the Ganga near Patna is 90% complete, with opening targeted "
             "for early next year.", "Patna City News", "bihar", "tracker",
             "A new six-lane Ganga bridge near Patna is 90% complete, officials say, with opening targeted for early "
             "next year. Tracking whether that date holds."),
    _affairs("Darbhanga airport to add evening flights to Delhi and Mumbai",
             "Darbhanga airport will add evening flights to Delhi and Mumbai from next month, after runway lighting "
             "upgrades were completed.", "Bihar Development Watch", "bihar", "tracker",
             "Darbhanga airport adds evening flights to Delhi and Mumbai from next month, after runway lighting "
             "upgrades. More connectivity for north Bihar."),
    _affairs("Bihar plans rooftop solar on 5,000 government school buildings",
             "The state government plans rooftop solar panels on 5,000 government school buildings over two years, "
             "starting with districts that have the most power cuts.", "Bihar Development Watch", "bihar", "tracker",
             "Bihar plans rooftop solar on 5,000 government school buildings over two years, starting with the "
             "districts with the most power cuts. A tracker worth keeping."),
    _affairs("Draft text for UN climate talks proposes tripling adaptation finance",
             "A draft negotiating text for the upcoming UN climate talks proposes tripling adaptation finance for "
             "developing countries by 2035.", "World Affairs Brief", "world", "outlook",
             "A draft text for the next UN climate talks proposes tripling adaptation finance for developing "
             "countries by 2035. The argument will be over who pays and how it's counted."),
    _affairs("India's first commercial chip fab begins trial production",
             "India's first commercial semiconductor fab began trial production this week, officials said, with "
             "volume output planned for next year.", "India Business Desk", "india", "tracker",
             "India's first commercial chip fab has started trial production, with volume output planned for next "
             "year. Yield is the number to watch from here."),
    _affairs("UPI processed 24 billion transactions in August",
             "The Unified Payments Interface processed 24 billion transactions in August, a new monthly record, "
             "according to official data.", "India Business Desk", "india", "tracker",
             "UPI processed 24 billion transactions in August, a monthly record. Public payments infrastructure keeps "
             "compounding."),
    _affairs("Patna Metro's second corridor begins tunnelling",
             "Tunnel boring began on Patna Metro's second corridor, with two machines working towards the railway "
             "station section.", "Patna City News", "bihar", "tracker",
             "Tunnelling has started on Patna Metro's second corridor, with two boring machines heading for the "
             "railway station section. Next milestone: breakthrough."),
    _affairs("Bihar sets up an export cell for makhana",
             "The state launched an export facilitation cell for makhana (fox nut), most of which is grown in north "
             "Bihar, to help farmer groups meet export standards.", "Bihar Development Watch", "bihar", "tracker",
             "Bihar launched an export cell for makhana, most of which is grown in north Bihar, to help farmer groups "
             "meet export standards. Good news if it reaches the growers."),
    _affairs("Bodh Gaya to host an international Buddhist conference",
             "Bodh Gaya will host an international Buddhist conference next month, with delegations expected from "
             "more than 20 countries.", "Bihar Development Watch", "bihar", "outlook",
             "Bodh Gaya hosts an international Buddhist conference next month, with delegations from more than 20 "
             "countries. Heritage tourism is one of Bihar's quieter strengths."),
    _affairs("Summit agrees shared standards for AI incident reporting",
             "Governments at a technology summit agreed shared standards for reporting serious AI incidents, "
             "including a common template and a 72-hour notification window.", "World Affairs Brief", "world",
             "tracker",
             "A summit agreed shared standards for reporting serious AI incidents: a common template and a 72-hour "
             "notification window. Incident reporting is how safety rules become real."),
    _affairs("20 countries sign up to adopt parts of India's digital public infrastructure",
             "Officials said 20 countries have signed agreements to adopt parts of India's digital public "
             "infrastructure, including identity and payments components.", "India Business Desk", "india",
             "tracker",
             "20 countries have signed up to adopt parts of India's digital public infrastructure, officials say, "
             "including identity and payments. Exporting rails, not apps."),
    _affairs("Patna–north Bihar expressway's first phase gets environmental clearance",
             "The first phase of a new expressway linking Patna to north Bihar received environmental clearance, "
             "allowing construction tenders to go out.", "Bihar Development Watch", "bihar", "tracker",
             "The first phase of the new Patna–north Bihar expressway has environmental clearance, so construction "
             "tenders can go out. Next to watch: tender timelines."),
    _affairs("Global trade growth forecast trimmed as tariffs bite",
             "A global trade body trimmed its forecast for merchandise trade growth next year to 1.8%, citing tariffs "
             "and weaker demand.", "World Affairs Brief", "world", "outlook",
             "The forecast for global merchandise trade growth next year is down to 1.8%, citing tariffs and weaker "
             "demand. Supply chains moving towards India are the angle to watch."),
    _affairs("Railways plan 100 Vande Bharat sleeper trains over three years",
             "Indian Railways said 100 Vande Bharat sleeper trains are planned over the next three years, with trial "
             "runs of the first rakes under way.", "India Business Desk", "india", "tracker",
             "Indian Railways plans 100 Vande Bharat sleeper trains over three years, with trial runs of the first "
             "rakes under way. Overnight routes to Bihar would be the test that matters."),
    _affairs("Donor countries pledge $800 million for early-warning systems",
             "A group of donor countries pledged $800 million for early-warning systems in countries most exposed to "
             "floods and cyclones.", "World Affairs Brief", "world", "outlook",
             "Donor countries pledged $800 million for early-warning systems in countries most exposed to floods and "
             "cyclones. Early warnings are among the cheapest adaptation there is."),
    _affairs("New medical college hospital in north Bihar opens outpatient services",
             "A new government medical college hospital in north Bihar opened its outpatient department, with "
             "inpatient wards due to open in phases over six months.", "Bihar Development Watch", "bihar", "tracker",
             "A new medical college hospital in north Bihar has opened outpatient services, with inpatient wards "
             "opening in phases over six months. Staffing will decide how useful it is."),
]

STARTUPS: list[Story] = [
    _startup("Quick-commerce startups report positive contribution margins",
             "Two quick-commerce startups reported positive contribution margins for the first time, citing higher "
             "order values and fewer discounts.", "Startup News",
             "Two quick-commerce startups say they're contribution-positive for the first time: bigger baskets, fewer "
             "discounts. Growth at any cost is over."),
    _startup("Australian pre-seed deals fall as investors favour AI",
             "Australian pre-seed deal count fell 15% year on year, while AI startups' share of deals rose to 40%, a "
             "funding report said.", "Australian Startup News",
             "Australian pre-seed deals fell 15% year on year, but AI's share rose to 40%. Harder to raise, unless "
             "you're in AI."),
    _startup("Bengaluru startup launches an AI tutor in 8 Indian languages",
             "A Bengaluru edtech startup launched an AI tutor that works in 8 Indian languages and runs on low-cost "
             "Android phones.", "Startup News",
             "A Bengaluru startup's AI tutor works in 8 Indian languages on low-cost Android phones. Distribution "
             "beats model size in Indian edtech."),
    _startup("Fintech gets a licence to lend to kirana shops using payment data",
             "A fintech startup received a lending licence to offer small working-capital loans to kirana shops, "
             "using sales data from their payment apps.", "Fintech News",
             "A fintech just got a licence to lend to kirana shops using their payment-app sales data. UPI data is "
             "becoming credit history."),
    _startup("Founders shift to smaller rounds and longer runways",
             "A survey of 500 founders found 64% plan to raise smaller rounds this year and target runways of at least "
             "24 months.", "Venture Research",
             "64% of 500 founders surveyed plan smaller rounds and at least 24 months of runway. Discipline is the "
             "new growth."),
    _startup("Indian SaaS companies grow revenue from AI add-ons",
             "A report on Indian SaaS companies found AI add-ons now contribute 12% of new revenue, up from 3% a year "
             "ago.", "SaaS Report",
             "AI add-ons now bring 12% of new revenue for Indian SaaS companies, up from 3% a year ago. The upsell is "
             "working."),
    _startup("Agritech startup uses satellite data to verify crop-loss claims",
             "An agritech startup is using satellite imagery to verify crop-loss claims for insurers, cutting "
             "assessment time from weeks to days.", "Startup News",
             "An agritech startup verifies crop-loss claims with satellite imagery, cutting assessment from weeks to "
             "days. Faster payouts matter most in a bad season."),
    _startup("Patna accelerator announces its first cohort",
             "A new startup accelerator in Patna announced its first cohort of 15 startups, focused on agriculture, "
             "logistics and education.", "Bihar Development Watch",
             "Patna's new accelerator picked its first 15 startups, in agriculture, logistics and education. Building "
             "for Bihar, from Bihar."),
    _startup("AI-native startups reach $1 million in revenue faster, investors say",
             "Investors tracking 200 AI-native startups said the median company reached $1 million in annual revenue "
             "in 14 months, about half the time of earlier SaaS companies.", "Venture Research",
             "The median AI-native startup hit $1 million in annual revenue in 14 months, per investors tracking 200 "
             "companies. About half the old SaaS timeline. Churn is the open question."),
    _startup("Logistics startup automates freight paperwork at Indian ports",
             "A logistics startup launched a tool that reads bills of lading and customs forms at Indian ports, "
             "claiming document processing in minutes instead of hours.", "Startup News",
             "A logistics startup reads bills of lading and customs forms at Indian ports in minutes instead of "
             "hours. Paperwork is still the slowest part of trade."),
    _startup("Healthtech startup raises $8 million to digitise small clinics",
             "A healthtech startup raised $8 million to bring electronic records and appointment booking to small "
             "clinics in tier-2 cities.", "Startup News",
             "$8 million for a startup digitising small clinics in tier-2 cities: records and appointment booking. "
             "The clinic next door is the real market."),
    _startup("Open-source AI tooling startup launches a paid enterprise tier",
             "An open-source AI tooling startup launched a paid enterprise tier with single sign-on, audit logs and "
             "support, after reaching 30,000 GitHub stars.", "Developer News",
             "An open-source AI tooling startup with 30,000 GitHub stars launched a paid tier: SSO, audit logs, "
             "support. The open-core playbook, now for AI."),
]

BY_TITLE: dict[str, Story] = {s.title.casefold(): s for s in [*FULL, *AFFAIRS, *STARTUPS]}

# ---------------------------------------------------------------------------
# Drafting from a story, following the style the real prompt carries
# ---------------------------------------------------------------------------

# Filler a first-week model tends to add; Ankit cuts it, the voice profile learns to avoid it.
FLUFF = [("This is a really important shift.", ("really",)),
         ("In today's fast-moving landscape, this matters.", ("landscape",)),
         ("It's a crucial reminder for anyone in automation.", ("crucial",))]
CLOSER = "Bottom line: the details matter more than the headline."
RECAP = "To sum up: "
TAGS = {"tech": "#AI #Automation", "affairs": "#Bihar", "startups": "#Startups"}


@dataclass
class PromptStyle:
    avoid: set[str]
    rules: list[str]
    hook_prefs: list[str]


def _line_after(prompt: str, prefix: str) -> str:
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def parse_style(prompt: str) -> PromptStyle:
    avoid = {p.strip().casefold() for p in _line_after(prompt, "Never use:").split(",") if p.strip()}
    prefs_line = _line_after(prompt, "Hook types he keeps most on")
    prefs = [p.strip() for p in prefs_line.split(":", 1)[-1].split(",") if p.strip()] if prefs_line else []
    rules: list[str] = []
    m = re.search(r"Style guide learned from his edits \(follow it\):\n(.*?)\n(?:What works on|Target length:)", prompt,
                  re.DOTALL)
    if m:
        rules = [r[2:].strip() for r in m.group(1).splitlines() if r.startswith("- ")]
    return PromptStyle(avoid=avoid, rules=rules, hook_prefs=prefs)


def _learned(style: PromptStyle, *words: str) -> bool:
    return any(w in a for w in words for a in style.avoid)


def _rule(style: PromptStyle, *needles: str) -> bool:
    return any(n in r.casefold() for n in needles for r in style.rules)


def _fluff_for(story: Story) -> tuple[str, tuple[str, ...]]:
    return FLUFF[int(ids.short_hash(story.title), 16) % len(FLUFF)]


def _x_hooks(story: Story) -> list[dict[str, str]]:
    if story.hooks:
        return [{"type": t, "text": textutil.truncate(h, 200)} for t, h in story.hooks.items()]
    sentences = textutil.split_sentences(story.x)
    first = sentences[0] if sentences else story.title
    has_number = bool(textutil.numeric_claims(first))
    return [{"type": "number" if has_number else "observation", "text": first},
            {"type": "observation", "text": sentences[-1] if len(sentences) > 1 else story.title},
            {"type": "question", "text": "What should happen next?"}]


def compose(story: Story, platform: str, fmt: str, prompt: str) -> dict[str, Any]:
    style = parse_style(prompt)
    claims = [{"text": textutil.truncate(story.fact, 200), "source": 0}]
    if platform == "linkedin":
        order = [t for t in style.hook_prefs if t in story.hooks] + [t for t in story.hooks if t not in style.hook_prefs]
        lead = order[0]
        so = story.so
        fluff, words = _fluff_for(story)
        if not _learned(style, *words):
            so = f"{fluff} {so}"
        parts = [story.hooks[lead], story.fact, so, story.ask]
        if not (_learned(style, "bottom line") or _rule(style, "summary paragraph")):
            parts.append(CLOSER)
        return {"text": "\n\n".join(parts), "posts": [], "hook_type": lead,
                "hooks": [{"type": t, "text": story.hooks[t]} for t in order],
                "claims": claims, "format_note": "", "angle": story.angle}
    hooks = _x_hooks(story)
    out: dict[str, Any] = {"text": "", "posts": [], "hook_type": hooks[0]["type"], "hooks": hooks, "claims": claims,
                           "format_note": "", "angle": story.angle or textutil.truncate(story.x, 100)}
    tags = "" if _rule(style, "hashtag") else f" {TAGS.get(story.x_lane, '')}"
    if fmt == "x_thread" and story.thread:
        posts = list(story.thread)
        if not _rule(style, "recap"):
            posts.append(RECAP + textutil.split_sentences(story.x)[-1])
        out["posts"] = posts
    elif fmt == "x_reply":
        out["text"] = textutil.truncate(story.so or story.x, 240)
        out["reply_context"] = f"Replies to posts about {textutil.truncate(story.title, 90)}"
        out["search_terms"] = textutil.sim_tokens(story.title)[:3]
    elif fmt == "x_quote":
        out["text"] = textutil.truncate(textutil.split_sentences(story.x)[-1], 250)
        out["quote_source"] = 0
    else:
        out["text"] = (story.x + tags).strip()
    return out
