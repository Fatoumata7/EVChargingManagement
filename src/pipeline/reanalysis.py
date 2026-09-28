"""
reanalysis.py — Re-derive the indicators of a finished run, without simulating.

A run keeps, for every case, the complete result (`results/<tag>.json`) and the
per-demand record (`tables/<tag>_latency.csv`). Everything below is recomputed
from those, so a change in how an indicator is *defined* or *reported* costs a
pass over the files, not a new campaign.

What changes with respect to the tables written at the end of the run:

`served_rate` (formerly `satisfied_rate`)
    A demand is *served* when at least one charging slot was delivered to it —
    even when that covers only part of its need. The former name suggested a
    fully met need; the definition is unchanged, only the name is.

`fully_satisfied_rate` (new)
    Share of the demands whose delivered energy covers the requested energy:
    `delivered >= requested - FULL_SERVICE_TOL_KWH`. Over **all** demands, the
    unserved ones included.

`service_ratio_mean` (kept, recomputed)
    Mean over **all** demands of `min(1, delivered / requested)`, an unserved
    demand counting 0: the share of the energy need actually met.
    `service_ratio_mean_served` restricts it to the served demands.

Full precision
    Rates are recomputed from counts rather than read back from the rounded
    rates of `summary.csv`, and every table is written unrounded. Rounding
    happens in `tables_display/` only. The few inputs that the simulator itself
    stored rounded (per-demand energies to 1e-4 kWh, station energies to
    0.1 kWh, latencies, planning coverage) are used as stored and listed in the
    README of the output.

Solver status
    `nb_ilp_not_optimal` counts every MILP solve not proven optimal;
    `nb_ilp_failed` those that returned no solution at all. Their difference is
    the solves stopped by the time limit with a feasible incumbent, which *did*
    produce offers. `solver_status.csv` lists them station by station.

Usage:
    python -m src.pipeline.reanalysis <source run dir> <output dir>
    python -m src.pipeline.reanalysis --figures-only <source run dir> <output dir>
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from src.env.station import ILP_TIME_LIMIT_MS
from src.metrics.metrics import CANCELLED_OUTCOMES
from src.pipeline import ablation, aggregate
from src.pipeline.ablation import GOAL_UP, Metric
from src.pipeline.store import RunStore, _coerce, _write_csv

#: Absolute tolerance (kWh) of "the need is fully met". Per-demand energies are
#: stored rounded to 1e-4 kWh, so a difference is known to +/- 1e-4 kWh; 1 Wh
#: covers that with margin and stays ~700 times below the energy of a single
#: charging slot (~0.7 kWh), so it cannot turn a missing slot into a full
#: service.
FULL_SERVICE_TOL_KWH = 1e-3

#: Tolerances reported side by side in `full_service_sensitivity.csv`, to show
#: that the indicator does not depend on the choice above.
SENSITIVITY_TOLS_KWH = (0., 1e-4, 1e-3, 1e-2, 1e-1)

#: Columns renamed in `summary.csv`.
RENAMED = {
    'nb_demands_satisfied':         'nb_demands_served',
    'satisfied_rate':               'served_rate',
    'service_ratio_mean_satisfied': 'service_ratio_mean_served',
}


# ----------------------------------------------------------------------
# Metrics of the re-analysis
# ----------------------------------------------------------------------

def _metrics() -> tuple[Metric, ...]:
    """The run's metrics, with the service indicators renamed and completed."""
    out: list[Metric] = []
    for m in ablation.METRICS:
        if m.column == 'satisfied_rate':
            out.append(Metric('served_rate', 'Demands served (even partially)',
                              GOAL_UP, '%'))
            out.append(Metric('fully_satisfied_rate', 'Demands fully satisfied',
                              GOAL_UP, '%'))
        elif m.column == 'service_ratio_mean':
            out.append(replace(m, label='Share of energy need met (all demands)'))
            out.append(Metric('service_ratio_mean_served',
                              'Share of energy need met (served demands)',
                              GOAL_UP, '%'))
        elif m.column == 'mean_service_rate':
            out.append(m)
            out.append(Metric('network_occupancy_rate',
                              'Charger occupancy (network, held slots)',
                              GOAL_UP, '%'))
            out.append(Metric('network_service_rate',
                              'Charger effective use (network, charging slots)',
                              GOAL_UP, '%'))
        else:
            out.append(m)
    return tuple(out)


