"""
test_service.py — Service rendered per demand, planning coverage, exclusions,
and a campaign that survives interruptions.

    python -m tests.test_service

* every demand ends in exactly one outcome, and the four groups (satisfied,
  abandoned, cancelled, in progress) partition the demands;
* the former "satisfaction" indicators are a planning coverage: a no-show is
  covered by the plan and still not served;
* a retry replaces the requested window of its demand instead of adding one;
* the vehicles excluded by an exhausted retry budget are counted;
* a parallel campaign gives the sequential results, and a campaign interrupted
  after some cases resumes without running them again.
"""

import json
import sys
import tempfile
import traceback
from pathlib import Path

from src.env.offer import Offer
from src.experiments.config import SimulationConfig
from src.metrics.metrics import (CANCELLED_OUTCOMES, DEMAND_OUTCOMES,
                                 MetricsCollector)
from src.pipeline import tables
from src.pipeline.cli import EXIT_ERROR, EXIT_OK, main as cli_main
from src.pipeline.runner import run_grid
from src.pipeline.store import RunStore
from tests.test_pipeline import tiny_params
from tests.test_priority1 import run_sim, small_config


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

class _Car:
    def __init__(self, idx, charging_power=6):
        self.idx = idx
        self.charging_power = charging_power


class _Station:
    def __init__(self, m):
        self.m = m


def _collector(total_time=48):
    cfg = SimulationConfig()
    cfg.set_TOTAL_TIME(total_time)
    return MetricsCollector([_Car(0), _Car(1)], [_Station(0)], cfg)


def _run(scenario='pessimistic', nb_car=30, slots=12 * 12, method='bramev'):
    return run_sim(small_config(scenario=scenario, nb_car=nb_car,
                                total_time=slots), method)


#: Columns measuring the machine, not the model: they differ run to run.
def _model_columns(row):
    return {k: v for k, v in row.items()
            if '_ms' not in k and 'wall_time' not in k}


# ----------------------------------------------------------------------
# Demand outcomes
# ----------------------------------------------------------------------

def test_every_demand_ends_in_exactly_one_outcome():
    sim = _run()
    srv = sim.metrics.service_report()
    assert srv['nb_demands'] == sim.nb_demands > 0
    assert sum(srv['outcome_counts'].values()) == srv['nb_demands']
    assert (srv['nb_demands_satisfied'] + srv['nb_demands_abandoned']
            + srv['nb_demands_cancelled'] + srv['nb_demands_in_progress']
            == srv['nb_demands'])
    assert srv['nb_demands_cancelled'] == sum(
        srv['outcome_counts'][o] for o in CANCELLED_OUTCOMES)
    assert set(srv['outcome_counts']) == set(DEMAND_OUTCOMES)
    ok, errors = sim.check_invariants()
    assert ok, errors


def test_outcomes_match_the_reservation_outcomes():
    """A demand outcome is the reservation outcome, seen from the user."""
    sim = _run()
    counts = sim.metrics.service_report()['outcome_counts']
    stations = sim.stations
    assert counts['satisfied'] + counts['missed'] == sum(s.nb_pres for s in stations)
    assert counts['no_show'] == sum(s.nb_no_show for s in stations)
    assert counts['cancelled_early'] == sum(s.nb_early_canc for s in stations)
    assert counts['cancelled_late'] == sum(s.nb_late_canc for s in stations)
    assert counts['breakdown'] == sum(s.nb_breakdown_canc for s in stations)
    assert counts['no_show'] > 0 and counts['satisfied'] > 0, "test is void"


def test_satisfied_means_energy_was_delivered():
    sim = _run()
    for rec in sim.metrics.demand_timings.values():
        if rec.outcome == 'satisfied':
            assert rec.slots_charged > 0 and rec.energy_delivered_kwh > 0
        elif rec.outcome in CANCELLED_OUTCOMES + ('abandoned',):
            assert rec.energy_delivered_kwh == 0, rec
    srv = sim.metrics.service_report()
    assert 0 < srv['service_ratio_mean'] <= srv['service_ratio_mean_satisfied'] <= 1


def test_a_demand_cannot_be_closed_twice():
    met = _collector()
    met.record_demand_emitted('d0', car_id=0, slot=0, energy_requested_kwh=6.)
    met.record_demand_outcome('d0', 'no_show')
    for outcome in ('satisfied', 'in_progress', 'unknown'):
        try:
            met.record_demand_outcome('d0', outcome)
        except ValueError:
            pass
        else:
            raise AssertionError(f'closed twice ({outcome})')


# ----------------------------------------------------------------------
# Planning coverage (formerly "satisfaction")
# ----------------------------------------------------------------------

def test_a_no_show_is_covered_by_the_plan_but_not_served():
    met = _collector()
    met.record_demand_emitted('d0', car_id=0, slot=0, energy_requested_kwh=6.)
    met.record_requested_window('d0', 0, 2, 12)
    offer = Offer(station_id=0, charger_id=0, t_arr=2, t_dep=12, d_prop=10,
                  distance=100.)
    met.record_reservation_confirmed(_Car(0), offer)
    met.record_demand_outcome('d0', 'no_show')

    cov = met.planning_coverage()
    srv = met.service_report()
    assert cov['plan_coverage_exact'] == 1. and cov['plan_coverage_volume'] == 1.
    assert srv['satisfied_rate'] == 0. and srv['cancelled_rate'] == 1.
    assert srv['service_ratio_mean'] == 0.


