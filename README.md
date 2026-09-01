# Behavior and Reputation-Aware Multi-Agent EV Charging (BRAM-EV)

**BRAM-EV (Behavior and Reputation-Aware Multi-Agent EV Charging)** is a multi-agent system for electric vehicle charging reservation management. The approach combines:

* behavior-aware user reputation,
* local station optimization,
* collective learning between charging stations,
* multi-criteria decision making for charging allocation.

The objective is to improve charging station utilization while reducing the impact of no-shows, late cancellations, and unreliable user behavior.

The project includes:

* a complete Python implementation of the BRAM-EV model;
* a simulation engine;
* visualization tools;
* experimental notebooks reproducing all results presented in the report.


## Description

This project proposes a multi-agent approach for optimizing electric vehicle (EV) charging in a distributed network of charging stations.

Vehicles send charging requests to nearby stations, which respond with optimized offers based on their capacity, profit strategy, and estimated user no-show risk derived from behavioral scoring. Each vehicle then selects the offer that maximizes its utility (distance, waiting time, cost, and energy demand).

The system includes:
- reservation management and no-show handling,
- user behavioral scoring system,
- reinforcement learning for station strategy optimization,
- intra-company cooperation between stations to share performance and improve policies.

The goal is to jointly optimize charging allocation, user satisfaction, and operator profitability.


# Repository Structure

```text
.
├── main.py                        # Point d'entrée du pipeline (CLI)
│
├── src
│   ├── env                        # Le modèle multi-agents
│   │   ├── car.py                 # Electric vehicle agent
│   │   ├── offer.py               # Charging offer (id, TTL, schedule version)
│   │   ├── society.py             # Charging company agent
│   │   ├── station.py             # Charging station agent (MILP allocation)
│   │   ├── utils.py               # Shared utility functions
│   │   └── visualizer.py          # Real-time simulation visualizer
│   │
│   ├── experiments                # Simulation & reproducibility
│   │   ├── config.py              # Simulation parameters + scenario table
│   │   ├── methods.py             # Method registry: the ablation plan
│   │   ├── seeding.py             # Seed management, per-agent RNG streams
│   │   ├── world.py               # Shared grid + fleets + per-scenario composition
│   │   ├── simulation.py          # Shared simulation loop (every method)
│   │   ├── simulation_greedy.py   # Nearest baseline (convenience subclass)
│   │   └── run.py                 # Single run with the visualizer
│   │
│   ├── metrics                    # Measurement
│   │   ├── metrics.py             # Metrics, latency, behaviour tracking
│   │   ├── other_metrics.py       # Occupancy / reservation dataframes
│   │   ├── plots_metrics.py       # Interactive per-run plots
│   │   └── plots_metrics_comparison.py
│   │
│   └── pipeline                   # Experiment orchestration
│       ├── params.py              # ExperimentParams: validation, YAML/JSON, CLI
│       ├── store.py               # Run layout and artifact persistence
│       ├── runner.py              # Case and grid execution
│       ├── tables.py              # Tidy tables extracted from a simulation
│       ├── ablation.py            # Per-component decomposition of the gains
│       ├── figures.py             # Figures built from tables, never from objects
│       └── cli.py                 # run / report / show / runs / scenarios /
│                                  #   methods / ablation
│
├── experiments                    # Ready-made campaign configurations
│   ├── ablation.yaml              # The four configurations, full grid
│   ├── ablation_variants.yaml     # BRAM-EV with one mechanism replaced
│   ├── full_grid.yaml
│   └── smoke.yaml
│
├── notebooks
│   ├── explore_run.ipynb          # Interactive exploration of a finished run
│   ├── ablation.ipynb             # The four configurations, component by component
│   └── ablation_variants.ipynb    # BRAM-EV with one mechanism replaced
│
├── tests                          # uv run python -m tests
│   ├── test_priority1.py          # Model fixes
│   ├── test_shared_world.py       # One grid & one fleet across all scenarios
│   ├── test_pipeline.py           # Params, storage, runner, figures, CLI
│   └── test_ablation.py           # Components, variants, decomposition
│
├── results_grid/                  # Run outputs (gitignored)
├── outputs/                       # Visualizer logs (gitignored)
├── pyproject.toml
├── uv.lock
└── README.md
```