METRICS: tuple[Metric, ...] = _metrics()

#: Metrics shown in the display tables, in this order.
HEADLINE: tuple[str, ...] = ('served_rate', 'fully_satisfied_rate',
                             'service_ratio_mean', 'service_ratio_mean_served')


# ----------------------------------------------------------------------
# Per-case recomputation
# ----------------------------------------------------------------------

def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as fh:
        return [{k: _coerce(v) for k, v in row.items()}
                for row in csv.DictReader(fh)]


def demand_service(demands: Sequence[Mapping[str, Any]],
                   tol_kwh: float = FULL_SERVICE_TOL_KWH) -> dict:
    """
    Service indicators from the per-demand records of one case.

    A demand with a non-positive request has no ratio (as in
    `MetricsCollector.service_report`); it still counts in the denominator of
    the rates, and is fully satisfied by construction.
    """
    n = len(demands)
    served = [d for d in demands if d['outcome'] == 'satisfied']
    full = sum(1 for d in demands
               if d['energy_delivered_kwh'] >= d['energy_requested_kwh'] - tol_kwh)

    def ratio(d):
        req = d['energy_requested_kwh']
        return None if req <= 0 else min(1., d['energy_delivered_kwh'] / req)

    all_ratios = [r for r in map(ratio, demands) if r is not None]
    srv_ratios = [r for r in map(ratio, served) if r is not None]
    return {
        'nb_demands_fully_satisfied': full,
        'fully_satisfied_rate':       _ratio(full, n),
        'fully_satisfied_share_of_served': _ratio(full, len(served)),
        'service_ratio_mean':         mean(all_ratios) if all_ratios else None,
        'service_ratio_mean_served':  mean(srv_ratios) if srv_ratios else None,
    }


def solver_rows(result: Mapping[str, Any], row: Mapping[str, Any]) -> list[dict]:
    """Stations of one case whose MILP was not proven optimal at least once."""
    out = []
    for st in result['stations']:
        not_opt = st.get('nb_ilp_not_optimal', 0)
        failed = st.get('nb_ilp_failed', 0)
        if not (not_opt or failed):
            continue
        proc = (result['metrics'].get('mean_processing_time_ms') or {})
        out.append({
            'scenario': row['scenario'], 'nb_cars': row['nb_cars'],
            'method': row['method'], 'world_seed': row['world_seed'],
            'station_id': st['station_id'], 'society_id': st.get('society_id'),
            'nb_charg_spot': st.get('nb_charg_spot'),
            'nb_request': st.get('nb_request'),
            'nb_ilp_not_optimal': not_opt,
            'nb_ilp_failed': failed,
            'nb_ilp_feasible_time_limit': not_opt - failed,
            'mean_processing_ms': proc.get(str(st['station_id'])),
            'time_limit_ms': ILP_TIME_LIMIT_MS,
        })
    return out


