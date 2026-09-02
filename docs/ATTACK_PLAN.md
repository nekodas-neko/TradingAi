# TradingAi — Build Attack Plan (DeepSeek draft)

Generated via the `deepseek` skill (`deepseek-v4-pro`) in response to the plan in
`../NOTES.md`. This is a first-pass technical plan, not yet reviewed/adopted line
by line — treat it as a strong starting point to argue with, not gospel.

## 0. Core architecture decision

For this strategy, **do not build the first version as a purely vectorized/DataFrame backtest**.

Market structure, swing highs/lows, break of structure, order blocks, developing POC, and liquidation levels are stateful, path-dependent, and very easy to backtest incorrectly with pandas vectorization. A rule like "price breaks above the last confirmed swing high" is only valid if the swing high was actually confirmable at that time.

The cleanest way to share code across Stage 1, Stage 2, and Stage 3 is:

> **Event-driven, bar-by-bar core.**
> Indicators are stateful objects updated on each completed bar.
> Strategy consumes the latest state and emits events.
> Backtester and live engine run the same `Strategy`/`Indicator` objects.

That is the foundation for everything below.

---

## 1. Recommended tech stack and why

### Primary language
**Python 3.11+** is still the practical choice for this kind of project.

Why:

- Fast enough for 1 year of minute data if the core is event-driven.
- Excellent ecosystem for data, analytics, charting, and broker APIs.
- Easy to prototype discretionary-style systematic rules.
- Libraries: `pandas`, `pyarrow`, `ccxt`, `plotly`, `pydantic`.

### Core packages

| Area | Recommendation | Why |
|---|---|---|
| Historical data storage | **Parquet + PyArrow** | Columnar, fast range reads, typed schema, works with pandas/polars |
| Data processing | **pandas** first, **polars** if too slow | pandas is fine for 1 year of 1m/5m data; polars helps later |
| Event engine | **Custom pure Python initially** | Full control over state, bar confirmation, multi-timeframe logic |
| Fast math/indicators | **NumPy/Numba optional** | Only optimize when needed |
| Config | **YAML + Pydantic** | Typed strategy/config validation |
| Testing | **pytest + pytest-benchmark + hypotheses** | Indicators are easy to unit test |
| Live data | **ccxt / exchange WebSockets** | For crypto OHLCV, liquidations, open interest |
| Supplementary data | **TradingView webhooks / ATAS adapter** | Isolate behind provider interface |
| Live signal DB/log | **SQLite or JSONL first; Redis later** | Simple, durable, replayable |
| UI | **Dash + Plotly** or **Streamlit** | Dash better for real-time charts; Streamlit faster for internal tools |
| Versioning | **git + DVC** | DVC for data files and features |
| Experiment tracking | **MLflow or simple CSV/JSON log** | Prevents self-deception during optimization |

### Why not Backtrader/VectorBT/NautilusTrader for Stage 1?

- **Backtrader** is okay, but its abstraction can fight you when implementing custom path-dependent structural rules and multi-timeframe state.
- **VectorBT** is excellent for vectorized portfolio backtests but wrong for stateful market-structure logic.
- **NautilusTrader** is technically strong but heavyweight; it may be appropriate later for live execution, not for fast Stage 1 iteration.

Start with your own small engine. It is not that hard, and it will be exactly testable.

---

## 2. Historical data pipeline and indicator library so Stages 1–3 share code

### 2.1 Directory layout