# Installation

The project uses **uv** for dependency management.

Install all dependencies:

```bash
uv sync
```

Every command below is prefixed with `uv run`, which resolves the environment on
the fly — no manual activation, and `uv sync` is only needed once (or after a
dependency change).


# Running the experiments

Everything runs through one entry point. `uv run main.py` and
`uv run python -m src.pipeline.cli` are equivalent.

### The campaigns

```bash
# 1. Smoke campaign — run this first: 1 scenario x 2 fleets x all 8 methods.
#    Validates the whole chain in about two minutes.
uv run main.py run --config experiments/smoke.yaml

# 2. Ablation ladder — 3 scenarios x 5 fleet sizes x the 4 configurations,
#    5 simulated days. This is the long one: check the plan before launching.
uv run main.py run --dry-run --config experiments/ablation.yaml
uv run main.py run --config experiments/ablation.yaml

# 3. BRAM-EV variants — one internal mechanism replaced at a time.
uv run main.py run --config experiments/ablation_variants.yaml

# 4. Historical two-method grid (Nearest vs BRAM-EV Full only).
uv run main.py run --config experiments/full_grid.yaml
```

Both write to `results_grid/<timestamp>_seed<seed>[_<label>]/`. A campaign is
fully described by its configuration file, and any CLI option overrides it:

```bash
# same grid, another seed — to check that a conclusion is not an artefact of one draw
uv run main.py run --config experiments/full_grid.yaml --seed 7 --label seed-7

# a custom campaign, without a configuration file
uv run main.py run --seed 42 --scenarios pessimistic --cars 50 100 150 \
    --methods ablation --total-time 1440

# one scenario, one fleet, one method — the quickest way to test a change
uv run main.py run --scenarios balance --cars 50 --methods bramev --total-time 288
```

### Reading a finished run

No simulation is re-run by any of these — they read the persisted tables:

```bash
uv run main.py runs                     # list available runs
uv run main.py show --latest            # summary table + diagnostics
uv run main.py report --latest          # rebuild every figure
uv run main.py scenarios                # the behaviour-probability table
uv run main.py run --help               # every parameter, with its default
```

### A single simulation, with the visualizer

```bash
SEED=42 uv run python -m src.experiments.run
```

This one is for watching the model behave, not for producing results: it opens a
pygame window and writes a detailed log to `outputs/`.

### Tests and self-checks

```bash
uv run python -m tests                  # all suites, 64 tests

uv run python -m src.experiments.world  # shared grid & nested fleets
uv run python -m src.experiments.seeding
uv run python -m src.experiments.config
```

Several modules carry an executable self-check under `if __name__ == "__main__"`,
which asserts the invariant that module is responsible for.


# Ablation study

Comparing Nearest against BRAM-EV Full tells you *that* there is a gap. It does
not tell you where the gap comes from — and the most likely explanation is also
the least interesting one: simply asking several stations instead of one.
The ablation answers that question by construction.

## The four configurations

Each rung adds **exactly one component** to the previous one:

| Configuration | Method name | Multi-station search | Reputation | Cross-station adaptation |
| --- | --- | :---: | :---: | :---: |
| Nearest | `greedy` (alias `nearest`) | no | no | no |
| Multi-Station Only | `multistation` | yes | no | no |
| Multi-Station + Reputation | `multistation_rep` | yes | yes | no |
| BRAM-EV Full | `bramev` | yes | yes | yes |

```bash
uv run main.py methods                    # the full plan, with the notes
uv run main.py run --methods ablation     # the four configurations
```

`greedy` and `bramev` keep their historical names, so earlier runs, tables and
figures stay readable; the ladder simply inserts the two missing rungs between
them.

## BRAM-EV variants

Each variant replaces **one internal mechanism** of the full method and is
compared against `bramev`. Where the ladder asks "what does adding this
component buy?", the variants ask "does this mechanism have to work the way it
does?".

| Variant | Mechanism neutralised | Replaced by |
| --- | --- | --- |
| `bramev_nearest_offer` | multi-criteria utility | the vehicle takes the nearest offer |
| `bramev_fixed_alpha` | heterogeneous alpha | one `--alpha-fixed` value for every station |
| `bramev_global_rep` | per-company reputation | a single score shared by all companies |
| `bramev_event_score` | duration-weighted score | a flat penalty per event |

