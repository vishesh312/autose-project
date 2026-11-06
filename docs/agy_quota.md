# Antigravity CLI (agy) quota, limits and terms (researched 2026-11-06)

Tags: VERIFIED = stated on the cited page (fetched today). UNVERIFIED = forum claim, aggregator, or our inference.
Note: WebFetch summarizes pages with a small model, so quotes are paraphrase-grade; re-read the primary pages before committing money.

## 1. Quota by plan

- VERIFIED: No numeric quotas are published anywhere. Limits "are set by available capacity", exist to prevent abuse, "correlate with the amount of work done by the agent" (simple tasks yield more prompts than complex ones), and may change. https://antigravity.google/docs/plans?app=cli
- VERIFIED: It is a work/compute-proportional quota, not a fixed request or token count. Plus optional purchased "AI credits" for overage.
- VERIFIED per plan (same page):
  - Ultra: "highest, most generous quota, refreshed every five hours"; highest weekly limit; third-party models.
  - Pro: "high, generous quota, refreshed every five hours until the weekly limit is reached"; higher weekly limit than non-Pro.
  - Everyone else (free / Plus): "meaningful quota, refreshed weekly" plus a weekly rate limit. No 5h window.
  - Workspace/Enterprise and API key: not described on the plans page. BYOK / bring-your-own-endpoint "for additional rate limits" is explicitly not supported.
