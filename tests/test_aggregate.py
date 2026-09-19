"""
test_aggregate.py — Tests of the statistics over the replicates.

    python -m tests.test_aggregate

What these tests protect, in order of importance:

1. **The arithmetic is the reference arithmetic.** The interval and the paired
   test are checked against `scipy.stats` rather than against numbers written
   by hand: a statistic that is subtly wrong looks exactly like a statistic
   that is right, and no simulation result would ever betray it.
2. **Student, not 1.96.** At three replicates the normal multiplier understates
   the interval by more than half. Hard-coding 1.96 is the single most likely
   way for this module to become quietly over-confident.
3. **The comparisons stay paired.** The difference is taken inside a world and
   only then averaged. Replacing that with two independent means would still
   produce a plausible table — with the variance between worlds folded into
   every interval.
4. **A missing spread is empty, never zero.** One replicate has an unknown
   spread, not a null one, and the difference decides whether a gap reads as
   established or as untested.
"""

from __future__ import annotations

import sys
import tempfile
import traceback

import numpy as np
from scipy import stats

from src.pipeline import ablation, aggregate
from src.pipeline.aggregate import BETTER, NOT_SIGNIFICANT, WORSE
from src.pipeline.params import ExperimentParams
from src.pipeline.runner import run_grid


def tiny_params(**overrides) -> ExperimentParams:
    """Smallest campaign carrying several replicates and one comparable pair."""
    base = dict(
        seeds=(1, 2, 3),
        scenarios=('pessimistic',),
        fleet_sizes=(12,),
        methods=('greedy', 'multistation'),
        total_time=60,
        nb_stations=6,
        nb_societies=2,
        log_every=10 ** 6,
        figures=False,
    )
    base.update(overrides)
    return ExperimentParams(**base)


def synthetic_rows(effect: float, world_spread: float, seeds=(1, 2, 3, 4, 5)):
    """
    Two methods, one constant effect, a large world-to-world offset.

    This is the shape the pairing exists for: the gap between the methods is
    the same everywhere, but each world sits at a completely different level.
    """
    rows = []
    for i, seed in enumerate(seeds):
        base = 0.5 + world_spread * i
        for method, value in (('greedy', base), ('multistation', base + effect)):
            rows.append({
                'scenario': 'pessimistic', 'nb_cars': 12, 'method': method,
                'seed': seed, 'world_seed': seed,
                'exact_satisfaction': value,
            })
    return rows


# ----------------------------------------------------------------------
# Estimation
# ----------------------------------------------------------------------

def test_confidence_interval_matches_scipy():
    """
    The interval must be the one `scipy.stats.t.interval` computes.

    Checked against the reference rather than against a literal: a wrong
    standard error or the wrong number of degrees of freedom produces an
    interval that still looks entirely reasonable.
    """
    for sample in ([0.90, 0.86, 0.85], [1., 2., 3., 4.], [12.5, 9.75]):
        est = aggregate.estimate(sample)
        low, high = stats.t.interval(0.95, len(sample) - 1,
                                     loc=np.mean(sample), scale=stats.sem(sample))
        assert np.isclose(est.mean, float(np.mean(sample)))
        assert np.isclose(est.sd, float(np.std(sample, ddof=1))), \
            'the sd must be the sample sd (ddof=1), not the population one'
        assert np.isclose(est.ci_low, low) and np.isclose(est.ci_high, high), \
            f'{sample}: [{est.ci_low}, {est.ci_high}] vs [{low}, {high}]'


def test_interval_uses_student_not_the_normal_quantile():
    """
    At these sample sizes the multiplier *is* the interval.

    t = 4.30 for 3 replicates against 1.96 asymptotically: using the normal
    quantile would publish an interval 2.2 times too narrow, and turn untested
    gaps into significant ones.
    """
    sample = [0.90, 0.86, 0.85]
    est = aggregate.estimate(sample)
    sem = float(stats.sem(sample))

    observed = est.halfwidth / sem
    assert np.isclose(observed, float(stats.t.ppf(0.975, 2))), \
        f'multiplier {observed:.3f}, expected t(0.975, 2) = 4.303'
    assert observed > 4., 'the normal quantile 1.96 would be far too narrow here'

    # The gap grows as the sample shrinks: 2 replicates is nearly unusable.
    two = aggregate.estimate([0.90, 0.86])
    assert two.halfwidth / float(stats.sem([0.90, 0.86])) > 12.


def test_a_single_replicate_has_no_interval():
    """
    One measurement has an *unknown* spread, not a null one.

    Reporting 0. would claim perfect precision from a single draw — the exact
    over-statement this module exists to prevent.
    """
    one = aggregate.estimate([0.7])
    assert one.n == 1 and one.mean == 0.7
    assert one.sd is None and one.sem is None
    assert one.ci_low is None and one.ci_high is None
    assert one.halfwidth is None
    assert not one.excludes_zero, 'an absent interval cannot exclude anything'

    empty = aggregate.estimate([])
    assert empty.n == 0 and empty.mean is None

    # A missing measurement is skipped, not read as a zero.
    assert aggregate.estimate([1., None, 3.]).n == 2
    assert np.isclose(aggregate.estimate([1., None, 3.]).mean, 2.)