def recompute_row(row: Mapping[str, Any], result: Mapping[str, Any],
                  demands: Sequence[Mapping[str, Any]],
                  acceptances: Sequence[Mapping[str, Any]]) -> dict:
    """
    One row of the new `summary.csv`: the old row, renamed, with every rate
    that a count can give recomputed from that count.
    """
    srv = result['metrics']['service']
    lat = result['metrics']['latency']
    beh = result['behaviors']
    stations = result['stations']
    counts = srv['outcome_counts']
    n = srv['nb_demands']

    # Coherence of the two sources before mixing them.
    if len(demands) != n:
        raise ValueError(f"{row['method']} {row['scenario']} {row['nb_cars']} "
                         f"seed {row['world_seed']}: {len(demands)} demand "
                         f"records for {n} demands")
    by_outcome = Counter(d['outcome'] for d in demands)
    if by_outcome['satisfied'] != srv['nb_demands_satisfied']:
        raise ValueError('served count differs between latency table and result')

    def total(key: str) -> float:
        return sum(s.get(key, 0) for s in stations)

    capacity = total('nb_charg_spot') * result['config']['total_time']

    out = {RENAMED.get(k, k): v for k, v in row.items()}
    cancelled = sum(counts.get(o, 0) for o in CANCELLED_OUTCOMES)
    out.update({
        'served_rate':       _ratio(srv['nb_demands_satisfied'], n),
        'cancelled_rate':    _ratio(cancelled, n),
        'in_progress_rate':  _ratio(srv['nb_demands_in_progress'], n),
        'abandon_rate':      _ratio(srv['nb_demands_abandoned'], n),
        'answer_rate':       _ratio(lat['nb_demands_answered'], n),
        'confirm_rate':      _ratio(lat['nb_demands_confirmed'], n),
        'no_offer_rate':     _ratio(n - lat['nb_demands_answered'], n),
        'request_rejection_rate': _ratio(n - lat['nb_demands_confirmed'], n),
        'mean_offers_per_demand': _ratio(lat['nb_offers_received'], n),
        'station_rejection_rate': _ratio(total('nb_station_level_rejections'),
                                         total('nb_request')),
        'slot_waste_rate':   (1. - total('nb_slots_served') / total('nb_slots_reserved')
                              if total('nb_slots_reserved') else None),
        'held_idle_rate':    (1. - total('nb_slots_served') / total('nb_slots_held')
                              if total('nb_slots_held') else None),
        'mean_booking_rate':   mean(s['booking_rate'] for s in stations),
        'mean_occupancy_rate': mean(s['occupancy_rate'] for s in stations),
        'mean_service_rate':   mean(s.get('service_rate', 0.) for s in stations),
        'excluded_car_share':  _ratio(result['excluded']['nb_cars_excluded'],
                                      row['nb_cars']),
        'nb_ilp_feasible_time_limit': (total('nb_ilp_not_optimal')
                                       - total('nb_ilp_failed')),
        # Network-wide, weighted by capacity: the per-station means above give
        # a 2-charger station the weight of a 6-charger one.
        'nb_chargers':            total('nb_charg_spot'),
        'network_occupancy_rate': _ratio(total('nb_slots_held'), capacity),
        'network_service_rate':   _ratio(total('nb_slots_served'), capacity),
    })
    planned = sum(result['metrics']['station_energy_planned_kWh'].values())
    delivered = sum(result['metrics']['station_energy_delivered_kWh'].values())
    out['energy_delivery_rate'] = _ratio(delivered, planned)

    observed = beh['observed_counts']
    intent = beh['intent_counts']
    nb_obs, nb_int = sum(observed.values()), sum(intent.values())
    for outcome in ('pres', 'abs', 'early', 'late'):
        out[f'rate_{outcome}'] = _ratio(observed.get(outcome, 0), nb_obs)
        out[f'intent_{outcome}'] = _ratio(intent.get(outcome, 0), nb_int)

    if acceptances:
        out['mean_travel_distance_km'] = mean(a['distance_km'] for a in acceptances)
        out['mean_waiting_time_min'] = mean(a['waiting_time_min'] for a in acceptances)

    out.update(demand_service(demands))
    return out


# ----------------------------------------------------------------------
# Display (the only place where numbers are rounded)
# ----------------------------------------------------------------------

def _pct(value: float | None, digits: int = 2) -> str:
    return '—' if value is None else f'{100. * value:.{digits}f}'


def _signed_pp(value: float | None, digits: int = 2) -> str:
    return '—' if value is None else f'{100. * value:+.{digits}f}'


def display_means(means: Sequence[Mapping[str, Any]]) -> str:
    """Mean ± 95 % CI half-width of the headline indicators, in %."""
    labels = {m.column: m.label for m in METRICS}
    idx = {(r['scenario'], r['nb_cars'], r['method'], r['metric']): r for r in means}
    cases = sorted({(r['scenario'], r['nb_cars'], r['method'], r['method_label'])
                    for r in means}, key=lambda c: (c[0], c[1], c[2]))
    head = ['Scenario', 'Fleet', 'Method'] + [labels[c] + ' (%)' for c in HEADLINE]
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    for scenario, nb_cars, method, label in cases:
        cells = [scenario, str(nb_cars), label]
        for col in HEADLINE:
            r = idx.get((scenario, nb_cars, method, col))
            if r is None:
                cells.append('—')
            else:
                cells.append(f"{_pct(r['mean'])} ± {_pct(r['ci95_halfwidth'])}")
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def display_paired(paired: Sequence[Mapping[str, Any]], kind: str) -> str:
    """Paired gaps (percentage points) of the headline indicators."""
    labels = {m.column: m.label for m in METRICS}
    rows = [r for r in paired if r['kind'] == kind and r['metric'] in HEADLINE]
    head = ['Scenario', 'Fleet', 'Comparison', 'Indicator',
            'Mean Δ (pp)', '95% CI (pp)', 'p', 'Improved', 'Verdict']
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    order = {c: i for i, c in enumerate(HEADLINE)}
    rows.sort(key=lambda r: (r['scenario'], r['nb_cars'], r['step'],
                             r['component'], order[r['metric']]))
    for r in rows:
        ci = ('—' if r['ci95_low'] is None else
              f"[{_signed_pp(r['ci95_low'])}, {_signed_pp(r['ci95_high'])}]")
        p = '—' if r['p_value'] is None else f"{r['p_value']:.3g}"
        lines.append('| ' + ' | '.join([
            r['scenario'], str(r['nb_cars']),
            f"{r['component']} ({r['from_method']} → {r['to_method']})",
            labels[r['metric']], _signed_pp(r['mean_delta']), ci, p,
            f"{r['nb_improved']}/{r['nb_pairs']}", r['verdict'],
        ]) + ' |')
    return '\n'.join(lines)