def test_a_retry_replaces_the_window_of_its_demand():
    """Four retries used to add four shifted windows: 14 slots asked for 10."""
    met = _collector()
    met.record_demand_emitted('d0', car_id=0, slot=0)
    for t in range(5):
        met.record_requested_window('d0', 0, 2 + t, 12 + t)
    offer = Offer(station_id=0, charger_id=0, t_arr=6, t_dep=16, d_prop=10,
                  distance=100.)
    met.record_reservation_confirmed(_Car(0), offer)
    cov = met.planning_coverage()
    assert cov['plan_coverage_exact'] == 1., cov


def test_summary_renames_the_satisfaction_columns():
    result = json.loads(json.dumps(_run().results(), default=str))
    row = tables.summary_row(result)
    for gone in ('exact_satisfaction', 'needs_satisfaction'):
        assert gone not in row and gone not in tables.SUMMARY_FIELDS
    for col in ('plan_coverage_exact', 'plan_coverage_volume', 'satisfied_rate',
                'cancelled_rate', 'in_progress_rate', 'abandon_rate',
                'service_ratio_mean', 'nb_cars_excluded'):
        assert col in row and col in tables.SUMMARY_FIELDS, col
    # the plan covers far more than what is served when half the users cancel
    assert row['plan_coverage_exact'] > row['satisfied_rate']


def test_occupancy_counts_each_charger_slot_once():
    """A slot released and booked again counts twice in the bookings, once held."""
    sim = _run(nb_car=40, slots=12 * 16)
    rebooked = 0
    for st in sim.stations:
        rep = st.outcomes_report()
        assert st.nb_slots_served <= st.nb_slots_held <= st.slot_capacity()
        assert 0 <= rep['service_rate'] <= rep['occupancy_rate'] <= 1
        assert (st.cumulative_occupancy_by_charger() <= 1).all()
        rebooked += st.nb_slots_reserved > st.nb_slots_held
    assert rebooked, "test is void: no station booked more than it held"


# ----------------------------------------------------------------------
# Exclusion after an exhausted retry budget (model assumption)
# ----------------------------------------------------------------------

def test_excluded_vehicles_are_counted():
    cfg = small_config(scenario='balance', nb_car=30, total_time=12 * 12)
    cfg.set_MAX_SEARCH_RETRIES(0)
    cfg.set_SEARCH_RADIUS(0., 50.)       # almost no station within reach
    sim = run_sim(cfg, 'bramev')
    excl = sim.excluded_report()
    gave_up = sum(1 for c in sim.cars if c.gave_up_charging)
    assert excl['nb_cars_excluded'] > 0, "test is void: nobody excluded"
    assert excl['nb_cars_excluded'] == excl['nb_cars_excluded_at_end'] == gave_up
    assert excl['excluded_car_share'] == round(gave_up / len(sim.cars), 4)
    assert 0 < excl['excluded_time_share'] < excl['excluded_car_share']
    abandoned = sim.metrics.service_report()['nb_demands_abandoned']
    assert abandoned >= excl['nb_cars_excluded']
    assert sim.results()['excluded'] == excl


# ----------------------------------------------------------------------
# Parallel campaign, saved as it goes, resumable
# ----------------------------------------------------------------------

def test_parallel_campaign_matches_the_sequential_one():
    with tempfile.TemporaryDirectory() as tmp:
        seq = run_grid(tiny_params(output_root=str(Path(tmp) / 'seq')))
        par = run_grid(tiny_params(output_root=str(Path(tmp) / 'par'), workers=2))
        rows_seq = [_model_columns(r) for r in seq.read_summary()]
        rows_par = [_model_columns(r) for r in par.read_summary()]
        assert rows_seq == rows_par
        assert par.read_manifest()['nb_cases_done'] == tiny_params().nb_cases


def test_interrupted_campaign_resumes_without_rerunning():
    class Stop(Exception):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = RunStore.create(params)
        done = []

        def crash_after_two(outcome):
            done.append(outcome.case.tag)
            if len(done) == 2:
                raise Stop

        try:
            run_grid(params, store=store, on_case=crash_after_two)
        except Stop:
            pass
        assert len(list(store.results_dir.glob('*.json'))) == 2
        assert len(store.read_summary()) == 2           # usable right away

        first = {p.name: p.stat().st_mtime_ns for p in store.results_dir.glob('*.json')}
        rerun = []
        run_grid(params, store=store, resume=True,
                 on_case=lambda o: rerun.append(o.case.tag))
        assert sorted(rerun + done) == sorted(c.tag for c in params.cases())
        assert not set(rerun) & set(done), 'a finished case was run again'
        for name, mtime in first.items():
            assert (store.results_dir / name).stat().st_mtime_ns == mtime

        manifest = store.read_manifest()
        assert manifest['nb_cases_done'] == params.nb_cases
        assert len({c['tag'] for c in manifest['cases']}) == params.nb_cases
        assert manifest.get('resumed_utc')

        # Same results as an uninterrupted campaign.
        clean = run_grid(tiny_params(output_root=str(Path(tmp) / 'clean')))
        assert ([_model_columns(r) for r in store.read_summary()]
                == [_model_columns(r) for r in clean.read_summary()])


def test_cli_resume_keeps_the_run_parameters():
    with tempfile.TemporaryDirectory() as tmp:
        store = run_grid(tiny_params(output_root=tmp, fleet_sizes=(12,)))
        assert cli_main(['-q', 'run', '--resume', str(store.root),
                         '--seed', '3']) == EXIT_ERROR
        assert cli_main(['-q', 'run', '--resume', str(store.root),
                         '--workers', '2']) == EXIT_OK


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------

def main():
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith('test_') and callable(obj)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as exc:
            failures.append((name, exc, traceback.format_exc()))
            print(f"  FAIL  {name}: {exc}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} tests passed")
    for name, exc, tb in failures:
        print(f"\n===== {name} =====\n{tb}")
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
