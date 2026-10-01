"""
congestion.py — Report of a congestion pilot against its reference campaign.

The pilot reruns a subset of a campaign (same seeds, hence same grid positions,
companies, initial alpha and fleets) with fewer chargers per station. Two
questions, in this order:

1. Does the pilot actually congest the network? Each method is compared with
   itself on the reference capacity, world by world (`capacity_effect.csv`).
2. What does each component bring once the network is congested? The ladder
   rungs and the baseline are compared within the pilot (`components.csv`).

Every table is computed at full precision from the per-case results (through
`reanalysis.recompute_run`, so the indicators are those of the re-analysis:
served / fully satisfied / share of need met). Numbers are rounded in
`README.md` only.

Usage:
    python -m src.pipeline.congestion <pilot run dir> <reference run dir> [<output dir>]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from src.pipeline import ablation, aggregate, reanalysis
from src.pipeline.ablation import GOAL_DOWN, GOAL_UP, Metric
from src.pipeline.store import RunStore, _write_csv

#: Indicators of the pilot table, in display order:
#: (column, label, display factor, format).
INDICATORS: tuple[tuple[str, str, float, str], ...] = (
    ('E_tot',                      'E_tot — energy delivered (MWh)',      1e-3, '.2f'),
    ('service_ratio_mean',         'S_del — mean energy satisfaction (%)', 100., '.2f'),
    ('fully_satisfied_rate',       'S_full — fully satisfied requests (%)', 100., '.2f'),
    ('served_rate',                'Requests served, even partially (%)', 100., '.2f'),
    ('U',                          'U — executed utilization (%)',        100., '.2f'),
    ('O_mean',                     'Mean O_m — held occupancy (%)',       100., '.2f'),
    ('O_max',                      'Max O_m — held occupancy (%)',        100., '.2f'),
    ('held_idle_rate',             'I_held — unused share of held capacity (%)', 100., '.2f'),
    ('no_offer_rate',              'Demands with no offer (%)',           100., '.2f'),
    ('request_rejection_rate',     'Demands never confirmed (%)',         100., '.2f'),
    ('station_rejection_rate',     'Station-level refusals (%)',          100., '.2f'),
    ('abandon_rate',               'Searches abandoned (%)',              100., '.2f'),
    ('mean_waiting_time_min',      'Scheduled delay (min)',               1.,   '.2f'),
    ('nb_demands',                 'Requests (N)',                        1.,   '.1f'),
    ('nb_cars_excluded',           'Permanent withdrawals',               1.,   '.1f'),
    ('nb_ilp_not_optimal',         'MILP solves not proven optimal',      1.,   '.2f'),
    ('nb_ilp_feasible_time_limit', '  of which feasible at time limit',   1.,   '.2f'),
    ('nb_ilp_failed',              '  of which failed (no solution)',     1.,   '.2f'),
)

#: Indicators with no better direction: their verdict is not displayed.
NO_DIRECTION = ('nb_demands',)

#: Solver counts are summed over the seeds in the display, not averaged.
SOLVER_COLUMNS = ('nb_ilp_not_optimal', 'nb_ilp_feasible_time_limit',
                  'nb_ilp_failed')

#: Indicators of the capacity check and of the component table.
KEY_INDICATORS: tuple[str, ...] = (
    'E_tot', 'service_ratio_mean', 'fully_satisfied_rate', 'served_rate',
    'U', 'O_mean', 'O_max', 'held_idle_rate',
    'no_offer_rate', 'request_rejection_rate', 'station_rejection_rate',
    'mean_waiting_time_min', 'nb_demands', 'nb_cars_excluded',
)


def _metrics() -> tuple[Metric, ...]:
    by_column = {m.column: m for m in reanalysis.METRICS}
    extra = {
        'nb_demands':       Metric('nb_demands', 'Requests (N)', GOAL_UP),
        'nb_cars_excluded': Metric('nb_cars_excluded', 'Permanent withdrawals',
                                   GOAL_DOWN),
        'nb_ilp_not_optimal':         Metric('nb_ilp_not_optimal',
                                             'MILP solves not proven optimal',
                                             GOAL_DOWN),
        'nb_ilp_feasible_time_limit': Metric('nb_ilp_feasible_time_limit',
                                             'MILP feasible at time limit',
                                             GOAL_DOWN),
        'nb_ilp_failed':              Metric('nb_ilp_failed', 'MILP failed',
                                             GOAL_DOWN),
    }
    return tuple(by_column.get(c) or extra[c] for c, *_ in INDICATORS)


METRICS: tuple[Metric, ...] = _metrics()
BY_COLUMN = {m.column: m for m in METRICS}


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------

def capacity_rows(pilot: Sequence[Mapping], reference: Sequence[Mapping]
                  ) -> list[dict]:
    """
    Pilot minus reference, per (scenario, method, indicator), paired on the
    seed: the same method on the same world, only the capacity differs.
    """
    ref = {(r['scenario'], r['method'], r['world_seed']): r for r in reference}
    grouped: dict[tuple, list[tuple]] = defaultdict(list)
    for row in pilot:
        other = ref.get((row['scenario'], row['method'], row['world_seed']))
        if other is None:
            continue
        for column in KEY_INDICATORS:
            if row.get(column) is None or other.get(column) is None:
                continue
            grouped[(row['scenario'], row['method'], column)].append(
                (row['world_seed'], float(other[column]), float(row[column])))

    out = []
    for (scenario, method, column), pairs in grouped.items():
        est, t_stat, p_value = aggregate.paired_test(p - r for _, r, p in pairs)
        out.append({
            'scenario': scenario, 'method': method, 'metric': column,
            'metric_label': BY_COLUMN[column].label,
            'nb_pairs': est.n,
            'seeds': aggregate._seed_tag(s for s, _, _ in pairs),
            'mean_reference': mean(r for _, r, _ in pairs),
            'mean_pilot': mean(p for _, _, p in pairs),
            'mean_delta': est.mean, 'sd_delta': est.sd,
            'ci95_low': est.ci_low, 'ci95_high': est.ci_high,
            't_stat': t_stat, 'p_value': p_value,
            'significant_95': est.excludes_zero,
        })
    order = {c: i for i, c in enumerate(KEY_INDICATORS)}
    out.sort(key=lambda r: (r['scenario'], r['method'], order[r['metric']]))
    return out


def component_rows(pilot: Sequence[Mapping]) -> list[dict]:
    """Ladder rungs and baseline, paired within the pilot."""
    metrics = [BY_COLUMN[c] for c in KEY_INDICATORS]
    detail = ablation.ladder_rows(pilot, metrics) + ablation.baseline_rows(pilot, metrics)
    return aggregate.paired_rows(detail, metrics=metrics)


# ----------------------------------------------------------------------
# Display (the only place where numbers are rounded)
# ----------------------------------------------------------------------

def _method_order(rows: Sequence[Mapping]) -> list[str]:
    order = ('nearest_available', 'greedy', 'multistation', 'multistation_rep',
             'bramev')
    present = {r['method'] for r in rows}
    return [m for m in order if m in present] + sorted(present - set(order))


def _fmt(value, factor: float, spec: str) -> str:
    return '—' if value is None else format(value * factor, spec)


def display_pilot(means: Sequence[Mapping], pilot: Sequence[Mapping],
                  scenario: str) -> str:
    """One column per method; mean over the seeds (± 95 % CI half-width)."""
    methods = _method_order(pilot)
    labels = {r['method']: r['method_label'] for r in means}
    idx = {(r['method'], r['metric']): r for r in means if r['scenario'] == scenario}
    lines = ['| Indicator | ' + ' | '.join(labels.get(m, m) for m in methods) + ' |',
             '|---|' + '---:|' * len(methods)]
    for column, label, factor, spec in INDICATORS:
        cells = []
        for method in methods:
            if column in SOLVER_COLUMNS:
                total = sum(r[column] for r in pilot
                            if r['scenario'] == scenario and r['method'] == method)
                cells.append(f'{total} (sum)')
                continue
            r = idx.get((method, column))
            if r is None:
                cells.append('—')
                continue
            hw = r['ci95_halfwidth']
            cells.append(_fmt(r['mean'], factor, spec)
                         + ('' if hw is None else f' ± {_fmt(hw, factor, spec)}'))
        lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def display_capacity(rows: Sequence[Mapping], scenario: str) -> str:
    """Reference → pilot, and the paired gap, one line per indicator."""
    factors = {c: (f, s) for c, _, f, s in INDICATORS}
    labels = {c: l for c, l, _, _ in INDICATORS}
    methods = _method_order(rows)
    head = ['Indicator'] + [m for m in methods]
    lines = ['| ' + ' | '.join(head) + ' |', '|---|' + '---|' * len(methods)]
    idx = {(r['method'], r['metric']): r for r in rows if r['scenario'] == scenario}
    for column in KEY_INDICATORS:
        factor, spec = factors[column]
        cells = []
        for method in methods:
            r = idx.get((method, column))
            if r is None:
                cells.append('—')
                continue
            ci = ('' if r['ci95_low'] is None else
                  f" [{_fmt(r['ci95_low'], factor, '+' + spec)}, "
                  f"{_fmt(r['ci95_high'], factor, '+' + spec)}]")
            cells.append(f"{_fmt(r['mean_reference'], factor, spec)} → "
                         f"{_fmt(r['mean_pilot'], factor, spec)}; "
                         f"Δ {_fmt(r['mean_delta'], factor, '+' + spec)}{ci}")
        lines.append(f'| {labels[column]} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def display_components(rows: Sequence[Mapping], scenario: str) -> str:
    factors = {c: (f, s) for c, _, f, s in INDICATORS}
    labels = {c: l for c, l, _, _ in INDICATORS}
    comps = []
    for r in rows:
        key = (r['kind'], r['step'], r['component'], r['from_method'], r['to_method'])
        if key not in comps:
            comps.append(key)
    comps.sort(key=lambda k: (k[0] != 'ladder', k[1]))
    head = ['Indicator'] + [(f'{c[2]} ({c[3]} → {c[4]})' if c[0] == 'ladder'
                             else f'BRAM-EV vs {c[2]} ({c[3]} → {c[4]})')
                            for c in comps]
    lines = ['| ' + ' | '.join(head) + ' |', '|---|' + '---|' * len(comps)]
    idx = {(r['kind'], r['component'], r['metric']): r
           for r in rows if r['scenario'] == scenario}
    for column in KEY_INDICATORS:
        factor, spec = factors[column]
        cells = []
        for kind, _, component, _, _ in comps:
            r = idx.get((kind, component, column))
            if r is None:
                cells.append('—')
                continue
            ci = ('' if r['ci95_low'] is None else
                  f" [{_fmt(r['ci95_low'], factor, '+' + spec)}, "
                  f"{_fmt(r['ci95_high'], factor, '+' + spec)}]")
            judged = ('' if column in NO_DIRECTION else
                      f" {r['nb_improved']}/{r['nb_pairs']} {r['verdict']}")
            cells.append(f"{_fmt(r['mean_delta'], factor, '+' + spec)}{ci}{judged}")
        lines.append(f'| {labels[column]} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def report(pilot_dir: Path, reference_dir: Path, out: Path | None = None) -> Path:
    """Write the report in `out` (default: `<pilot_dir>/congestion`)."""
    pilot_dir, reference_dir = Path(pilot_dir), Path(reference_dir)
    pilot, fields, solver, _ = reanalysis.recompute_run(pilot_dir)

    seeds = {r['world_seed'] for r in pilot}
    cases = {(r['scenario'], r['nb_cars'], r['method']) for r in pilot}
    reference, _, _, _ = reanalysis.recompute_run(
        reference_dir,
        keep=lambda r: (r['world_seed'] in seeds
                        and (r['scenario'], r['nb_cars'], r['method']) in cases))

    means = aggregate.metric_rows(pilot, METRICS)
    ref_means = aggregate.metric_rows(reference, METRICS)
    capacity = capacity_rows(pilot, reference)
    components = component_rows(pilot)

    out = Path(out) if out is not None else pilot_dir / 'congestion'
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / 'summary.csv', pilot, fields)
    _write_csv(out / 'reference_summary.csv', reference, fields)
    _write_csv(out / 'pilot_by_method.csv', means, aggregate.METRIC_FIELDS)
    _write_csv(out / 'reference_by_method.csv', ref_means, aggregate.METRIC_FIELDS)
    _write_csv(out / 'capacity_effect.csv', capacity)
    _write_csv(out / 'components.csv', components, aggregate.PAIRED_FIELDS)
    _write_csv(out / 'solver_status.csv', solver,
               list(solver[0].keys()) if solver else ['scenario'])

    chargers = sorted({r['nb_chargers'] for r in pilot})
    ref_chargers = sorted({r['nb_chargers'] for r in reference})
    scenarios = sorted({r['scenario'] for r in pilot})
    text = [
        f'# Congestion pilot — {pilot_dir.name}',
        '',
        f'Reference: `{reference_dir.name}`, same seeds '
        f'({", ".join(map(str, sorted(seeds)))}), same scenarios, fleet and methods.',
        f'Chargers in the network: pilot {chargers}, reference {ref_chargers} '
        '(one value per seed).',
        '',
        'Definitions of the paper: U = executed charger-slots / capacity and '
        'O_m = held charger-slots / capacity, per station, U averaged with equal '
        'station weights; I_held pools held and executed slots within each run; '
        'E_tot sums the energy delivered over the request records. '
        'Refusal rates: *no offer* and '
        '*never confirmed* are per demand; *station-level refusals* are per '
        '(station, demand) request. MILP counts are summed over the seeds.',
        '',
        'All CSVs are at full precision; the tables below are rounded for '
        'display. With 3 seeds the Student multiplier is 4.30: the intervals '
        'are wide by construction.',
    ]
    for scenario in scenarios:
        text += ['', f'## {scenario} — pilot, per method (mean ± 95 % CI half-width)',
                 '', display_pilot(means, pilot, scenario),
                 '', f'## {scenario} — capacity effect (reference → pilot, paired Δ [95 % CI])',
                 '', display_capacity(capacity, scenario),
                 '', f'## {scenario} — components within the pilot (paired Δ [95 % CI], worlds improved, verdict)',
                 '', display_components(components, scenario)]
    (out / 'README.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
    # Figures on the re-analysed rows (served / fully satisfied), not on the
    # raw `summary.csv` of the run, which still carries the former names.
    from src.pipeline import figures
    from src.pipeline.cli import _shared_tables
    figures.render_all(pilot, out / 'figures',
                       **_shared_tables(RunStore.open(pilot_dir)))
    (out / 'manifest.json').write_text(json.dumps({
        'pilot_run': pilot_dir.name, 'reference_run': reference_dir.name,
        'seeds': sorted(seeds), 'nb_pilot_cases': len(pilot),
        'nb_reference_cases': len(reference),
        'full_service_tol_kwh': reanalysis.FULL_SERVICE_TOL_KWH,
    }, indent=2) + '\n')
    return out


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__.split('Usage:')[1])
    print(report(*map(Path, sys.argv[1:])))