def display_solver(solver: Sequence[Mapping[str, Any]],
                   rows: Sequence[Mapping[str, Any]]) -> str:
    """Non-optimal solves, grouped by world, method by method."""
    per_case = defaultdict(lambda: [0, 0, 0])
    for s in solver:
        key = (s['scenario'], s['nb_cars'], s['world_seed'], s['method'])
        per_case[key][0] += s['nb_ilp_not_optimal']
        per_case[key][1] += s['nb_ilp_feasible_time_limit']
        per_case[key][2] += s['nb_ilp_failed']
    head = ['Scenario', 'Fleet', 'Seed', 'Method', 'Not optimal',
            'Feasible at time limit', 'Failed (no solution)']
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    for key in sorted(per_case):
        lines.append('| ' + ' | '.join(map(str, key + tuple(per_case[key]))) + ' |')
    tot = [sum(v[i] for v in per_case.values()) for i in range(3)]
    lines.append(f'| **Total** | | | | {tot[0]} | {tot[1]} | {tot[2]} |')
    nb_cases = len(rows)
    lines.append('')
    lines.append(f'{len(per_case)} cases out of {nb_cases} contain at least one '
                 'solve not proven optimal.')
    return '\n'.join(lines)


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def recompute_run(source: Path, keep=None
                  ) -> tuple[list[dict], list[str], list[dict], list[dict]]:
    """
    `(rows, fields, solver, sensitivity)` of a finished run: the new
    `summary.csv` rows and their column order, the non-optimal solves, and the
    fully-satisfied rate under each tolerance of `SENSITIVITY_TOLS_KWH`.
    `keep(row)` restricts the cases read, on the old `summary.csv` row.
    """
    source = Path(source)
    rows = [r for r in RunStore.open(source).read_summary()
            if keep is None or keep(r)]

    new_rows, solver, sensitivity = [], [], []
    for row in rows:
        tag = (f"seed{row['seed']}_{row['scenario']}_{row['nb_cars']}cars_"
               f"{row['method']}")
        result = json.loads((source / 'results' / f'{tag}.json').read_text())
        demands = _read_csv(source / 'tables' / f'{tag}_latency.csv')
        acc_path = source / 'tables' / f'{tag}_acceptances.csv'
        acceptances = _read_csv(acc_path) if acc_path.is_file() else []

        new = recompute_row(row, result, demands, acceptances)
        # Sanity: the recomputed ratio agrees with the one the run stored.
        stored = result['metrics']['service']['service_ratio_mean']
        if stored is not None and abs(new['service_ratio_mean'] - stored) > 1e-3:
            raise ValueError(f'{tag}: service_ratio_mean {new["service_ratio_mean"]}'
                             f' vs stored {stored}')
        new_rows.append(new)
        solver.extend(solver_rows(result, row))
        sens = {k: row[k] for k in ('scenario', 'nb_cars', 'method', 'world_seed')}
        for tol in SENSITIVITY_TOLS_KWH:
            sens[f'fully_satisfied_rate_tol_{tol:g}kWh'] = \
                demand_service(demands, tol)['fully_satisfied_rate']
        sensitivity.append(sens)

    fields = list(new_rows[0].keys())
    # Keep the new service columns next to the ones they complete.
    for col in ('nb_demands_fully_satisfied', 'fully_satisfied_rate',
                'fully_satisfied_share_of_served', 'service_ratio_mean_served'):
        fields.remove(col)
    anchor = fields.index('served_rate') + 1
    fields[anchor:anchor] = ['nb_demands_fully_satisfied', 'fully_satisfied_rate',
                             'fully_satisfied_share_of_served']
    fields.insert(fields.index('service_ratio_mean') + 1, 'service_ratio_mean_served')
    fields.insert(fields.index('nb_ilp_failed'), 'nb_ilp_feasible_time_limit')
    for col in ('network_occupancy_rate', 'network_service_rate'):
        fields.remove(col)
    anchor = fields.index('mean_service_rate') + 1
    fields[anchor:anchor] = ['nb_chargers', 'network_occupancy_rate',
                             'network_service_rate']
    return new_rows, fields, solver, sensitivity


