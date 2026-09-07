# BRAM-EV — Behavior and Reputation-Aware Multi-Agent EV Charging

A multi-agent system for EV charging reservation, combining behaviour-aware user
reputation, local station optimisation (MILP), collective learning between
stations of the same company, and multi-criteria offer selection by the vehicle.
The objective is to improve charger utilisation while limiting the cost of
no-shows and late cancellations.

Vehicles emit a charging request when their state of charge drops below their
threshold. Stations within the search radius answer with offers built from their
own calendar, arbitraging profit against the no-show risk read from the driver's
reputation. The vehicle confirms exactly one offer.

The repository contains the model, a reproducible experiment pipeline, and an
**ablation study** designed so that every measured gain is attributable to one
component.


## Repository structure

```text
.
├── main.py                        # CLI entry point (== python -m src.pipeline.cli)
│
├── src
│   ├── env                        # The multi-agent model
│   │   ├── car.py                 # Vehicle agent: requests, utility, reputation
│   │   ├── offer.py               # Offer: id, TTL, schedule version
│   │   ├── society.py             # Company agent: collective learning
│   │   ├── station.py             # Station agent: MILP allocation, scoring
│   │   ├── utils.py               # Shared helpers (nominal_arrival, draws)
│   │   └── visualizer.py          # Real-time pygame visualizer
│   │
│   ├── experiments                # Simulation & reproducibility
│   │   ├── config.py              # Parameters, scenarios, derived thresholds
│   │   ├── methods.py             # Method registry: the ablation plan
│   │   ├── seeding.py             # Root seed, per-agent RNG streams
│   │   ├── world.py               # Shared grid + fleets + scenario composition
│   │   ├── simulation.py          # The single simulation loop (every method)
│   │   ├── simulation_greedy.py   # Nearest baseline (convenience subclass)
│   │   └── run.py                 # One run, with the visualizer
│   │
│   ├── metrics                    # Measurement
│   │   ├── metrics.py             # Metrics, latency, BehaviorTracker
│   │   ├── other_metrics.py       # Occupancy / reservation dataframes
│   │   ├── plots_metrics.py       # Per-run plots
│   │   └── plots_metrics_comparison.py
│   │
│   └── pipeline                   # Experiment orchestration
│       ├── params.py              # ExperimentParams: validation, YAML/JSON, CLI
│       ├── store.py               # Run layout and artifact persistence
│       ├── runner.py              # Case and grid execution
│       ├── tables.py              # Tidy tables extracted from a simulation
│       ├── ablation.py            # Decomposition: ladder, baselines, variants
│       ├── figures.py             # Figures built from tables, never from objects
│       └── cli.py                 # run / report / show / runs / scenarios /
│                                  #   methods / ablation
│
├── experiments                    # Ready-made campaigns
│   ├── smoke.yaml                 # ~2 min, all 11 methods
│   ├── ablation.yaml              # 4 ladder rungs + 3 baselines
│   ├── ablation_variants.yaml     # BRAM-EV with one mechanism replaced
│   └── full_grid.yaml             # Published grid: BRAM-EV vs every baseline
│
├── notebooks                      # Read run artifacts; no experiment logic
│   ├── explore_run.ipynb
│   ├── ablation.ipynb
│   └── ablation_variants.ipynb
│
├── tests                          # uv run python -m tests  (114 tests)
├── results_grid/                  # Run outputs (gitignored)
├── outputs/                       # Visualizer logs (gitignored)
└── pyproject.toml, uv.lock
```


## Installation

```bash
uv sync          # once, or after a dependency change
```

Every command is prefixed with `uv run`, which resolves the environment on the
fly.


## Running experiments

`uv run main.py` and `uv run python -m src.pipeline.cli` are equivalent.

### Campaigns

```bash
# 1. Smoke — run this first: 1 scenario x 2 fleets x 11 methods, 24 h. ~2 min.
uv run main.py run --config experiments/smoke.yaml

# 2. Ablation ladder + baselines — 3 scenarios x 5 fleets x 7 methods, 5 days.
uv run main.py run --dry-run --config experiments/ablation.yaml
uv run main.py run --config experiments/ablation.yaml

# 3. BRAM-EV variants — bramev + its 4 variants, same grid.
uv run main.py run --config experiments/ablation_variants.yaml

# 4. Published comparison grid — bramev, the 3 baselines and greedy (5 methods).
uv run main.py run --config experiments/full_grid.yaml
```

