"""
energy_fix.py — Migrate a run written before the planned/delivered energy split.

    python -m src.pipeline.energy_fix results_grid/<run>                 # estimate
    python -m src.pipeline.energy_fix results_grid/<run> --resimulate    # exact

Results written before the split carry a single `station_demand_kWh`, with
three defects:

* **unit** — `charging_power` (km/slot) x 0.1 kWh/km is an energy *per slot*,
  but it was multiplied by a duration in hours: every value is 12 times too
  small on a 5-minute slot;
* **scope** — it was logged in `record_offer_accepted`, which a no-show never
  reaches: the reservations whose slots are blocked and never used were left
  out;
* **meaning** — it priced the other reservations at their full duration, so
  cancellations and cut-short sessions counted as supplied energy.

Neither the no-show reservations nor the energy of each charging slot were
stored, so the two energies cannot be read back from a legacy result:

* ``--resimulate`` replays every case on its persisted world. The simulation is
  deterministic and the energy measurement feeds no decision, so the replay
  reproduces the run exactly; this is checked on every decision-driven field
  before anything is written, and the whole run is refused otherwise. Both
  energies are then **exact** (``energy_exact`` True).
* by default, both are **estimated** station by station, from what the result
  and the tables do store: ``nb_slots_reserved`` and ``nb_slots_served``, each
  priced at ``e_m``, the mean kWh per slot of the vehicles the station accepted
  (`tables/<tag>_acceptances.csv` joined with the fleet), times a calibration
  factor (`PLANNED_FACTOR`, `DELIVERED_FACTOR`). ``energy_exact`` is False,
  and the flag follows the values into `summary.csv`. The factors and the
  error of the estimator, measured against the exact replay of the smoke run,
  are documented next to them.

Then `summary.csv`, the station tables, the ablation and replicate tables and
the figures are rebuilt from the migrated results; the manifest records the
migration. A result already migrated is left untouched, so the command can be
rerun safely.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from loguru import logger

from src.metrics.metrics import kwh_per_slot
from src.experiments.config import SimulationConfig
from src.pipeline import ablation, aggregate, figures, tables
from src.pipeline.params import CaseParams
from src.pipeline.store import RunStore, _utc_stamp

LEGACY_KEY = 'station_demand_kWh'

#: Fields that a replay must reproduce exactly. Latencies and wall time are
#: machine time and are left out; the energy is what is being rebuilt.
REPLAY_CHECKED = ('stations', 'behaviors', 'breakdowns', 'nb_demands',
                  'invariant_ok')
REPLAY_CHECKED_METRICS = ('user_request_satisfaction',
                          'mean_travel_distance_km', 'mean_waiting_time_h')


# Calibration of the estimator, fitted on the exact replay of
# 20260919T190635Z_seeds1-2-3_smoke (36 cases, pessimistic, 150 vehicles):
# sum of the exact energies over sum of the estimates at factor 1.
#
# * DELIVERED_FACTOR < 1: the slot that fills the battery is only partly used.
# * PLANNED_FACTOR < 1: `e_m` averages the accepted vehicles one per
#   reservation, but a powerful vehicle needs fewer slots for the same need,
#   so the slot-weighted mean power is lower than the plain mean.
#
# Leave-one-seed-out error on the per-case totals (fit on two seeds, test on
# the third): delivered mean +0.01 %, sd 0.91 %, max |err| 1.64 %; planned mean
# +0.06 %, sd 2.77 %, max |err| 4.00 %. Per station the spread is wider (sd ~6-7
# %). The factors were fitted on one scenario and one horizon: a run with other
# settings should be replayed (`--resimulate`) wherever the exact value matters.
PLANNED_FACTOR = 0.9333
DELIVERED_FACTOR = 0.9417


def fleet_kwh_per_slot(fleet_cars) -> dict:
    """car_id -> kWh per slot, from a persisted fleet."""
    config = SimulationConfig()
    return {int(car['idx']): kwh_per_slot(car['charging_power'], config)
            for car in fleet_cars}


def estimate_energy(result: Mapping[str, Any], acceptances, car_kwh: Mapping,
                    planned_factor: float = PLANNED_FACTOR,
                    delivered_factor: float = DELIVERED_FACTOR,
                    ) -> tuple[dict, dict]:
    """
    `(planned, delivered)` kWh per station, estimated from the stored counts.

    planned_m   = nb_slots_reserved_m x e_m x PLANNED_FACTOR
    delivered_m = nb_slots_served_m   x e_m x DELIVERED_FACTOR

    `e_m` is the mean kWh per slot of the vehicles accepted by station m; a
    station that accepted nobody falls back on the fleet mean (it then has no
    served slot anyway).
    """
    fleet_mean = sum(car_kwh.values()) / len(car_kwh)
    per_station: dict[str, list[float]] = {}
    for row in acceptances:
        per_station.setdefault(str(row['station_id']), []).append(
            car_kwh[int(row['car_id'])])
    planned, delivered = {}, {}
    for station in result['stations']:
        sid = str(station['station_id'])
        values = per_station.get(sid)
        e_m = sum(values) / len(values) if values else fleet_mean
        planned[sid] = round(
            station.get('nb_slots_reserved', 0) * e_m * planned_factor, 3)
        delivered[sid] = round(
            station.get('nb_slots_served', 0) * e_m * delivered_factor, 3)
    return planned, delivered


def case_of(result: Mapping[str, Any]) -> CaseParams:
    return CaseParams(scenario=result['scenario'],
                      nb_cars=result['config']['nb_cars'],
                      method=result['mode'], seed=result['seed'])


def _replay(args) -> dict:
    """Worker: replay one case, return its fresh result."""
    from src.pipeline.runner import run_case
    root, case = args
    store = RunStore.open(root)
    params = store.read_params()
    spec = store.load_world(case.scenario, case.nb_cars, case.seed)
    _, outcome = run_case(case, params, spec)
    # Same round trip as `save_result`, so that the comparison with the stored
    # result sees string keys and lists, not ints and tuples.
    return json.loads(json.dumps(outcome.result, default=str))


def check_replay(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """Names of the decision-driven fields where the replay diverges."""
    diffs = [k for k in REPLAY_CHECKED if old.get(k) != new.get(k)]
    diffs += [f'metrics.{k}' for k in REPLAY_CHECKED_METRICS
              if old['metrics'].get(k) != new['metrics'].get(k)]
    return diffs


def migrate_result(result: dict, fresh: Mapping[str, Any] | None = None,
                   acceptances=None, car_kwh: Mapping | None = None) -> dict:
    """
    Rewrite the energy fields of one result, in place, and return it.

    With `fresh` (a validated replay) both energies are copied from it;
    otherwise they are estimated from `acceptances` and `car_kwh`.
    """
    met = result['metrics']
    if fresh is not None:
        planned, delivered = (
            {str(k): v for k, v in fresh['metrics'][key].items()}
            for key in ('station_energy_planned_kWh',
                        'station_energy_delivered_kWh'))
        method = 'resimulated'
    else:
        planned, delivered = estimate_energy(result, acceptances, car_kwh)
        method = (f'estimated (planned x{PLANNED_FACTOR}, '
                  f'delivered x{DELIVERED_FACTOR})')
    legacy = met.pop(LEGACY_KEY)
    met['station_energy_planned_kWh'] = planned
    met['station_energy_delivered_kWh'] = delivered
    met['energy_exact'] = fresh is not None
    result['energy_fix'] = {
        'migrated_utc': _utc_stamp(),
        'legacy_station_demand_kWh': legacy,
        'method': method,
    }
    return result


def migrate_run(root: str | Path, resimulate: bool = False,
                workers: int | None = None, render: bool = True) -> dict:
    """
    Migrate every result of a run, then rebuild its derived tables.

    Returns a small report: counts, and for a replay the cases refused.
    """
    store = RunStore.open(root)
    manifest = store.read_manifest()
    cases = [CaseParams(scenario=c['scenario'], nb_cars=c['nb_cars'],
                        method=c['method'], seed=c['seed'])
             for c in manifest['cases']]
    results = {case.tag: store.load_result(case) for case in cases}
    todo = [case for case in cases
            if LEGACY_KEY in results[case.tag]['metrics']]
    logger.info(f'{store.root.name}: {len(todo)}/{len(cases)} results to migrate '
                f'({"replay" if resimulate else "estimate"})')

    fresh: dict[str, dict] = {}
    refused: dict[str, list[str]] = {}
    if resimulate and todo:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            jobs = [(str(store.root), case) for case in todo]
            for case, new in zip(todo, pool.map(_replay, jobs)):
                diffs = check_replay(results[case.tag], new)
                if diffs:
                    refused[case.tag] = diffs
                    logger.error(f'  {case.tag}: replay diverges on {diffs}')
                else:
                    fresh[case.tag] = new
                    logger.info(f'  {case.tag}: replay identical')
        if refused:
            raise RuntimeError(
                f'{len(refused)} replays diverge from the stored run; nothing '
                f'written. First: {next(iter(refused.items()))}')

    fleets: dict[tuple, dict] = {}
    for case in todo:
        if case.tag in fresh:
            result = migrate_result(results[case.tag], fresh[case.tag])
        else:
            key = (case.nb_cars, case.seed)
            if key not in fleets:
                fleets[key] = fleet_kwh_per_slot(
                    store.load_fleet(case.nb_cars, case.seed).cars)
            acceptances = _read_table(store.table_path(case, 'acceptances'))
            result = migrate_result(results[case.tag], None,
                                    acceptances, fleets[key])
        store.save_result(case, result)
        store.write_table(case, 'stations', tables.station_table(result))

    # Every derived table is a pure function of the results: rebuild them all,
    # in the manifest order the campaign wrote them in.
    rows = [tables.summary_row(results[case.tag]) for case in cases]
    store.write_summary(rows, tables.SUMMARY_FIELDS)
    ablation.write_tables(store, rows)
    aggregate.write_tables(store, rows)
    if render:
        from src.pipeline.cli import _shared_tables
        figures.render_all(store.read_summary(), store.figures_dir,
                           **_shared_tables(store))

    if todo:
        manifest = store.read_manifest()
        manifest.setdefault('energy_fix', []).append({
            'migrated_utc': _utc_stamp(),
            'nb_results': len(todo),
            'method': 'resimulated' if resimulate else 'estimated',
        })
        store.write_manifest(manifest)
    return {'migrated': len(todo), 'total': len(cases),
            'resimulated': len(fresh)}


def _read_table(path: Path) -> list[dict]:
    import csv
    if not path.is_file():
        return []        # a case with no accepted offer writes no table
    with path.open(newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('runs', nargs='+', help='run directories')
    p.add_argument('--resimulate', action='store_true',
                   help='replay every case: exact planned and delivered energy')
    p.add_argument('--workers', type=int, default=None)
    p.add_argument('--no-figures', action='store_true')
    args = p.parse_args(argv)
    for root in args.runs:
        report = migrate_run(root, resimulate=args.resimulate,
                             workers=args.workers, render=not args.no_figures)
        logger.info(f'{root}: {report}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