def reanalyse(source: Path, target: Path) -> dict:
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError(f'{target} already exists')
    new_rows, fields, solver, sensitivity = recompute_run(source)

    detail = ablation.detail_rows(new_rows, METRICS)
    means = aggregate.metric_rows(new_rows, METRICS)
    paired = aggregate.paired_rows(detail, metrics=METRICS)

    target.mkdir(parents=True)
    _write_csv(target / 'summary.csv', new_rows, fields)
    _write_csv(target / 'ablation.csv', detail, ablation.ROW_FIELDS)
    _write_csv(target / 'ablation_mean.csv', ablation.mean_rows(detail),
               ablation.MEAN_FIELDS)
    _write_csv(target / 'summary_mean.csv', means, aggregate.METRIC_FIELDS)
    _write_csv(target / 'paired.csv', paired, aggregate.PAIRED_FIELDS)
    _write_csv(target / 'solver_status.csv', solver,
               list(solver[0].keys()) if solver else ['scenario'])
    _write_csv(target / 'full_service_sensitivity.csv', sensitivity)
    shutil.copy2(source / 'params.json', target / 'params.json')

    display = target / 'tables_display'
    display.mkdir()
    (display / 'service_means.md').write_text(
        '# Service indicators — mean ± 95 % CI half-width over the seeds (%)\n\n'
        + display_means(means) + '\n', encoding='utf-8')
    for kind, title in (('ladder', 'Ablation ladder'),
                        ('baseline', 'BRAM-EV against the baselines'),
                        ('variant', 'BRAM-EV variants')):
        (display / f'paired_{kind}.md').write_text(
            f'# {title} — paired gaps, percentage points\n\n'
            + display_paired(paired, kind) + '\n', encoding='utf-8')
    (display / 'solver_status.md').write_text(
        '# MILP solves not proven optimal\n\n'
        + display_solver(solver, new_rows) + '\n', encoding='utf-8')

    manifest = {
        'run': target.name,
        'kind': 'reanalysis',
        'source_run': source.name,
        'created_utc': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
        'simulations_rerun': False,
        'nb_cases': len(new_rows),
        'full_service_tol_kwh': FULL_SERVICE_TOL_KWH,
        'renamed_columns': RENAMED,
        'nb_ilp_not_optimal': sum(s['nb_ilp_not_optimal'] for s in solver),
        'nb_ilp_feasible_time_limit': sum(s['nb_ilp_feasible_time_limit']
                                          for s in solver),
        'nb_ilp_failed': sum(s['nb_ilp_failed'] for s in solver),
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    render_figures(source, target)
    return manifest


def render_figures(source: Path, target: Path) -> list[Path]:
    """
    Figures of the re-analysis, in `<target>/figures/`.

    Performance figures read the new `summary.csv` (served / fully satisfied);
    grid and fleet figures read the environment tables of the source run,
    which the re-analysis does not copy.
    """
    from src.pipeline import figures
    from src.pipeline.cli import _shared_tables

    rows = RunStore.open(target).read_summary()
    return figures.render_all(rows, Path(target) / 'figures',
                              **_shared_tables(RunStore.open(source)))


if __name__ == '__main__':
    args = sys.argv[1:]
    only_figures = '--figures-only' in args
    args = [a for a in args if a != '--figures-only']
    if len(args) != 2:
        sys.exit(__doc__.split('Usage:')[1])
    source, target = map(Path, args)
    if only_figures:
        for path in render_figures(source, target):
            print(path)
    else:
        print(json.dumps(reanalyse(source, target), indent=2))