A campaign is fully described by its configuration file; any CLI option
overrides it:

```bash
# same grid, another seed — is the conclusion an artefact of one draw?
uv run main.py run --config experiments/full_grid.yaml --seed 7 --label seed-7

# a custom campaign, without a configuration file
uv run main.py run --seed 42 --scenarios pessimistic --cars 50 100 150 \
    --methods ablation --total-time 1440

# one scenario, one fleet, one method — the quickest way to test a change
uv run main.py run --scenarios balance --cars 50 --methods bramev --total-time 288
```

Output goes to `results_grid/<timestamp>_seed<seed>[_<label>]/`.

### Reading a finished run

None of these re-runs a simulation — they read the persisted tables:

```bash
uv run main.py runs                     # list available runs
uv run main.py show --latest            # summary table + diagnostics
uv run main.py report --latest          # rebuild every figure
uv run main.py ablation --latest        # decompose the gains per component
uv run main.py scenarios                # the behaviour-probability table
uv run main.py methods                  # the ablation plan, with its notes
uv run main.py run --help               # every parameter, with its default
```

### One simulation, with the visualizer

```bash
SEED=42 uv run python -m src.experiments.run
```

For watching the model behave, not for producing results: it opens a pygame
window (driven by `config.VISUALIZE`, so the pipeline stays headless) and writes
a detailed log plus `world_spec_A.json` to `outputs/`, from which the run can be
replayed with `define_agents_from_spec`.

### Tests and self-checks

```bash
uv run python -m tests                  # all suites, 114 tests, no test dependency

uv run python -m src.experiments.world  # shared grid & nested fleets
uv run python -m src.experiments.seeding
uv run python -m src.experiments.config
```

Several modules carry an executable self-check under `if __name__ == "__main__"`
asserting the invariant that module is responsible for.


## The model

Grid of 3 km, slots of 5 min, vehicle speed 4.167 km/slot. Default parameters
live in `src/experiments/config.py`; behaviour probabilities are **not** edited
there — use `config.set_scenario(name)`.

### Agents

| Agent | Does |
| --- | --- |
| `Car` | moves on the grid, requests a charge below its SoC threshold, ranks the offers received, confirms one, then honours or cancels its reservation |
| `Station` | solves a MILP over its own calendar, issues offers, revalidates them at confirmation, records behaviour outcomes into reputation |
| `Society` | owns stations, holds the reputation ledger, and periodically propagates the `alpha` of its best station to the others |

A vehicle's utility trades off energy shortfall, distance and waiting time,
weighted by its own preferences; it is always computed (it is the reported
satisfaction, `car.u_total`) even when it does not drive the choice.

Companies learn collectively every `SOCIETY_UPDATE_INTERVAL` slots (24 = 2 h):
the station with the most allocated slots keeps its `alpha`, the others move
towards it by `alpha += GAMMA * (best - alpha)`.

### Station allocation

`Station.process_demands` maximises, over `a[n,j,t]` (demand *n* occupies
charger *j* at slot *t*):

```
alpha * (w1*z - w2*D)  +  (1 - alpha) * score_n
```

`D` is the temporal distance to the nominal slot, `score_n` the driver's
reputation as seen by this station, `alpha` its risk aversion. Contiguity is
enforced in the model itself, with a start-of-charge indicator and at most one
rising edge per demand:

```
s[n,j,t] >= a[n,j,t] - a[n,j,t-1]        (missing a => 0)
sum_{j,t} s[n,j,t] <= 1
```

Duration stays variable (partial offers allowed, `<= d_n`) but `[t_arr, t_dep)`
now covers exactly `d_prop` slots — previously the solver could pick scattered
slots that the code then turned into a continuous interval, booking slots the
optimiser had never allocated.

### Offer protocol