```
TradingAi/
├── config/
│   ├── settings.yaml
│   ├── symbols.yaml
│   ├── strategy_params.yaml
│   └── live.yaml
├── data/
│   ├── raw/                    # immutable, as downloaded
│   ├── normalized/             # canonical OHLCV/liquidations/funding
│   ├── processed/              # derived bars/features, Parquet
│   └── catalog.yml
├── trading_ai/
│   ├── data/
│   │   ├── schema.py
│   │   ├── catalog.py
│   │   ├── loaders/
│   │   ├── normalizers/
│   │   └── synthetic.py
│   ├── indicators/
│   │   ├── base.py
│   │   ├── ema.py
│   │   ├── market_structure.py
│   │   ├── bos.py
│   │   ├── order_block.py
│   │   ├── poc.py
│   │   ├── volume_profile.py
│   │   └── liquidation.py
│   ├── strategy/
│   │   ├── context.py
│   │   ├── base.py
│   │   ├── signals.py
│   │   ├── rules.py
│   │   └── strategies/
│   │       └── mls_ema_poc_liq.py
│   ├── backtest/
│   │   ├── engine.py
│   │   ├── data_source.py
│   │   ├── execution_sim.py
│   │   ├── portfolio.py
│   │   ├── metrics.py
│   │   └── report.py
│   ├── live/
│   │   ├── feeds.py
│   │   ├── aggregators.py
│   │   ├── engine.py
│   │   ├── warmup.py
│   │   ├── state_store.py
│   │   └── signal_sink.py
│   ├── execution/
│   │   ├── broker.py
│   │   ├── risk.py
│   │   ├── order_manager.py
│   │   └── adapters/
│   ├── ui/
│   │   ├── charts.py
│   │   └── dashboard.py
│   └── utils/
│       └── time.py
├── tests/
├── notebooks/
└── outputs/
```

### 2.2 Canonical data schema

Freeze this early. Do not let every source create its own column names.

#### Completed bar

```python
@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str
    open_time: int          # ms UTC
    close_time: int         # ms UTC
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None
    trade_count: int | None = None
    vwap: float | None = None
    open_interest: float | None = None
    liquidations_long: float | None = None       # base qty
    liquidations_short: float | None = None      # base qty
    liquidations_long_quote: float | None = None
    liquidations_short_quote: float | None = None
    funding_rate: float | None = None
    extras: dict | None = None
```

Parquet path:

```
data/processed/bars/symbol=BTCUSDT/timeframe=5m/year=2024/month=06/part.parquet
```

Partition by symbol/timeframe/month. This makes backtest range loading fast and avoids huge files.

#### Trade/signal log

```python
@dataclass
class Signal:
    signal_id: str
    strategy_version: str
    strategy_id: str
    symbol: str
    decision_time: int      # bar close
    execution_time: int     # next bar open / live timestamp
    side: str               # LONG, SHORT, EXIT_LONG, EXIT_SHORT
    type: str               # ENTRY, EXIT, REJECTED, INFO
    price_ref: float
    stop_price: float | None
    target_price: float | None
    confidence: float
    reason: str
    metadata: dict
```

#### Liquidations

```
data/processed/liquidations/source=binance_futures/symbol=BTCUSDT/year=2024/month=06/part.parquet
```

Columns:

```
ts, symbol, side, price, qty_base, qty_quote, exchange
```

Aggregate liquidations onto bars but keep raw events.

#### Volume profile/POC

Use a separate table/Parquet:

```
data/processed/volume_profile/symbol=BTCUSDT/session_type=daily/year=2024/month=06/part.parquet
```

Columns:

```
session_id, session_start_ms, session_end_ms,
poc_price, value_area_high, value_area_low,
profile_state,       # developing | completed
profile_timestamp    # when this row was valid as of
```

> Important: **`developing` POC must only be built from bars completed up to that timestamp.**
> If you precompute the full day and then backtest with it, that is lookahead.

### 2.3 Indicator interface that works in both backtest and live

Do not write indicators as vectorized pandas functions that use `shift(-2)`.

Use stateful objects:

```python
class Indicator(ABC):
    def on_bar(self, ctx: StrategyContext, bar: Bar) -> None:
        """Update internal state from a completed bar."""

    def reset(self) -> None:
        """Reset all state."""

    def state_dict(self) -> dict:
        """Serialize state for warmup/restart."""

    def load_state(self, state: dict) -> None:
        """Restore state from a snapshot."""
```

The `StrategyContext` exposes only point-in-time values:

