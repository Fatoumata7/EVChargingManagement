"""
holm.py — Paired tests of the ablation ladder, Holm-corrected per contrast.

One family per contrast of the ladder (a component added to the previous
rung): every (scenario, fleet) configuration of the campaign crossed with the
three service indicators. With 3 scenarios x 3 fleets x 3 indicators, each
family holds 27 paired t-tests, and the Holm step-down procedure controls the
family-wise error rate at `ALPHA` within it.

    greedy           -> multistation      Multi-station search
    multistation     -> multistation_rep  Reputation
    multistation_rep -> bramev            Cross-station adaptation

Each test pairs the two methods on the same world (same seed, same grid, same
fleet, same behaviour draws): it is the one-sample t-test of the per-seed
differences, `aggregate.paired_test`. The 95 % confidence intervals reported
next to it are the unadjusted per-comparison intervals.

Usage:
    python -m src.pipeline.holm <run dir with the re-analysed summary.csv>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import src.experiments.methods as methods
from src.pipeline import aggregate, reanalysis
from src.pipeline.ablation import index_by_world
from src.pipeline.store import RunStore, _write_csv

ALPHA = 0.05

#: Service indicators of each family, as defined by the re-analysis.
INDICATORS: tuple[str, ...] = ('served_rate', 'fully_satisfied_rate',
                               'service_ratio_mean')

FIELDS: tuple[str, ...] = (
    'step', 'component', 'from_method', 'to_method',
    'scenario', 'nb_cars', 'metric', 'metric_label',
    'nb_pairs', 'seeds', 'mean_from', 'mean_to',
    'mean_delta', 'sd_delta', 'ci95_low', 'ci95_high',
    't_stat', 'p_value', 'holm_rank', 'family_size', 'p_holm',
    'reject_holm_05',
)


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """
    Holm step-down adjusted p-values, in the order of `p_values`.

    Sorted ascending, the i-th smallest (1-based) is multiplied by
    `m - i + 1`; the running maximum keeps the adjusted values monotone, and
    they are capped at 1. Rejecting `p_holm <= alpha` is Holm's procedure.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.] * m
    running = 0.
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p_values[i])
        adjusted[i] = min(1., running)
    return adjusted


def family_rows(rows: Sequence[Mapping[str, Any]],
                indicators: Sequence[str] = INDICATORS) -> list[dict]:
    """Paired tests of every ladder contrast, Holm-adjusted per contrast."""
    labels = {m.column: m.label for m in reanalysis.METRICS}
    index = index_by_world(rows)
    configs = sorted({(w[0], w[1]) for w in index},
                     key=lambda c: (str(c[0]), c[1]))

    out: list[dict] = []
    for step, (src, dst, component) in enumerate(methods.LADDER_STEPS, start=1):
        family: list[dict] = []
        for scenario, nb_cars in configs:
            worlds = [(w[2], by) for w, by in index.items()
                      if (w[0], w[1]) == (scenario, nb_cars)
                      and src in by and dst in by]
            for column in indicators:
                pairs = [(seed, float(by[src][column]), float(by[dst][column]))
                         for seed, by in worlds]
                est, t_stat, p_value = aggregate.paired_test(
                    b - a for _, a, b in pairs)
                if p_value is None:
                    raise ValueError(
                        f'{component} {scenario} {nb_cars} {column}: '
                        'paired test undefined (fewer than 2 pairs or no spread)')
                family.append({
                    'step': step, 'component': component,
                    'from_method': src, 'to_method': dst,
                    'scenario': scenario, 'nb_cars': nb_cars,
                    'metric': column, 'metric_label': labels.get(column, column),
                    'nb_pairs': est.n,
                    'seeds': aggregate._seed_tag(s for s, _, _ in pairs),
                    'mean_from': sum(a for _, a, _ in pairs) / len(pairs),
                    'mean_to': sum(b for _, _, b in pairs) / len(pairs),
                    'mean_delta': est.mean, 'sd_delta': est.sd,
                    'ci95_low': est.ci_low, 'ci95_high': est.ci_high,
                    't_stat': t_stat, 'p_value': p_value,
                })
        adjusted = holm_adjust([r['p_value'] for r in family])
        ranks = sorted(range(len(family)), key=lambda i: family[i]['p_value'])
        for rank, i in enumerate(ranks, start=1):
            family[i]['holm_rank'] = rank
        for row, p_holm in zip(family, adjusted):
            row.update(family_size=len(family), p_holm=p_holm,
                       reject_holm_05=p_holm <= ALPHA)
        out.extend(family)
    return out


def display(rows: Sequence[Mapping[str, Any]]) -> str:
    """Markdown, one table per contrast; rounded for display only."""
    lines: list[str] = []
    for step in sorted({r['step'] for r in rows}):
        family = [r for r in rows if r['step'] == step]
        head = family[0]
        nb_rejected = sum(r['reject_holm_05'] for r in family)
        lines += [f"## {head['component']} ({head['from_method']} → "
                  f"{head['to_method']}) — family of {len(family)}, "
                  f"{nb_rejected} rejected at α = {ALPHA} after Holm", '',
                  '| Scenario | Fleet | Indicator | Mean Δ (pp) | 95% CI (pp) '
                  '| p | p Holm | Significant |',
                  '|---|---:|---|---:|---|---:|---:|---|']
        for r in family:
            lines.append(
                f"| {r['scenario']} | {r['nb_cars']} | {r['metric_label']} "
                f"| {100 * r['mean_delta']:+.2f} "
                f"| [{100 * r['ci95_low']:+.2f}, {100 * r['ci95_high']:+.2f}] "
                f"| {r['p_value']:.3g} | {r['p_holm']:.3g} "
                f"| {'yes' if r['reject_holm_05'] else 'no'} |")
        lines.append('')
    return '\n'.join(lines)


def write(run_dir: Path) -> list[Path]:
    run_dir = Path(run_dir)
    rows = family_rows(RunStore.open(run_dir).read_summary())
    csv_path = run_dir / 'holm_ladder.csv'
    md_path = run_dir / 'tables_display' / 'holm_ladder.md'
    _write_csv(csv_path, rows, FIELDS)
    md_path.parent.mkdir(exist_ok=True)
    md_path.write_text(
        '# Ablation ladder — paired t-tests, Holm correction per contrast\n\n'
        'Family = 9 configurations (3 scenarios × 3 fleets) × 3 service '
        'indicators = 27 tests per contrast. Paired on the seed (10 worlds). '
        'CIs are unadjusted.\n\n' + display(rows), encoding='utf-8')
    return [csv_path, md_path]


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__.split('Usage:')[1])
    for path in write(Path(sys.argv[1])):
        print(path)