An offer is a **revocable commitment**: it carries an `offer_id`, an expiry
(`OFFER_TTL_SLOTS`) and the charger schedule version seen when it was issued.
The vehicle ranks its offers and confirms exactly one; the station revalidates
it (expiry, contiguity, slots still free) before writing to its schedule, and
every other offer is explicitly expired. A refused confirmation makes the
vehicle fall back to the next-best offer instead of giving up. Every issued
offer therefore ends up confirmed, expired or refused:

```
nb_offer_issued == nb_offer_expired + nb_reservations + nb_confirm_refused
```

### Search retries

A demand that receives no offer does not send the vehicle back on the road: it
parks (`PARKED_SEARCHING`) and re-emits the **same** demand — same id, same
`d_n`, `g_n` and `l_n` — with a radius widened by `SEARCH_RADIUS_GROWTH` (1.5),
up to `MAX_SEARCH_RETRIES` (4) times and capped by the grid diagonal. Parking
rather than driving means an unsuccessful search cannot itself cause a
breakdown, and re-drawing nothing means the retry budget does not consume
randomness at a method-dependent rate.

### Reputation score

`Station.update_car_score` reads the outcome's stake in its company's scale and
**normalises it by the largest stake of that scale**, giving a signed value in
`[-1, 1]` — positive for a presence. The vehicle averages those over its
`SCORE_MEMORY` (5) last reservations, weighted by the reserved duration
(`score_weighting = 'duration'`) or by 1 (`'event'`), and attenuated by how full
the window is:

```
score = (Σ stake_i * w_i / Σ w_i) * (n / SCORE_MEMORY)     ∈ [-1, 1]
```

Three consequences, all intended:

* **Right to be forgotten** — beyond `SCORE_MEMORY` reservations the oldest
  outcomes leave the window.
* **Effective redemption** — without the attenuation a *single* negative
  outcome reached the floor (mean of one event); the vehicle became ineligible
  everywhere, never got another reservation, and its window could no longer
  turn — measured at 0 redemptions out of 9 sanctioned vehicles. Reaching the
  floor now requires a *sustained* degradation.
* **Reliability, not seniority** — it is a rate, not a cumulative sum, and a
  vehicle with no history (score 0, "unknown") is no longer confused with one
  whose record is exactly balanced.

Normalising by `max(mu)` rather than by a constant preserves the order and the
ratios of a company's scale while putting two companies on the same axis.

### Planning horizon `l_n`

Each request carries a **planning horizon** `l_n`: the number of slots between
its emission and the slot the driver actually targets. The nominal arrival slot
is defined once, in `src/env/utils.py`, and read by the station MILP, by the
utility and by the waiting-time measurement:

```
nominal_arrival(t_n, l_n, distance) = ceil(t_n + l_n + distance / CAR_SPEED)
```

`l_n = 0` means "charge now". `l_n` is drawn per request in
`Car.emit_request` from `RESERVATION_LEAD_PARAMS`, on the **dedicated** RNG
stream `car_lead` (`seeding.STREAM_CODES`, code 9) — sharing `rng_request` would
shift the duration, radius and patience of every later request as soon as the
horizon is enabled, so the two arms of the ablation would no longer differ by
the horizon alone.

Two things depend on it:

* **Early cancellation becomes reachable.** Without a horizon `t_arr ≈ t_n`, no
  reservation has any lead to lose, and every cancellation is mechanically
  late (see below).
* **The wanted delay is not endured waiting.** `l_n` enters `compute_utility`
  and the accepted-offer waiting time. Omitting it there would count the
  driver's own anticipation as waiting, push `waitingTime / maxWaitingTime`
  above 1, and let the final `max(0., u)` flatten *every* utility to zero —
  making the ranking arbitrary, with no error and no warning.

Defaults: the pipeline draws `l_n` uniformly in **[0, 12] slots** (0–1 h,
`ExperimentParams.reservation_lead_low/high`); a bare `SimulationConfig` uses
`{'low': 12, 'high': 48}`. `low = 0` is deliberate — part of the requests stay
"charge now", which keeps a non-anticipable control group in every run and keeps
the `early -> late` reclassification observable. `{'low': 0, 'high': 0}` disables
the horizon entirely: that is the control arm of the ablation.

```bash
uv run main.py run --reservation-lead-low 0 --reservation-lead-high 24
uv run main.py run --reservation-lead-low 0 --reservation-lead-high 0   # control arm
```