```python
class StrategyContext:
    current_time: int
    symbol: str
    primary_timeframe: str

    def get_latest(self, key: str) -> Any | None
    def get_history(self, key: str, n: int) -> list[Any]
    def add_indicator(self, key: str, indicator: Indicator)
```

Example:

```python
class EMA(Indicator):
    def __init__(self, period: int):
        self.period = period
        self.alpha = 2 / (period + 1)
        self.initialized = False
        self.value = None

    def on_bar(self, ctx, bar):
        if not self.initialized:
            self.value = bar.close
            self.initialized = True
        else:
            self.value = self.alpha * bar.close + (1 - self.alpha) * self.value
```

The engine calls:

```python
for bar in data_source.bars(start, end):
    ctx.on_bar_start(bar)
    strategy.on_bar(ctx, bar)
    ctx.commit(bar)  # finalize values as of bar close
```

This same loop is used in backtest and live.

### 2.4 Multi-timeframe handling

Use a **TimeframeAggregator** that consumes a base timeframe, usually 1m or 5m, and emits completed higher-timeframe bars.

Rules:

- Higher-timeframe bars are formed from lower-timeframe completed bars.
- A higher-timeframe bar is emitted only when its `close_time` is reached.
- The strategy sees only completed higher-timeframe values.

Example:

```
Primary data: 5m
Higher timeframes: 15m, 1h, 4h, 1d
```

In live mode, the same aggregator runs on WebSocket data. In backtest, it runs on historical bars.

### 2.5 Precomputed features vs streaming features

Some features should be precomputed for speed:

- Daily/weekly POC from 1m volume profile.
- Rolling liquidation volume by price bins.
- Daily/weekly open levels.

But the strategy must access them as of the correct point in time.

Prefer this design:

- **Heavy features**: precomputed into Parquet.
- **Light indicators/stateful signals**: computed inside the event engine.

Example:

- Previous completed day POC: precompute.
- Current developing POC: compute from 1m bars inside the engine if needed.
- EMA: compute inside the engine.
- Swing/BOS/order blocks: compute inside the engine.

---

## 3. Concrete Stage 1 build order

### Milestone 0 — Skeleton, config, logging, tests

**What to build:**

- Repo layout.
- YAML settings loading with Pydantic validation.
- Logging.
- Basic pytest setup.
- `StrategyContext`, `Bar`, `Signal` data classes.
- Git + DVC initialized.

**Exit criteria:**

- You can run `pytest` and an empty backtest without error.
- Config loads from YAML.
- Logs contain time, symbol, strategy version, data version.

---

### Milestone 1 — Data contract and loaders

**What to build:**

- Canonical `Bar` schema.
- Normalizer for OHLCV data.
- Parquet catalog loader.
- Synthetic data generator.

The synthetic generator should create:

- Random OHLCV bars.
- Known swing highs/lows.
- Injected BOS events.
- Artificial liquidation events.
- Known daily/weekly opens.

**Exit criteria:**

- You can load a date range from Parquet.
- You can generate synthetic 1m/5m/daily bars.
- Data validation checks pass:

```
high >= max(open, close)
low <= min(open, close)
volume >= 0
open_time < close_time
no duplicate timestamps
```

---

### Milestone 2 — Replay engine and bar aggregation

**What to build:**

- `HistoricalDataSource` that returns completed bars in chronological order.
- `TimeframeAggregator` for higher timeframes.
- Basic event loop that iterates over bars.

**No strategy yet.** The engine should just advance time and call no-op callbacks.

**Exit criteria:**

- The engine replays 1 year of 5m data deterministically.
- Higher-timeframe bars match exchange-resampled bars.
- No lookahead: engine cannot see bar `t+1` when processing bar `t`.

---

### Milestone 3 — Indicator library

Build indicators one by one with unit tests on hand-calculated data.

Priority order:

