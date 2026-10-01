"""
Tests of the Holm-corrected paired tests of the ablation ladder.

    python -m tests.test_holm
"""

import random
import sys
import traceback

from scipy import stats

from src.pipeline import holm


def test_holm_adjust_matches_a_hand_computed_example():
    # Sorted: 0.005*4=0.02, 0.01*3=0.03, 0.03*2=0.06, 0.04*1=0.04 -> max 0.06.
    got = holm.holm_adjust([0.01, 0.04, 0.03, 0.005])
    assert [round(p, 12) for p in got] == [0.03, 0.06, 0.06, 0.02], got


def test_holm_adjust_is_capped_and_monotone():
    # Sorted: 0.2*3=0.6, 0.5*2=1.0, 0.9*1=0.9 -> kept at 1.0 (monotone, capped).
    got = holm.holm_adjust([0.9, 0.5, 0.2])
    assert [round(p, 12) for p in got] == [1., 1., 0.6], got


def _rows():
    rng = random.Random(7)
    rows = []
    for scenario in ('optimistic', 'balance', 'pessimistic'):
        for nb_cars in (50, 150, 250):
            for seed in range(1, 11):
                base = rng.uniform(0.3, 0.7)
                for i, method in enumerate(('greedy', 'multistation',
                                            'multistation_rep', 'bramev')):
                    value = base + 0.01 * i + rng.gauss(0, 0.005)
                    rows.append({'scenario': scenario, 'nb_cars': nb_cars,
                                 'world_seed': seed, 'seed': seed,
                                 'method': method,
                                 'service_ratio_mean': value,
                                 'fully_satisfied_rate': value - 0.1,
                                 'E_tot': 30000. * value})
    return rows


def test_one_family_of_27_per_ladder_contrast():
    out = holm.family_rows(_rows())
    assert len(out) == 81
    for step in (1, 2, 3):
        family = [r for r in out if r['step'] == step]
        assert len(family) == 27
        assert all(r['family_size'] == 27 and r['nb_pairs'] == 10 for r in family)
        assert sorted(r['holm_rank'] for r in family) == list(range(1, 28))


def test_families_use_the_three_endpoints_of_the_paper():
    out = holm.family_rows(_rows())
    assert {r['endpoint'] for r in out} == {'S_del', 'S_full', 'E_tot'}
    assert {r['metric'] for r in out} == {'service_ratio_mean',
                                          'fully_satisfied_rate', 'E_tot'}


def test_p_values_are_those_of_the_paired_t_test():
    rows = _rows()
    out = holm.family_rows(rows)
    r = out[0]
    get = lambda m: [x[r['metric']] for x in sorted(
        (x for x in rows if x['method'] == m and x['scenario'] == r['scenario']
         and x['nb_cars'] == r['nb_cars']), key=lambda x: x['world_seed'])]
    ref = stats.ttest_rel(get(r['to_method']), get(r['from_method']))
    assert abs(ref.pvalue - r['p_value']) < 1e-12
    assert abs(ref.statistic - r['t_stat']) < 1e-9
    assert r['p_holm'] >= r['p_value']


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
