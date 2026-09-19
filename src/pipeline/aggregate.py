"""
aggregate.py — Statistics over the replicates of a multi-seed campaign.

`summary.csv` holds one row per (seed, scenario, fleet, method): a single
measurement, on a single world. A campaign run with several seeds measures the
same quantity on several worlds, and the question stops being "what did this
run give?" and becomes "what can be claimed beyond this run?". That needs a
spread, not just a mean.

Two tables, written at the root of the run:

`summary_mean.csv` — the distribution of each metric
    One row per (scenario, fleet, method, metric): `n` replicates, mean,
    standard deviation and **95 % confidence interval of the mean**. It answers
    "what does this method score, and how precisely do we know it?".

`paired.csv` — the comparisons, replicate by replicate
    One row per (scenario, fleet, comparison, metric): the difference is taken
    **within each world** and only then averaged, with the CI and the paired
    t-test of those differences. It answers "does A beat B, and is the gap
    bigger than the noise?".

Why the comparisons are paired
------------------------------
Two methods of the same replicate run on the same grid, the same fleet and the
same behaviour draws (see `src/experiments/world.py`): the only difference is
the method. Comparing their two *independent* means would throw that away and
pay for the variance between worlds, which is large here — a change of seed
moves the satisfaction rate by more than most components do. Taking the
difference first cancels the world out, so the test is on N differences rather
than on 2N measurements, and it is far more powerful at equal N.

This is also why `paired.csv` never groups across fleet sizes: the gap at 25
vehicles and the gap at 250 are not draws from the same distribution, and
averaging them would describe no regime in particular. `ablation_mean.csv`
deliberately does pool everything — it is the descriptive overview; this module
is the inferential one.

Reading the interval
--------------------
The half-width uses Student's *t* with `n - 1` degrees of freedom, not 1.96:
with 3 seeds the multiplier is 4.30, with 2 seeds it is 12.71. A campaign with
a handful of replicates produces intervals wide enough to cover almost any
claim, and that is the honest answer — the fix is more seeds, not a narrower
formula. With a single seed there is no interval at all: the columns are empty
rather than zero, because one measurement has no spread, it has an unknown one.

`significant_95` is read off the interval — 0 outside it — rather than off the
p-value. The two agree, and the interval also decides the degenerate case where
every replicate gives exactly the same difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean as _mean, stdev
from typing import Any, Iterable, Mapping, Sequence

from scipy import stats

import src.experiments.methods as methods
from src.pipeline import ablation
from src.pipeline.ablation import METRICS, Metric

Row = Mapping[str, Any]
Rows = Sequence[Row]

DEFAULT_CONFIDENCE = 0.95

METRIC_FIELDS: tuple[str, ...] = (
    'scenario', 'nb_cars', 'method', 'method_label', 'method_family',
    'metric', 'metric_label', 'goal', 'unit',
    'nb_seeds', 'seeds',
    'mean', 'sd', 'sem', 'ci95_low', 'ci95_high', 'ci95_halfwidth',
    'min', 'max',
)

PAIRED_FIELDS: tuple[str, ...] = (
    'kind', 'scenario', 'nb_cars', 'metric', 'metric_label', 'goal', 'unit',
    'step', 'component', 'from_method', 'to_method',
    'nb_pairs', 'seeds',
    'mean_value_from', 'mean_value_to',
    'mean_delta', 'sd_delta', 'sem_delta', 'ci95_low', 'ci95_high',
    'mean_delta_pct', 't_stat', 'p_value', 'significant_95',
    'nb_improved', 'share_improved', 'verdict',
)

#: `verdict` values: the direction of a gap that the interval actually
#: separates from zero. `ns` means the replicates do not settle the question.
BETTER, WORSE, NOT_SIGNIFICANT = 'better', 'worse', 'ns'


# ----------------------------------------------------------------------
# Estimation
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Estimate:
    """Mean of a sample and the precision with which it is known."""

    n: int
    mean: float | None = None
    sd: float | None = None
    sem: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None

    @property
    def halfwidth(self) -> float | None:
        if self.ci_low is None or self.ci_high is None:
            return None
        return (self.ci_high - self.ci_low) / 2.

    @property
    def excludes_zero(self) -> bool:
        """True when the whole interval sits on one side of 0."""
        if self.ci_low is None or self.ci_high is None:
            return False
        return self.ci_low > 0. or self.ci_high < 0.


def _floats(values: Iterable[Any]) -> list[float]:
    """Keep what is numeric. A `None` is a missing measurement, not a zero."""
    out = []
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def estimate(values: Iterable[Any],
             confidence: float = DEFAULT_CONFIDENCE) -> Estimate:
    """
    Mean and confidence interval of a sample of replicates.

    `n = 1` returns the mean alone: a single measurement has no spread, and
    filling the interval with zeros would claim perfect precision from one
    draw. `n = 0` returns nothing at all.

    A sample where every replicate gives the same value collapses the interval
    onto the mean. That is correct, not a failure: `sd = 0` does mean the
    measurement did not move — over the seeds actually run.
    """
    sample = _floats(values)
    n = len(sample)
    if n == 0:
        return Estimate(n=0)
    point = _mean(sample)
    if n == 1:
        return Estimate(n=1, mean=point)

    sd = stdev(sample)                      # sample sd, ddof = 1
    sem = sd / (n ** 0.5)
    # Student's t, not 1.96: at these sample sizes the difference is the whole
    # interval (t = 4.30 for n = 3, against 1.96 asymptotically).
    half = float(stats.t.ppf(0.5 + confidence / 2., n - 1)) * sem
    return Estimate(n=n, mean=point, sd=sd, sem=sem,
                    ci_low=point - half, ci_high=point + half)


def paired_test(deltas: Iterable[Any],
                confidence: float = DEFAULT_CONFIDENCE
                ) -> tuple[Estimate, float | None, float | None]:
    """
    One-sample test on the differences — which is the paired test.

    Returns `(estimate, t, p)`. `t` and `p` are `None` when they are not
    defined: fewer than two pairs, or differences with no spread at all. In
    that last case the interval still answers the question, which is why
    significance is read off the interval and not off `p`.
    """
    est = estimate(deltas, confidence)
    if est.n < 2 or not est.sem:
        return est, None, None
    t_stat = est.mean / est.sem
    p_value = float(2. * stats.t.sf(abs(t_stat), est.n - 1))
    return est, float(t_stat), p_value


def _verdict(est: Estimate, metric: Metric) -> str:
    """Direction of the gap, but only when the interval separates it from 0."""
    if not est.excludes_zero:
        return NOT_SIGNIFICANT
    return BETTER if metric.improves(est.mean) else WORSE


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _seed_tag(seeds: Iterable[Any]) -> str:
    """
    The replicates behind a row, so a table stays auditable on its own.

    Sorted numerically when they all are numbers — `1|2|10`, not `1|10|2` —
    and lexically otherwise, so the column never depends on row order.
    """
    values = list(seeds)
    try:
        ordered = sorted(values, key=lambda s: (0, float(s)))
    except (TypeError, ValueError):
        ordered = sorted(values, key=str)
    return '|'.join(str(s) for s in ordered)


# ----------------------------------------------------------------------
# summary_mean.csv — the distribution of each metric
# ----------------------------------------------------------------------

def metric_rows(rows: Rows, metrics: Sequence[Metric] = METRICS,
                confidence: float = DEFAULT_CONFIDENCE) -> list[dict]:
    """
    Mean and 95 % CI of every metric, over the replicates.

    Grouped by (scenario, fleet, method): each group holds one value per seed.
    A seed appearing twice in the same group means `summary.csv` holds
    duplicates, and is reported rather than averaged in — a silently doubled
    replicate would tighten the interval on nothing.
    """
    grouped: dict[tuple, dict[Any, Row]] = {}
    for row in rows:
        method = row.get('method')
        if method is None:
            continue
        key = (row.get('scenario'), row.get('nb_cars'), method)
        # `world_seed` is the identity of the replicate; `seed` is the campaign
        # seed the row was produced under. They coincide today, and the
        # fallback keeps a hand-built table without `world_seed` readable.
        seed = row.get('world_seed')
        if seed is None:
            seed = row.get('seed')
        bucket = grouped.setdefault(key, {})
        if seed in bucket:
            raise ValueError(
                f"Replicate {seed!r} present twice for {key}: summary.csv "
                "contains duplicates."
            )
        bucket[seed] = row

    out: list[dict] = []
    for (scenario, nb_cars, method), by_seed in grouped.items():
        seeds = list(by_seed)
        spec = methods.METHODS.get(method)
        for metric in metrics:
            values = _floats(r.get(metric.column) for r in by_seed.values())
            if not values:
                continue
            est = estimate(values, confidence)
            out.append({
                'scenario':       scenario,
                'nb_cars':        nb_cars,
                'method':         method,
                'method_label':   spec.label if spec else method,
                'method_family':  spec.family if spec else None,
                'metric':         metric.column,
                'metric_label':   metric.label,
                'goal':           metric.goal,
                'unit':           metric.unit,
                'nb_seeds':       est.n,
                'seeds':          _seed_tag(seeds),
                'mean':           _round(est.mean),
                'sd':             _round(est.sd),
                'sem':            _round(est.sem),
                'ci95_low':       _round(est.ci_low),
                'ci95_high':      _round(est.ci_high),
                'ci95_halfwidth': _round(est.halfwidth),
                'min':            _round(min(values)),
                'max':            _round(max(values)),
            })

    order = {m.column: i for i, m in enumerate(metrics)}
    out.sort(key=lambda r: (str(r['scenario']), r['nb_cars'] or 0,
                            str(r['method']), order.get(r['metric'], 99)))
    return out


# ----------------------------------------------------------------------
# paired.csv — the comparisons, replicate by replicate
# ----------------------------------------------------------------------

def paired_rows(detail: Rows,
                confidence: float = DEFAULT_CONFIDENCE) -> list[dict]:
    """
    Paired statistics of every comparison the ablation already defines.

    Input is `ablation.detail_rows`: each of its rows is *already* one
    difference computed within one world, so the pairing is inherited rather
    than redone — one definition of "what is compared to what", shared with
    `ablation.csv`.

    Grouped by (kind, scenario, fleet, comparison, metric); each group holds
    one difference per replicate.
    """
    grouped: dict[tuple, list[Row]] = {}
    for row in detail:
        key = (row['kind'], row.get('scenario'), row.get('nb_cars'),
               row['step'], row['component'],
               row['from_method'], row['to_method'], row['metric'])
        grouped.setdefault(key, []).append(row)

    out: list[dict] = []
    for key, group in grouped.items():
        kind, scenario, nb_cars, step, component, src, dst, column = key
        metric = ablation.METRICS_BY_COLUMN.get(column)
        if metric is None:
            continue

        est, t_stat, p_value = paired_test((r['delta'] for r in group),
                                           confidence)
        pcts = _floats(r.get('delta_pct') for r in group)
        nb_improved = sum(1 for r in group if r['improvement'])

        out.append({
            'kind':            kind,
            'scenario':        scenario,
            'nb_cars':         nb_cars,
            'metric':          column,
            'metric_label':    group[0]['metric_label'],
            'goal':            group[0]['goal'],
            'unit':            group[0]['unit'],
            'step':            step,
            'component':       component,
            'from_method':     src,
            'to_method':       dst,
            'nb_pairs':        est.n,
            'seeds':           _seed_tag(r.get('world_seed') for r in group),
            'mean_value_from': _round(_mean(_floats(
                r['value_from'] for r in group))),
            'mean_value_to':   _round(_mean(_floats(
                r['value_to'] for r in group))),
            'mean_delta':      _round(est.mean),
            'sd_delta':        _round(est.sd),
            'sem_delta':       _round(est.sem),
            'ci95_low':        _round(est.ci_low),
            'ci95_high':       _round(est.ci_high),
            'mean_delta_pct':  _round(_mean(pcts), 4) if pcts else None,
            't_stat':          _round(t_stat, 4),
            'p_value':         _round(p_value, 6),
            'significant_95':  est.excludes_zero,
            'nb_improved':     nb_improved,
            'share_improved':  round(nb_improved / len(group), 4),
            'verdict':         _verdict(est, metric),
        })

    order = {m.column: i for i, m in enumerate(METRICS)}
    out.sort(key=lambda r: (r['kind'] != 'ladder', str(r['scenario']),
                            r['nb_cars'] or 0, r['step'], str(r['component']),
                            order.get(r['metric'], 99)))
    return out


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------

def write_tables(store, rows: Rows | None = None,
                 metrics: Sequence[Metric] = METRICS,
                 confidence: float = DEFAULT_CONFIDENCE) -> list:
    """
    Write `summary_mean.csv` and `paired.csv` at the root of the run.

    Both are produced whatever the number of seeds: a single-seed campaign gets
    its means, with empty interval columns. Nothing is written when there is no
    row to write — a one-method campaign has no comparison to pair.
    """
    rows = list(rows if rows is not None else store.read_summary())
    if not rows:
        return []
    written = [
        store.write_root_table('summary_mean',
                               metric_rows(rows, metrics, confidence),
                               METRIC_FIELDS),
        store.write_root_table('paired',
                               paired_rows(ablation.detail_rows(rows, metrics),
                                           confidence),
                               PAIRED_FIELDS),
    ]
    return [path for path in written if path is not None]


# ----------------------------------------------------------------------
# Text rendering
# ----------------------------------------------------------------------

def render_paired_table(paired: Rows, metric: str = 'exact_satisfaction',
                        kinds: Sequence[str] = ('ladder', 'baseline', 'variant'),
                        ) -> str:
    """
    One comparison per line: the gap, its interval, and whether it holds.

    Deliberately one metric at a time — an interval is only readable next to
    the quantity it measures, in its own unit.
    """
    selected = [r for r in paired if r['metric'] == metric and r['kind'] in kinds]
    if not selected:
        return f'No paired comparison for {metric!r}.'

    label = selected[0]['metric_label']
    unit = selected[0]['unit']
    head = f'{label}{f" ({unit})" if unit else ""} — paired over the replicates'
    lines = [head, '=' * len(head), '']

    by_kind: dict[str, list[Row]] = {}
    for row in selected:
        by_kind.setdefault(row['kind'], []).append(row)

    titles = {'ladder': 'Ablation ladder (component added)',
              'baseline': 'Reference baselines (gap to BRAM-EV)',
              'variant': 'BRAM-EV variants (mechanism neutralised)'}

    for kind in kinds:
        group = by_kind.get(kind)
        if not group:
            continue
        lines.append(titles.get(kind, kind))
        lines.append(f"{'comparison':<26}{'fleet':>7}{'n':>4}"
                     f"{'mean Δ':>11}{'95% CI':>24}{'p':>9}  verdict")
        for row in group:
            ci = ('—' if row['ci95_low'] is None
                  else f"[{row['ci95_low']:+.4f}, {row['ci95_high']:+.4f}]")
            p = '—' if row['p_value'] is None else f"{row['p_value']:.4f}"
            lines.append(
                f"{str(row['component'])[:25]:<26}"
                f"{row['nb_cars']:>7}{row['nb_pairs']:>4}"
                f"{row['mean_delta']:>+11.4f}{ci:>24}{p:>9}  {row['verdict']}"
            )
        lines.append('')

    lines.append('Δ is measured within each replicate, then averaged: the world '
                 'cancels out.')
    lines.append('A verdict of `ns` means the replicates do not separate the '
                 'gap from zero.')
    return '\n'.join(lines)