1. EMA.
2. ATR.
3. Swing highs/lows with confirmation lag.
4. Break of structure.
5. Order blocks.
6. Session POC / volume profile.
7. Rolling liquidation clusters.
8. Daily/weekly open levels.

**Swing example definition:**

A swing high is confirmed only after `N` bars close below it.

```python
swing_high = bar.high > max(previous_left_highs)
             and bar.high > max(next_right_highs)
```

In live event processing, you can only confirm it after the right side has closed.

**Exit criteria:**

- Each indicator has deterministic output for the same bar sequence.
- Each indicator has `reset()` and `state_dict()`/`load_state()`.
- No test uses future data.
- Indicators are identical when replayed vs streamed bar-by-bar.

---

### Milestone 4 — Strategy rule engine

Implement the actual trading strategy.

Start simple. For example:

- Trend filter: 5m close above 20 EMA and 20 EMA above 50 EMA for longs.
- Structure filter: confirmed bullish BOS.
- Entry zone: price retraces into the last bull order block.
- Confluence: price is within X% of previous daily POC or weekly open.
- Liquidation filter: a liquidation cluster exists near the entry.
- Exit: opposing BOS, stop below order block/ATR, target at next liquidity pool.

Make the strategy emit signals only with a reason code.

Example reason string:

```
LONG_OB_RETEST+DAILY_POC+LIQ_CLUSTER+EMA_TREND
```

**Exit criteria:**

- Strategy can run on synthetic data and produce plausible signals.
- Signals include entry, stop, target, and explainability metadata.
- No discretionary guessing inside the engine.

---

### Milestone 5 — Simulated execution and portfolio

**What to build:**

- `SimBroker` that fills orders.
- `Portfolio` that tracks cash, position, PnL, margin.
- Fee model.
- Slippage model.
- Funding if crypto perps.

Execution rules:

- Signal created at bar close.
- Market entry assumed fill at next bar open.
- Limit/stop orders checked intrabar using high/low sequence.

Example limit logic:

```
For a limit buy:
    if next_bar.open <= limit_price:
        fill_price = min(limit_price, next_bar.open)  # gap-aware
    elif next_bar.low <= limit_price:
        fill_price = limit_price
```

**Exit criteria:**

- Backtest can execute entry/exit and track PnL.
- Fee and slippage are applied.
- The system rejects unrealistic executions, e.g., entry beyond traded range.

---

### Milestone 6 — Backtest report and metrics

**What to build:**

- Trade log export.
- Equity curve.
- Drawdown chart.
- Win rate.
- Profit factor.
- Expectancy.
- Sharpe/Sortino.
- Maximum adverse excursion / favorable excursion.
- Per-symbol and per-strategy breakdown.

**Exit criteria:**

- Every backtest produces one folder:

```
outputs/backtests/
├── run_20250101_120000/
│   ├── params.yaml
│   ├── trades.parquet
│   ├── equity.parquet
│   ├── metrics.json
│   ├── drawdown.png
│   └── report.html
```

---

### Milestone 7 — Validation harness

**What to build:**

- Train/test split.
- Walk-forward runner.
- Parameter sensitivity grids.
- Monte Carlo bootstrap of trades.
- Deflated Sharpe / Probabilistic Sharpe Ratio.
- Random data benchmark.

**Exit criteria:**

- You can run one command to validate a strategy on multiple symbols and multiple splits.
- You can see which parameter regions are stable vs fragile.

---

### Milestone 8 — Iterate only after validation

Do not optimize endlessly. After validation, either:

- freeze the strategy and move to Stage 2, or
- simplify it significantly.

Most strategies fail because they are too complex for the data available.

---

## 4. How to validate that a strategy is not overfit

With only one year of data, overfitting is the biggest risk.

### 4.1 Train/test split

Do not validate on the same data used to design the rules.

Recommended split:

```
In-sample: first 7 months
Out-of-sample: last 5 months
```

But a single split is weak. Use **walk-forward**.

### 4.2 Walk-forward procedure

Example:

