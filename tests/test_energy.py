"""
test_energy.py — Planned vs delivered energy, and the migration of old runs.

    python -m tests.test_energy

Covers the slot/hour unit fix (`kwh_per_slot`), the split between the energy
booked by the reservations and the energy the charging slots actually added,
and `src.pipeline.energy_fix` for results written before that split.
"""

import copy
import json
import sys
import traceback

from src.experiments.config import SimulationConfig
from src.metrics.metrics import kwh_per_km, kwh_per_slot
from src.pipeline import energy_fix, tables
from tests.test_priority1 import run_sim, small_config


# ----------------------------------------------------------------------
# Units
# ----------------------------------------------------------------------

def test_kwh_per_slot_is_an_energy_per_slot():
    cfg = SimulationConfig()
    assert abs(kwh_per_km(cfg) - 0.1) < 1e-12          # 10 kWh / 100 km
    # 6 km of range per slot = 0.6 kWh per 5-minute slot = 7.2 kW.
    assert abs(kwh_per_slot(6, cfg) - 0.6) < 1e-12
    one_hour = cfg.NB_SLOTS_IN_ONE_HOUR
    assert abs(kwh_per_slot(6, cfg) * one_hour - 7.2) < 1e-9, (
        "one hour at 6 km/slot must deliver 7.2 kWh, not 0.6 (factor 12)")


def test_charge_one_slot_returns_range_actually_added():
    sim = run_sim(small_config(total_time=12), 'greedy')
    car = sim.cars[0]
    car.charging_power = 6
    car.soc_m = car.autonomy - 6e3 - 1.
    assert abs(car.charge_one_slot() - 6e3) < 1e-6      # full slot
    assert abs(car.charge_one_slot() - 1.) < 1e-6       # capped by the battery
    assert car.charge_one_slot() == 0.                  # already full


# ----------------------------------------------------------------------
# Planned vs delivered, on a real run
# ----------------------------------------------------------------------

def _run():
    return run_sim(small_config(scenario='pessimistic', nb_car=30,
                                total_time=12 * 12), 'bramev')


def test_planned_prices_every_reservation_at_its_duration():
    sim = _run()
    met = sim.metrics
    planned = met.station_energy_planned()
    power = {c.idx: c.charging_power for c in sim.cars}
    for s in sim.stations:
        log = met.station_charging_log[s.m]
        expected = sum(kwh_per_slot(power[car_id], sim.config) * nb_slots
                       for car_id, _, _, nb_slots in log)
        assert abs(planned[s.m] - expected) < 1e-3
        # One entry per confirmed reservation, no-shows included: the planned
        # slots are exactly the slots written to the calendar.
        assert len(log) == s.nb_reservations, (s.m, len(log), s.nb_reservations)
        assert sum(n for *_, n in log) == s.nb_slots_reserved
    assert sum(planned.values()) > 0, "the run booked nothing: test is void"
    assert sum(s.nb_no_show for s in sim.stations) > 0, "no no-show: test is void"


def test_delivered_is_bounded_by_planned_and_served_slots():
    sim = _run()
    planned = sim.metrics.station_energy_planned()
    delivered = sim.metrics.station_energy_delivered()
    max_slot = max(kwh_per_slot(c.charging_power, sim.config) for c in sim.cars)
    for s in sim.stations:
        # A car only charges inside its reserved slots.
        assert delivered[s.m] <= planned[s.m] + 1e-6, (s.m, delivered, planned)
        assert delivered[s.m] <= s.nb_slots_served * max_slot + 1e-6
        assert (delivered[s.m] > 0) == (s.nb_slots_served > 0)
    # With no-shows and cancellations some booked energy is never supplied.
    assert sum(delivered.values()) < sum(planned.values())


def test_summary_carries_both_energies():
    sim = _run()
    result = json.loads(json.dumps(sim.results(), default=str))
    row = tables.summary_row(result)
    assert row['energy_planned_kwh'] >= row['energy_delivered_kwh'] > 0
    assert 0 < row['energy_delivery_rate'] <= 1
    assert row['energy_exact'] is True
    stations = tables.station_table(result)
    assert abs(sum(r['energy_delivered_kwh'] for r in stations)
               - row['energy_delivered_kwh']) < 1e-2


# ----------------------------------------------------------------------
# Migration of a legacy result
# ----------------------------------------------------------------------

def _legacy_result(sim):
    """A current result, rewritten the way the old code stored its energy."""
    result = json.loads(json.dumps(sim.results(), default=str))
    met = result['metrics']
    planned = met.pop('station_energy_planned_kWh')
    met.pop('station_energy_delivered_kWh')
    met['station_demand_kWh'] = {sid: round(e / 12, 3)
                                 for sid, e in planned.items()}
    return result


def test_legacy_result_is_refused_until_migrated():
    legacy = _legacy_result(_run())
    try:
        tables.summary_row(legacy)
    except KeyError as exc:
        assert 'energy_fix' in str(exc)
    else:
        raise AssertionError('a legacy result must not be read silently')


def test_estimate_prices_slot_counts_at_the_accepted_cars_mean():
    sim = _run()
    legacy = _legacy_result(sim)
    acceptances = [{'car_id': str(r.car_id), 'station_id': str(r.station_id)}
                   for r in sim.metrics.acceptance_records]
    car_kwh = {c.idx: kwh_per_slot(c.charging_power, sim.config)
               for c in sim.cars}
    migrated = energy_fix.migrate_result(copy.deepcopy(legacy), None,
                                         acceptances, car_kwh)
    met = migrated['metrics']
    assert 'station_demand_kWh' not in met
    for station in migrated['stations']:
        sid = str(station['station_id'])
        accepted = [car_kwh[int(r['car_id'])] for r in acceptances
                    if r['station_id'] == sid]
        if not accepted:
            continue
        e_m = sum(accepted) / len(accepted)
        assert abs(met['station_energy_planned_kWh'][sid]
                   - station['nb_slots_reserved'] * e_m
                   * energy_fix.PLANNED_FACTOR) < 1e-3
        assert abs(met['station_energy_delivered_kWh'][sid]
                   - station['nb_slots_served'] * e_m
                   * energy_fix.DELIVERED_FACTOR) < 1e-3
    assert met['energy_exact'] is False
    assert migrated['energy_fix']['method'].startswith('estimated')
    assert tables.summary_row(migrated)['energy_exact'] is False


def test_migration_with_replay_is_exact():
    sim = _run()
    legacy = _legacy_result(sim)
    fresh = json.loads(json.dumps(_run().results(), default=str))
    assert energy_fix.check_replay(legacy, fresh) == []
    migrated = energy_fix.migrate_result(copy.deepcopy(legacy), fresh)
    for key in ('station_energy_planned_kWh', 'station_energy_delivered_kWh'):
        assert migrated['metrics'][key] == fresh['metrics'][key]
    assert migrated['metrics']['energy_exact'] is True


def test_replay_divergence_is_detected():
    legacy = _legacy_result(_run())
    fresh = json.loads(json.dumps(_run().results(), default=str))
    fresh['stations'][0]['nb_slots_served'] += 1
    assert 'stations' in energy_fix.check_replay(legacy, fresh)


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
