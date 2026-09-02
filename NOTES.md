# TradingAi — Project Notes

## What this is

A system for developing, testing, and eventually automating a discretionary-style
trading strategy that's been made systematic. The strategy looks for price
reactions at key market-structure levels rather than a single indicator crossover.

The end goal: a bot that trades on its own, with no user input, once the
underlying method has been proven profitable on historical data and validated
on live signals first.

## Signals / rules under investigation

The strategy centers on how price reacts at these reference levels:

- **Market structure** — swing highs/lows, break of structure, order blocks
- **EMAs** — reactions/rejections at key moving averages
- **POC** (Point of Control, from volume profile)
- **Weekly / daily opens** — reaction around the open price of the current week/day
- **Liquidations / order flow** — from TradingView and ATAS (liquidation levels,
  footprint/order flow data)

These aren't finalized — stage 1 is exactly where we figure out which of these,
combined how, actually produce an edge.

## Data

- **Historical data**: a year of historical market data is being downloaded to
  local disk by a separate agent/process running outside this environment. This
  repo does not yet contain that data or know its exact path/format — treat the
  data location as a config value (e.g. an env var or config file), not a
  hardcoded path, so whichever machine actually runs the backtester can point at
  wherever the data lands locally.
- **Live/supplementary data**: TradingView and ATAS for order flow, liquidations,
  and volume profile (POC) — these aren't standard OHLCV, so we'll need either a
  manual export/import path or an API/webhook integration per source.

## Stages

### Stage 1 — Backtester (current focus)
A working backtester that:
- Loads historical OHLCV (and eventually order-flow/volume-profile) data from
  local disk
- Lets us define/compose indicators (EMAs, POC, market structure detection,
  weekly/daily open markers)
- Lets us define entry/exit rules against those indicators
- Runs a strategy over historical data and reports:
  - Trade log (entry/exit price, time, direction, size)
  - Win/loss ratio
  - P&L / equity curve
  - Other standard stats (max drawdown, avg R, expectancy, etc.)
- Purpose: iterate on the rule set quickly until we have something with a real
  edge, before risking anything live.

### Stage 2 — Live signals
Once a rule set backtests well:
- Run the same rule engine against live/streaming data
- Surface trade signals (not execution) — a live chart view showing what the
  system *would* trade, so we can shadow-test it against real-time conditions
  before trusting it with money
- Same win/loss tracking as backtest, but on forward (live) data

### Stage 3 — Automated execution
Once live signals prove out:
- Wire signal generation to an execution layer (broker/exchange API) that
  actually places and manages orders (entries, exits, stops) with no manual
  input required

## Architecture (proposed, not yet built)

Rough separation of concerns, so stage 1 code is reusable in stages 2 and 3
rather than rewritten:

```
data/          # loading historical data, normalizing formats (OHLCV, order flow, POC)
indicators/    # EMA, market structure detection, POC, weekly/daily open calculation
strategy/      # rule definitions — entry/exit logic composed from indicators
backtest/      # backtest engine: runs strategy over historical data, computes stats
signals/       # stage 2: live rule evaluation, signal output
execution/     # stage 3: order placement/management against a broker/exchange API
ui/            # chart view — historical backtest visualization now, live view later
```

The same `strategy/` and `indicators/` code should run unchanged across the
backtester, live signal generator, and eventually the execution layer — only the
data feed and the output side (report vs. live chart vs. order placement)
should differ per stage.

## Open decisions (not yet made)

- **Language/stack** — not chosen yet. Python is the natural fit for this kind
  of work (pandas/numpy for data handling, mature backtesting libraries,
  broker/exchange SDKs for stage 3) but this hasn't been confirmed.
- **Historical data format/location** — depends on what the other agent is
  downloading (file format, path, symbols/timeframes covered). Needs to be
  confirmed before stage 1 can actually load real data.
- **Broker/exchange for stage 3** — not chosen; depends on what market(s) the
  strategy targets (crypto, futures, forex, etc.), which affects what ATAS/order
  -flow data is even relevant.
- **UI approach for the chart view** — not decided (web app, desktop app, or
  reusing an existing charting library/platform).
