# Scouting, writing and free-provider update (6 November 2026)

The pipeline still runs on GitHub Actions and the desk on Pages. No paid search, social API, or paid-model
fallback has been enabled. Each hosted provider has finite limits: additional providers improve availability,
but cannot guarantee unlimited free generation. Use free-tier accounts with billing disabled. PBS's call caps
are conservative application budgets, not a substitute for the provider's account billing controls.

## AI setup

- Existing Gemini, Groq and OpenRouter keys keep working. OpenRouter is pinned to `openrouter/free`.
- Optional: add the `CEREBRAS_API_KEY` repository Actions secret. The pipeline tries Cerebras after Groq and
  before Flash-Lite for drafts. No source or private-data files need manual editing. The default Cerebras models
  are `gpt-oss-120b` and `qwen-3.8-27b`; availability is subject to the account's free limits.
- Studio has its own device-local keys: Settings → Studio → Backup AI providers. Save a Groq, Cerebras or
  OpenRouter key. Text requests fail over in that order after Gemini. These replies are labelled as having no
  web search. Pictures remain with the vision-capable Gemini path; a text backup never silently drops them.
  Keys are never written to either GitHub repo. A fallback receives the redacted chat, so choose providers whose
  data policies suit the material you send. Invalid or unavailable keys are reported on the first request.
- Optional local operation: install Ollama, pull `qwen3:8b`, run its local service, and set
  `PBS_OLLAMA_ENABLED=1` before running `pbs tick`. Change the local model through the provider settings if needed.
  The adapter accepts loopback hosts only and refuses cloud models. It has no hosted API quota, but uses your
  hardware. It is not installed or enabled on GitHub's hosted runner.

Parallel drafts now reserve their request budget before sending. Failed provider attempts consume the local
budget too, and rate-limited models cool down instead of being retried by each subsequent draft. A provider
attempt may internally try multiple configured models; the counters are not a token-accurate billing ledger.

Groq retired Compound in September 2026. Its former search adapter is disabled by default rather than silently
switching to a potentially billable search tool. Old provider names remain readable for saved configurations.

## What scouting can actually see

The scout adds a public Bluesky author feed with observed likes, replies and reposts, and indexed public
LinkedIn/X coverage through Google News feeds. It also uses the existing Hacker News and Mastodon signals.
These public services may return no results, deny anonymous access, or rate-limit requests; Sources shows their
health. This does not access logged-in LinkedIn/X timelines or obtain private competitor analytics.

Live checks returned LinkedIn/X discovery entries and the Bluesky public author feed. Anonymous Bluesky search
returned HTTP 403, so it is supported only as an optional source kind, not enabled by default. The initial
Bluesky watchlist follows Simon Willison's AI/software posts; add other public author feeds in Sources.

Insights → What's working now shows **Social evidence**:

- **Observed activity:** counts returned by a public endpoint, with a collection time. Counts from different
  platforms are not comparable engagement rates.
- **Indexed coverage:** discovery material with unknown reach and engagement.
- **Search-cited post:** a direct post URL present in the search provider's citations. A model-only URL or a
  search-results link cannot establish a conversation. The proposed angle is labelled as a hypothesis.

Healthy feeds no longer disappear just because no post was selected from them. On the next scout, a one-time
migration restores sources paused by the old `No picked cards from …` rule. User pauses, deleted sources and
HTTP-failure pauses remain. Low selection yield prompts a review of source relevance and ranking.

Story grouping checks every pair in a cluster, separates different companies' earnings/funding events, and
revalidates historical memberships. Sources closest to the selected story lead the drafting material and links.
More source detail reaches the writer. Headline-only stories get short, attributed treatment; one company or
paper is not evidence of a whole-market trend. Source-specific figure warnings appear on the card.

Explicit zero-weight topics are excluded from suggestions. New skip feedback and strategy changes invalidate
cached triage immediately instead of waiting for its six-hour expiry.

## Analytics and learning

The review shows measured and unmeasured posts separately for LinkedIn and X. A metric snapshot stays intact:
new impressions are not combined with engagement from an older snapshot. Weighted engagement rates use only
posts with both measurements. Small groups are labelled insufficient, time/day comparisons are observational,
and posting-window conclusions require at least five measured posts on each side. Export-period counts and
post ages are explicit context, not equivalent lifetime measurements.

Rejecting a measurement also removes any reward it previously contributed. Missing X analytics cannot become
a claim that X performs poorly. Upload each platform's native analytics regularly and review ambiguous matches.

These checks reduce known failure modes; they do not automatically fact-check every sentence. Review the source
and the final draft before posting. Improvements should be judged by your edit ratio, selection rate and new
platform-specific performance measurements over the next few weeks.

## Verification and references

Regression coverage includes contaminated story clusters, primary-source ordering, source recovery, zero-weight
topics, uncited social claims, no-AI observations, concurrent budgets, model cooldowns, local-only Ollama,
analytics snapshots, rejected rewards, and Studio fallback/cancellation/image handling. Synthetic fixtures only;
private production data is not included in this public repository.

Provider documentation checked for this update:

- [Groq model retirement](https://console.groq.com/docs/deprecations)
- [Cerebras model catalog](https://inference-docs.cerebras.ai/models/overview) and [rate limits](https://inference-docs.cerebras.ai/support/rate-limits)
- [OpenRouter free models](https://openrouter.ai/collections/free-models)
- [Ollama API compatibility](https://docs.ollama.com/api/openai-compatibility)