### Cancellation semantics

Each confirmed reservation draws an intent from `theta`; the intent decides
**when** the cancellation happens, and the observed outcome is derived from the
time actually left before the planned arrival:

| Intent | Cancels at | Observed outcome |
| --- | --- | --- |
| `pres` | never | `pres` once the session ends |
| `abs` | never shows up, slot held until `t_dep` | `abs` |
| `early` | first slot after the reservation | `early` if more than `threshold` slots remain, otherwise `late` |
| `late` | when `threshold` slots or fewer remain | `late` |

```
late_cancel_threshold(lead) = max(1, min(LATE_CANCEL_REF, floor(lead * LATE_CANCEL_FRACTION)))
```

`LATE_CANCEL_REF` (12 slots = 1 h) assumes a reservation taken well in advance;
bounding the threshold by a fraction of the *actual* request-to-arrival delay
(`LATE_CANCEL_FRACTION = 0.5`) is what makes both regimes reachable on this grid.

**Reachability of `early`.** An early cancellation fires at the earliest one slot
after the reservation, so `slots_left = lead - 1`, and it is observed as `early`
only if `slots_left > late_cancel_threshold(lead)`. That requires an effective
delay of at least 3 slots — `config.min_lead_for_early_cancel()`, which derives
the bound from `LATE_CANCEL_FRACTION` rather than hard-coding it. The effective
delay is `l_n + ceil(travel)`, i.e. `l_n + 1` on this grid, so `l_n >= 2`
suffices. Under the default `[0, 12]` the branch is exercised; without the
horizon it was structurally unreachable and `nb_early_canc` stayed at 0.

Three guards keep this honest rather than assumed:

* `ExperimentParams.validate` warns, before any simulation, when
  `reservation_lead_high + 1 < min_lead_for_early_cancel()` — no drawn horizon
  could ever produce an early cancellation.
* `BehaviorTracker.diagnostics()` separates the control arm (anticipation
  deliberately off — nothing to report) from "horizon requested but never
  obtained", and stays silent below `MIN_EARLY_SAMPLE` intents, where a missing
  `early` outcome is noise rather than a symptom.
* `anticipable_share`, `mean_lead_slots` and `median_lead_slots` are reported in
  every result: they distinguish a structural impossibility (share = 0) from a
  sampling accident.

`BehaviorTracker` records the drawn intent, the observed outcome and every
reclassification, so the gap between scenario probabilities and measured rates
is visible instead of being attributed to the model.

### Reservation invariant

Every confirmed reservation resolves into exactly one outcome:

```
nb_reservations == nb_pres + nb_no_show + nb_early_canc + nb_late_canc
                 + nb_breakdown_canc + nb_unresolved
```

`nb_breakdown_canc` (vehicle stranded before its session) and `nb_unresolved`
(reservation still open at the end of the horizon) close the identity that was
previously false and under-counted no-shows. `Simulation._finalize` closes any
remaining reservation, and `check_reservation_invariant` is verified per station
at the end of every run — a violation is exit code 3.

A no-show now stays parked (`PARKED_NO_SHOW`) until its reserved slot is
released: it has given up its trip, not only its charge, so it no longer
consumes energy — and can no longer break down — while holding the slot.


## Ablation study

Comparing Nearest against BRAM-EV Full tells you *that* there is a gap, not
where it comes from — and the most likely explanation is also the least
interesting one: simply asking several stations instead of one.

A method is **not a class**: it is a flag set (`MethodSpec`) applied to the
single `Simulation` loop, declared once in `src/experiments/methods.py`. Two
neighbouring rungs therefore run strictly the same code with one boolean
flipped.

### The ladder — each rung adds exactly one component

| Configuration | Method | Multi-station search | Reputation | Cross-station adaptation |
| --- | --- | :---: | :---: | :---: |
| Nearest | `greedy` (alias `nearest`) | no | no | no |
| Multi-Station Only | `multistation` | yes | no | no |
| Multi-Station + Reputation | `multistation_rep` | yes | yes | no |
| BRAM-EV Full | `bramev` | yes | yes | yes |