- Train/optimize on 6 months.
- Test on the next 1 month.
- Roll forward by 1 month.
- Repeat until data ends.

Then compare:

```
walk-forward eff. = out-of-sample net profit / in-sample net profit
```

If in-sample looks great and walk-forward is near zero or negative, the strategy is overfit.

### 4.3 Parameter sensitivity

Do not pick a single best parameter set. Plot heatmaps.

Example:

- EMA fast period: `[10, 20, 30, 40]`
- EMA slow period: `[50, 100, 150, 200]`
- Swing lookback: `[3, 5, 10, 20]`

A robust strategy has a **plateau**, not one sharp green cell.

If the only profitable cell is `EMA fast=37, slow=183, swing=17`, it is almost certainly noise.

### 4.4 Bootstrap and Monte Carlo

Take the actual trade list and resample it thousands of times. Compute:

- 5th/95th percentile Sharpe.
- Probability of max drawdown worse than observed.
- Probability that win rate is due to luck.

Also shuffle entries randomly on the same price data and compare.

If random entries perform similarly, the edge is not strong.

### 4.5 Deflated Sharpe / Probabilistic Sharpe Ratio

Implement or use the methods from Bailey and López de Prado.

A raw Sharpe of 1.5 after 100 parameter combinations may not be significant.

Track:

```
number of strategies tested
expected max Sharpe under multiple testing
deflated Sharpe
Probabilistic Sharpe Ratio / false-discovery rate
```

### 4.6 Synthetic adversarial data

Run the strategy on:

- Random walk data.
- Trendless range data.
- Inverted price data.
- Permuted return data.

This reveals hidden lookahead or curve-fit logic.

---

## 5. Pitfalls specific to combining market-structure/EMA/POC/liquidation rules

This is where most projects die.

### 5.1 Market structure repainting

Do not write:

```python
df['swing_high'] = df['high'] > df['high'].shift(1) & df['high'] > df['high'].shift(-1)
```

This uses `shift(-1)`, i.e. the future.

In live trading, a swing high is not known until several bars later.

Your backtester must explicitly delay confirmation:

```
bar t: possible swing high
bar t+1: no action
bar t+2: swing confirmed only after close
```

### 5.2 Break of structure must be close-confirmed

Define whether BOS is based on:

- wick close
- body close
- close below low
- close below previous low with volume

Be exact.

Example:

> A bullish BOS occurs when a 5m bar closes above the last confirmed swing high.

If you use intra-bar high, you introduce lookahead or ambiguity.

### 5.3 Order blocks are discretionary by nature

Traders often draw order blocks differently.

You must define an algorithm.

Example:

- After a bullish BOS, find the last down candle before the impulse.
- Its high/low become the order block.
- Invalidation = low of that block.
- Entry = price re-enters the block and close back above the block high.

If you cannot write the algorithm in code, it is not ready for backtesting.

### 5.4 EMA calculations on the current bar

Using the current bar's EMA before its close causes repainting.

Example:

```python
ema_value = compute_ema(history.including_current_unfinished_bar)
```

Your strategy should use:

```python
ema_value = ctx.get_latest("ema_20_5m")  # only completed bars
```

### 5.5 POC lookahead

A daily POC is not known until the daily session closes.

If you use the full day's POC on an intraday backtest, you are cheating.

Two valid choices:

1. Use **previous session POC** only.
2. Use **developing session POC** computed only from completed bars so far.

Choose one and enforce it in both backtest and live.

### 5.6 Liquidation data quality

TradingView/ATAS liquidation data is often:

- derived or estimated;
- delayed;
- restated after the fact;
- not true order flow.

Treat it as a **sentiment/flow feature**, not as precise exchange truth.

If you download historical liquidation data after the fact, verify it is point-in-time.

> Note for this project specifically: the Bybit historical dataset already pulled
> (see `../NOTES.md`) has **no liquidation data at all** — Bybit has no free
> historical liquidation archive. So this pitfall applies doubly: for
> backtesting, liquidation confluence either needs a proxy (CVD/OI/book-imbalance
> derived) or has to be dropped until live data is wired up in Stage 2.