- VERIFIED: Per-model limits are not numeric. The model selector groups usage into two pools, "Gemini Models" and "Claude and GPT models", each with a 5-hour and a weekly limit. https://antigravity.google/docs/models
- VERIFIED model availability (https://antigravity.google/docs/models):
  - Gemini 3.8 Flash (Low/Medium/High thinking): Free/Plus, Pro, Ultra, Enterprise.
  - Claude Sonnet 4.6 and Opus 4.6 (Thinking): Free/Plus and Pro only, NOT Ultra, NOT Enterprise. Both marked to be removed 2026-11-18 (12 days from today).
  - GPT-OSS-120b: Free/Plus, Pro, Ultra. Also marked "Will be removed on November 18, 2026".
  - So Claude and GPT-OSS runs must be done before Nov 18. Verify with `agy models` on your account.
- VERIFIED exhaustion behaviour (Pro/Ultra only): setting "AI Credit Overages" = Never means wait for the baseline refresh; Always means spend credits then return to baseline. Credits billed at "standard Gemini Enterprise consumption pricing". Plans page.
- UNVERIFIED (press, forum): credits cost $25 per 2,500 (The Register, https://www.theregister.com/2026/03/12/users_protest_as_google_antigravity/). Ultra includes 25,000 monthly credits (forum). Value of one credit in agy is not documented.
- UNVERIFIED (forum): error on exhaustion is `RESOURCE_EXHAUSTED (code 429): Individual quota reached` (https://discuss.ai.google.dev/t/google-ai-ultra-refund-request-gemini-cli-issues-and-unusable-antigravity-ai-credits/166590). Users report multi-day lockouts on Pro instead of a 5h reset (https://discuss.ai.google.dev/t/google-ai-pro-subscription-antigravity-quota-not-working-as-advertised-10-day-lockout-instead-of-5-hour-reset/118505). Prices: Pro about $20/mo, Ultra tiers about $100 and $200 (aggregators, e.g. https://www.cloudzero.com/blog/google-antigravity-pricing/; they disagree on rounding).
- UNVERIFIED: Free-tier limits reported as cut repeatedly since launch (preuve.ai review). Expect the free tier to be the tightest.
- VERIFIED: Headless mode has no documented quota of its own, no time limit by default (`--print-timeout` to set one). https://antigravity.google/docs/cli/headless
- UNVERIFIED (forum, not Google): headless runs draw on the same account entitlements as interactive use (https://discuss.ai.google.dev/t/is-external-orchestration-of-antigravity-cli-headless-mode-supported-with-account-based-usage/183051).

## 2. Checking remaining quota

- VERIFIED (third-party cheat sheet quoting docs, https://computingforgeeks.com/antigravity-cli-cheat-sheet/): in the interactive TUI, `/usage` (alias `/quota`) "Show model quota usage"; `/credits` shows remaining credits; `/context` shows context-window usage. These are TUI slash commands only. There is no documented non-interactive `agy` subcommand for quota (subcommands: mcp, plugin, models, agents, update, changelog, remote-control, install). `agy models` lists models (needs signed-in session).
- VERIFIED: `--output-format json` returns `usage` with input_tokens, output_tokens, thinking_tokens, cache_read_tokens, total_tokens; `stream-json` emits init / step_update / result events with token usage; in multi-turn sessions usage is cumulative. Headless page. This gives our own token accounting but not remaining account quota.
- Inference: to script a quota check, there is no documented way; try piping `/usage` via interactive session manually between batches. Config is at `~/.gemini/antigravity-cli/settings.json`; tokens are in the OS keyring (not read).
- Note: the 2-pool (Gemini vs Claude/GPT) 5h + weekly structure is visible in the model selector (VERIFIED, models page).

## 3. Terms of use for batch / automated use

- VERIFIED: FAQ (https://antigravity.google/docs/faq): "`agy -p` is intended for direct scripting and CI workflows." So running our own scripts around `agy -p` is the intended use. But "wrapping `agy` inside third-party coding agents or applications" is "not supported under consumer plans", and automating account rotation is unsupported. Using third-party tools to access the service is "a violation of our Terms of Service" and can lead to suspension or termination.
- VERIFIED: Additional Terms (https://antigravity.google/terms): s4 you are responsible for actions of an AI Agent; s6 prohibits using third-party software/tools/services to access the Service and abusing, interfering with or disrupting it; s8 third-party model terms apply. Terms do NOT address multiple accounts, rate-limit circumvention, or numeric limits.
- Verdict (inference): a harness that directly spawns `agy -p` locally on one account, sequentially or low-concurrency, is the documented scripting use and likely OK. Risk points: (a) our benchmark framework wrapping agy as a "harness adapter" could be read as the "wrapping in third-party applications" the FAQ calls unsupported on consumer plans (ambiguous; a forum thread of 2026-10-27 flags this exact conflict and has no official answer); (b) heavy sustained load could count as "abuse/disrupt". Keep it modest, never extract tokens or call backend directly, no multi-account.
- Google's recommended path for third-party agents: "a Gemini Enterprise or Google AI Studio API key" (FAQ).
- API key with agy: UNVERIFIED/contradictory. Cheat sheet says `GEMINI_API_KEY` is read when `modelProvider` is `gemini`; plans page says no BYOK "for additional rate limits"; headless docs say nothing about keys. Test on a throwaway prompt before relying on it; if it works it is pay-as-you-go and outside subscription quota.
- VERIFIED API price, Gemini 3.8 Flash (https://aistudio.google.com/docs/pricing), per 1M tokens, Standard paid tier: input $0.75, output incl. thinking $3.75, cached input $0.075 through 2026-12-31; then $1.50 / $7.50 / $0.15 from 2027-01-01. No price difference by thinking level (Low/Med/High differ only in tokens used).

## 4. Concurrency

- VERIFIED: no documented concurrent-session limit anywhere (plans, headless, FAQ). Each `agy -p` is a separate process.
- UNVERIFIED: no data on throttling thresholds. Since quota is shared per account and capacity-based, parallelism does not add quota; it only drains it faster and risks 429s. Recommendation: start at 2 parallel sessions, watch for 429/RESOURCE_EXHAUSTED in stream-json, back off.

## 5. Back-of-envelope estimate (ESTIMATE, not from Google)

Our measurements: toy run 837K in / 6K out for 2 tasks, about 420K in / 3K out per task. Real tasks 2-5x: about 0.84M to 2.1M input and 6-15K output per task-session. A CooperBench pair is probably 2 agents per task, so double again for task-pairs.

- Dollar-equivalent at API list price (no caching): per task 0.42M*$0.75 + 3K*$3.75 = about $0.33 (toy); real 2-5x = about $0.65-$1.65. With cache reads at $0.075 for most repeated context it could be several times lower. Use this as a rough "compute" measure only; subscription quota is not billed this way.
- Quota in tokens is unknown, so tasks/window cannot be computed. Parametrize: if one 5h Pro window allowed N M input tokens, task-sessions per window = N / (0.84 to 2.1). E.g. N = 10M gives about 5-12 task-sessions per window; N = 50M gives about 24-60. Pro 5h windows plus an unknown weekly cap means perhaps 2-3 windows/day at best; the weekly cap probably binds first.
- Free/consumer-free tier has a single weekly bucket (no 5h refresh): plan on a small fixed number of task-sessions per week.
- Recommended plan: run a calibration (one real task, then `/usage` before/after, manually) to get percent-of-window per task, then size the benchmark. For large runs use a GEMINI_API_KEY / AI Studio billing path: e.g. 100 real tasks at about $1.65 is about $165 worst case at list price (rates double 2027-01-01), likely far less with caching.
- Claude Sonnet/Opus 4.6 and GPT-OSS only on Free/Plus/Pro (not Ultra) and removed 2026-11-18, with a shared "Claude and GPT" pool that is separate from Gemini; budget them in the next 12 days.
