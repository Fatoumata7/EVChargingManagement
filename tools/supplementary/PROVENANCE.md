# Provenance of the executed code

Commit identifiers were removed for anonymity. `provenance.json` gives the
SHA-256 of every module each campaign executed and whether it is
byte-identical to the corresponding file in `code/`.

## What each campaign executed

A campaign is run with `python -m src.pipeline.cli run --config <yaml>`. The
modules it imports are listed in `provenance.json`: the simulator
(`src/env`, `src/experiments`, `src/metrics`) and the run pipeline
(`src/pipeline/{cli,runner,params,store,tables,ablation,aggregate,figures}`).

- **Main campaign (`ablation_campaign/`).** Run from a clean working tree.
  The directory is that tree.
- **Congestion pilot (`congestion_pilot/`).** Its run manifest reports local
  modifications (`git_dirty: true`), so the commit it started from is not
  enough to recover the code. Those modifications only touched the analysis
  layer: storage at full precision in `ablation.py`/`aggregate.py`, new
  figure labels in `figures.py`, and the new re-analysis modules. The
  modified tree was committed right after the run. Every module the pilot
  imported was last modified *before* the pilot started, so the committed
  files are exactly the ones executed. The directory holds those files.
  - `reanalysis.py` and `congestion.py` are left out. The pilot never
    imported them, and they were extended after its launch.
  - Their final versions are in `code/`, which produced every table.

- **Which code built the tables.** Every table and figure in `outputs/` is
  built by `code/`, from the per-case results and per-request data. The main
  campaign ran older versions of three post-processing modules (`ablation.py`,
  `aggregate.py`, `figures.py`: storage rounding and former labels). They only
  produced the raw run's root-level tables and figures, which are not shipped
  and are superseded by `outputs/`. The simulator it executed is identical to
  the one in `code/`.

## Checks

- The simulator (`src/env`, `src/experiments`, `src/metrics`) is
  byte-identical in both campaigns: `simulator_identical_across_campaigns` is
  `true` in `provenance.json`. Only the capacity parameters in the
  configuration differ.
- The random draws of the grid do not depend on the number of chargers. For
  seeds 1–3, the pilot's station positions, operator assignments, initial
  alpha values, operator strategies and 250-vehicle fleets are identical to
  those of the main campaign (`data/*/grids`, `data/*/fleets`). Only
  `nb_charg_spot` changes. This is tested in
  `code/tests/test_shared_world.py::test_charger_count_changes_nothing_else_in_the_grid`.
- Only the project `name` and `description` fields of `pyproject.toml` and
  `uv.lock` were changed, for anonymity. Every `.py` file is shipped as
  executed.