### 5.7 Volume profile from OHLCV is approximate

If you do not have actual volume-by-price data, volume profile is an approximation.

Common hack:

- Assign each bar's volume to its typical price.
- Or distribute bar volume uniformly between high and low.

This is acceptable for a first version, but it is not true market profile.

> Note: the pulled dataset is 5-second bars with book-imbalance and trade
> aggregates (not raw trade-by-trade), so POC/volume-profile computed from it
> will be more granular than daily-bar approximations, but still bucketed —
> real volume-at-price precision is bounded by the 5s resolution.

### 5.8 Multiple timeframes can leak

When combining 5m, 15m, 1h, daily, and weekly levels, ensure each value is only available after its parent bar closes.

Example:

- A weekly open is known at the start of the week.
- A weekly high/low is not known until the week closes.
- A developing weekly POC is not valid unless computed only from completed bars.

### 5.9 Too many confluence conditions

This may look smart:

```
EMA aligned
+ BOS
+ order block
+ daily POC
+ weekly open
+ liquidation cluster
+ volume spike
```

But every condition adds a parameter and reduces sample size.

Start with 2–4 conditions. Add more only if out-of-sample performance improves materially.

---

## 6. Bridging Stage 1 to Stage 2 cleanly

### 6.1 Data source abstraction

Define an interface that both backtest and live use:

```python
class DataSource(Protocol):
    def historical_bars(self, symbol, timeframe, start, end) -> Iterable[Bar]:
        ...

    def subscribe(self, symbol, timeframe) -> AsyncIterable[Bar]:
        ...
```

Backtest uses `historical_bars`. Live uses `subscribe`.

The rest of the engine does not care.

### 6.2 Same engine loop

Backtest:

```python
engine.run_historical(data_source, strategy, start, end)
```

Live:

```python
engine.run_live(data_source, strategy)
```

Inside both:

```python
for bar in data_source.bars():
    ctx.advance(bar)
    strategy.on_bar(ctx, bar)
    signal_sink.handle(strategy.signals)
```

### 6.3 Warmup

A live strategy cannot start cold.

If EMA 200 needs 200 bars, and order blocks need prior swing levels, you must warm up.

Pipeline:

1. Replay historical data until `now - 1 bar`.
2. Save `strategy.state_dict()`.
3. Start live WebSocket feed.
4. Load state and continue.

This guarantees that Stage 2 starts with the same state as a Stage 1 backtest that ended at the same time.

### 6.4 Signal logging

Log every signal to SQLite/JSONL/Parquet:

```
ts, symbol, signal_id, side, type, reason, price_ref, stop, target,
strategy_version, data_version, state_hash
```

This lets you compare forward signals against backtest expectations.

### 6.5 Data versioning

If historical data is restated or indicator code changes, signals are not comparable.

Store with every signal:

- `strategy_version`
- `indicator_version`
- `data_version`
- `config_hash`

### 6.6 Live chart UI

For Stage 2, keep UI read-only.

Recommended approach:

- Live engine writes signals to SQLite/JSONL.
- Dash/Plotly reads from that store.
- Chart shows candlesticks, EMAs, swing levels, order blocks, POC, liquidation clusters, and recent signals.

Do not let the UI execute or modify orders.

### 6.7 Staleness and feed monitoring

If the live feed disconnects:

- Stop emitting signals.
- Set status `STALE`.
- Do not treat missed bars as confirmed signals.

The engine should detect gaps and require warmup after a reconnect.

---

## 7. Risk-management and execution considerations before Stage 3

You should not reach Stage 3 until paper signals match backtest behavior and execution assumptions are realistic.

### 7.1 Realistic backtest execution

Before automation, backtest execution must include:

- Taker fees.
- Slippage.
- Spread.
- Partial fills.
- Funding for perpetuals.
- Borrow costs if applicable.
- Exchange downtime.
- Limit order queue behavior if you use maker orders.

