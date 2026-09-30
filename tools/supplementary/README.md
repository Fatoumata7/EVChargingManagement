# Supplementary material — reproducing the tables and analyses

This archive rebuilds every table, confidence interval, paired test (with Holm
correction) and figure of the paper from the stored simulation outputs.
**No simulation is needed.** The full rebuild takes about a minute.

## Contents

```
README.md                  this file
SHA256SUMS                 checksum of every file of the archive
code/                      analysis code (and simulator) used to build outputs/
code_executed/             code each campaign actually executed, with provenance
  ablation_campaign/       main campaign
  congestion_pilot/        congestion pilot
  PROVENANCE.md, provenance.json
configs/                   YAML configurations and full resolved parameters
data/
  ablation_run/<run>/      main campaign: raw per-case results and per-request data
  pilot_run/<run>/         congestion pilot: same layout
outputs/
  ablation_modified/       main campaign: corrected indicators and statistics
  congestion_pilot/        pilot: same indicators, capacity effect, components
scripts/
  rebuild_all.sh           rebuilds outputs/ into rebuilt/ and compares them
  compare_outputs.py       comparison + definition-consistency check
```

## Environment

| Component | Version |
|---|---|
| Python | 3.12.0 (`requires-python >= 3.12`) |
| OR-Tools | 9.15.6755 (`ortools` wheel) |
| SCIP | 10.0.0, bundled in the OR-Tools wheel (LP solver SoPlex 8.0.0) |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |
| Matplotlib | 3.10.9 |
| loguru | 0.7.3 |
| PyYAML | 6.0.3 |

- The exact dependency set is pinned in `code/uv.lock`, created with uv
  0.11. It also includes packages the analysis does not use: pandas, seaborn,
  pygame, ipykernel, python-dotenv.
- The simulations ran on macOS 26 (arm64) with 8 worker processes.
- The analysis itself is platform-independent.

## Rebuilding everything

