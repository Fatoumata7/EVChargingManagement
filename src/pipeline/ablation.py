"""
ablation.py — Decomposition of the gains per component.

The Nearest / BRAM-EV comparison says *that* there is a gap; it does not say
where it comes from. This module answers the question asked by the ablation
study: **which part of the gain is attributable to which component?**

Two readings, produced from `summary.csv` alone:

Ablation ladder (`kind='ladder'`)
    The four rungs (`methods.LADDER`) add one component at a time. For a given
    world — same seed, same grid, same fleet, same behaviour draws — the gap
    between two consecutive rungs *is* the contribution of the component added,
    with no other confounding variable.

BRAM-EV variants (`kind='variant'`)
    Each variant replaces an internal mechanism (multi-criteria selection, alpha
    heterogeneity, reputation scope, score weighting) and is compared against
    `bramev`. The gap measures what that mechanism brings *inside* the complete
    method.

The raw sign of a gap is not enough: a drop in the number of no-shows is
progress, a drop in the satisfaction rate is not. Each metric therefore declares
its direction (`GOAL_UP` / `GOAL_DOWN`), and `improvement` turns the gap into a
judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

import src.experiments.methods as methods

Row = Mapping[str, Any]
Rows = Sequence[Row]

GOAL_UP = 'up'      # the bigger the better
GOAL_DOWN = 'down'  # the smaller the better


@dataclass(frozen=True)
class Metric:
    """A metric tracked by the ablation, with its direction and its unit."""

    column: str
    label: str
    goal: str
    unit: str = ''

    def improves(self, delta: float) -> bool:
        return delta > 0 if self.goal == GOAL_UP else delta < 0


#: Metrics decomposed by default: user satisfaction, cost to the users,
#: reliability of the reservations, use of the infrastructure, compute cost.
METRICS: tuple[Metric, ...] = (
    Metric('exact_satisfaction',          'Exact satisfaction',      GOAL_UP,   '%'),
    Metric('needs_satisfaction',          'Needs satisfied',         GOAL_UP,   '%'),
    Metric('confirm_rate',                'Confirmation rate',       GOAL_UP,   '%'),
    Metric('mean_waiting_time_min',       'Mean waiting time',       GOAL_DOWN, 'min'),
    Metric('mean_travel_distance_km',     'Mean distance',           GOAL_DOWN, 'km'),
    Metric('rate_pres',                   'Show-up rate',            GOAL_UP,   '%'),
    Metric('rate_abs',                    'No-show rate',            GOAL_DOWN, '%'),
    Metric('nb_no_show',                  'No-shows',                GOAL_DOWN, ''),
    Metric('nb_reservations',             'Confirmed reservations',  GOAL_UP,   ''),
    Metric('mean_occupancy_rate',         'Occupancy rate',          GOAL_UP,   '%'),
    Metric('mean_service_rate',           'Service rate',            GOAL_UP,   '%'),
    Metric('slot_waste_rate',             'Wasted reserved slots',   GOAL_DOWN, '%'),
    Metric('nb_station_level_rejections', 'Rejected demands',        GOAL_DOWN, ''),
    Metric('total_ms_mean',               'End-to-end latency',      GOAL_DOWN, 'ms'),
    Metric('wall_time_s',                 'Wall time',               GOAL_DOWN, 's'),
)

METRICS_BY_COLUMN = {m.column: m for m in METRICS}

#: Mechanism neutralised by each variant, as displayed in the tables.
VARIANT_MECHANISM: Mapping[str, str] = {
    'bramev_nearest_offer': 'Multi-criteria utility',
    'bramev_fixed_alpha':   'Alpha heterogeneity',
    'bramev_global_rep':    'Per-company reputation',
    'bramev_event_score':   'Duration-weighted score',
}

#: Label of each baseline in the tables, as published.
BASELINE_LABEL: Mapping[str, str] = {
    name: methods.label(name) for name in methods.BASELINES
}

ROW_FIELDS: tuple[str, ...] = (
    'kind', 'scenario', 'nb_cars', 'metric', 'metric_label', 'goal', 'unit',
    'step', 'component', 'from_method', 'to_method',
    'value_from', 'value_to', 'delta', 'delta_pct', 'improvement',
)

MEAN_FIELDS: tuple[str, ...] = (
    'kind', 'metric', 'metric_label', 'goal', 'unit', 'step', 'component',
    'from_method', 'to_method', 'nb_worlds',
    'mean_value_from', 'mean_value_to', 'mean_delta', 'mean_delta_pct',
    'nb_improved', 'share_improved',
)


# ----------------------------------------------------------------------
# Row selection
# ----------------------------------------------------------------------

def _world_key(row: Row) -> tuple:
    """Identity of the world of a case: two rows with the same key are comparable."""
    return (row.get('scenario'), row.get('nb_cars'), row.get('world_seed'))


def index_by_world(rows: Rows) -> dict[tuple, dict[str, Row]]:
    """
    `{world: {method: row}}`.

    A method duplicated within the same world (partial re-run) is reported
    rather than silently overwritten: the ablation would become wrong with no
    way to see it.
    """
    index: dict[tuple, dict[str, Row]] = {}
    for row in rows:
        method = row.get('method')
        if method is None:
            continue
        bucket = index.setdefault(_world_key(row), {})
        if method in bucket:
            raise ValueError(
                f"Method {method!r} present twice for the world "
                f"{_world_key(row)}: summary.csv contains duplicates."
            )
        bucket[method] = row
    return index


def _pairs(index: Mapping[tuple, Mapping[str, Row]],
           couples: Sequence[tuple[str, str, str]]):
    """Enumerate (world, component, row_before, row_after) for the pairs present."""
    for world, by_method in sorted(index.items(), key=lambda kv: str(kv[0])):
        for src, dst, component in couples:
            if src in by_method and dst in by_method:
                yield world, component, by_method[src], by_method[dst]


# ----------------------------------------------------------------------
# Building the tables
# ----------------------------------------------------------------------

def _delta_row(kind: str, world: tuple, component: str, step: int,
               before: Row, after: Row, metric: Metric) -> dict | None:
    value_from = before.get(metric.column)
    value_to = after.get(metric.column)
    if value_from is None or value_to is None:
        return None
    try:
        delta = float(value_to) - float(value_from)
    except (TypeError, ValueError):
        return None

    # Relative gap: undefined when the reference is zero (not 'infinite').
    base = abs(float(value_from))
    delta_pct = round(100. * delta / base, 4) if base > 1e-12 else None

    scenario, nb_cars, _ = world
    return {
        'kind':         kind,
        'scenario':     scenario,
        'nb_cars':      nb_cars,
        'metric':       metric.column,
        'metric_label': metric.label,
        'goal':         metric.goal,
        'unit':         metric.unit,
        'step':         step,
        'component':    component,
        'from_method':  before.get('method'),
        'to_method':    after.get('method'),
        'value_from':   round(float(value_from), 6),
        'value_to':     round(float(value_to), 6),
        'delta':        round(delta, 6),
        'delta_pct':    delta_pct,
        'improvement':  metric.improves(delta),
    }


def ladder_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """Contribution of each component, world by world and metric by metric."""
    index = index_by_world(rows)
    steps = {(src, dst): i + 1 for i, (src, dst, _) in enumerate(methods.LADDER_STEPS)}
    out: list[dict] = []
    for world, component, before, after in _pairs(index, methods.LADDER_STEPS):
        step = steps[(before['method'], after['method'])]
        for metric in metrics:
            row = _delta_row('ladder', world, component, step, before, after, metric)
            if row is not None:
                out.append(row)
    return out


def variant_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """
    Gap of each variant to `bramev`.

    The reading direction is "BRAM-EV -> variant": a false `improvement` means
    that the mechanism neutralised by the variant was useful.
    """
    index = index_by_world(rows)
    couples = [('bramev', name, VARIANT_MECHANISM.get(name, name))
               for name in methods.VARIANTS]
    out: list[dict] = []
    for world, component, before, after in _pairs(index, couples):
        for metric in metrics:
            row = _delta_row('variant', world, component, 0, before, after, metric)
            if row is not None:
                out.append(row)
    return out


def baseline_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """
    Gap of `bramev` to each reference baseline.

    The reading direction is the opposite of the variants': "baseline ->
    BRAM-EV", so that a true `improvement` means that BRAM-EV does better than
    the baseline. That is the question asked of a baseline, whereas a variant
    answers "is this mechanism good for anything?".
    """
    index = index_by_world(rows)
    couples = [(name, 'bramev', BASELINE_LABEL.get(name, name))
               for name in methods.BASELINES]
    out: list[dict] = []
    for world, component, before, after in _pairs(index, couples):
        for metric in metrics:
            row = _delta_row('baseline', world, component, 0, before, after, metric)
            if row is not None:
                out.append(row)
    return out


def detail_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """Complete detailed table: ablation ladder, baselines, then variants."""
    return (ladder_rows(rows, metrics)
            + baseline_rows(rows, metrics)
            + variant_rows(rows, metrics))


def mean_rows(detail: Rows) -> list[dict]:
    """
    Mean of the gaps over every world, per (component, metric).

    This is the table to quote in the report: a component that only improves
    half of the worlds (`share_improved` close to 0.5) has no robust
    contribution, even if its mean gap is positive.
    """
    grouped: dict[tuple, list[Row]] = {}
    for row in detail:
        key = (row['kind'], row['step'], row['component'],
               row['from_method'], row['to_method'], row['metric'])
        grouped.setdefault(key, []).append(row)

    out: list[dict] = []
    for key, group in grouped.items():
        kind, step, component, from_method, to_method, metric = key
        pcts = [r['delta_pct'] for r in group if r['delta_pct'] is not None]
        nb_improved = sum(1 for r in group if r['improvement'])
        out.append({
            'kind':            kind,
            'metric':          metric,
            'metric_label':    group[0]['metric_label'],
            'goal':            group[0]['goal'],
            'unit':            group[0]['unit'],
            'step':            step,
            'component':       component,
            'from_method':     from_method,
            'to_method':       to_method,
            'nb_worlds':       len(group),
            'mean_value_from': round(mean(r['value_from'] for r in group), 6),
            'mean_value_to':   round(mean(r['value_to'] for r in group), 6),
            'mean_delta':      round(mean(r['delta'] for r in group), 6),
            'mean_delta_pct':  round(mean(pcts), 4) if pcts else None,
            'nb_improved':     nb_improved,
            'share_improved':  round(nb_improved / len(group), 4),
        })

    order = {m.column: i for i, m in enumerate(METRICS)}
    out.sort(key=lambda r: (r['kind'] != 'ladder', r['step'], r['component'],
                            order.get(r['metric'], 99)))
    return out


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------

def write_tables(store, rows: Rows | None = None,
                 metrics: Sequence[Metric] = METRICS) -> list:
    """
    Write `ablation.csv` and `ablation_mean.csv` at the root of the run.

    With no comparable pair (a single method in the campaign), nothing is
    written and the returned list is empty: a single-method campaign stays
    valid, it simply has nothing to decompose.
    """
    rows = list(rows if rows is not None else store.read_summary())
    detail = detail_rows(rows, metrics)
    if not detail:
        return []
    written = [
        store.write_root_table('ablation', detail, ROW_FIELDS),
        store.write_root_table('ablation_mean', mean_rows(detail), MEAN_FIELDS),
    ]
    return [path for path in written if path is not None]


# ----------------------------------------------------------------------
# Text rendering
# ----------------------------------------------------------------------

DEFAULT_REPORT_METRICS: tuple[str, ...] = (
    'exact_satisfaction', 'rate_abs', 'mean_service_rate',
    'slot_waste_rate', 'nb_reservations',
)


def render_mean_table(means: Rows,
                      metric_columns: Sequence[str] = DEFAULT_REPORT_METRICS) -> str:
    """
    Readable table: one row per component, one column per metric.

    Each cell carries the mean gap and, in parentheses, the share of the worlds
    where the component improves the metric — the mean contribution and its
    robustness are read at a glance.

    The gap is relative when the reference is non-zero. It is not always
    (a zero mean waiting time, for instance): the cell then falls back on the
    absolute gap, prefixed with `Δ`, rather than showing a dash that would make
    a measurement taken look like a measurement missing.
    """
    selected = [c for c in metric_columns if c in METRICS_BY_COLUMN]
    by_component: dict[tuple, dict[str, Row]] = {}
    for row in means:
        if row['metric'] not in selected:
            continue
        key = (row['kind'], row['step'], row['component'])
        by_component.setdefault(key, {})[row['metric']] = row
    if not by_component:
        return '(no computable contribution)'

    headers = [METRICS_BY_COLUMN[c].label for c in selected]
    name_width = max(len('Component'),
                     *(len(k[2]) for k in by_component))
    widths = [max(len(h), 16) for h in headers]

    def line(cells: Sequence[str], first: str) -> str:
        parts = [first.ljust(name_width)]
        parts += [c.rjust(w) for c, w in zip(cells, widths)]
        return '  '.join(parts)

    out = [line(headers, 'Component'),
           line(['-' * w for w in widths], '-' * name_width)]

    for kind in ('ladder', 'baseline', 'variant'):
        keys = sorted(k for k in by_component if k[0] == kind)
        if not keys:
            continue
        title = {
            'ladder':   'Ablation ladder (contribution of the added component)',
            'baseline': 'Reference baselines (gap from the baseline to BRAM-EV)',
            'variant':  'BRAM-EV variants (effect of the neutralised mechanism)',
        }[kind]
        out.append('')
        out.append(title)
        for key in keys:
            cells = []
            for column in selected:
                row = by_component[key].get(column)
                if row is None:
                    cells.append('-')
                    continue
                if row['mean_delta_pct'] is not None:
                    value = f"{row['mean_delta_pct']:+.1f}%"
                else:
                    value = f"Δ{row['mean_delta']:+.3g}"
                cells.append(f"{value} ({row['share_improved']:.0%})")
            out.append(line(cells, key[2]))
    out.append('')
    out.append("Reading: mean relative gap over every world of the run "
               "(share of the worlds where the component improves the metric).")
    return '\n'.join(out)