```bash
uv run main.py run --methods bramev variants
uv run main.py run --methods all          # ladder + variants, 8 methods
```

`bramev_fixed_alpha` keeps collective learning switched on, but it becomes
inert: with every alpha equal, the best station has nothing to propagate. The
variant therefore isolates the contribution of alpha *heterogeneity* itself.

## Why the numbers are attributable

A measured gap is only attributable to a component if nothing else moved. Three
properties, all enforced by tests (`tests/test_ablation.py`), make that true:

* **One switch per rung.** Methods are declarative flag sets in
  `src/experiments/methods.py`; a single `Simulation` class reads them. Two
  neighbouring rungs run strictly the same code, on the same world, with one
  boolean flipped.
* **One world per comparison.** The grid, the fleet and the behaviour draws are
  sampled once per campaign and reused for every method (see *One world, all
  scenarios and all methods* below). The per-vehicle RNG streams are
  independent, so a decision that diverges under one method does not shift the
  draws of another.
* **A stated direction per metric.** Fewer no-shows is a gain; less
  satisfaction is not. Each metric declares its direction, and the reported
  `improvement` is a judgement, not a sign.

## Reading the decomposition

```bash
uv run main.py ablation --latest
uv run main.py ablation --latest --metrics exact_satisfaction rate_abs nb_reservations
```

```text
Composant                       Satisfaction exacte   Taux de no-show   Taux de service
------------------------------  -------------------  ----------------  ----------------

Échelle d'ablation (contribution du composant ajouté)
Recherche multi-stations                 +4.1% (92%)      -2.7% (83%)        +6.0% (92%)
Réputation                               +0.6% (58%)     -11.4% (100%)       +2.2% (75%)
Adaptation entre stations                +0.2% (50%)      -0.4% (58%)        +0.3% (50%)
```

Each cell carries the mean relative gap **and, in parentheses, the share of
worlds where the component actually improves that metric**. The parenthesis is
the part that matters: a component that helps in half the worlds
(`share_improved ≈ 50%`) has no robust contribution, however good its average
looks. `ablation.csv` keeps every world separately, so the dispersion behind an
average stays auditable.

Two tables are written at the root of every run, and rebuilt by the `ablation`
sub-command without simulating:

| File | Content |
| --- | --- |
| `ablation.csv` | one line per (world, component, metric): both values, delta, relative delta, improvement |
| `ablation_mean.csv` | one line per (component, metric): mean delta, `nb_improved`, `share_improved` |

Both are rewritten after **every case**, like `summary.csv`: a full grid takes
hours, so the decomposition has to be readable while the campaign is still
running, and an interrupted campaign has to stay analysable.

Figures `ablation_components.png`, `ablation_variants.png` and
`ablation_ladder_<scenario>.png` are produced with the rest.

## Notebooks

Two notebooks read those artifacts and run no simulation of their own:

| Notebook | Reads | Answers |
| --- | --- | --- |
| `notebooks/ablation.ipynb` | a run holding the four rungs | where the Nearest → BRAM-EV gap comes from |
| `notebooks/ablation_variants.ipynb` | a run holding `bramev` and its variants | whether each internal mechanism earns its place |

Both pick their run with `RunStore.latest_with_methods(...)`: the most recent
campaign that actually contains the methods being compared, rather than the
most recent one full stop — and, failing that, a message listing what each run
does contain.

Both open with the same check: **which flags were actually applied**, read from
`summary.csv` rather than from the registry. A rung that flips more than one
component, or a variant that neutralises more than one mechanism, is reported
before any result is read — because from that point on no number is
attributable.

They also close on the two readings that a bare average would hide: the
dispersion across worlds, and whether the mechanism was solicited at all
(collective learning needs an horizon longer than `SOCIETY_UPDATE_INTERVAL`;
multi-criteria selection needs demands that receive more than one offer). A
`+0.0%` under those conditions means *never exercised*, not *useless*.

## Caveats when reading a short run

Two components need a long enough horizon to express themselves at all:

* **Cross-station adaptation** only fires every `SOCIETY_UPDATE_INTERVAL` slots
  (144 by default, 12 h). A campaign shorter than that measures a contribution
  of exactly zero — because the mechanism never ran, not because it is useless.