With [uv](https://docs.astral.sh/uv/):

```bash
uv sync --frozen --project code
PYTHON="uv run --project code python" scripts/rebuild_all.sh
```

Without uv, in any Python 3.12 environment:

```bash
python -m pip install ortools==9.15.6755 numpy==2.4.6 scipy==1.17.1 \
    matplotlib==3.10.9 loguru==0.7.3 pyyaml==6.0.3
scripts/rebuild_all.sh
```

`rebuild_all.sh` runs three steps:

1. `python -m src.pipeline.reanalysis data/ablation_run/<run> rebuilt/ablation_modified`
   recomputes the indicators of the 720 cases of the main campaign and writes:
   - the means and 95 % confidence intervals;
   - the paired differences and paired t-tests;
   - the Holm-corrected ladder tests;
   - the figures.
2. `python -m src.pipeline.congestion data/pilot_run/<run> data/ablation_run/<run> rebuilt/congestion_pilot`
   does the same for the 24 pilot cases, and pairs each pilot case with the
   same method on the same world at the reference capacity.
3. `python scripts/compare_outputs.py outputs rebuilt` checks every shipped CSV
   (same header and rows, numeric cells within 1e-12 relative) and Markdown
   table. It also checks that the pilot and the main campaign use identical
   indicator columns, and that the pilot's reference rows are identical to
   the main campaign's.

Each step can also be run on its own, from `code/`, with `PYTHONPATH=.`:

```bash
python -m src.pipeline.holm <dir holding a re-analysed summary.csv>   # Holm tables only
python -m src.pipeline.reanalysis --figures-only <raw run> <output>   # figures only
python -m tests                                                       # test suites
```

## The two campaigns

| | Main campaign | Congestion pilot |
|---|---|---|
| Configuration | `configs/ablation.yaml` | `configs/congestion_pilot.yaml` |
| Seeds (replicates) | 1–10 | 1–3 |
| Scenarios | optimistic, balance, pessimistic | balance, pessimistic |
| Fleet sizes | 50, 150, 250 | 250 |
| Methods | greedy, multistation, multistation_rep, bramev, nearest_available, min_waiting, load_aware, random_feasible | nearest_available, multistation, multistation_rep, bramev |
| Stations / operators | 40 / 4 | 40 / 4 |
| Chargers per station | uniform in {4, 5, 6} (194–205 in total) | 2 (80 in total) |
| Horizon | 1440 slots of 5 min (5 days) | same |
| Cases | 720 | 24 |

- Every other parameter is identical; see `configs/*_params.json`.
- A seed fixes the grid, the fleet and the behaviour draws. All methods of the
  same seed, scenario and fleet run on the same world, which is what makes the
  paired comparisons possible.
- The pilot keeps the grid and the fleets of seeds 1–3: only the number of
  chargers changes (see `code_executed/PROVENANCE.md`).

## Data

Each `data/*/<run>/` directory contains:

| File | Content |
|---|---|
| `results/<tag>.json` | complete result of one case: counts, per-station outcomes, solver statuses |
| `tables/<tag>_latency.csv` | **one row per request**: outcome, energy requested and delivered, offers, latencies |
| `tables/<tag>_acceptances.csv` | one row per accepted offer: distance, waiting time |
| `tables/<tag>_stations.csv`, `_behaviors.csv`, `_alpha.csv` | per-station, per-behaviour and alpha tables |
| `tables/seed<s>_grid_*.csv`, `seed<s>_fleet_*.csv` | the grid and the fleet, flat |
| `grids/`, `fleets/`, `worlds/` | the generated worlds, as JSON |
| `summary.csv` | raw per-case summary written by the simulator (**former indicator names**) |
| `params.json`, `manifest.json` | resolved parameters; per-case wall time and invariant check |

`<tag>` is `seed<s>_<scenario>_<n>cars_<method>`.

The raw `summary.csv` is only an input. It still uses the former name
`satisfied_rate`, and its rates are rounded to 4 decimals. Every analysis uses
`outputs/*/summary.csv`.

## Indicators

All service indicators are computed over **all requests**, from the
per-request table.

| Column | Definition |
|---|---|
| `served_rate` | request **served, even partially**: at least one charging slot delivered (formerly `satisfied_rate`) |
| `fully_satisfied_rate` | request **fully satisfied**: `delivered ≥ requested − 0.001 kWh` |
| `service_ratio_mean` | mean of `min(1, delivered / requested)`; an unserved request counts 0 |
| `service_ratio_mean_served` | same, over served requests only |
| `network_occupancy_rate` | charger-slots still booked at their own slot / (chargers × horizon) |
| `network_service_rate` | charger-slots actually spent charging / (chargers × horizon) — effective use |
| `no_offer_rate`, `request_rejection_rate` | requests with no offer / never confirmed, per request |
| `station_rejection_rate` | refusals per (station, request) pair |
| `mean_waiting_time_min` | mean waiting time over accepted offers |
| `excluded_car_share` | vehicles excluded (stranded) during the run |
| `nb_ilp_not_optimal` | MILP solves not proven optimal |
| `nb_ilp_feasible_time_limit` | of which: stopped at the 5-min time limit **with** a feasible solution (used to make offers) |
| `nb_ilp_failed` | of which: no solution at all (true failures) |

**Tolerance of full satisfaction.**
- Per-request energies are stored rounded to 1e-4 kWh, so a difference is
  known to within ±1e-4 kWh.
- One charging slot delivers about 0.7 kWh. A 1 Wh tolerance therefore cannot
  turn a missing slot into full service.
- `outputs/ablation_modified/full_service_sensitivity.csv` recomputes the rate
  with tolerances of 0, 1e-4, 1e-3, 1e-2 and 1e-1 kWh. The mean over the 720
  cases moves by 0.02 percentage points between 0 and 1e-3 kWh.

**Precision.**
- Rates are recomputed from counts, and every CSV is written at full
  precision. Rounding happens only in `tables_display/*.md` and in the pilot
  `README.md`.
- A few inputs exist only as rounded by the simulator:
  - per-request energies (1e-4 kWh);
  - per-station energies (0.1 kWh), hence `energy_delivered_kwh` and
    `energy_delivery_rate`;
  - per-station rates (4 decimals);
  - planning coverage and latencies.

**Solver status.**
- Main campaign: 84 solves were not proven optimal. All 84 stopped at the time
  limit with a feasible solution, and none failed.
  - They occur only with 250 vehicles, at 4 (seed, station) pairs, and in the
    7 methods that query several stations.
  - Their incumbent can depend on machine load.
  - They are listed in `outputs/ablation_modified/solver_status.csv`.
- Pilot: every solve was proven optimal.

## Statistics

- **Means and intervals** (`summary_mean.csv`, `pilot_by_method.csv`): mean
  over the seeds, sample standard deviation, and 95 % CI with Student's *t* on
  n − 1 degrees of freedom.
- **Paired comparisons** (`paired.csv`, `components.csv`, `capacity_effect.csv`):
  - The difference is taken within each world (same seed, scenario and fleet),
    then averaged.
  - The test is a paired t-test, i.e. a one-sample t-test of the per-seed
    differences.
  - `significant_95` is read off the 95 % CI.
- **Holm correction** (`outputs/ablation_modified/holm_ladder.csv` and
  `tables_display/holm_ladder.md`):
  - There is one family per contrast of the ablation ladder:
    - multi-station search (greedy → multistation);
    - reputation (multistation → multistation_rep);
    - cross-station adaptation (multistation_rep → bramev).
  - Each family holds 9 configurations (3 scenarios × 3 fleet sizes) × 3
    service indicators (`served_rate`, `fully_satisfied_rate`,
    `service_ratio_mean`) = 27 paired t-tests, with 10 pairs each.
  - Holm's step-down procedure controls the family-wise error rate at
    α = 0.05 within each family. The CIs shown next to it are unadjusted.
  - Result:
    - multi-station search: 15 of 27 tests significant after correction;
    - reputation: 0 of 27;
    - adaptation: 0 of 27 (smallest adjusted p = 0.51).
- **Pilot:** exploratory (3 seeds, Student multiplier 4.30). No multiplicity
  correction is applied.

## Output files

| File | Content |
|---|---|
| `ablation_modified/summary.csv` | one row per case (720), corrected indicators |
| `ablation_modified/summary_mean.csv` | mean, SD, 95 % CI per (scenario, fleet, method, metric) |
| `ablation_modified/paired.csv` | paired differences: ladder, baselines, variants |
| `ablation_modified/ablation.csv`, `ablation_mean.csv` | per-world differences / pooled means |
| `ablation_modified/holm_ladder.csv` | the 3 × 27 Holm-corrected ladder tests |
| `ablation_modified/solver_status.csv` | stations with a non-optimal solve |
| `ablation_modified/full_service_sensitivity.csv` | full-satisfaction rate under each tolerance |
| `ablation_modified/tables_display/*.md` | rounded display tables |
| `ablation_modified/figures/*.png` | figures |
| `congestion_pilot/summary.csv` | one row per pilot case (24), same columns as the main campaign |
| `congestion_pilot/reference_summary.csv` | the 24 matching main-campaign cases (4–6 chargers) |
| `congestion_pilot/pilot_by_method.csv`, `reference_by_method.csv` | mean, SD, 95 % CI per method |
| `congestion_pilot/capacity_effect.csv` | pilot − reference, paired on the seed |
| `congestion_pilot/components.csv` | ladder rungs and baseline, paired within the pilot |
| `congestion_pilot/solver_status.csv` | non-optimal solves (none) |
| `congestion_pilot/README.md` | rounded display tables |
| `congestion_pilot/figures/*.png` | figures |

## Re-running the simulations (not needed)

```bash
cd code
python -m src.pipeline.cli run --config experiments/ablation.yaml --workers 8
python -m src.pipeline.cli run --config experiments/congestion_pilot.yaml --workers 8
```

- The main campaign took about 17.5 h on 8 workers; the pilot took 13 min.
- The simulations are seeded and deterministic, except for the 84 solves that
  hit the MILP time limit. Their incumbent may differ on another machine.
