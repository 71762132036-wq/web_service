# Gamma Analytics Platform — Chart & Signal Guide

A professional-grade options analytics dashboard built for intraday Nifty/BankNifty/Sensex trading. This guide explains how to read every chart and extract actionable trading insights.

---

## Table of Contents

1. [Quick Start Workflow](#quick-start-workflow)
2. [Key Concepts](#key-concepts)
3. [Metric Cards](#metric-cards)
4. [Exposure Charts](#exposure-charts)
5. [Volatility Charts](#volatility-charts)
6. [Open Interest Charts](#open-interest-charts)
7. [Others](#others)
8. [Advanced Charts](#advanced-charts)
9. [Signal Engine](#signal-engine)
10. [God Tier Charts](#god-tier-charts)
11. [Compare Mode](#compare-mode)
12. [Color Legend](#color-legend)

---

## Quick Start Workflow

**Before market open:**
1. Load the latest data file or fetch live data
2. Check **Metric Cards** — Spot, Flip Point, Regime, Quant Power
3. Open **Gamma Exposure** chart to see where dealer walls sit
4. Check **Max Pain** for the day's pin target
5. Open **Signals > Composite Score** for move probability

**During market hours:**
1. Fetch new snapshots every 3-5 minutes
2. Watch **Flip Proximity** — if distance drops below 0.3%, prepare for regime change
3. Monitor **Wall Decay** — dying walls mean breakouts are coming
4. Check **IV Divergence** — IV rising while spot falls = protection buying = drop ahead
5. Use **OI Buildup** to confirm direction: Short Covering on puts = rally fuel

**Decision framework:**
- Composite Score 60+ = high probability move within the session
- Composite Score 40-59 = elevated, wait for confirmation from OI or IV
- Below 40 = range-bound, sell premium or wait

---

## Key Concepts

### Dealer Perspective
All exposure charts show the **dealer's position**, not the buyer's. Dealers are short options, so:
- **Positive GEX (Indigo bars)** = Dealers are long gamma at this strike = they hedge by selling rallies and buying dips = **MEAN REVERSION / STABILIZING**
- **Negative GEX (Rose bars)** = Dealers are short gamma = they hedge by buying rallies and selling dips = **TREND ACCELERATION / FUEL**

### Flip Point (Zero Gamma)
The strike where dealer GEX crosses from positive to negative. This is the single most important level on the board.
- **Spot ABOVE Flip** → Long Gamma regime → Mean reversion expected → Sell straddles, sell breakouts
- **Spot BELOW Flip** → Short Gamma regime → Trend/momentum expected → Buy breakouts, trail stops

### Gamma Cage
A range of strikes around ATM (default ±4 strikes × 50pts = ±200pts for Nifty) where dealer gamma is concentrated. Price tends to oscillate within this cage during Long Gamma regimes. Outside the cage is the **Vacuum Zone** where price can move freely.

### Power Zones
The top 3 strikes by absolute GEX. These are the strongest support/resistance levels on the board. Highlighted as amber vertical bands on all exposure charts.

---

## Metric Cards

Displayed at the top of the dashboard for every index.

| Metric | What It Tells You | Trading Action |
|--------|-------------------|----------------|
| **Spot** | Current underlying price | Reference point for all levels |
| **Flip Point** | Zero gamma crossing | Above = sell premium; Below = buy breakouts |
| **Flip Distance** | How far spot is from flip (%) | Below 0.3% = regime change imminent |
| **Regime** | LONG GAMMA or SHORT GAMMA | Determines your entire strategy bias |
| **Quant Power** | Blended GEX + Vanna equilibrium | The strike where cumulative dealer delta = 0; gravitational center |
| **Cum GEX** | Total gamma across all strikes | Positive = market is stabilized; Negative = market is volatile |
| **Cum DEX** | Total delta across all strikes | Shows net directional dealer tilt |
| **Max Pain** | Strike minimizing option holder gains | End-of-day pin target; strongest on expiry day |
| **Pin Risk** | Probability of pinning at max pain | High near expiry with high OI concentration |
| **PCR (Vol)** | Put-Call Ratio by volume | Above 1.2 = bearish flow; Below 0.7 = bullish |
| **PCR (OI)** | Put-Call Ratio by open interest | Accumulation signal; divergence from PCR Vol = smart money |

---

## Exposure Charts

### Gamma Exposure (GEX)

**Bucket:** Exposure > Gamma > Gamma Exposure

**What it shows:** Per-strike dealer gamma exposure as a bar chart. Indigo bars = stabilizing gamma (positive). Rose bars = fuel/trending gamma (negative). The pale yellow filled line on the secondary axis shows absolute gamma heat.

**Formula:** `GEX = -gamma × OI × lot_size × spot² × 0.01`

**How to read it:**
- The tallest indigo bar is the strongest resistance (dealers sell into rallies there)
- The tallest rose bar is where breakdowns accelerate
- The amber vertical bands mark Power Zones (top 3 by absolute GEX)
- The amber vertical line = Spot, the white dotted line = Flip Point

**Trading insight:**
- If spot is sitting right on a tall indigo bar → expect mean reversion → fade breakouts
- If spot is between two tall rose bars → expect acceleration → buy momentum
- Concentration on one side (all positive or all negative) = strong directional conviction from dealers

### Cumulative GEX

**Bucket:** Exposure > Gamma > Cumulative GEX

**What it shows:** Running sum of GEX from lowest to highest strike. The line on the secondary axis shows the cumulative curve.

**How to read it:**
- Where the cumulative line crosses zero = **Flip Point**
- The slope at the spot price tells you how sensitive the market is to the next point of movement
- Steep upward slope = each tick of movement triggers massive dealer hedging = high sensitivity
- Flat slope = dealers are balanced, price moves freely

**Trading insight:**
- If the curve is steeply positive above spot → strong gamma ceiling → sell calls
- If the curve plunges negative below spot → gamma vacuum → buy puts for acceleration
- Compare the curve shape across sessions — a flattening curve means gamma is dissipating

### Volume-Weighted GEX (VWGEX)

**Bucket:** Exposure > Gamma > Volume-Weighted

**What it shows:** GEX adjusted by the Volume/OI ratio at each strike. This separates **live walls** (fresh positioning today) from **ghost walls** (legacy OI with no active trading).

**Formula:** `VWGEX = GEX × (Volume / OI)`

**How to read it:**
- A strike with high GEX but low VWGEX = **ghost wall** (nobody is defending it — it will break)
- A strike with high VWGEX = **live wall** (active trading is reinforcing it)
- Compare VWGEX to standard GEX — divergences reveal which walls are real

**Trading insight:**
- Never trust a gamma wall that isn't backed by volume
- If the largest GEX wall has declining VWGEX across snapshots → it's about to break → position for the breakout
- Fresh VWGEX walls forming away from spot = institutional positioning → follow them

### GEX Decay (DTE-Normalized)

**Bucket:** Exposure > Gamma > GEX Decay (DTE)

**What it shows:** GEX adjusted for time-to-expiry inflation. Near-expiry gamma is naturally inflated (gamma spikes as DTE → 0). This chart normalizes it to show structurally real walls.

**Formula:** `Decay_GEX = GEX × min(1.0, sqrt(DTE / 7))`

**How to read it:**
- On weekly expiry day (DTE ≤ 1), decay factor is ~0.38 — most "walls" shrink to a third of their apparent size
- Walls that remain prominent even after decay adjustment are **structurally real** (carried by OI mass, not gamma inflation)
- Compare original GEX bars to decay-adjusted bars — the difference is what evaporates at expiry

**Trading insight:**
- On expiry morning, only trust Decay-GEX walls, not raw GEX
- If a wall looks huge in raw GEX but vanishes in Decay GEX → it's a theta mirage → don't respect it
- Mid-week (DTE ≥ 7), decay factor = 1.0, so this chart matches raw GEX exactly

### Delta Exposure (DEX)

**Bucket:** Exposure > Delta > Delta Exposure

**What it shows:** Per-strike dealer delta exposure. Delta is directional — it tells you how much the dealer's hedge position shifts per point of underlying movement.

**Formula:** `DEX = -delta × OI × lot_size × spot`

**How to read it:**
- Positive DEX = dealers need to BUY to maintain hedges = supportive
- Negative DEX = dealers need to SELL = creates resistance
- The net sum across all strikes = Cumulative DEX = directional dealer tilt

**Trading insight:**
- Large positive DEX at a strike below spot = strong support
- Large negative DEX above spot = ceiling
- If Cum DEX is strongly positive → dealers are net long → supportive for underlying
- DEX shifts faster than GEX during trending markets — watch it for confirmation

### Cumulative Delta

**Bucket:** Exposure > Delta > Cumulative Delta

**What it shows:** Running sum of dealer delta from lowest to highest strike.

**Trading insight:**
- If the cumulative line is rising steeply as you approach spot from below → strong dealer buying pressure → support
- If it's declining steeply above spot → strong dealer selling pressure → resistance

### Gamma × Delta Combined

**Bucket:** Exposure > Greek Interaction > Gamma × Delta

**What it shows:** Overlay of GEX and DEX on the same chart, allowing you to see where gamma walls align with delta walls.

**Trading insight:**
- Strikes where both GEX and DEX are strongly positive = **fortress levels** (extremely hard to break)
- Strikes where GEX is positive but DEX is negative (or vice versa) = conflicting signals = weaker levels

### Vanna Exposure (VEX)

**Bucket:** Exposure > Vanna > Vanna Exposure

**What it shows:** Dealer vanna exposure — sensitivity of delta to changes in implied volatility.

**Formula:** `VEX = -vanna × OI × lot_size × spot × 0.01`

**How to read it:**
- When IV rises (fear/vol spike), vanna exposure tells you where delta shifts
- Positive VEX = as IV rises, dealer delta becomes more positive = they buy more = stabilizing
- Negative VEX = as IV rises, dealers sell more = destabilizing

**Trading insight:**
- Before FOMC/RBI/events, check VEX — it predicts how dealer hedging shifts when IV spikes
- If large negative VEX sits above spot → an IV spike will trigger dealer selling → double whammy (vol up + selling)
- Vanna is the "second derivative of fear" — GEX tells you about price moves, VEX tells you about volatility moves

### Cumulative Vanna

**Bucket:** Exposure > Vanna > Cumulative Vanna

Same cumulative treatment as GEX/DEX but for vanna.

### Charm Exposure (CEX)

**Bucket:** Exposure > Charm > Charm Exposure

**What it shows:** Dealer charm exposure — sensitivity of delta to time passage. Charm is the "overnight risk."

**How to read it:**
- Positive CEX = as time passes, dealers gain delta → they sell → creates resistance
- Negative CEX = as time passes, dealers lose delta → they buy → creates support

**Trading insight:**
- On expiry day, charm exposure spikes. Check which direction charm pushes dealers
- Large positive charm below spot = overnight support that grows stronger each day
- This explains why certain levels become stronger as expiry approaches without any new OI

### Cumulative Charm

**Bucket:** Exposure > Charm > Cumulative Charm

Same cumulative treatment for charm.

---

## Volatility Charts

### IV Smile

**Bucket:** Volatility > IV Smile/Skew > IV Smile

**What it shows:** Call IV and Put IV across strikes, forming the classic volatility smile/skew shape.

**How to read it:**
- A symmetrical smile = balanced market, no directional fear
- Left skew (put IV >> call IV) = downside protection demand = fear of drop
- Right skew (call IV > put IV) = unusual, often before short squeezes or event-driven rallies
- The steepness of the skew = intensity of directional fear

**Trading insight:**
- Steep left skew → market fears a crash → sell put spreads cautiously or buy call spreads (risk reversal)
- Flat smile → range-bound expectation → sell straddles/strangles
- If the smile flattens during a selloff → vol sellers are stepping in → potential bottom

### Actual vs Black-Scholes Pricing

**Bucket:** Volatility > BS Pricing > Actual vs BS

**What it shows:** Market prices vs theoretical Black-Scholes prices for calls and puts.

**How to read it:**
- Market price > BS price = option is **overpriced** (premium selling opportunity)
- Market price < BS price = option is **underpriced** (buying opportunity)
- Large deviations at specific strikes = institutional activity or liquidity effects

**Trading insight:**
- Systematically overpriced puts near support = fear premium → sell for income
- Underpriced calls at specific strikes = smart money accumulating quietly
- The BS model assumes constant vol — deviations reveal where the market disagrees

### Risk Reversal & Butterfly

**Bucket:** Volatility > Risk Reversal > RR & BF

**What it shows:**
- **25-Delta Risk Reversal (RR25):** Call 25d IV minus Put 25d IV. Measures skew direction.
- **10-Delta Butterfly (BF10):** Average of 10d wings minus ATM IV. Measures tail risk pricing.

**How to read it:**
- RR25 > 0 → Calls more expensive than puts → Bullish sentiment
- RR25 < 0 → Puts more expensive → Bearish / protective sentiment
- BF10 > 0 → Tails are expensive → Market pricing tail risk events
- BF10 < 0 → Wings are cheap → Complacency

**Trading insight:**
- RR25 at extreme negative = peak fear → contrarian buy signal
- BF10 spiking = event risk priced in → sell wings (iron condors)
- RR25 flipping from negative to positive = sentiment shift → follow the move

### IV Cone (Expected Range)

**Bucket:** Volatility > Expected Range > IV Cone

**What it shows:** 1SD and 2SD price cones projected forward from today to expiry, based on ATM implied volatility.

**Formula:** `Move = Spot × IV × sqrt(Days / 252)`

**How to read it:**
- The 1SD cone = 68% probability range
- The 2SD cone = 95% probability range
- Spot near the edge of 1SD = stretched, mean reversion likely
- Spot outside 2SD = extreme move, potential reversal

**Trading insight:**
- Sell strangles at the 1SD boundaries for the week
- If spot is inside the inner cone → range is holding → iron condors work
- Narrowing cone (as expiry approaches) = theta acceleration = premium sellers' paradise

### Gamma-Adjusted Range

**Bucket:** Volatility > Expected Range > Gamma-Adjusted

**What it shows:** The straddle-implied expected move vs. the gamma-adjusted expected move. Straddle price alone doesn't account for dealer hedging — gamma walls compress or amplify the actual move.

**Formula:** `Gamma_Move = Straddle_Move × (1 - normalized_gex × 0.35)`, clamped between [0.5x, 1.8x]

**How to read it:**
- When GEX is strongly positive → gamma adjustment compresses the range (dealers absorb moves)
- When GEX is negative → gamma adjustment expands the range (dealers amplify moves)
- The difference between straddle-implied and gamma-adjusted = "gamma tax" or "gamma boost"

**Trading insight:**
- If gamma-adjusted range is 60% of straddle-implied → straddles are overpriced → SELL them
- If gamma-adjusted range is 150% of straddle-implied → straddles are underpriced → BUY them
- This is the single best metric for pricing strangles correctly

### Volatility Trigger Level (VTL)

**Bucket:** Volatility > Vol Trigger > Volatility Trigger

**What it shows:** The price level where combined GEX + Vanna exposure flips sign. This is where the volatility regime changes.

**How to read it:**
- Price ABOVE VTL → Positive exposure → Vol compression → Selling vol is safe
- Price BELOW VTL → Negative exposure → Vol expansion → Buying vol is safe
- Distance from spot to VTL = buffer before regime change

**Trading insight:**
- If spot breaks below VTL → vol will spike → buy straddles immediately
- VTL converging toward spot = regime change approaching → reduce short vol positions
- VTL and Flip Point often coincide but not always — when they diverge, watch the one spot approaches first

### Intraday IV Tracker

**Bucket:** Volatility > Intraday IV > IV Tracker

**What it shows:** ATM implied volatility tracked across intraday snapshots.

**Trading insight:**
- Rising IV with falling spot = put buying acceleration = more downside likely
- Falling IV with rising spot = vol sellers stepping in = rally may be real
- IV spike with flat spot = smart money buying protection quietly → move is coming

### 3D Vol Surface

**Bucket:** Volatility > 3D Surface > 3D Vol Surface

**What it shows:** A three-dimensional surface of IV across strikes and historical snapshots.

**Trading insight:**
- Ridges on the surface = persistent skew at specific strikes
- Valleys = vol is cheap at those strikes = buying opportunity
- Surface tilting over time = systematic shift in market expectations

---

## Open Interest Charts

### OI Strike Map (Analysis)

**Bucket:** OI > OI Strike Map > Analysis

**What it shows:** Call OI and Put OI side by side at each strike. The classical support/resistance map.

**How to read it:**
- Heavy Put OI = support (put writers defend this level)
- Heavy Call OI = resistance (call writers cap the rally)
- The strike with maximum Call OI = likely ceiling for the expiry
- The strike with maximum Put OI = likely floor for the expiry

**Trading insight:**
- Range for the week = [Max Put OI strike, Max Call OI strike]
- If spot breaks above Max Call OI → short covering rally → acceleration
- If OI at a strike is increasing while spot approaches → writers are adding → level is stronger

### OI Change (Daily Shift)

**Bucket:** OI > OI Change > Daily Shift

**What it shows:** Change in OI from the previous session at each strike.

**How to read it:**
- Rising Call OI at a strike above spot = writers adding resistance
- Rising Put OI at a strike below spot = writers adding support
- Falling OI at key strikes = writers are closing → level weakens → breakout likely

**Trading insight:**
- New OI being added at extreme strikes = institutional positioning for a big move
- OI declining at current resistance + spot approaching = imminent breakout

### OI Buildup Classification

**Bucket:** OI > OI Change > Buildup Class

**What it shows:** Each strike classified into one of four categories based on OI change + price change:

| OI Change | Price Change | Classification | Meaning |
|-----------|-------------|----------------|---------|
| Up | Up | **Long Buildup** | Fresh longs entering → Bullish |
| Up | Down | **Short Buildup** | Fresh shorts entering → Bearish |
| Down | Up | **Short Covering** | Shorts exiting → Bullish |
| Down | Down | **Long Unwinding** | Longs exiting → Bearish |

**Trading insight:**
- Majority Short Covering on puts = put writers are running = rally signal
- Majority Long Buildup on calls + Short Buildup on puts = strong bullish setup
- If the dominant pattern flips from Long Buildup to Long Unwinding mid-day → trend is dying

### Intraday OI Tracker

**Bucket:** OI > Intraday OI Tracker

Two modes:
- **Overall:** Total call/put OI accumulation across all strikes through the day
- **Change:** Delta OI per snapshot — shows where fresh positioning is happening

**Trading insight:**
- Accelerating put OI additions mid-day = bearish institutional flow
- OI additions that cluster at specific strikes = that's the new wall to watch

### Premium Flow (Net Direction)

**Bucket:** OI > Premium Flow > Net Direction

**What it shows:** Whether premium at each strike is being bought (aggressive) or sold (passive), based on whether the option trades above or below ATM IV.

**How to read it:**
- Positive flow = buyer-initiated (paying up) = aggressive directional bet
- Negative flow = seller-initiated (hitting bid) = premium harvesting

**Trading insight:**
- Large positive premium flow on puts = institutional hedging = fear
- Large positive premium flow on calls at OTM strikes = speculative call buying = squeeze potential
- Net premium flow across all strikes: positive = money entering the market; negative = money leaving

### OI Flow (Volume vs OI)

**Bucket:** OI > OI Flow > OI vs Vol

**What it shows:** Relationship between volume and open interest at each strike.

**Trading insight:**
- High volume + low OI = day traders → level won't hold overnight
- High OI + low volume = legacy position → ghost level (use VWGEX to confirm)
- Both high = actively defended institutional level

### PCR Analysis (Volume vs OI)

**Bucket:** OI > PCR Analysis > Vol vs OI PCR

**What it shows:** Put-Call Ratio computed two ways — by intraday volume and by accumulated OI.

**How to read it:**
- PCR Volume = intraday sentiment (reactive, fast)
- PCR OI = accumulated positioning (strategic, slow)
- When they diverge: PCR Vol rising but PCR OI falling = short-term fear but long-term accumulation = bullish

**Trading insight:**
- PCR Vol > 1.5 = extreme bearish panic → contrarian buy (especially if PCR OI is stable)
- PCR Vol < 0.5 = extreme euphoria → contrarian sell
- PCR OI steadily rising over days = institutional put accumulation → big move down being prepared

### Overall & Strike Filter

**Bucket:** OI > Filter

Filters strikes by GEX percentile threshold and trend direction. Use to focus on only the most significant strikes.

---

## Others

### Quant Power

**Bucket:** Others > Quant > Quant Power

**What it shows:** A blended GEX + Vanna equilibrium analysis. Finds the strike where cumulative dealer delta (weighted by both gamma and vanna) crosses zero.

**How to read it:**
- Quant Power strike = the gravitational center of the options market
- The Power Zone (±1 standard deviation of the blended GEX distribution) = the expected range where price orbits
- Bar chart shows the blended exposure at each strike

**Trading insight:**
- If spot is outside the Power Zone → expect mean reversion back toward Quant Power
- If Quant Power shifts significantly between sessions → institutional repositioning → follow it
- Quant Power diverging from Flip Point = vanna is pulling in a different direction than gamma

### Dealer Regime Map

**Bucket:** Others > Quant > Dealer Regime

**What it shows:** Visual map of the gamma cage, vacuum zones, and regime boundaries.

### Max Pain & Pin Risk

**Bucket:** Others > Max Pain > Pain & Pin Risk

**What it shows:** The strike that minimizes total option holder gains (maximizes pain to all option buyers). Includes a pin risk score.

**How to read it:**
- Max Pain strike = where the market "wants" to settle at expiry
- Pin Risk Score: HIGH = strong magnet effect; LOW = other forces dominate
- The pain profile shows how total pain varies across strikes

**Trading insight:**
- On weekly expiry day, max pain is highly predictive (especially last 2 hours)
- Spot deviating >1% from max pain on expiry morning often snaps back by 3:00 PM
- If max pain shifts significantly between sessions → large OI repositioning happened → new target
- Pin risk is highest when: (a) GEX is positive at max pain strike, (b) volume is low, (c) DTE < 2

---

## Advanced Charts

### Gamma Waltz (Migration)

**Bucket:** Advanced > Migration Pulse > Gamma Waltz

**What it shows:** Historical trajectory of key levels (Flip Point, Max GEX, Power Zones) across intraday snapshots.

**Trading insight:**
- Flip Point migrating toward spot = regime change building → prepare for volatility shift
- Power Zones converging = gamma concentration increasing → bigger move when it breaks
- Levels that stay stable across 10+ snapshots = structurally significant

### IV vs RV (Vol Spread)

**Bucket:** Advanced > Vol Mispricing > IV vs RV

**What it shows:** Current Implied Volatility vs. Realized Volatility (actual historical price movement).

**How to read it:**
- IV > RV → Options are overpriced (vol premium exists) → Sell premium
- IV < RV → Options are underpriced (rare, usually after sudden moves) → Buy premium
- The spread between them = "Variance Risk Premium" — the edge that systematic vol sellers capture

**Trading insight:**
- When IV-RV spread is in the top 20% historically → ideal time to sell straddles/strangles
- When IV < RV → market underpricing risk → buy protection (cheap puts)
- After events (budget, elections), IV often collapses below RV briefly → buy vol

### Ignition Zone (Sensitivity Heatmap)

**Bucket:** Advanced > Ignition Zone > Sensitivity Heatmap

**What it shows:** A 2D heatmap of GEX mass across simulated prices (y-axis) and strikes (x-axis). Bright zones = areas where price movement triggers maximum dealer hedging.

**How to read it:**
- Hot zones (high values) = price entering this area triggers a cascade of dealer hedging
- Cold zones = price moves freely here
- The transition from hot to cold = the ignition boundary → breakout point

**Trading insight:**
- If spot is near a hot-to-cold boundary → a small push triggers massive dealer flow
- Plan entries at the edge of cold zones → if it breaks through, ride the momentum
- This is where gamma "explodes" — the chart literally shows you where the fireworks start

### Flow Momentum

**Bucket:** Advanced > Institutional Flow > Flow Momentum

**What it shows:** Intraday flow momentum derived from sequential snapshot analysis.

### FII/DII Positioning

**Bucket:** Advanced > Institutional Flow > FII/DII Position

**What it shows:** Participant-wise OI breakdown — FII, DII, Client, and Pro positioning in futures and options.

**How to read it:**
- FII net long + increasing = bullish institutional flow
- FII net short + increasing = bearish institutional flow
- Client vs FII divergence = retail is often the counter-indicator

**Trading insight:**
- When FII and Pro are on the same side → follow them
- When Clients are heavily long and FII is heavily short → classic top signal
- FII position change velocity matters more than absolute level

### FII × Gamma Alignment

**Bucket:** Advanced > Institutional Flow > FII × Gamma

**What it shows:** Whether FII positioning aligns with or fights the gamma regime.

**How to read it:**
- FII long + Long Gamma regime = aligned → strong rally continuation
- FII long + Short Gamma regime = fighting gamma → choppy, potential reversal
- FII short + Short Gamma regime = aligned → strong selloff continuation

**Trading insight:**
- Aligned FII + Gamma = high conviction trade → increase size
- Misaligned = gamma will win short-term, FII will win medium-term → trade the gamma signal intraday, but respect FII for swing

### Systemic Pulse & Total GEX/DEX

**Bucket:** Advanced > Systemic Pulse

**What it shows:** Cross-index gamma state — Nifty + BankNifty + Sensex combined.

**Trading insight:**
- All three in Long Gamma = extremely stable market → sell premium aggressively
- All three in Short Gamma = systemic volatility → reduce positions, buy tails
- Mixed regime = rotational, trade individual indices based on their own gamma

---

## Signal Engine

The signal engine scans the last 30 intraday snapshots and computes 5 independent signals that collectively predict moves before they happen.

### Composite Score

**Bucket:** Signals > Composite Score > Move Imminent

**What it shows:** An aggregated score (0–100) combining all 5 signals, with directional bias and urgency label.

| Score | Urgency | Action |
|-------|---------|--------|
| 60–100 | **MOVE IMMINENT** | Enter positions immediately; breakout/breakdown in progress |
| 40–59 | **ELEVATED** | Prepare positions; wait for one more confirmation |
| 20–39 | **WATCHLIST** | Monitor; conditions are developing |
| 0–19 | **CALM** | Range-bound; sell premium or sit out |

**Directional bias** is determined by a voting system across the signals that have triggered. BULLISH / BEARISH / NEUTRAL.

**Trading insight:**
- Composite 60+ BULLISH → buy calls or sell puts; use gamma-adjusted range for target
- Composite 60+ BEARISH → buy puts or sell calls
- If composite is high but direction is NEUTRAL → a big move is coming but direction is unclear → buy a straddle

### Signal 1: Flip Proximity (0–30 points)

**Bucket:** Signals > Flip Proximity > Regime Break

**What it shows:** How close spot is to the flip point, and whether it's approaching quickly (velocity).

| Proximity | Points | Label |
|-----------|--------|-------|
| < 0.15% | 30 | REGIME BREAK IMMINENT |
| < 0.30% | 20 | APPROACHING FLIP |
| < 0.50% | 10 | NEARING |
| > 0.50% | 0 | STABLE |

Velocity bonus: +10 points if approaching at >0.1% per snapshot.

**Chart shows:** Time series of distance-to-flip with danger zone lines at 0.3% and 0.15%.

**Trading insight:**
- Distance falling rapidly toward 0.15% = seconds away from regime change
- A regime flip from Long → Short gamma = volatility explosion → buy breakout
- A regime flip from Short → Long gamma = vol compression → sell straddles

### Signal 2: Wall Decay (0–20 points)

**Bucket:** Signals > Wall Decay > Live vs Ghost

**What it shows:** Health status of the top 3 gamma walls based on their Volume/OI ratio trend across snapshots.

| Status | Meaning | Visual |
|--------|---------|--------|
| **LIVE (Defended)** | Vol/OI ratio > 0.5 and stable | Green bar |
| **WEAK** | Low activity or unclear trend | Amber bar |
| **GHOST (Dying)** | Vol/OI declining + ratio < 0.3 | Red bar |

**Scoring:** +10 points per dying wall (max 20).

**Trading insight:**
- All 3 walls LIVE → range is holding → sell premium inside the range
- 2+ walls dying → breakout imminent → buy straddles or directional if combined with other signals
- A single wall dying on one side (e.g., call wall) while put wall stays live → directional breakout toward the dying wall

### Signal 3: IV-Spot Divergence (0–25 points)

**Bucket:** Signals > IV Divergence > Smart Money Tell

**What it shows:** Compares the rate-of-change of ATM IV vs. spot price over the last 5 snapshots. Divergence between IV and spot movement is a classic "smart money tell."

| Pattern | Points | Label |
|---------|--------|-------|
| IV up + Spot down | 25 | Protection Buying → Drop Expected |
| IV down + Spot up | 25 | Vol Selling Into Rally → Mean Reversion |
| IV moving, Spot flat | 15 | Smart Money Hedging / Vol Compression |
| No divergence | 0 | Normal |

**Chart shows:** Dual-axis: ATM IV on left, Spot price on right, across all snapshots.

**Trading insight:**
- IV rising while spot drops = institutional protection buying = more downside ahead. This is the highest-conviction bearish signal
- IV falling while spot rises = vol sellers are harvesting premium into the rally = rally may reverse
- IV rising while spot is flat = smart money buying insurance before news/event → move is being prepared

### Signal 4: OI Buildup Asymmetry (0–15 points)

**Bucket:** Signals > OI Asymmetry > Directional Trigger

**What it shows:** Whether call and put OI buildup classifications are asymmetric (one side unwinding while the other builds).

| Pattern | Points | Direction |
|---------|--------|-----------|
| Call unwinding >60% + Put buildup >60% | 15 | BULLISH (Rally Signal) |
| Put unwinding >60% + Call buildup >60% | 15 | BEARISH (Drop Signal) |
| Single-side unwinding >50% | 8 | Directional lean |
| Balanced | 0 | No signal |

**Chart shows:** Grouped bar chart of Long Buildup / Short Buildup / Short Covering / Long Unwinding counts for calls and puts.

**Trading insight:**
- Call writers capitulating (Short Covering) + fresh put writing (Short Buildup) = strong bullish setup
- The reverse = strong bearish setup
- If both sides are building (Long Buildup on calls AND puts) = range expansion expected, direction unclear → buy straddle

### Signal 5: Delta Acceleration (0–10 points)

**Bucket:** Signals > Delta Acceleration > Cascade Detector

**What it shows:** The second derivative (acceleration) of net dealer delta across snapshots. Detects feedback loops where dealer hedging is feeding on itself.

| Normalized Accel | Points | Label |
|-----------------|--------|-------|
| > 2.0x average | 10 | FEEDBACK LOOP — Dealer Cascade Active |
| > 1.5x average | 5 | ELEVATED ACCELERATION |
| ≤ 1.5x | 0 | Normal |

**Chart shows:** Bar chart of delta velocity + line chart of acceleration on secondary axis.

**Trading insight:**
- Feedback loop detected = dealers are chasing their own hedging = the move will accelerate
- This signal typically fires DURING a move, confirming that it has legs
- If acceleration is high but velocity is near zero → coiled spring → explosion in either direction

---

## God Tier Charts

### Dealer Reflexivity (Hedge Curve)

**Bucket:** God Tier > Dealer Reflexivity > Hedge Curve

**What it shows:** Simulated dealer hedging flow (in delta terms) required for ±2% moves in 0.5% increments.

**How to read it:**
- Positive flow at a price = dealers must BUY there → supportive
- Negative flow at a price = dealers must SELL there → resistance
- The asymmetry between upside and downside flow = directional bias in hedging

**Trading insight:**
- If dealer flow is strongly positive on downside moves → dealers are a natural buyer of dips → strong support
- If the curve is asymmetric (much more selling on rallies than buying on dips) → bearish lean
- Compare the reflexivity score across sessions — rising score = dealer positioning is intensifying

### Hedge Flow Simulation

**Bucket:** God Tier > Dealer Reflexivity > Hedge Simulation

**What it shows:** Detailed hedge flow simulation for ±3% moves, showing the delta change (hedge requirement) at each price step.

**How to read it:**
- Where the hedge flow bars accelerate = convexity kicks in
- Convexity score = standard deviation of hedge flows → higher = more explosive reactions

**Trading insight:**
- High convexity + Short Gamma = the market is a powder keg → one move triggers a cascade
- Low convexity + Long Gamma = placid conditions → sell premium confidently

### Liquidity Depth (Voids & Depth)

**Bucket:** God Tier > Liquidity Profile > Voids & Depth

**What it shows:** Bid-ask liquidity depth at each near-money strike.

**How to read it:**
- High depth = thick book → hard to push through
- Low depth ("Void") = thin book → price flies through this level
- Combine with GEX: a gamma wall at a liquid strike = fortress; a gamma wall at a thin strike = paper tiger

**Trading insight:**
- Enter positions at strikes with high liquidity (tighter fills)
- Place targets at liquidity voids (price accelerates through them)
- Avoid selling premium at strikes with low depth — your delta hedge will slip

### Spread Conviction

**Bucket:** God Tier > Liquidity Profile > Spread Conviction

**What it shows:** Bid-ask spread percentage at each strike alongside GEX, with a conviction score.

| Conviction | Criteria |
|-----------|----------|
| **Strong** | GEX above 75th percentile AND spread < 3% |
| **Weak** | Everything else |

**Trading insight:**
- Only trust gamma walls with "Strong" conviction
- Wide spread at a high-GEX strike = market makers aren't confident → wall is bluffing
- Use this to filter which levels to include in your support/resistance map

### Level Heat (Stickiness)

**Bucket:** God Tier > Stickiness > Level Heat

**What it shows:** The ratio of GEX mass to session volume at each strike. High stickiness = level is hard to break.

**Formula:** `Stickiness = |GEX| / (Volume + 1)`

**How to read it:**
- High stickiness = lots of gamma but little trading → the level hasn't been tested → it will hold
- Low stickiness = heavy trading at this gamma level → it's being "worked through" → may break

**Trading insight:**
- The stickiest level in the chain = the day's most probable pin target
- If the stickiest level is also the max pain strike → extremely high pin probability

### Delta Neutral Apex

**Bucket:** God Tier > Delta Magnet > Neutral Apex

**What it shows:** The price where total dealer net delta equals zero. Found using Brent's root-finding algorithm for precision.

**How to read it:**
- Apex price = the market's equilibrium → price is gravitationally pulled here
- Distance from spot to apex = how far from equilibrium the market currently is
- The chart shows the delta curve — where it crosses zero is the apex

**Trading insight:**
- If spot is far from apex → expect mean reversion toward it
- If apex is shifting toward spot → equilibrium is adjusting to the market (normal)
- If apex is shifting away from spot → institutional repositioning is changing the landscape

### Gamma Profile (Sharpness)

**Bucket:** God Tier > Gamma Sharpness > Gamma Profile

**What it shows:** Concentration of gamma across strikes, measured as a concentration index (kurtosis-like metric).

**How to read it:**
- High concentration (sharp) = gamma is piled on a few strikes → binary outcome (holds or snaps)
- Low concentration (diffuse) = gamma is spread across many strikes → gradual transitions

**Trading insight:**
- Sharp concentration + spot approaching the peak = high-stakes test → breakout or massive rejection
- Diffuse gamma = messy, range-bound market → no clean levels to trade
- If top strike holds >40% of total near-money gamma → that strike is THE level of the day

### GEX Slope (Curve Steepness)

**Bucket:** God Tier > Curve Steepness > GEX Slope

**What it shows:** The gradient (slope) of the cumulative GEX curve at the current spot price.

**How to read it:**
- High slope (>70% normalized) = High Sensitivity → each point of price move triggers massive dealer hedging
- Moderate slope (35-70%) = Moderate Grip → normal dealer interaction
- Low slope (<35%) = Stable Grip → dealers are balanced, price moves freely

**Trading insight:**
- High sensitivity + approaching flip = volatile, fast moves → use wider stops
- Stable grip = grind-mode → scalp for small targets
- Slope increasing over the day = gamma is concentrating near spot → move is brewing

### System Gamma (Cross-Index)

**Bucket:** God Tier > System Gamma > Cross-Index

**What it shows:** Aggregated gamma regime across Nifty, BankNifty, and Sensex.

**Trading insight:**
- All indices in same regime = systemic trade → higher conviction
- Divergent regimes = rotational market → trade the outlier
- System gamma score trending → useful for portfolio-level hedging decisions

---

## Compare Mode

When you select two data files, the dashboard switches to Compare Mode with these charts:

### Compare OI Change
Shows the OI difference between two snapshots at each strike. Reveals where positioning shifted.

### Flow Intensity
Activity heatmap between the two snapshots — where the action happened.

### Net Pressure
Strike-level net buying/selling pressure between snapshots.

**Trading insight for Compare Mode:**
- Load a morning snapshot and an afternoon snapshot → see how positioning evolved
- Load today vs. yesterday → see overnight changes
- Large OI additions at new strikes between snapshots = institutional repositioning

---

## Color Legend

| Color | Hex | Meaning |
|-------|-----|---------|
| Indigo | `#6366F1` | Positive / Stabilizing / Call-side |
| Rose | `#F43F5E` | Negative / Fuel / Put-side |
| Amber | `#F59E0B` | Spot price marker |
| Slate | `#94A3B8` | ATM / neutral reference |
| Cloud White | `#F1F5F9` | Flip Point |
| Pale Yellow | `rgba(239,222,11,0.3)` | Absolute value heat fill |
| Amber bands | `rgba(245,158,11,0.12)` | Power Zone highlights |

All charts use a transparent dark background that inherits from the CSS theme. The grid is ultra-subtle for clean readability.

---

## Data Flow

```
Upstox API → Parquet snapshots (per expiry/time)
    → Load into in-memory store
    → FastAPI endpoints calculate metrics on-the-fly
    → Plotly JSON returned to frontend
    → Dashboard renders with mode switching (net/raw)
```

**Snapshot frequency:** Every 1-5 minutes during market hours (configurable).
**Signal engine:** Needs at least 2 snapshots; best with 10-30 for full signal coverage.

---

## Supported Indices & Stocks

| Index | Lot Size | Expiry |
|-------|----------|--------|
| Nifty | 25 | Weekly (Tuesday) |
| BankNifty | 15 | Monthly (Last Tuesday) |
| Sensex | 10 | Weekly (Thursday) |

180+ individual stocks are also supported via `stocks.csv` with lot size of 1.

---

## Running the Platform

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
# Open frontend/index.html in browser, or serve via any static server
```

The frontend connects to `http://localhost:8000` by default (configured in `api.js`).
