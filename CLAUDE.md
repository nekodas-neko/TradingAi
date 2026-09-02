# TradingAi — Claude Code Context

A systematic/discretionary crypto trading strategy: backtester now, live signals next,
automated execution last — once each stage proves out on the one before it. Full picture:
[`NOTES.md`](NOTES.md) (project state, data, stages, open decisions) and
[`docs/ATTACK_PLAN.md`](docs/ATTACK_PLAN.md) (a DeepSeek-drafted technical build plan — a strong
starting point to argue with, not yet adopted line by line). Read both before writing code; this
file is the standing rules, not a restatement of either.

Stack is not finalized yet (see NOTES.md "Open decisions") — `ATTACK_PLAN.md` recommends
Python 3.11+ with Parquet/PyArrow, pandas, Pydantic, pytest. Nothing below assumes that choice is
final; update this file once it is.

---

## Session workflow

- **Rely on Claude Code's automatic context compaction — don't write a handoff doc just because
  context is getting long.** Keep working in the same session; compaction summarizes older turns
  as needed and cached tokens keep working for you. Write a handoff doc (`docs/handoff-*.md`, or
  just a clear closing summary if the skill isn't installed here) only when a session is ending for
  a real reason: the user says so, the work is being handed to a different session/person, or the
  session is lost outside your control.
- **State what was NOT verified, every time.** This project's entire value is in not fooling
  itself — a backtest result, an indicator's output, or a strategy signal that "looks right" but
  wasn't checked against hand-calculated values or a synthetic-data test is exactly the kind of
  claim that costs real money later. When reporting work, say plainly which paths were exercised
  (unit test, synthetic data, a real historical slice) and which were not.
- **Never mark something fixed or validated from intent.** Only say a backtest/indicator/strategy
  change works after actually running it and looking at the output — not because the code "should"
  produce the right result.

## No lookahead bias — the project's single most important rule

Distilled from `docs/ATTACK_PLAN.md` §5, which has the full detail and worked examples. Read it
before touching any indicator or strategy code; this is the compressed version to hold in mind
every time:

- **Never compute an indicator, swing point, break-of-structure, order block, or POC using data
  from after the timestamp the strategy is deciding at.** No `.shift(-N)`, no "full day's POC" fed
  into an intraday backtest, no EMA computed on an unfinished current bar.
- **A market-structure level is only usable once it would have been *confirmable* at that time** —
  a swing high needs the bars to its right to have actually closed; a weekly high/low isn't known
  until the week closes; a "developing" POC/profile is built only from bars completed so far.
- **The backtest and the live path must run the same indicator/strategy code**, not a fast
  vectorized backtest version and a separate live version — divergence between the two is exactly
  where hidden lookahead hides.
- **If an algorithm can't be written in code precisely** (e.g. "where a trader would draw an order
  block"), it is not ready to be backtested — pin down the exact rule first.
- Before trusting a backtest result: check it against a walk-forward split (not just one
  in-sample/out-of-sample split), and be suspicious of a strategy whose only profitable parameters
  are one sharp point rather than a stable region — see `ATTACK_PLAN.md` §4 for the full validation
  methodology (walk-forward, parameter sensitivity, bootstrap, deflated Sharpe, adversarial/random
  data).

## AI output, risk, and fail-closed defaults

- **No LLM-generated number may gate an automated decision, or be shown to the user as fact.** A
  model's confidence score, sentiment read, or "this looks like a good entry" judgment does not
  decide position size, order placement, or risk limits — that math is deterministic and lives in
  code. This matters more here than in most projects: an LLM being wrong about a trade is a
  financial loss, not a UI glitch.
- **The risk engine is separate from the strategy and the strategy never sizes its own positions.**
  Position sizing, max risk per trade, daily loss limits, and max leverage are computed by one
  risk-engine component every strategy goes through — never inline in strategy/signal code. See
  `ATTACK_PLAN.md` §7.3 for the shape of this.
- **No silent fallback on a failed data fetch, indicator computation, or order action.** Log and
  surface the failure; never swallow an exception and continue as if nothing happened — a strategy
  silently running on stale or partial data is worse than one that stops.
- **Security/auth checks (broker API keys, webhook secrets, any live-trading credential) fail
  closed.** A missing or invalid credential is a rejection, never a skip that lets a request through
  unauthenticated.
- **Before going live with real money, Stage 3 needs both a kill switch (manual and automatic:
  daily-loss/drawdown/heartbeat-timeout triggers) and idempotent order handling (client-generated
  order IDs, position reconciliation after any reconnect).** See `ATTACK_PLAN.md` §7.5–7.7. Never
  build straight from paper/backtest to live execution without these in place.

## Data integrity

- **The historical/live data path is a config value (env var or config file), never hardcoded** —
  the pulled dataset lives on whichever machine ran the pull (see `NOTES.md` "Data"), not in this
  repo, and that will vary by machine.
- **Freeze the canonical bar/signal schema early and don't let each data source invent its own
  column names** — normalize at the loader boundary. See `ATTACK_PLAN.md` §2.2 for the schema this
  project has already sketched.
- **Data validation on load, not on trust**: `high >= max(open, close)`, `low <= min(open, close)`,
  no duplicate timestamps, `open_time < close_time`. A silently malformed bar corrupts every
  indicator built on it downstream.

## Decisions That Come Back To Me

Most choices (file layout, which indicator/library to reach for, two equivalent implementations)
are yours to make — state what you picked and why in one line, then continue. Bring back only what
is genuinely hard or expensive to reverse: the primary language/stack, the broker/exchange for live
execution, real trading credentials, or anything that risks real money. When you do bring one back:

1. **The recommendation, first line** — one named option, not a menu.
2. **Why**, framed a year out — what it costs to live with, not just what's fastest today.
3. **Alternatives**, each with the reason it lost and what it would genuinely be better at.
4. **Reversal cost** — if this is wrong in three months, what does undoing it take?
5. **Plain English** — assume the reader knows the strategy cold and the internals not at all.

Keep it under a minute's reading. Never manufacture a trade-off if one option is just correct.

## General engineering hygiene

- Don't add abstractions, config knobs, or error handling for scenarios that can't happen yet —
  this project has three explicit stages for a reason; don't build Stage 3's execution layer while
  still validating Stage 1's edge.
- **Sibling-surface sweep**: a fix or convention change to one indicator/strategy component applies
  to its siblings in the same PR (e.g. a confirmation-lag fix to swing-high detection almost
  certainly applies to swing-low too).
- **No orphaned findings**: anything found wrong or missing while working (a data gap, a lookahead
  bug, a missing validation) gets written down — a NOTES.md/backlog line at minimum — in the same
  session, not left to be rediscovered later.

## Safety & Reversibility

- Never commit API keys, exchange credentials, or `.env` files. `DEEPSEEK_API_KEY` and any future
  broker/exchange key stay out of git — the `deepseek` skill already reads from environment or the
  git-ignored `.claude/settings.local.json` for exactly this reason.
- Confirm before any action with real money or real external effect: placing a live or testnet
  order, enabling automated execution, or rotating/regenerating a credential. Backtesting, writing
  code, and running against historical data need no such confirmation.
- Never force-push or rewrite history on a shared branch without being asked.

## Git & package management (once code exists)

No CI or package manifest exists yet — this section is intentionally light until Milestone 0
(`ATTACK_PLAN.md` §3) sets up the repo skeleton. Once it does:

- Feature branches with names that describe the change, not generated names.
- Commit messages explain *why*, not what (the diff shows what).
- Once a lockfile exists (`requirements.txt`/`poetry.lock`/`uv.lock` or equivalent), commit it in
  the same commit as any dependency change — don't let it drift from what's actually installed.