`greedy` and `bramev` keep their historical names, so earlier runs, tables and
figures stay readable.

### Reference baselines — does BRAM-EV beat a simpler rule at all?

All three share the exact protocol of `multistation` — broadcast to the stations
within `r_n`, no reputation, no adaptation — and differ from it by **one thing
only: the rule used to pick an offer**. Same information, same protocol, so a
measured gap is attributable to the rule and not to an information advantage.

| Baseline | Method | Picks the offer with... |
| --- | --- | --- |
| Minimum Waiting Time | `min_waiting` | the lowest waiting time (proposed vs. targeted slot) |
| Load-Aware | `load_aware` | the lowest *future* occupancy at its station |
| Random Feasible | `random_feasible` | a uniform draw among the offers received |

`greedy` completes the set as the single-station floor: it is the only method
that contacts one station instead of broadcasting.

Three implementation points make these comparable rather than merely present:

* **Feasibility is not a filter.** Every offer received is feasible by
  construction, so `random_feasible` draws among all of them and is a genuine
  floor: what the protocol yields with no policy at all.
* **Future occupancy, not lifetime occupancy.** `Station.future_occupancy_rate`
  measures the share of charger-slots booked *from the current slot onwards*;
  the `occupancy_rate` in the tables spans the whole horizon, past included, and
  tells a vehicle looking for a plug nothing useful. The value travels on the
  offer, so ranking stays a pure function of what the vehicle received.
* **The random draw is reproducible and order-free.** It uses the dedicated
  `car_choice` stream, and offers are sorted by station id before being
  permuted — otherwise the "random" pick would inherit the order in which
  stations answered.

### BRAM-EV variants — does this mechanism have to work this way?

Each variant replaces **one internal mechanism** and is compared against
`bramev`.

| Variant | Mechanism neutralised | Replaced by |
| --- | --- | --- |
| `bramev_nearest_offer` | multi-criteria utility | the nearest offer |
| `bramev_fixed_alpha` | heterogeneous alpha | one `--alpha-fixed` value everywhere |
| `bramev_global_rep` | per-company reputation | a single score shared by all companies |
| `bramev_event_score` | duration-weighted score | a flat penalty per event |

`bramev_fixed_alpha` keeps collective learning on, but inert: with every alpha
equal the best station has nothing to propagate. The variant therefore isolates
the contribution of alpha *heterogeneity* itself.

### Selecting methods

```bash
uv run main.py run --methods ablation     # the four rungs
uv run main.py run --methods baselines    # the three rules
uv run main.py run --methods reference    # bramev + the three + greedy
uv run main.py run --methods bramev variants
uv run main.py run --methods all          # 11 methods
```

> **Contention is the prerequisite.** None of these comparisons can separate
> anything on a grid where every request fits. With 40 stations of 5 chargers,
> roughly half of the station-side MILP batches hold a single demand and no
> arbitration ever happens: every method then returns the same allocation. Check
> `mean_offers_per_demand` and `mean_service_rate` before concluding that a
> component "does not help"; if the methods are tied, lower `nb_stations` or
> raise the fleet until they are not.

### Why the numbers are attributable

Enforced by `tests/test_ablation.py`:

* **One switch per rung.** A single `Simulation` reads declarative flag sets;
  two neighbouring rungs differ by one boolean.
* **One world per comparison.** Grid, fleet and behaviour draws are sampled once
  per campaign and reused for every method (see *One world* below). Per-vehicle
  RNG streams are independent, so a decision that diverges under one method does
  not shift the draws of another.
* **A stated direction per metric.** Fewer no-shows is a gain; less satisfaction
  is not. Each metric declares its direction, and the reported `improvement` is
  a judgement, not a sign.

### Reading the decomposition

```bash
uv run main.py ablation --latest
uv run main.py ablation --latest --metrics exact_satisfaction rate_abs nb_reservations
```

