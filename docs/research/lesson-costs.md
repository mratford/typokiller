# Which LLM should write Lessons, and what will it cost?

Resolves issue #5 (part of map issue #1). Researched 2026-10-25. Originally framed as "what will Lessons cost with Claude Haiku?"; widened to compare Haiku against competing models. Vocabulary follows `CONTEXT.md`: a **Lesson** is a **Source** written by the LLM on request (for example "async with examples" in Python or Gleam), which is then split into **Passages** to type.

## Short answer

- **Cost does not discriminate between candidates.** A typical Lesson (~1,500 words of prose and code, about 4,000 output tokens and 600 input tokens) costs between about **0.12p and 0.6p** on every small or "lite" model compared, and about **3p** on the mid-tier models (Claude Sonnet 5.5, OpenAI GPT-6.1 Sol). At £5/month that is roughly **800 to 4,000 small-model Lessons or about 160 mid-tier Lessons** a month, far more than a personal tool will use.
- **Claude Haiku 5.5 ($0.10 / $0.50 per MTok) is price-identical to OpenAI GPT-6 Luna** and within about 25% of the cheapest alternatives (gpt-5-nano, Gemini 2.5 Flash-Lite). Nothing found is cheap enough to justify choosing on price.
- **Quality on Gleam is the real risk, not cost.** The only published Gleam benchmark I found (arXiv 2606.16827) shows older flagship and open models scoring 0.2% to 20% pass@1 on Gleam versus 70% to 97% on Python. No benchmark of the current small models on Gleam exists that I could find. So the choice should be made by a small measured bake-off, not by price list.
- **Recommendation**: build a provider-neutral Lesson-generation seam; default to **Claude Haiku 5.5 for Python Lessons** and a **mid-tier model (Claude Sonnet 5.5 or GPT-6.1 Sol, both $2 / $10) for Gleam Lessons**, then confirm or overturn with a roughly $2 bake-off that compiles the generated code. Haiku is a reasonable default but not demonstrably "the right choice"; the evidence does not exist yet.
- **Hard monthly cap**: every major provider offers a server-side spend limit; OpenAI, OpenRouter and Anthropic offer clean ones. Combine with app-side token accounting regardless of provider (section 7).

## 1. Candidates and current prices

All prices are USD per million tokens (MTok), standard (non-batch) rates, from each provider's own pricing page, fetched 2026-10-25. Batch is about half price on Anthropic, OpenAI and Gemini.