* **The multi-criteria utility** only matters when a demand receives several
  offers. On a small grid most demands receive zero or one, and
  `bramev_nearest_offer` is then indistinguishable from `bramev`.
  `mean_offers_per_demand` in `summary.csv` says whether the comparison had any
  substance.

# Reproducibility and Fair Comparison

## The pipeline

All experiments are driven from the command line (see *Running the experiments*
for the commands). There is no experiment logic in notebooks: parameters,
orchestration, persistence and figures each live in their own module under
`src/pipeline/`, and a campaign is fully described by its parameters.

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

The sub-commands deliberately separate computing (`run`) from reporting
(`report`, `show`): figures are regenerated from the persisted tables, without
re-running a single simulation.

```bash
uv run main.py show --run-dir results_grid/<run> \
    --columns scenario nb_cars method rate_late
```

Exit codes: `0` success, `1` parameter or I/O error, `2` usage, `3` at least one
reservation invariant violated.

### Parameters

Every parameter has a CLI flag and a key in the configuration file; the CLI wins
over the file, so a preset can be reused with a single change:

```bash
uv run main.py run --config experiments/full_grid.yaml --seed 7 --label seed-7
```

| Group | Options |
| --- | --- |
| Experiment plan | `--seed`, `--scenarios`, `--cars`, `--methods` |
| Simulated world | `--total-time`, `--nb-stations`, `--nb-societies`, `--charg-spot-low/high`, `--strategy-noise` |
| Protocol | `--offer-ttl-slots`, `--late-cancel-fraction`, `--society-update-interval`, `--alpha-fixed` |
| Outputs | `--output-root`, `--label`, `--keep-logs`, `--save-latency`, `--save-tables`, `--figures`, `--log-every` |