```text
Component                 Exact satisfaction      No-show rate      Service rate
------------------------  ------------------  ----------------  ----------------

Ablation ladder (contribution of the added component)
Multi-station search              +4.1% (92%)       -2.7% (83%)       +6.0% (92%)
Reputation                        +0.6% (58%)      -11.4% (100%)      +2.2% (75%)
Cross-station adaptation          +0.2% (50%)       -0.4% (58%)       +0.3% (50%)

Reference baselines (gap from the baseline to BRAM-EV)
Minimum Waiting Time              +0.3% (67%)       -1.1% (75%)       +0.8% (58%)
Load-Aware                        +0.5% (75%)       -0.9% (67%)       +1.4% (75%)
Random Feasible                  +2.6% (100%)       -3.4% (92%)      +5.6% (100%)
```

The baseline block reads **`baseline -> bramev`**, the opposite direction to the
variants: `improvement = true` means BRAM-EV does better than the baseline.

Each cell carries the mean relative gap **and, in parentheses, the share of
worlds where the component actually improves that metric**. The parenthesis is
the part that matters: a component that helps in half the worlds has no robust
contribution, however good its average looks.

| File | Content |
| --- | --- |
| `ablation.csv` | one line per (world, component, metric): both values, delta, relative delta, improvement; the `kind` column separates `ladder`, `baseline` and `variant` |
| `ablation_mean.csv` | one line per (component, metric): mean delta, `nb_improved`, `share_improved` |

Both are rewritten after **every case**, like `summary.csv`: a full grid takes
hours, so an interrupted campaign has to stay analysable. Figures
`ablation_components.png`, `ablation_variants.png` and
`ablation_ladder_<scenario>.png` are produced with the rest; baseline rows appear
in `ablation.csv` and in the text report, with no dedicated figure yet.

### Notebooks

They read run artifacts and run **no simulation of their own**.

| Notebook | Reads | Answers |
| --- | --- | --- |
| `explore_run.ipynb` | any finished run | summary, figures, detailed tables |
| `ablation.ipynb` | a run holding the four rungs, and the baselines if present | where the Nearest → BRAM-EV gap comes from |
| `ablation_variants.ipynb` | a run holding `bramev` and its variants | whether each internal mechanism earns its place |

The two ablation notebooks pick their run with `RunStore.latest_with_methods(...)`
— the most recent campaign that actually contains the methods being compared,
not the most recent one full stop. Both open on the same check: **which flags
were actually applied**, read from `summary.csv` rather than from the registry.
A rung that flips more than one component is reported before any result is read,
because from that point on no number is attributable. Both close on the two
readings a bare average hides: the dispersion across worlds, and whether the
mechanism was solicited at all.

### Caveats when reading a short run

Two components need a long enough horizon to express themselves. A `+0.0%` under
these conditions means *never exercised*, not *useless*:

* **Cross-station adaptation** only fires every `SOCIETY_UPDATE_INTERVAL` slots
  (24 = 2 h). A shorter campaign measures a contribution of exactly zero.
* **Multi-criteria selection** only matters when a demand receives several
  offers; on a small grid most receive zero or one, and `bramev_nearest_offer`
  is then indistinguishable from `bramev`. `mean_offers_per_demand` says whether
  the comparison had any substance.


## Reproducibility and fair comparison

All experiments are driven from the command line. There is no experiment logic
in notebooks: parameters, orchestration, persistence and figures each live in
their own module under `src/pipeline/`.

### Commands

| Command | Purpose |
| --- | --- |
| `run` | Runs a campaign and writes every artifact |
| `report` | Rebuilds all figures of an existing run, without simulating |
| `show` | Prints the summary table and the diagnostics of a run |
| `runs` | Lists available runs |
| `scenarios` | Prints the behaviour-probability table |
| `methods` | Prints the ablation plan: which components each method enables |
| `ablation` | Decomposes the gains per component, without simulating |

Computing (`run`) and reporting (`report`, `show`, `ablation`) are deliberately
separate: fixing an axis or a colour costs a second instead of a full campaign.

```bash
uv run main.py show --run-dir results_grid/<run> \
    --columns scenario nb_cars method rate_late
```

Exit codes: `0` success, `1` parameter or I/O error, `2` usage, `3` at least one
reservation invariant violated.

### Parameters

Every parameter has a CLI flag and a configuration-file key; the CLI wins over
the file. Parameters are validated **as a whole** and up front: an unknown
scenario, a duplicated fleet size or more companies than stations is reported
before any simulation starts, with the full list of problems rather than the
first one.