| Provider / model | Input | Output | Notes | Source |
|---|---|---|---|---|
| Anthropic Claude Haiku 5.5 | $0.10 | $0.50 | Batch $0.05 / $0.25; cache read $0.01; prompts over 100K tokens $0.50 / $2.50 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Anthropic Claude Sonnet 5.5 | $2 | $10 | Batch $1 / $5; cache read $0.10 | same |
| OpenAI GPT-6 Luna | $0.10 | $0.50 | "Our most efficient model for focused, high-volume tasks"; 1.05M context, 128K max output, knowledge cutoff 18 May 2026 | [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [OpenAI models](https://developers.openai.com/api/docs/models) |
| OpenAI GPT-5.6 Luna | $0.20 | $1.20 | | OpenAI pricing |
| OpenAI gpt-5-nano | $0.05 | $0.40 | Older generation, cheapest on the page | OpenAI pricing |
| OpenAI gpt-5.4-nano / gpt-5-mini | $0.20 / $0.25 | $1.25 / $2.00 | | OpenAI pricing |
| OpenAI GPT-6.1 Sol | $2 | $10 | "Near-Astra performance for complex work at a lower cost"; knowledge cutoff 30 Apr 2026 | OpenAI pricing, OpenAI models |
| Google Gemini 2.5 Flash-Lite | $0.10 | $0.40 | Free tier available; older generation | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Google Gemini 3.1 Flash-Lite | $0.25 | $1.50 | Free tier | Gemini pricing |
| Google Gemini 3.5 Flash-Lite | $0.30 | $2.50 | Free tier | Gemini pricing |
| Google Gemini 3.8 Flash | $0.75 to 31 Dec 2026, then $1.50 | $3.75 to 31 Dec 2026, then $7.50 | Free tier | Gemini pricing |
| DeepSeek `deepseek-flash` (V4.1 Flash) | $0.30 peak / $0.15 off-peak (cache miss) | $1.20 peak / $0.60 off-peak | Off-peak is half price; peak is 01:00-04:00 and 06:00-10:00 UTC Mon-Fri; 1M context | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) |
| DeepSeek `deepseek-v4-pro` | $1.32 peak / $0.66 off-peak | $3.96 peak / $1.98 off-peak | | DeepSeek pricing |
| Mistral Small 4 | $0.15 | $0.60 | | [Mistral pricing](https://docs.mistral.ai/inference/pricing) |
| Mistral Codestral | $0.30 | $0.90 | | Mistral pricing |
| Mistral Medium 3.5 / Large 4 | $1.50 / $1.36 | $7.50 / $4.18 | | Mistral pricing |
| OpenRouter (aggregator) | provider list price | provider list price | No inference markup; 5.5% fee on credit purchases (Standard plan) | [OpenRouter pricing](https://openrouter.ai/pricing), [FAQ](https://openrouter.ai/docs/faq) |

Notes on reading the table:

- The Mistral pricing page gave no stated tier (standard versus batch); I assumed standard. The Mistral marketing page ([mistral.ai/pricing](https://mistral.ai/pricing)) separately says batch "reduces the price by 50%".
- Anthropic says Claude 4.7 and later models use a tokenizer that "produces approximately 30% more tokens for the same text" than earlier models. I did not find equivalent statements for the other vendors' current tokenizers, so the per-Lesson numbers below use the same token counts for all models. If other tokenizers are about 30% more compact, their real costs are about 25% lower than shown.
- Prices on the Gemini page show scheduled changes (3.8 Flash doubles on 1 Jan 2027; Gemini 4 Argon rises on 1 Dec 2026), so a Gemini price list ages quickly.

## 2. Token estimate for a typical Lesson

These are estimates (assumptions), not measurements.

- **Output**: 1,500 words of prose with code examples. English prose is roughly 1.3 tokens per word on older tokenizers and code is denser; with Anthropic's documented ~30% uplift this lands around 3,500 to 4,500 tokens. I use **4,000** as typical (3,000 low, 6,000 high).
- **Input**: a short system prompt (Passage-friendly formatting, length, language) plus the request. About **600 tokens**.
- **Hidden reasoning is billed as output.** Haiku 5.5 reasons by default (adaptive thinking, effort default `medium`); per Anthropic's `claude-api` reference, `thinking: {type: "disabled"}` is accepted at effort `high` or below and thinking tokens are billed the same whether or not displayed. Other vendors' reasoning models behave similarly. For prose generation, turn reasoning off or to low effort, otherwise output tokens (and cost) can multiply.
- Replace this estimate with measured numbers from the first dozen Lessons (`usage` on each response).

## 3. Cost per typical Lesson (600 in / 4,000 out) and Lessons per £5

Exchange rate assumed: **£1 = $1.3369**, derived from the ECB euro reference rates of 23 October 2026 (1 EUR = 1.1193 USD and 1 EUR = 0.83728 GBP; [ECB USD](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html), [ECB GBP](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-gbp.en.html)). £5 is **$6.68**. Card foreign-exchange fees and OpenRouter's 5.5% credit fee are excluded.

| Model | Cost per Lesson | Pence | Lessons per £5 |
|---|---|---|---|
| OpenAI gpt-5-nano | $0.00163 | 0.12p | 4,100 |
| Gemini 2.5 Flash-Lite | $0.00166 | 0.12p | 4,026 |
| **Claude Haiku 5.5** | **$0.00206** | **0.15p** | **3,244** |
| OpenAI GPT-6 Luna | $0.00206 | 0.15p | 3,244 |
| DeepSeek flash (off-peak) | $0.00249 | 0.19p | 2,684 |
| Mistral Small 4 | $0.00249 | 0.19p | 2,684 |
| Mistral Codestral | $0.00378 | 0.28p | 1,768 |
| OpenAI GPT-5.6 Luna | $0.00492 | 0.37p | 1,358 |
| DeepSeek flash (peak) | $0.00498 | 0.37p | 1,342 |
| OpenAI gpt-5.4-nano | $0.00512 | 0.38p | 1,305 |
| Gemini 3.1 Flash-Lite | $0.00615 | 0.46p | 1,086 |
| OpenAI gpt-5-mini | $0.00815 | 0.61p | 820 |
| Gemini 3.5 Flash-Lite | $0.01018 | 0.76p | 656 |
| Gemini 3.8 Flash (promo) | $0.01545 | 1.16p | 432 |
| Mistral Large 4 | $0.01754 | 1.31p | 381 |
| Gemini 3.8 Flash (from 2027) | $0.03090 | 2.31p | 216 |
| Mistral Medium 3.5 | $0.03090 | 2.31p | 216 |
| **Claude Sonnet 5.5** | **$0.04120** | **3.08p** | **162** |
| OpenAI GPT-6.1 Sol | $0.04120 | 3.08p | 162 |

(Calculation: cost = (600 x input price + 4,000 x output price) / 1,000,000.) Output tokens are about 97% of the cost for the cheap models, so the output price is what matters; input price and prompt caching are almost irrelevant. For Haiku 5.5, a high-end Lesson (800 in / 6,000 out) is $0.0031 (about 2,170 per £5); with the Batch API everything is halved.

Context for a personal tool: 1 to 5 Lessons a day on a small model is **about 5p to 25p a month**, and even 20 mid-tier Lessons a month is about 62p. The £5 cap is loose for everything here; the only way to hit it is bulk generation or a runaway loop, which is why the cap in section 7 matters more than the model's price.

Prompt caching and Batch:

- **Caching**: not worth designing around for plain Lessons. Haiku 5.5's minimum cacheable prompt is 512 tokens ([Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)), the default lifetime is 5 minutes, and a 600-token prompt saves at most about $0.00005. It would matter only if the prompt grows to many thousands of tokens, which is plausible for Gleam (see section 5: pasting current Gleam stdlib notes into the prompt).
- **Batch**: 50% off on Anthropic, OpenAI and Gemini, but results can take up to 24 hours ([Anthropic batch docs](https://platform.claude.com/docs/en/build-with-claude/batch-processing)). It suits overnight pre-generation of a Lesson queue, not an interactive "write me a Lesson now" flow. At 0.15p per Lesson, skip it for v1.

## 4. Free tiers

- **Google Gemini**: the Flash-Lite and Flash models above list "Input and output free of charge" on the free tier ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)); I did not find the free-tier rate limits. Catch: on the unpaid tier Google "uses the content you submit ... and any generated responses to provide, improve, and develop" products and "human reviewers may read, annotate, and process your API input and output" ([Gemini API terms](https://ai.google.dev/gemini-api/terms)). Since Lesson prompts are only topics (no typing data), this is low stakes. The same terms say that in the EEA, Switzerland and the UK the paid-services data terms apply to all services, including unpaid ones.
- **OpenRouter**: free models (IDs ending `:free`) are limited to 50 requests per day, or 1,000 per day with at least 10 credits purchased ([OpenRouter limits](https://openrouter.ai/docs/api-reference/limits), [FAQ](https://openrouter.ai/docs/faq)). Enough volume for Lessons; quality of the free models was not assessed.
- **Anthropic, OpenAI, DeepSeek, Mistral**: I did not find a free API allowance on the pages fetched. The Mistral pricing page says only that the Free plan gives limited access to chat and Studio, not a stated API allowance.

A free tier saves under £1 a month at realistic volume, so I treat it as a bonus rather than a selection criterion.

## 5. Quality for code, especially Gleam

**What the evidence says.** The only published Gleam code-generation numbers I found are from Giagnorio, Martin-Lopez and Bavota, "No Resource, No Benchmarks, No Problem? Evaluating and Improving LLMs for Code Generation in No-Resource Languages" ([arXiv 2606.16827](https://arxiv.org/abs/2606.16827)). It treats Gleam (and MoonBit) as "no-resource" languages because LLMs saw almost no training data. Zero-shot pass@1 (%), from Table IV of the HTML version ([arxiv.org/html/2606.16827v1](https://arxiv.org/html/2606.16827v1)):

| Model | Benchmark | Gleam | Python |
|---|---|---|---|
| GPT-4o | HumanEval | 7.60 | 91.23 |
| GPT-4o | MBPP | 20.31 | 84.90 |
| GPT-4o | McEval-Hard | 0.97 | 77.67 |
| o3-mini | HumanEval | 4.55 | 96.75 |
| o3-mini | MBPP | 7.75 | 84.34 |
| o3-mini | McEval-Hard | 0.18 | 88.94 |
| Qwen 2.5 Coder 32B Instruct | HumanEval | 6.49 | 89.61 |
| Qwen 3 32B | MBPP | 6.23 | 83.66 |

(Table abridged; all four models in the paper show the same pattern, with Gleam scores of 0.18% to 20.31% and Python scores of 70% to 97%.)

**Caveats**: these are 2024/2025-era models (GPT-4o, o3-mini, Qwen), not Haiku 5.5, GPT-6 Luna or any current model; the tasks are short algorithmic problems translated into Gleam, not 1,500-word explanations with idiomatic examples; and the numbers are zero-shot. I found **no published benchmark of any current small or mid-tier model on Gleam**, and no comparative benchmark for Python Lesson-style writing either. So I cannot rank Haiku 5.5 against GPT-6 Luna, Gemini Flash-Lite, DeepSeek or Mistral on code quality from primary sources.

**What can be concluded**:

- Python is a high-resource language where every candidate is likely to produce correct short examples; this is an inference from the Python column above, not a measurement of current models.
- Gleam is the risk. Older models were poor at it, so Gleam Lessons are likely to contain invented functions or outdated stdlib calls. Because the user types the code verbatim, wrong code is wrong practice material.
- Knowledge cutoff matters for a fast-moving language: GPT-6 Luna's is 18 May 2026 and GPT-6.1 Sol's is 30 April 2026 (OpenAI models page). I did not gather equivalent cutoffs for the others.
- Mitigations that apply to any model: (1) put a compact, current Gleam cheat sheet (stdlib signatures) in the system prompt, which is also where prompt caching starts to pay off; (2) **compile every generated Gleam code block with `gleam build`/`gleam check` and regenerate on failure**, which turns "is the model good at Gleam?" into a cheap measurable pass rate; (3) use a larger model for Gleam.

**Bake-off to settle it** (suggested, estimated under $2 in total): 10 topics x 2 languages (Python, Gleam) x 4 candidates (Claude Haiku 5.5, Claude Sonnet 5.5, GPT-6 Luna, GPT-6.1 Sol; optionally Gemini 3.8 Flash and DeepSeek flash). Score by compile/run pass rate of every code block, then eyeball prose. OpenRouter is a convenient way to run it with one key.

## 6. Data use and privacy

Lesson requests contain only a topic and formatting instructions, not the keystroke data that is the core of typokiller, so privacy risk from this feature is low whichever provider is used. Even so:

| Provider | Training on API data | Retention / notes | Source |
|---|---|---|---|
| Anthropic | Not by default: "By default, we will not use your inputs or outputs from our commercial products" to train models | Retention for API data not stated on the page fetched | [Anthropic privacy centre](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training) |
| OpenAI | Not by default: API data "is not used to train or improve OpenAI models" unless you opt in | Abuse-monitoring logs retained up to 30 days; zero data retention available only with prior approval | [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data) |
| Google Gemini | Paid services: prompts and responses not used to improve products. Unpaid/free: used to improve products and may be human-reviewed | Paid: logged "for a limited period"; UK/EEA/Switzerland get paid terms on all services | [Gemini API terms](https://ai.google.dev/gemini-api/terms) |
| DeepSeek | **Could not confirm from a primary source.** The API terms of service are silent on DeepSeek's own training use, storage location and retention, and defer to a privacy policy I could not fetch. Secondary reporting (not primary; treat with caution) says the consumer service stores data on servers in the PRC and may use inputs to improve its models | Unverified | [DeepSeek API terms](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) |
| Mistral | **Could not confirm for the API.** The help-centre article fetched covers Studio pay-as-you-go opt-out only | Unverified | [Mistral help](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-models) |
| OpenRouter | Prompts and completions "are not logged by default"; providers that log or cannot be confirmed are excluded unless the training toggle is on | Optional logging for a 1% discount | [OpenRouter FAQ](https://openrouter.ai/docs/faq) |

DeepSeek and Mistral both fall short on verifiable data terms from the pages I could reach, which is a reason to rank them last for a personal tool unless a bake-off shows a clear quality win. (Their prices are also not meaningfully lower than Haiku 5.5 for equivalent small models.)

## 7. Enforcing a hard monthly cap, by provider

| Provider | Server-side cap | Behaviour when hit | Caveats | Source |
|---|---|---|---|---|
| Anthropic | Organization spend limit set on the Console Billing page, below the tier cap (Start tier cap is $500/month); optional per-workspace spend limits (not on the Default Workspace) | Own limit: HTTP 400 `invalid_request_error` ("You have reached your specified API usage limits"). Tier cap: HTTP 429 `enforced_spend_limit_reached`, no `retry-after` | Minimum settable value and enforcement lag not documented; usage data "typically appears within 5 minutes". Usage and Cost Admin API is "unavailable for individual accounts" | [Rate limits](https://platform.claude.com/docs/en/api/rate-limits), [Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces), [Usage and Cost API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api) |
| OpenAI | "Hard spend limit" per organization or project; also a spend alert that only notifies | Requests return 429 once the amount is reached | Separate from the tier's monthly usage limit (Build tier $500/month after $5 of credit purchases) | [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits) |
| Google Gemini | Project spend caps in AI Studio (experimental); billing-account tier caps (Tier 1 $250/month) pause service; prepay balance | Project caps: "subject to overages for around a 10 minute latency period"; batch and agent sessions may overrun | Weakest of the options; not available for invoiced accounts | [Gemini billing](https://ai.google.dev/gemini-api/docs/billing) |
| OpenRouter | Prepaid credits plus an optional per-key credit `limit` (with `limit_reset` interval) | HTTP 402 with `limit_source: openrouter_key_limit` once a key's limit is spent | One cap across every model behind the key, which is convenient for multi-model use | [OpenRouter limits](https://openrouter.ai/docs/api-reference/limits) |
| DeepSeek | Not documented on the pages fetched | Unknown | Unverified | [DeepSeek rate limit page](https://api-docs.deepseek.com/quick_start/rate_limit) |
| Mistral | Not verified | Unknown | Unverified | |

**App-side accounting (do this regardless of provider)**: every provider returns token usage on each response. Multiply by a constants table of per-model prices, add to a month-to-date ledger stored locally, and check before each request using a worst case of input tokens plus `max_tokens` times the output price. Refuse, or downgrade from a mid-tier to a small model, when the ledger would exceed the cap. Treat the provider's "limit reached" response as a normal UI state, not a retryable error. Set `max_tokens` (about 8,000) so no single request can be expensive. The app-side ledger is the day-to-day gauge; the provider's server-side limit is the backstop against bugs, loops and leaked keys.

## Recommendation

1. **Do not choose on price.** Every candidate costs under 1p per small-model Lesson and about 3p per mid-tier Lesson. £5/month covers hundreds to thousands of Lessons, so quality and operational simplicity decide.
2. **Defaults**: Claude Haiku 5.5 for Python Lessons (price-tied with GPT-6 Luna for the cheapest current-generation small model, not trained on by default, clean Console hard cap, one vendor) and a mid-tier model for Gleam Lessons (Claude Sonnet 5.5 or GPT-6.1 Sol; about 3p each, so roughly 20 a month for 62p). This is not Haiku-for-everything: the only Gleam evidence says niche-language correctness is the weak point, and a Gleam Lesson is cheap enough to buy the stronger model.
3. **Confirm with a bake-off before committing** (section 5): compile-check generated code and compare Haiku 5.5, Sonnet 5.5, GPT-6 Luna and GPT-6.1 Sol on identical topics. If GPT-6 Luna matches Haiku 5.5 at the same price, either is fine; pick on which cap/billing flow you prefer.
4. **Skip DeepSeek and Mistral** for now: no verifiable data terms for the API from the pages I could reach, and no price advantage over Haiku 5.5. **Skip Gemini's free tier** as the default (a hobby saving of pennies for "used to improve products" terms on the unpaid tier, and the weakest spend cap), though Gemini 2.5 Flash-Lite at $0.10 / $0.40 is a fair low-cost fallback.
5. **OpenRouter is optional**: useful for the bake-off and as a single-key, single-cap way to switch models later, at the cost of a 5.5% credit fee and an extra intermediary. For production, going direct to one or two providers is simpler.
6. **Design implications for typokiller**: (a) put model choice behind a provider-neutral Lesson-generation interface so model and language can be swapped per request; (b) validate generated Gleam (and Python) code blocks automatically before a Lesson is saved or split into Passages; (c) turn reasoning off or low and cap `max_tokens`; (d) keep a local month-to-date cost ledger and set a provider-side spend limit of about $6.70 (£5) as the backstop; (e) skip caching and Batch in v1.
7. **Assumptions to re-check once real Lessons exist**: the 4,000-token output estimate (measure it), the £1 = $1.337 rate, prompt-token growth if a Gleam cheat sheet is added, and the unverified items flagged above (DeepSeek and Mistral data terms and caps, Anthropic's spend-limit minimum and lag, Gemini free-tier rate limits).

## 8. Bake-off results (issue #11)

Run 2026-10-25 through OpenRouter, total spend **$0.84**. Harness, prompts, all 48 Lessons and raw results are in `docs/research/lesson-trial/` (`trial.py`, `lessons/`, `results/`); `build_viewer.py` renders them side by side.

**Setup.** 4 models (Claude Haiku 5.5, Claude Sonnet 5.5, GPT-6 Luna, GPT-6.1 Sol) x 2 languages (Gleam, Python) x 6 topics (pattern matching, error handling, lists and recursion, custom types, string processing, concurrency). Same system prompt for all: a 1,200 to 1,500 word Lesson with 3 to 5 examples, each a complete program (Gleam: full module with `pub fn main() -> Nil`, only gleam_stdlib 1.0, gleam_erlang 1.3, gleam_otp 1.3; Python: stdlib-only script), plain ASCII. Reasoning effort `low`, `max_tokens` 8,000. Every fenced block was built and run in isolation: `gleam build` then `gleam run -m lesson` (gleam 1.18.1), or `py_compile` then run (Python 3.14), with a timeout.

| Model | Lang | Blocks compile | Blocks run | Lessons all-pass | Mean out tok | Mean reasoning tok | Mean cost | Mean secs |
|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | Gleam | 21/32 (66%) | 18/32 (56%) | 0/6 | 4,843 | 2,239 | $0.0024 | 22 |
| Sonnet 5.5 | Gleam | 27/28 (96%) | 26/28 (93%) | 4/6 | 4,943 | 1,524 | $0.0499 | 33 |
| GPT-6 Luna | Gleam | 20/28 (71%) | 20/28 (71%) | 2/6 | 2,612 | 976 | $0.0013 | 29 |
| GPT-6.1 Sol | Gleam | 25/25 (100%) | 25/25 (100%) | 6/6 | 2,521 | 408 | $0.0256 | 53 |
| Haiku 5.5 | Python | 27/27 | 27/27 | 6/6 | 3,224 | 1,078 | $0.0016 | 14 |
| Sonnet 5.5 | Python | 29/29 | 29/29 | 6/6 | 3,414 | 223 | $0.0345 | 23 |
| GPT-6 Luna | Python | 27/27 | 27/27 | 6/6 | 2,390 | 503 | $0.0012 | 25 |
| GPT-6.1 Sol | Python | 24/24 | 24/24 | 6/6 | 2,293 | 129 | $0.0232 | 43 |

**Gleam failure modes.**

- Haiku 5.5: hallucinated or stale APIs (`list.range` x3, `process.start` in all 4 concurrency blocks), 3 syntax errors, 3 modules with no `main` (compile but break the prompt's rule).
- GPT-6 Luna: old or invented syntax and APIs in concurrency (all 4 blocks fail, e.g. `process.receive_timeout`), `>` on Floats, unknown modules.
- Sonnet 5.5: one `list.range`, one module with no `main`.
- GPT-6.1 Sol: none.

**Other observations.**

- Python is solved: every model's every block ran. Haiku's Python Lessons often run short (751 to 1,267 words against a 1,200 to 1,500 target); Sol's are the most consistent (1,325 to 1,476 words).
- Measured costs are close to section 3's estimates for the small models; Sonnet runs about 60% over (longer output plus reasoning tokens), still about 5 cents per Gleam Lesson.
- Non-ASCII characters were near zero for every model (0 to 3 across 12 Lessons).

**Decision** (human, after reading the Lessons side by side): **Claude Sonnet 5.5 writes Gleam Lessons; Claude Haiku 5.5 writes Python Lessons.** Sonnet's residual Gleam errors (about 1 block in 14) are what the build-and-run validation with regeneration (section 7 / recommendation 6b) exists to catch, and a missing `main` should count as a validation failure. GPT-6.1 Sol scored best on Gleam and stays the obvious swap behind the provider-neutral interface if Sonnet's failure rate proves annoying in practice.