# ----------------------------------------------------------------------
# Paired test
# ----------------------------------------------------------------------

def test_paired_test_matches_scipy_ttest_rel():
    """The paired test on the pairs must equal the one-sample test on the gaps."""
    before = [0.70, 0.62, 0.81, 0.55]
    after = [0.74, 0.68, 0.83, 0.61]
    deltas = [b - a for a, b in zip(before, after)]

    est, t_stat, p_value = aggregate.paired_test(deltas)
    reference = stats.ttest_rel(after, before)

    assert est.n == 4
    assert np.isclose(t_stat, reference.statistic), \
        f't = {t_stat} vs {reference.statistic}'
    assert np.isclose(p_value, reference.pvalue), \
        f'p = {p_value} vs {reference.pvalue}'


def test_zero_variance_gaps_are_handled_not_divided_by_zero():
    """
    Every replicate giving the same gap is a real case, and `scipy` answers
    `nan` to it. The interval still settles the question, which is why
    significance is read off the interval rather than off `p`.
    """
    # Identical and null: nothing happened.
    est, t_stat, p_value = aggregate.paired_test([0., 0., 0.])
    assert est.sd == 0. and est.ci_low == 0. and est.ci_high == 0.
    assert t_stat is None and p_value is None
    assert not est.excludes_zero

    # Identical and non-null: the gap is real, the t statistic is degenerate.
    est, t_stat, p_value = aggregate.paired_test([0.5, 0.5, 0.5])
    assert est.mean == 0.5 and est.ci_low == 0.5 and est.ci_high == 0.5
    assert t_stat is None and p_value is None
    assert est.excludes_zero, (
        'a gap identical on every replicate is separated from zero: reading '
        'significance off the p-value alone would lose it'
    )

    # Fewer than two pairs: no test at all.
    assert aggregate.paired_test([0.4])[1] is None


def test_pairing_survives_a_world_effect_that_swamps_it():
    """
    The reason the comparisons are paired.

    A constant gap of 0.01 under a world-to-world spread of 0.2: comparing the
    two independent means cannot see it, taking the difference inside each
    world sees it exactly. A refactor replacing the pairing by two means would
    pass every other test in this file and fail this one.
    """
    rows = synthetic_rows(effect=0.01, world_spread=0.2)
    paired = aggregate.paired_rows(ablation.detail_rows(rows))
    row = [r for r in paired if r['metric'] == 'exact_satisfaction'][0]

    assert row['nb_pairs'] == 5
    assert np.isclose(row['mean_delta'], 0.01)
    assert row['significant_95'], 'the paired gap must be detected'
    assert row['verdict'] == BETTER

    # The unpaired comparison on the same numbers sees nothing at all.
    by_method = {'greedy': [], 'multistation': []}
    for r in rows:
        by_method[r['method']].append(r['exact_satisfaction'])
    unpaired = stats.ttest_ind(by_method['multistation'], by_method['greedy'])
    assert unpaired.pvalue > 0.5, (
        'inconclusive test: the world effect must swamp the unpaired comparison'
    )


def test_verdict_follows_the_direction_of_the_metric():
    """
    A gap that is significant is not therefore good: `nb_no_show` going up is a
    loss. The verdict must read the goal of the metric, not the sign.
    """
    rows = []
    for seed in (1, 2, 3, 4):
        for method, sat, noshow in (('greedy', 0.70, 10.), ('multistation', 0.75, 14.)):
            rows.append({'scenario': 'pessimistic', 'nb_cars': 12,
                         'method': method, 'seed': seed, 'world_seed': seed,
                         'exact_satisfaction': sat + 0.001 * seed,
                         'nb_no_show': noshow + seed})
    paired = {r['metric']: r for r in
              aggregate.paired_rows(ablation.detail_rows(rows))}

    up = paired['exact_satisfaction']
    assert up['mean_delta'] > 0 and up['verdict'] == BETTER

    down = paired['nb_no_show']
    assert down['mean_delta'] > 0 and down['significant_95']
    assert down['verdict'] == WORSE, (
        'more no-shows is a loss: the verdict must not follow the raw sign'
    )


def test_significance_agrees_with_the_p_value_when_both_exist():
    """
    Two readings of the same test must not disagree — a table where the
    interval and the p-value tell different stories is unusable.
    """
    rows = synthetic_rows(effect=0.01, world_spread=0.2)
    rows += [dict(r, nb_cars=24) for r in synthetic_rows(effect=0.0005,
                                                         world_spread=0.2)]
    for row in aggregate.paired_rows(ablation.detail_rows(rows)):
        if row['p_value'] is None:
            continue
        assert row['significant_95'] == (row['p_value'] < 0.05), (
            f"{row['component']}@{row['nb_cars']}: CI says "
            f"{row['significant_95']}, p = {row['p_value']}"
        )


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------

