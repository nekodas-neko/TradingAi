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

### Historical training data (handoff from a separate local agent)

A separate Claude Code agent, running locally (not in this remote sandbox), pulled
and validated a year of Bybit historical market-state data using a purpose-built
tool. This repo does not contain that data — it lives on the local machine that
ran the pull — so the backtester's data path must be a config value (env var /
config file), never hardcoded, so it can point wherever the data actually sits
on whichever machine runs it.

| Property | Value |
|---|---|
| Symbols | BTCUSDT, ETHUSDT, SOLUSDT (linear perps) |
| Range | 2025-09-01 → 2026-08-31 (365 days each) |
| Resolution | 5 seconds → 17,280 rows/day |
| Partitions | 1,095 (365 × 3), 0 failed / 0 unavailable |
| Format | Parquet, hive-partitioned, SHA-256 manifest + schema hash per partition |
| Total size | ~2.5 GB |
| Schema version | `market-state-v1` |

**Location** (local machine, Windows path):
```
D:\Projects\TradingTrainingData\market-state\
  symbol=BTCUSDT\year=2025\month=09\day=01\market_state_5s_2025-09-01.parquet
  ... (same tree for ETHUSDT, SOLUSDT)
```
Hive partitions: `symbol={SYM}/year={YYYY}/month={MM}/day={DD}/`. Each day dir
holds one `market_state_5s_{date}.parquet` plus a `manifest.json` (SHA-256,
schema hash, builder version).

**Schema (35 columns)**:
- Timestamp/identity: `TimestampMs` (ms epoch UTC bucket start), `Symbol`, `IntervalSeconds`
- Price/book: `BestBidPrice`, `BestAskPrice`, `MidPrice`, `MicroPrice`, `Spread`,
  `SpreadBps`, `BidSizeLevel1`, `AskSizeLevel1`, `BidSizeTop5`, `AskSizeTop5`,
  `BidSizeTop20`, `AskSizeTop20`, `BookImbalanceLevel1`, `BookImbalanceTop5`,
  `BookImbalanceTop20`, `OrderBookUpdates`, `LastUpdateId`
- Trades (aggregated per 5s bucket): `TradeCount`, `TradeVolume`, `BuyVolume`,
  `SellVolume`, `TradeNotional`, `Vwap`, `TradeOpen`, `TradeHigh`, `TradeLow`,
  `TradeClose`, `CvdDelta` (cumulative-volume-delta change)
- Derived/external: `OpenInterest`, `HasOpenInterest`, `FundingRate`, `HasFundingRate`
  (the `Has*` flags mark buckets where OI/funding were unavailable — those are
  sampled less often than every 5s)

**No liquidation data** — Bybit has no free historical liquidation archive, so
none was fabricated or included. This directly affects the strategy: the
liquidation/order-flow confluence rules (see Signals above) can't be backtested
against this dataset as-is. Options: source liquidations from ATAS/another paid
provider for backtesting, approximate liquidation pressure from `CvdDelta` +
`OpenInterest` deltas + book imbalance, or drop liquidation confluence from the
backtested rule set and treat it as a live-only overlay once Stage 2 has real
ATAS/TradingView feeds.

**How it was produced**: `TrainingDataBuilder` (https://github.com/jsboiss/TrainingDataBuilder,
.NET 10, Parquet.Net 6.0.3), run per symbol, e.g.:
```powershell
dotnet run --project src/TrainingDataBuilder -- `
  --symbol BTCUSDT --start 2025-09-01 --end 2026-08-31 `
  --interval-seconds 5 --parallelism 4 `
  --output "D:/Projects/TradingTrainingData"
```
Pipeline per day: download Bybit archives → reconstruct L2 order book → aggregate
5s market-state rows → validate coverage → write one atomic Parquet partition +
manifest → delete raw archives. Sources (public, no API key): order book from
`quote-saver.bycsi.com`, trades from `public.bybit.com`, OI/funding from
`api.bybit.com/v5/market/*`. Resume-safe (checksum-validated partitions are
skipped); supports more symbols, different date windows, `--overwrite`,
`--keep-raw`, and a `--dashboard` web UI. Output root is overridable via
`--output` or `TRAINING_DATA_ROOT` env var — useful since the documented default
(`B:\Dev\TradingTrainingData`) doesn't exist on the machine that ran this.

**Next steps flagged by that agent** (not yet done):
1. Load a partition and verify exact Parquet column names/types (pyarrow or
   Parquet.Net) match this schema.
2. Feature engineering + label derivation (future returns / direction / regime).
3. Train/val/test split — must respect time order (data is chronological per
   symbol); this lines up with the walk-forward validation approach below.

### Live/supplementary data

TradingView and ATAS for order flow, liquidations, and volume profile (POC) —
these aren't standard OHLCV, so we'll need either a manual export/import path or
an API/webhook integration per source. Liquidations in particular aren't in the
historical dataset above, so this is also where liquidation confluence rules
would first get real data, in Stage 2.

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
- **Historical data format/location** — resolved, see Data section above
  (Parquet, hive-partitioned, on a local Windows machine). Still open: no
  liquidation data is included, so the liquidation-confluence rule needs a
  fallback (proxy features, or live-only) until a real source is wired up.
- **Broker/exchange for stage 3** — not chosen; depends on what market(s) the
  strategy targets (crypto, futures, forex, etc.), which affects what ATAS/order
  -flow data is even relevant.
- **UI approach for the chart view** — not decided (web app, desktop app, or
  reusing an existing charting library/platform).