| Group | Options |
| --- | --- |
| Experiment plan | `--seed`, `--scenarios`, `--cars`, `--methods` |
| Simulated world | `--total-time`, `--nb-stations`, `--nb-societies`, `--charg-spot-low/high`, `--strategy-noise` |
| Protocol | `--offer-ttl-slots`, `--late-cancel-fraction`, `--reservation-lead-low`, `--reservation-lead-high`, `--society-update-interval`, `--alpha-fixed` |
| Outputs | `--output-root`, `--label`, `--keep-logs`, `--save-latency`, `--save-tables`, `--figures`, `--log-every` |

### What a run produces

```text
results_grid/<timestamp>_seed<seed>[_<label>]/
    params.json                       campaign parameters (replayable as is)
    manifest.json                     seed, git commit, platform, progress, timings
    summary.csv                       one line per case, ready for plotting
    ablation.csv                      one line per (world, component, metric)
    ablation_mean.csv                 contribution of each component, averaged
    grid.json                         THE grid: societies, stations, alpha, strategies
    fleets/fleet_<n>cars.json         one fleet per size, shared by every scenario
    worlds/<scenario>_<n>cars.json    composed world (grid + fleet + scenario)
    results/<tag>.json                full metrics of one case
    tables/grid_stations.csv          position, company, spots, alpha
    tables/grid_societies.csv         position, strategy points, holdings
    tables/fleet_<n>cars.csv          initial position, autonomy, preferences…
    tables/<tag>_<table>.csv          stations, behaviors, acceptances, alpha, latency
    figures/grid.png, fleet_<n>cars.png, *.png
    logs/<tag>.txt                    detailed log (--keep-logs)
```

`grid.json` and `fleets/` are written **before the first simulation**, so the
environment is inspectable even if the campaign is interrupted — or never run
(`--dry-run` prints the plan without touching the disk). Other artifacts are
written case by case, atomically: an interrupted campaign leaves a valid
`summary.csv` and a manifest saying how far it got.

Figures are built from the persisted tables, never from live simulation objects:
the shared environment (`grid.png`, one `fleet_<n>cars.png` per size); per
scenario satisfaction, travel and waiting time, latency breakdown, demand funnel,
reservation outcomes, offer-protocol health, station load; and across scenarios
satisfaction overview, scalability, and intent-vs-observed behaviour.

### Single seed, independent streams

`src/experiments/seeding.py` derives every random source from one root seed
through `numpy.random.SeedSequence` (`random.seed` and `numpy.random.seed` are
also set, for the few draws not routed through a stream).

Each vehicle owns independent streams — movement, behaviour, request parameters,
planning horizon, offer draw — keyed by `(seed, vehicle index)`. A stream depends
on its key, not on call order, so the k-th draw of a given vehicle is the same
for every method under the same seed (*common random numbers*). The honest
limitation: once methods diverge, realised trajectories diverge too, since a
served vehicle does not consume the same number of movement draws as one that is
not. What is guaranteed is a common source of randomness, not identical
histories.

### One world, all scenarios and all methods

`src/experiments/world.py` builds the initial world in three layers:

| Layer | Drawn | Depends on | Shared by |
| --- | --- | --- | --- |
| `GridSpec` | once per campaign | the seed only | every scenario, fleet size and method |
| `FleetSpec` | once per fleet size | the seed only | every scenario and method |
| `WorldSpec` | composed, no draw | grid + fleet + scenario | every method of that case |

**The grid** — companies (position, strategy points) and stations (position,
owner, chargers, initial `alpha`) — is drawn before the first simulation and
reused verbatim, so the three scenarios run on the same map.

**The fleet** — initial position and SoC, autonomy, threshold, preferences,
charging power — is drawn once per size. Each vehicle uses its own
`('car_init', idx)` stream, so fleets are **nested**: the first 50 vehicles of a
100-vehicle fleet are exactly the 50-vehicle fleet. The scalability curve
therefore measures *adding* vehicles, not resampling them.

**The scenario** changes exactly one thing: `theta`. Each vehicle carries a fixed
normalised noise `u_k ∈ [-1, 1]` drawn with the fleet:

```
theta_k ∝ max(0.1, base_k + base_k * noise_scale * u_k)
```