def test_paired_rows_never_pool_across_fleet_sizes():
    """
    The gap at 12 vehicles and the gap at 24 are not draws from the same
    distribution; averaging them would describe no regime. Each fleet size
    keeps its own row, with its own replicates.
    """
    rows = synthetic_rows(effect=0.01, world_spread=0.05)
    rows += [dict(r, nb_cars=24) for r in synthetic_rows(effect=0.10,
                                                         world_spread=0.05)]
    paired = [r for r in aggregate.paired_rows(ablation.detail_rows(rows))
              if r['metric'] == 'exact_satisfaction']

    assert len(paired) == 2, f'one row per fleet size, got {len(paired)}'
    by_fleet = {r['nb_cars']: r for r in paired}
    assert np.isclose(by_fleet[12]['mean_delta'], 0.01)
    assert np.isclose(by_fleet[24]['mean_delta'], 0.10)
    assert all(r['nb_pairs'] == 5 for r in paired)


def test_metric_rows_describe_the_distribution_over_the_seeds():
    """`summary_mean.csv`: one row per (world, method, metric), n = the seeds."""
    rows = synthetic_rows(effect=0.01, world_spread=0.2)
    out = [r for r in aggregate.metric_rows(rows)
           if r['metric'] == 'exact_satisfaction']

    assert {r['method'] for r in out} == {'greedy', 'multistation'}
    for row in out:
        assert row['nb_seeds'] == 5
        assert row['seeds'] == '1|2|3|4|5', 'the replicates must stay auditable'
        assert row['min'] <= row['mean'] <= row['max']
        assert row['ci95_low'] < row['mean'] < row['ci95_high']
        assert np.isclose(row['ci95_halfwidth'],
                          (row['ci95_high'] - row['ci95_low']) / 2)
        assert row['method_label'] and row['goal'] == ablation.GOAL_UP


def test_a_duplicated_replicate_is_refused():
    """
    The same seed twice would tighten the interval on nothing. Reported rather
    than silently averaged in, like the duplicated methods of the ablation.
    """
    rows = synthetic_rows(effect=0.01, world_spread=0.1, seeds=(1, 2))
    rows.append(dict(rows[0]))
    try:
        aggregate.metric_rows(rows)
    except ValueError as exc:
        assert 'twice' in str(exc)
    else:
        raise AssertionError('a duplicated replicate should have been refused')


def test_tables_are_written_by_a_real_campaign():
    """End to end: a multi-seed run must produce both files, ready to read."""
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        for name, fields in (('summary_mean', aggregate.METRIC_FIELDS),
                             ('paired', aggregate.PAIRED_FIELDS)):
            written = store.read_root_table(name)
            assert written, f'{name}.csv missing or empty'
            assert set(written[0]) == set(fields), f'{name}.csv: unexpected columns'

        paired = store.read_root_table('paired')
        assert all(r['nb_pairs'] == len(params.seeds) for r in paired), (
            'each comparison must be paired on every replicate')
        assert all(r['seeds'] == '1|2|3' for r in paired)

        means = store.read_root_table('summary_mean')
        assert all(r['nb_seeds'] == len(params.seeds) for r in means)
        assert all(r['ci95_low'] is not None for r in means), (
            'three replicates: every interval must be computable')


def test_a_single_seed_still_produces_means_without_intervals():
    """
    A mono-seed campaign must not crash, and must not invent a spread: the
    means are there, the interval columns are empty.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = run_grid(tiny_params(output_root=tmp, seeds=(7,)))

        means = store.read_root_table('summary_mean')
        assert means, 'summary_mean.csv must exist even with one replicate'
        assert all(r['nb_seeds'] == 1 for r in means)
        assert all(r['mean'] is not None for r in means)
        assert all(r['sd'] is None and r['ci95_low'] is None for r in means), (
            'one replicate has an unknown spread, not a null one'
        )

        for row in store.read_root_table('paired'):
            assert row['nb_pairs'] == 1
            assert row['t_stat'] is None and row['p_value'] is None
            assert row['significant_95'] is False
            assert row['verdict'] == NOT_SIGNIFICANT, (
                'a single replicate settles nothing'
            )


def test_render_paired_table_reads_as_a_table():
    rows = synthetic_rows(effect=0.01, world_spread=0.2)
    paired = aggregate.paired_rows(ablation.detail_rows(rows))
    text = aggregate.render_paired_table(paired, 'exact_satisfaction')

    assert 'Exact satisfaction' in text and '95% CI' in text
    assert 'Multi-station search' in text
    assert aggregate.render_paired_table(paired, 'wall_time_s').startswith('No ')


def main() -> int:
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith('test_') and callable(obj)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f'  ok    {name}')
        except Exception as exc:
            failures.append((name, traceback.format_exc()))
            print(f'  FAIL  {name}: {exc}')

    print(f'\n{len(tests) - len(failures)}/{len(tests)} tests passed')
    for name, tb in failures:
        print(f'\n===== {name} =====\n{tb}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