Parameters are validated up front, as a whole: an unknown scenario, a duplicated
fleet size or more companies than stations is reported before any simulation
starts, with the full list of problems rather than the first one.

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
    tables/grid_stations.csv          the grid, flat: position, company, spots, alpha
    tables/grid_societies.csv         companies: position, strategy points, holdings
    tables/fleet_<n>cars.csv          the fleet, flat: initial position, autonomy…
    tables/<tag>_<table>.csv          stations, behaviors, acceptances, alpha, latency
    figures/grid.png                  the shared grid
    figures/fleet_<n>cars.png         initial vehicle positions on that grid
    figures/*.png                     rebuilt by `report`, no simulation needed
    logs/<tag>.txt                    detailed log (--keep-logs)
```

`grid.json` and `fleets/` are written **before the first simulation**, so the
environment is inspectable even if the campaign is interrupted — or never run
(`--dry-run` prints the plan without touching the disk). The worlds under
`worlds/` are entirely derived from them and kept for traceability only.

Other artifacts are written case by case, atomically: an interrupted campaign
leaves a valid `summary.csv` and a manifest that says how far it got.

### Figures decoupled from simulation

Figures are built from the persisted tables, never from live simulation objects.
Fixing an axis or a colour therefore costs a second instead of a full campaign:

```bash
uv run main.py report --latest
```

The generated figures are: the shared environment (`grid.png`, one
`fleet_<n>cars.png` per fleet size); per scenario: satisfaction, travel and
waiting time, latency breakdown, demand funnel, reservation outcomes, offer
protocol health, station load; and across scenarios: satisfaction overview,
scalability, and intent-vs-observed behaviour.

### Exploring a run

`notebooks/explore_run.ipynb` loads a finished run and displays its summary,
figures and detailed tables. It contains no experiment logic — that is the point:
the pipeline is the source of truth, the notebook only looks at its output.

## Single seed, independent streams

`src/experiments/seeding.py` derives every random source from one root seed
through `numpy.random.SeedSequence`. `random.seed` and `numpy.random.seed` are
also set, for the few draws that do not go through a dedicated stream.

Each vehicle owns three independent streams — movement, behaviour, request
parameters — keyed by `(seed, vehicle index)`. A stream depends on its key, not
on the call order, so the k-th behaviour draw of a given vehicle is the same for
every method under the same seed (*common random numbers*). Note the honest
limitation: once the methods diverge, realised trajectories diverge too, since a
vehicle that is served does not consume the same number of movement draws as one
that is not. What is guaranteed is a common source of randomness, not identical
histories.

## One world, all scenarios and all methods

`src/experiments/world.py` builds the initial world in three layers, so that a
measured difference can only come from what is actually being compared.

| Layer | Drawn | Depends on | Shared by |
| --- | --- | --- | --- |
| `GridSpec` | once per campaign | the seed only | every scenario, every fleet size, every method |
| `FleetSpec` | once per fleet size | the seed only | every scenario, every method |
| `WorldSpec` | composed, no draw | grid + fleet + scenario | every method of that case |

**The grid** — companies (position, strategy points) and stations (position,
owner, number of charging spots, initial `alpha`) — is drawn before the first
simulation and reused verbatim. `optimistic`, `balance` and `pessimistic`
therefore run on the same map, with the same capacity, owned by the same
companies.

**The fleet** — initial position, initial SoC, autonomy, recharge threshold,
preferences, charging power — is drawn once per fleet size. Each vehicle uses
its own `('car_init', idx)` stream, so fleets are **nested**: the first 50
vehicles of a 100-vehicle fleet are exactly the 50-vehicle fleet. The
scalability curve thus measures *adding* vehicles to a population, not
resampling it.

**The scenario** changes exactly one thing: `theta`, the behaviour
probabilities. Each vehicle carries a fixed normalised noise `u_k ∈ [-1, 1]`
drawn with the fleet, and the scenario supplies the base probabilities:

```
theta_k ∝ max(0.1, base_k + base_k · noise_scale · u_k)
```

A given vehicle therefore keeps the same "personality" — its relative deviation
from the average — in all three scenarios; only the base moves.

Finally, `build_world(spec, config)` turns a specification into agents **without
any random draw**, so calling it twice yields two identical but independent
worlds — that is what lets two methods run on exactly the same environment.
`define_agents(config, seed)` follows the same path, so any entry point gets the
same guarantee.

These properties are structural but invisible when reading the code: one stray
draw inside a scenario-dependent function would silently break them.
`tests/test_shared_world.py` therefore asserts them at three levels — on the
specs, on the materialised agents, and end-to-end on a real campaign: identical
grid across scenarios, identical initial vehicle positions, nested fleets, and
`theta` reproducible as a pure function of noise and base probabilities.

## Scenarios: a single source of truth

Behaviour probabilities live in `SimulationConfig.SCENARIOS` and are applied
with `config.set_scenario(name)`:

| Scenario | pres | abs | early | late | noise |
| --- | --- | --- | --- | --- | --- |
| optimistic | 75 | 10 | 9 | 6 | 0.15 |
| balance | 60 | 20 | 12 | 8 | 0.15 |
| pessimistic | 40 | 25 | 15 | 20 | 0.15 |

Severity grows monotonically from `optimistic` to `pessimistic` on the two
outcomes that cost the operator (`abs` and `late`), and `noise` is the same
everywhere so that scenarios differ only by their probabilities.

This table is the only place behaviour probabilities are defined. The values
previously hard-coded in the notebooks have been dropped: they contained two
inconsistencies — `late` was not monotone (6 -> 8 -> 5) and `early`/`late` were
swapped in the pessimistic scenario (35/5) — while `noise` varied across
scenarios (0.15 / 0.10 / 0.05), which confounded the comparison.

`uv run main.py scenarios` prints the table.

## Cancellation semantics

Each confirmed reservation draws an intent from `theta`, and the intent decides
**when** the cancellation happens. The observed outcome is then derived from the
time actually left before the planned arrival:

| Intent | Cancels at | Observed outcome |
| --- | --- | --- |
| `pres` | never | `pres` once the session ends |
| `abs` | never shows up, slot held until `t_dep` | `abs` |
| `early` | first slot after the reservation | `early` if more than `threshold` slots remain, otherwise `late` |
| `late` | when `threshold` slots or fewer remain | `late` |

`threshold = config.late_cancel_threshold(lead)` is bounded both by
`LATE_CANCEL_REF` (24 slots = 2 h) and by a fraction of the actual
request-to-arrival delay, so that both regimes are reachable.

`BehaviorTracker` records the drawn intent, the observed outcome, and every
reclassification, so the gap between scenario probabilities and measured rates
is visible instead of being attributed to the model.

### Known finding: `early` is currently unreachable

With `MAX_RAY_SEARCH = 1 km` and `CAR_SPEED = 4.167 km/slot`, a vehicle reaches
any eligible station within a single slot, so stations offer immediate slots and
the request-to-arrival delay is 0 to 1 slot (`mean_lead_slots` in every result).
There is nothing to anticipate: an `early` intent is always realised as a
`late` cancellation, and `nb_early_canc` stays at 0.

`BehaviorTracker.diagnostics()` reports this explicitly on every run. Two ways
forward, both model decisions rather than bug fixes:

* state in the report that `early` and `late` are indistinguishable under the
  current parameters, and give the `early` probability to `late`;
* introduce advance booking — a request emitted for a future arrival — which
  would give reservations a real lead time.

## Offer protocol

An offer is a revocable commitment. It carries an `offer_id`, an expiry
(`OFFER_TTL_SLOTS`) and the charger schedule version seen when it was issued.
A vehicle ranks the offers it received and confirms **exactly one**; the station
revalidates it (expiry, contiguity, slots actually free) before writing to its
schedule, and all other offers are explicitly expired. If a confirmation is
refused, the vehicle falls back to the next-best offer instead of giving up.

Every issued offer therefore ends up confirmed, expired or refused — the
identity `nb_offer_issued == nb_offer_expired + nb_reservations +
nb_confirm_refused` is asserted by the test suite.

## Contiguous charging slots

The MILP now enforces contiguity directly, with a start-of-charge indicator and
at most one rising edge per demand:

```
s[n,j,t] >= a[n,j,t] - a[n,j,t-1]        (missing a => 0)
sum_{j,t} s[n,j,t] <= 1
```

Duration stays variable (partial offers are still allowed, `<= d_n`) but
`[t_arr, t_dep)` now covers exactly `d_prop` slots. Previously the solver could
pick scattered slots that the code then turned into a continuous interval,
booking slots the optimiser had never allocated.

## Latency measurement

Demand identifiers used to be `t_c * len(cars)` — identical for every vehicle in
the same slot, so latency records overwrote each other. They are now
`t<slot>-c<vehicle>`, and a duplicate raises immediately.

Each demand records its full timeline: emission, reception of **each** offer,
reception of the last offer, selection by the vehicle, and confirmation.
`latency_report()` aggregates each stage independently over the demands where it
is defined, so a demand that received no offer is not counted as a zero.

## Reservation invariant

Every confirmed reservation resolves into exactly one outcome:

```
nb_reservations == nb_pres + nb_no_show + nb_early_canc + nb_late_canc
                 + nb_breakdown_canc + nb_unresolved
```

`nb_breakdown_canc` (vehicle stranded before its session) and `nb_unresolved`
(reservation still open at the end of the horizon) were missing, which made the
invariant structurally false and under-counted no-shows. `Simulation._finalize`
closes any remaining reservation, and `check_reservation_invariant` is checked
per station at the end of every run.

## Tests

```bash
uv run python -m tests                     # all suites
uv run python -m tests.test_priority1      # model fixes
uv run python -m tests.test_shared_world   # shared grid and fleets
uv run python -m tests.test_pipeline       # pipeline
uv run python -m tests.test_ablation       # ablation study
```

86 tests, no external test dependency.

`test_priority1.py` (26) covers the model fixes: reproducibility, shared
environment, unique demand identifiers, latency decomposition, slot contiguity,
offer confirmation safety, cancellation semantics.

`test_shared_world.py` (17) covers the comparability of the scenarios: one grid
for the whole campaign, fleets independent of the scenario and nested across
sizes, `theta` as a pure function of the fixed noise and the scenario's base
probabilities, and the same properties verified end-to-end on a real campaign.

`test_pipeline.py` (22) covers the orchestration: parameter validation, YAML/JSON
round-trip, CLI precedence over configuration files, run layout and artifact
round-trip, incremental writing, same-world comparison, reproducibility of a
whole campaign, figures rebuilt from the persisted tables alone, and CLI exit
codes.

`test_ablation.py` (21) covers the attributability of the results: each rung of
the ladder flips exactly one flag and leaves the internal mechanisms untouched,
each variant differs from `bramev` by exactly one mechanism, those flags
actually reach the agents (score index, score weighting, alpha, offer ranking),
the decomposition matches `summary.csv` with the right direction per metric, a
duplicated method in `summary.csv` is refused rather than silently overwritten,
the tables are rewritten after every case so a running campaign is already
analysable, every shipped config declares its `methods` explicitly (omitting the
key silently falls back to the default ladder — that mistake once cost a 21-hour
campaign), and — end to end — broadcasting really does produce more offers per
demand, which is what makes a measured contribution interpretable.


# Running a Simulation

A single simulation can be executed with:

```bash
uv sync

SEED=42 uv run python -m src.experiments.run
```

The seed defaults to `seeding.DEFAULT_SEED`. The initial world is written next to
the logs as `world_spec_A.json`, so the exact same run can be replayed later with
`define_agents_from_spec`.

For a full campaign, use the pipeline (`uv run main.py run`) — see *The pipeline*
above.

Default parameters are defined in:

```text
src/experiments/config.py
```

You can modify this file to change:

* number of vehicles;
* number of stations;
* simulation duration;
* charging station configuration;
* learning parameters;
* optimization settings;
* offer time-to-live and cancellation thresholds.

Scenario behaviour probabilities are **not** meant to be edited here: use
`config.set_scenario(name)`, which reads `SimulationConfig.SCENARIOS`.


# Running the Visualization Tool

The project includes a visualizer allowing the evolution of the simulation to be observed in real time.

The visualizer is driven by `config.VISUALIZE` (`True` by default in
`src/experiments/config.py`), and `run.py` runs a single BRAM-EV simulation with
it enabled:

```bash
SEED=42 uv run python -m src.experiments.run
```

The pygame window is only opened when `VISUALIZE` is `True`, so the pipeline runs
headless.

The visualizer will display:

* vehicle movements on the 2D grid;
* charging station locations;
* charging requests;
* charging sessions;
* simulation evolution over time.


# Scenarios

Three behavioral scenarios are available:

| Scenario    | Description                                                     |
| ----------- | --------------------------------------------------------------- |
| Optimistic  | Most users honor their reservations. Low no-show rate.          |
| Balance     | Intermediate behavior with moderate cancellations and absences. |
| Pessimistic | High rate of no-shows and late cancellations.                   |

Probabilities are defined once in `SimulationConfig.SCENARIOS` — see
*Scenarios: a single source of truth* above.

Each vehicle is assigned behavior probabilities governing:

* reservation fulfillment;
* early cancellation;
* late cancellation;
* absence.


## Main Components

### Vehicle Agents

Vehicle agents:

* move continuously on a 2D grid;
* generate charging requests when necessary;
* evaluate charging offers according to:

  * energy satisfaction,
  * travel distance,
  * waiting time.

### Charging Stations

Charging stations:

* receive charging requests;
* solve a local optimization problem;
* balance:

  * charging infrastructure utilization,
  * cancellation risk.

### Companies

Companies:

* own charging stations;
* maintain reputation systems;
* periodically update station strategies through collective learning.


## Reproducibility

Every simulation is driven by a single seed. The recommended way to reproduce the
results of the report is:

```bash
uv run main.py run --config experiments/full_grid.yaml
```

Each run stores its parameters, the shared grid (`grid.json`), the fleets
(`fleets/`), the composed world of every case and the full metrics, so a figure
can always be traced back to the campaign that produced it — see *The pipeline*
for the layout. All scenarios of a run share one grid and, at equal fleet size,
one set of initial vehicle positions; only the behaviour probabilities change
(see *One world, all scenarios and all methods*).

Also available:

* the single-run launcher with the visualizer, `uv run python -m src.experiments.run`;
* `notebooks/explore_run.ipynb` to explore a finished run interactively.

Visualizer logs go to `outputs/`, campaign artifacts to `results_grid/`.

The three per-scenario notebooks that previously held the experiments (about 400
cells each, duplicated across `results/` and `bram-ev/`) have been replaced by
this pipeline. They remain in the history:

```bash
git show 68b16ad:results/Optimistic.ipynb > Optimistic.ipynb
```


## Author

Fatoumata WADIOU