A vehicle therefore keeps the same "personality" — its relative deviation from
the average — in all three scenarios; only the base moves.

`build_world(spec, config)` turns a specification into agents **without any
random draw**, so calling it twice yields two identical but independent worlds.
These properties are structural but invisible when reading the code: one stray
draw inside a scenario-dependent function would silently break them, so
`tests/test_shared_world.py` asserts them on the specs, on the materialised
agents, and end-to-end on a real campaign.

### Scenarios: a single source of truth

Behaviour probabilities live in `SimulationConfig.SCENARIOS` and are applied with
`config.set_scenario(name)` — `uv run main.py scenarios` prints the table.

| Scenario | pres | abs | early | late | noise | Description |
| --- | --- | --- | --- | --- | --- | --- |
| optimistic | 75 | 10 | 9 | 6 | 0.15 | most users honour their reservation |
| balance | 60 | 20 | 12 | 8 | 0.15 | moderate cancellations and absences |
| pessimistic | 40 | 25 | 15 | 20 | 0.15 | high no-show and late-cancellation rate |

Severity grows monotonically on the two outcomes that cost the operator (`abs`
and `late`), and `noise` is identical everywhere so that scenarios differ only by
their probabilities. The values previously hard-coded in the notebooks were
dropped: `late` was not monotone (6 → 8 → 5), `early`/`late` were swapped in the
pessimistic scenario (35/5), and `noise` varied across scenarios (0.15 / 0.10 /
0.05), which confounded the comparison.

### Latency measurement

Demand identifiers are `t<slot>-c<vehicle>` — they used to be `t_c * len(cars)`,
identical for every vehicle in the same slot, so latency records overwrote each
other; a duplicate now raises immediately. Each demand records its full timeline:
emission, reception of **each** offer, reception of the last one, selection, and
confirmation. `latency_report()` aggregates each stage independently over the
demands where it is defined, so a demand that received no offer is not counted
as a zero.


## Tests

```bash
uv run python -m tests                     # all suites, 114 tests
uv run python -m tests.test_priority1      # model
uv run python -m tests.test_shared_world   # shared grid and fleets
uv run python -m tests.test_pipeline       # pipeline
uv run python -m tests.test_ablation       # ablation study
```

No external test dependency: each suite is a module exposing `main() -> int`.

* **`test_priority1.py` (46)** — model fixes: reproducibility, shared
  environment, unique demand identifiers, latency decomposition, slot
  contiguity, offer confirmation safety, cancellation semantics, and the
  planning horizon (`nominal_arrival` as the single formula, bounds and
  dedicated stream of the `l_n` draw, `min_lead_for_early_cancel` consistent
  with the threshold, and the horizon actually opening the `early` branch that
  is unreachable without it).
* **`test_shared_world.py` (17)** — comparability of the scenarios: one grid per
  campaign, fleets independent of the scenario and nested across sizes, `theta`
  as a pure function of the fixed noise and the scenario base, verified
  end-to-end on a real campaign.
* **`test_pipeline.py` (24)** — orchestration: parameter validation, YAML/JSON
  round-trip, CLI precedence over configuration files, run layout and artifact
  round-trip, incremental writing, same-world comparison, reproducibility of a
  whole campaign, figures rebuilt from the persisted tables alone, CLI exit codes.
* **`test_ablation.py` (27)** — attributability: each rung flips exactly one flag
  and leaves the internal mechanisms untouched, each variant differs from
  `bramev` by exactly one mechanism, those flags actually reach the agents, the
  decomposition matches `summary.csv` with the right direction per metric, a
  duplicated method is refused rather than silently overwritten, the tables are
  rewritten after every case, every shipped config declares its `methods`
  explicitly (omitting the key falls back to the default ladder — a mistake that
  once cost a 21-hour campaign), and broadcasting really does produce more offers
  per demand.


## History

The three per-scenario notebooks that previously held the experiments (about 400
cells each, duplicated across `results/` and `bram-ev/`) have been replaced by
this pipeline. They remain in the history:

```bash
git show 68b16ad:results/Optimistic.ipynb > Optimistic.ipynb
```


## Author

Fatoumata WADIOU