Stress-test with:

```
slippage = 1 bps
slippage = 5 bps
slippage = 10 bps
fee = 0.04%
fee = 0.08%
```

If the strategy dies at 5 bps slippage, it is not executable.

### 7.2 Choose broker/exchange based on data, not preference

Since liquidation and order-flow data are central, **crypto perpetuals are the path of least resistance**.

Good candidates:

- Binance Futures / Testnet
- Bybit USDT Perpetual / Testnet
- OKX Perpetual

They provide:

- OHLCV.
- Liquidation events or aggregated liquidations.
- Open interest.
- Funding.
- Paper trading.

For traditional futures:

- CQG/Rithmic for order flow.
- Interactive Brokers for execution.
- ATAS for market profile/footprint.

But liquidation data is not native to traditional futures.

> Given the historical dataset is Bybit perps (BTCUSDT/ETHUSDT/SOLUSDT), Bybit
> USDT Perpetual (with testnet for paper trading) is the natural default for
> Stage 3 unless there's a reason to switch — it keeps historical, live, and
> execution data on the same venue with the same symbol conventions.

### 7.3 Risk engine must be separate from strategy

Never let the strategy decide position size directly.

Risk engine inputs:

```
account_equity
max_risk_per_trade  = 0.5%
daily_loss_limit    = 3%
max_leverage        = 2
max_correlated_exposure
```

Example position size:

```python
qty = (equity * risk_per_trade) / (entry - stop)
```

### 7.4 Stop-loss and take-profit management

Use exchange-native order types where possible:

- Stop-market for stops.
- Limit reduce-only for targets.
- Reduce-only flag on all exits.

Avoid mental stops in automated execution.

### 7.5 Order manager and idempotency

Every order gets a client-generated ID:

```
client_order_id = f"{strategy_id}_{signal_id}_{side}"
```

If the network fails after sending an order, retry with the same `client_order_id`.

Never blindly resend without checking order status.

### 7.6 Position reconciliation

On startup and after reconnects:

1. Fetch open positions from the exchange.
2. Fetch open orders.
3. Reconcile with local portfolio state.
4. Resolve differences manually or automatically with strict rules.

### 7.7 Kill switch

Implement two types:

- **Manual kill switch**: one command/button cancels all orders and flattens.
- **Automatic kill switch**: triggered by:

```
daily loss > 3%
equity drawdown > 10% from peak
heartbeat timeout > 30s
position size mismatch
```

### 7.8 Paper trading first

Stage 2 is not enough. You need **Stage 2.5**: automated paper trading.

Run the system exactly as it would trade live, but with a testnet/paper broker.

Forward paper trade for at least a few weeks or months, depending on trade frequency.

Track:

- Signal timestamps.
- Order entry/exit timestamps.
- Slippage vs backtest assumption.
- Latency.
- Unexplained missed fills.

Only then consider real money.

---

## Final sequence recommendation

### Stage 1 first month

1. Freeze symbol universe and data format.
2. Build synthetic data.
3. Build event engine.
4. Build market structure indicators.
5. Build strategy.
6. Build execution sim.
7. Run first backtest.
8. Run walk-forward.
9. Simplify strategy.
10. Final validation.

### Stage 2 second/third month

1. Put engine behind data source abstraction.
2. Add live WebSocket feed.
3. Add warmup.
4. Log signals.
5. Build live chart UI.
6. Run paper signals.

### Stage 3 only after Stage 2.5

1. Connect paper broker.
2. Reconcile orders/positions.
3. Run automated paper trading.
4. Review execution quality.
5. Enable real execution with tiny size.
6. Ramp up only after live metrics match backtest ranges.

The single most important rule is:

> **Make the backtest and live path identical. Any divergence will be exploited by overfitting and hidden lookahead.**

---
*(DeepSeek tokens — prompt: 602, completion: 19382, total: 19984)*
