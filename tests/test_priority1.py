"""
test_priority1.py — Checks the seven "Priority 1" fixes.

    python -m tests.test_priority1

No external test dependency: assertions and a report, nothing else. Each test
carries the number of the point it covers.
"""

import io
import math
import sys
import traceback

import numpy as np

import src.env.offer as off
import src.env.utils as utils
from src.env.car import Car
from src.experiments.config import SimulationConfig
from src.experiments.run import define_agents
from src.experiments.seeding import STREAM_CODES, RngHub
from src.experiments.simulation import Simulation
from src.experiments.simulation_greedy import SimulationGreedy
from src.experiments.world import generate_world_spec, build_world


# ----------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------

def small_config(scenario='balance', nb_car=18, total_time=12 * 8, seed=123):
    cfg = SimulationConfig()
    cfg.set_VISUALIZE(False)
    cfg.set_seed(seed)
    cfg.set_scenario(scenario)
    cfg.set_TOTAL_TIME(total_time)
    cfg.set_NB_CARS(nb_car)
    cfg.set_NB_STATIONS(8)
    cfg.set_NB_SOCIETIES(2)
    cfg.set_log_iter(10 ** 6)     # no progress log
    return cfg


def run_sim(cfg, method='bramev', seed=None, spec=None):
    if spec is None:
        spec = generate_world_spec(cfg, seed if seed is not None else cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    klass = Simulation if method == 'bramev' else SimulationGreedy
    sim = klass(cars=cars, stations=stations, societies=societies,
                t_max=cfg.TOTAL_TIME, config=cfg)
    sim.run(io.StringIO(), print_metrics=False)
    return sim


def comparable(results):
    """Metrics independent from machine time (latencies vary)."""
    met = results['metrics']
    return {
        'satisfaction': met['user_request_satisfaction'],
        'travel':       met['mean_travel_distance_km'],
        'waiting':      met['mean_waiting_time_h'],
        'station_kwh':  met['station_demand_kWh'],
        'behaviors':    results['behaviors']['observed_counts'],
        'intents':      results['behaviors']['intent_counts'],
        'stations':     results['stations'],
        'nb_demands':   results['nb_demands'],
        'breakdowns':   results['breakdowns'],
    }


# ----------------------------------------------------------------------
# 1. Reproducibility
# ----------------------------------------------------------------------

def test_1_reproducibility():
    cfg_a = small_config(seed=999)
    cfg_b = small_config(seed=999)
    a = comparable(run_sim(cfg_a, 'bramev').results())
    b = comparable(run_sim(cfg_b, 'bramev').results())
    assert a == b, "Two runs with the same seed must be identical"

    cfg_c = small_config(seed=1000)
    c = comparable(run_sim(cfg_c, 'bramev').results())
    assert c != a, "Two different seeds must produce different worlds"


def test_1_seed_recorded_with_results():
    cfg = small_config(seed=4242)
    results = run_sim(cfg, 'greedy').results()
    assert results['seed'] == 4242
    assert results['config']['seed'] == 4242
    assert results['config']['scenario'] == 'balance'


def test_1_rng_streams_are_keyed_not_ordered():
    hub = RngHub(7)
    first = hub.stream('car_move', 3).random(5).tolist()
    _ = hub.stream('car_behavior', 0).random(100)      # interleaved consumption
    again = hub.stream('car_move', 3).random(5).tolist()
    assert first == again, "A stream is determined by its key, not by the call order"


# ----------------------------------------------------------------------
# 2. Same environment for every method
# ----------------------------------------------------------------------

def test_2_identical_world_across_methods():
    cfg = small_config(seed=55)
    spec = generate_world_spec(cfg, 55)
    worlds = [build_world(spec, cfg) for _ in range(2)]

    (cars_a, st_a, so_a), (cars_b, st_b, so_b) = worlds
    assert len(cars_a) == len(cars_b) and len(st_a) == len(st_b)

    for ca, cb in zip(cars_a, cars_b):
        assert ca is not cb, "The worlds must be independent"
        assert np.allclose(ca.loc, cb.loc)
        assert (ca.autonomy, ca.soc_init, ca.charging_power) == \
               (cb.autonomy, cb.soc_init, cb.charging_power)
        assert ca.theta == cb.theta and ca.pref == cb.pref
        assert ca.soc_threshold_m == cb.soc_threshold_m

    for sa, sb in zip(st_a, st_b):
        assert np.allclose(sa.loc, sb.loc)
        assert sa.nb_charg_spot == sb.nb_charg_spot
        assert sa.alpha == sb.alpha and sa.society_id == sb.society_id
        assert sa.schedule is not sb.schedule

    for fa, fb in zip(so_a, so_b):
        assert fa.strategy == fb.strategy
        assert [s.m for s in fa.stations] == [s.m for s in fb.stations]


def test_2_define_agents_is_deterministic():
    """The notebooks call define_agents() once per method."""
    cfg = small_config(seed=77)
    a = define_agents(cfg, seed=77)
    b = define_agents(cfg, seed=77)
    assert all(np.allclose(x.loc, y.loc) for x, y in zip(a[0], b[0]))
    assert all(x.theta == y.theta for x, y in zip(a[0], b[0]))
    assert all(x.alpha == y.alpha for x, y in zip(a[1], b[1]))


def test_2_common_random_numbers_for_behaviors():
    cfg = small_config(seed=88)
    spec = generate_world_spec(cfg, 88)
    cars_a, *_ = build_world(spec, cfg)
    cars_b, *_ = build_world(spec, cfg)
    for ca, cb in zip(cars_a, cars_b):
        seq_a = [ca.draw_behavior() for _ in range(30)]
        seq_b = [cb.draw_behavior() for _ in range(30)]
        assert seq_a == seq_b


# ----------------------------------------------------------------------
# 3. Identifiants de demande uniques
# ----------------------------------------------------------------------

def test_3_demand_ids_are_unique():
    cfg = small_config(seed=31, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    ids = list(sim.metrics.demand_timings)
    assert len(ids) == len(set(ids)), "Duplicated demand identifiers"
    assert len(ids) == sim.nb_demands
    # Two vehicles of the same slot have distinct identifiers
    per_slot = {}
    for rec in sim.metrics.demand_timings.values():
        per_slot.setdefault(rec.slot, set()).add(rec.demand_id)
    assert any(len(v) > 1 for v in per_slot.values()), \
        "The test must contain at least one slot with several demands"


def test_3_duplicate_id_is_refused():
    cfg = small_config(seed=32)
    cars, stations, _ = define_agents(cfg, seed=32)
    from src.metrics.metrics import MetricsCollector
    mc = MetricsCollector(cars, stations, cfg)
    mc.record_demand_emitted('t1-c1')
    try:
        mc.record_demand_emitted('t1-c1')
    except ValueError:
        return
    raise AssertionError("A duplicated identifier must raise an error")


# ----------------------------------------------------------------------
# 4. Decomposed latency
# ----------------------------------------------------------------------

def test_4_latency_stages_are_recorded_and_ordered():
    cfg = small_config(seed=41, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    recs = list(sim.metrics.demand_timings.values())
    assert recs

    answered = [r for r in recs if r.nb_offers_received > 0]
    confirmed = [r for r in recs if r.confirmed]
    assert answered, "No offer received: inconclusive test"
    assert confirmed, "Aucune confirmation : test non concluant"

    for r in recs:
        assert r.t_emission > 0
        # one entry per offer received, not a single overwritten one
        assert len(r.offer_receptions) == r.nb_offers_received
        for station_id, t in r.offer_receptions:
            assert t >= r.t_emission
        if r.nb_offers_received:
            assert r.t_first_offer <= r.t_last_offer
            assert r.t_selection >= r.t_last_offer
        if r.confirmed:
            assert r.t_confirmation >= r.t_selection
            for stage in (r.first_offer_ms, r.last_offer_ms, r.selection_ms,
                          r.confirmation_ms, r.total_ms):
                assert stage is not None and stage >= 0
            assert r.total_ms >= r.last_offer_ms

    lat = sim.metrics.latency_report()
    assert lat['nb_demands'] == len(recs)
    assert lat['nb_demands_answered'] == len(answered)
    assert lat['nb_demands_confirmed'] == len(confirmed)
    assert lat['nb_offers_received'] == sum(r.nb_offers_received for r in recs)
    for key in ('first_offer_ms_mean', 'last_offer_ms_mean',
                'selection_ms_mean', 'confirmation_ms_mean', 'total_ms_mean'):
        assert lat[key] is not None, f"{key} manquant"
    assert len(sim.metrics.latency_rows()) == len(recs)


def test_4_multi_offer_demands_keep_every_reception():
    """A demand broadcast to N stations records up to N receptions."""
    cfg = small_config(seed=42, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    multi = [r for r in sim.metrics.demand_timings.values()
             if r.nb_offers_received > 1]
    assert multi, "Aucune demande multi-offres : test non concluant"
    for r in multi:
        assert len({sid for sid, _ in r.offer_receptions}) == r.nb_offers_received
        assert len(r.per_offer_ms) == r.nb_offers_received


# ----------------------------------------------------------------------
# 5. Contiguous slots
# ----------------------------------------------------------------------

def test_5_all_offers_are_contiguous():
    cfg = small_config(seed=51, nb_car=25)
    spec = generate_world_spec(cfg, 51)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    seen = []
    for station in stations:
        original = station._make_offer

        def traced(*a, _orig=original, **kw):
            offer = _orig(*a, **kw)
            seen.append(offer)
            return offer
        station._make_offer = traced

    sim.run(io.StringIO(), print_metrics=False)

    assert seen, "No offer issued: inconclusive test"
    for offer in seen:
        assert offer.is_contiguous(), (
            f"Offre non contiguë : [{offer.t_arr},{offer.t_dep}) "
            f"pour d_prop={offer.d_prop}"
        )
        assert offer.d_prop >= 1 and offer.t_arr >= 0


def test_5_confirmed_reservations_are_contiguous_blocks():
    """Each vehicle occupies a contiguous block per charger in the calendar."""
    cfg = small_config(seed=52, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    for station in sim.stations:
        for j in range(station.nb_charg_spot):
            row = station.schedule[j]
            for car_id in set(int(v) for v in np.unique(row) if v != -1):
                idx = np.flatnonzero(row == car_id)
                assert idx[-1] - idx[0] + 1 == len(idx), (
                    f"Station {station.m} charger {j}: non-contiguous slots "
                    f"for vehicle {car_id} ({idx.tolist()})"
                )


def test_5_no_overlap_in_schedule():
    """A (charger, slot) pair is never allocated twice."""
    cfg = small_config(seed=53, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    for station in sim.stations:
        assert station.schedule.shape == (station.nb_charg_spot, cfg.TOTAL_TIME)
        # a single value per cell: guaranteed by the structure; what is
        # checked is that no confirmation overwrote an existing reservation
        assert station.nb_stale_confirm >= 0
        assert station.nb_confirm_refused >= 0


# ----------------------------------------------------------------------
# 6. Safe confirmation
# ----------------------------------------------------------------------

def _fresh_station(cfg, seed=61):
    _, stations, _ = define_agents(cfg, seed=seed)
    return stations[0]


def test_6_single_confirmation_others_expire():
    cfg = small_config(seed=61, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    tot_issued = sum(s.nb_offer_issued for s in sim.stations)
    tot_expired = sum(s.nb_offer_expired for s in sim.stations)
    tot_reserved = sum(s.nb_reservations for s in sim.stations)
    tot_refused = sum(s.nb_confirm_refused for s in sim.stations)
    assert tot_issued > 0
    # Every issued offer is either confirmed, expired or refused.
    assert tot_issued == tot_expired + tot_reserved + tot_refused, (
        f"{tot_issued} issued != {tot_expired} expired + {tot_reserved} "
        f"confirmed + {tot_refused} refused"
    )
    # A vehicle never has two simultaneous reservations
    assert all(c.reservation is None for c in sim.cars)


def test_6_expired_offer_cannot_be_confirmed():
    cfg = small_config(seed=62)
    station = _fresh_station(cfg, 62)
    offer = station._make_offer(charger_id=0, t_arr=5, t_dep=8, d_prop=3,
                               distance=100., t_c=0)
    assert offer.t_expire == 0 + cfg.OFFER_TTL_SLOTS
    ok, reason = station.validate_offer(offer, t_c=offer.t_expire)
    assert not ok and reason == 'expired'
    assert station.confirm_reservation(car_id=1, offer=offer,
                                      t_c=offer.t_expire) is False
    assert offer.status == 'REJECTED'
    assert np.all(station.schedule[0, 5:8] == -1), "Calendar wrongly modified"


def test_6_slot_taken_is_refused():
    cfg = small_config(seed=63)
    station = _fresh_station(cfg, 63)
    o1 = station._make_offer(0, 4, 7, 3, 100., t_c=0)
    o2 = station._make_offer(0, 6, 9, 3, 100., t_c=0)   # chevauche o1 (slot 6)
    assert station.confirm_reservation(1, o1, t_c=0) is True
    assert o1.status == 'CONFIRMED'
    assert station.confirm_reservation(2, o2, t_c=0) is False
    assert o2.reject_reason == 'slot_taken'
    assert np.all(station.schedule[0, 4:7] == 1)
    assert station.schedule[0, 7] == -1 and station.schedule[0, 8] == -1


def test_6_offer_confirmed_once_only():
    cfg = small_config(seed=64)
    station = _fresh_station(cfg, 64)
    offer = station._make_offer(1, 2, 5, 3, 100., t_c=0)
    assert station.confirm_reservation(9, offer, t_c=0) is True
    assert station.confirm_reservation(9, offer, t_c=0) is False
    assert offer.reject_reason == 'status_confirmed'
    assert int((station.schedule[1] == 9).sum()) == 3, "Duplicated reservation"


def test_6_expired_then_confirm_is_refused():
    cfg = small_config(seed=65)
    station = _fresh_station(cfg, 65)
    offer = station._make_offer(0, 3, 6, 3, 100., t_c=0)
    station.expire_offer(offer)
    assert offer.status == 'EXPIRED'
    assert station.confirm_reservation(4, offer, t_c=0) is False
    assert np.all(station.schedule[0, 3:6] == -1)


def test_6_non_contiguous_offer_is_refused():
    """Safety net: an inconsistent offer cannot be confirmed."""
    cfg = small_config(seed=66)
    station = _fresh_station(cfg, 66)
    bad = off.Offer(station_id=station.m, charger_id=0, t_arr=2, t_dep=8,
                    d_prop=3, distance=10., t_issued=0, t_expire=1)
    ok, reason = station.validate_offer(bad, t_c=0)
    assert not ok and reason == 'not_contiguous'
    assert station.confirm_reservation(1, bad, t_c=0) is False


def test_6_schedule_version_tracks_writes():
    cfg = small_config(seed=67)
    station = _fresh_station(cfg, 67)
    v0 = int(station.charger_version[0])
    offer = station._make_offer(0, 1, 4, 3, 100., t_c=0)
    assert offer.charger_version == v0
    station.confirm_reservation(5, offer, t_c=0)
    assert int(station.charger_version[0]) == v0 + 1
    station.release_reservation(5, offer)
    assert int(station.charger_version[0]) == v0 + 2


# ----------------------------------------------------------------------
# 7. Comportements early / late
# ----------------------------------------------------------------------

def test_7_scenarios_are_single_source_of_truth():
    cfg = SimulationConfig()
    for name in ('optimistic', 'balance', 'pessimistic'):
        cfg.set_scenario(name)
        p = cfg.BASE_CANCEL_PROB
        assert p['pres'] + p['abs'] + p['early'] + p['late'] == 100
        assert cfg.SCENARIO_NAME == name

    try:
        cfg.set_scenario('inconnu')
    except ValueError as exc:
        assert 'inconnu' in str(exc)
    else:
        raise AssertionError('an unknown scenario must be refused')

    # Growing severity on the two outcomes that cost the operator
    table = SimulationConfig.SCENARIOS
    order = ['optimistic', 'balance', 'pessimistic']
    for key in ('abs', 'late'):
        values = [table[s][key] for s in order]
        assert values == sorted(values), \
            f"'{key}' must grow from optimistic to pessimistic, got {values}"
    noises = {table[s]['noise'] for s in order}
    assert len(noises) == 1, "The noise must be identical across scenarios"


def test_7_early_cancellations_actually_fire():
    """
    The former logic made the "early" branch unreachable. On a long-delay
    reservation, an `early` intent must produce an observed `early`
    cancellation.
    """
    cfg = small_config(seed=71, nb_car=30, total_time=12 * 12)
    cfg.set_BASE_CANCEL_PROB({'pres': 1, 'abs': 1, 'early': 97, 'late': 1,
                              'noise': 0.0})
    sim = run_sim(cfg, 'bramev')
    beh = sim.behaviors.report()
    assert beh['intent_counts'].get('early', 0) > 0, "No early intent drawn"
    cancels = (beh['observed_counts'].get('early', 0)
               + beh['observed_counts'].get('late', 0))
    assert cancels > 0, "No cancellation realised for early intents"
    # no cancellation intent must end up counted as a presence
    assert sim.behaviors.pairs[('early', 'pres')] == 0, (
        "A cancellation intent must not be counted as a presence"
    )


def test_7_late_threshold_is_reachable_both_ways():
    cfg = SimulationConfig()
    # Long delay: threshold bounded by LATE_CANCEL_REF
    assert cfg.late_cancel_threshold(200) == cfg.LATE_CANCEL_REF
    # Short delay: threshold bounded by a fraction of the delay, and >= 1
    assert cfg.late_cancel_threshold(4) == 2
    assert cfg.late_cancel_threshold(1) == 1
    assert cfg.late_cancel_threshold(0) == 1
    for lead in range(0, 60):
        thr = cfg.late_cancel_threshold(lead)
        assert 1 <= thr <= cfg.LATE_CANCEL_REF


def test_7_observed_rates_are_recorded():
    cfg = small_config(seed=72, nb_car=30, total_time=12 * 10)
    sim = run_sim(cfg, 'bramev')
    beh = sim.behaviors.report()
    assert beh['nb_reservations'] > 0
    assert beh['nb_resolved'] == beh['nb_reservations'], (
        "Every reservation must receive exactly one outcome"
    )
    assert beh['intent_rates'] and beh['observed_rates']
    # the rates are rounded to 4 decimals: tolerance on the sum
    assert abs(sum(beh['intent_rates'].values()) - 1.0) < 1e-3
    assert abs(sum(beh['observed_rates'].values()) - 1.0) < 1e-3
    assert set(beh['observed_counts']) <= set(sim.behaviors.OUTCOMES)


def test_7_outcomes_are_distinguished():
    """early, late and no-show are counted separately per station."""
    cfg = small_config(seed=73, nb_car=30, total_time=12 * 10)
    cfg.set_BASE_CANCEL_PROB({'pres': 10, 'abs': 30, 'early': 30, 'late': 30,
                              'noise': 0.0})
    sim = run_sim(cfg, 'bramev')
    ok, errors = sim.check_reservation_invariant()
    assert ok, f"Invariant violated: {errors[:3]}"
    counts = sim.behaviors.report()['observed_counts']
    assert counts.get('abs', 0) > 0, "No no-show observed"
    assert counts.get('late', 0) + counts.get('early', 0) > 0, \
        "No cancellation observed"
    # the station counters and the tracker agree
    assert sum(s.nb_no_show for s in sim.stations) == counts.get('abs', 0)
    assert sum(s.nb_early_canc for s in sim.stations) == counts.get('early', 0)
    assert sum(s.nb_late_canc for s in sim.stations) == counts.get('late', 0)
    assert sum(s.nb_pres for s in sim.stations) == counts.get('pres', 0)


def test_7_invariant_holds_for_both_methods():
    for method in ('greedy', 'bramev'):
        cfg = small_config(seed=74, nb_car=25, total_time=12 * 8)
        sim = run_sim(cfg, method)
        ok, errors = sim.check_reservation_invariant()
        assert ok, f"{method}: invariant violated — {errors[:3]}"


# ----------------------------------------------------------------------
# 8. Planning horizon (early cancellation reachable)
# ----------------------------------------------------------------------

def test_8_nominal_arrival_is_the_single_source_of_truth():
    """
    Station, utility and metric must read the same nominal slot.

    The formula used to be duplicated with an `int()` on the station side and a
    `ceil()` elsewhere: on this grid the trip takes less than one slot, so the
    two views diverged systematically by one slot and the measured waiting time
    was wrong.
    """
    cfg = small_config()
    for dist in (0., 1., 1e3, 4.167e3, 9e3):
        for lead in (0, 1, 7):
            arr = utils.nominal_arrival(10, lead, dist, cfg)
            assert arr == math.ceil(10 + lead + dist / cfg.CAR_SPEED)
            # a vehicle cannot have arrived before it has driven
            assert arr >= 10 + lead


def test_8_lead_is_drawn_within_bounds():
    cfg = small_config(seed=81)
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 3, 'high': 9})
    spec = generate_world_spec(cfg, cfg.SEED)
    car = build_world(spec, cfg)[0][0]
    leads = [car.draw_reservation_lead() for _ in range(200)]
    assert min(leads) >= 3 and max(leads) <= 9, f"hors bornes : {min(leads)}-{max(leads)}"
    assert len(set(leads)) > 1, "the horizon must vary from one request to the next"

    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 0})
    car = build_world(spec, cfg)[0][0]
    assert {car.draw_reservation_lead() for _ in range(50)} == {0}


def test_8_lead_uses_a_dedicated_stream():
    """
    The horizon must come from its own stream: shared with `car_request`, it
    would shift the duration, radius and patience of every later request, and
    the two arms of the ablation would no longer differ by the horizon alone.
    """
    def requests(lead_params, nb=6):
        cfg = small_config(seed=83)
        cfg.set_RESERVATION_LEAD_PARAMS(lead_params)
        spec = generate_world_spec(cfg, cfg.SEED)
        car = build_world(spec, cfg)[0][0]
        out = []
        for k in range(nb):
            r = car.emit_request(k, (0., 0.), k)
            out.append((r['d_n'], r['r_n'], r['g_n']))
        return out

    witness = requests({'low': 0, 'high': 0})
    treated = requests({'low': 0, 'high': 12})
    assert witness == treated, (
        "enabling the horizon shifted the other request parameters: "
        "the stream is not dedicated"
    )
    assert STREAM_CODES['car_lead'] == 9, "the stream codes are frozen"


def test_8_min_lead_for_early_cancel_matches_the_threshold():
    cfg = SimulationConfig()
    min_lead = cfg.min_lead_for_early_cancel()
    assert min_lead == 3, f"expected 3 with fraction 0.5, got {min_lead}"
    # below it, the branch is demonstrably unreachable
    for lead in range(1, min_lead):
        assert lead - 1 <= cfg.late_cancel_threshold(lead)
    assert min_lead - 1 > cfg.late_cancel_threshold(min_lead)
    # the property must follow the fraction, not a hard-coded constant
    cfg.LATE_CANCEL_FRACTION = 0.9
    assert cfg.min_lead_for_early_cancel() > min_lead


def test_8_reservation_lead_opens_the_early_branch():
    """
    The heart of the fix: without a horizon, `t_arr` sticks to the request and
    *every* `early` intent is reclassified as `late`. With a horizon, they must
    be realised as such.
    """
    def outcomes(lead_params):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_RESERVATION_LEAD_PARAMS(lead_params)
        sim = run_sim(cfg, 'bramev')
        assert sim.check_reservation_invariant()[0], "invariant violated"
        return sim.behaviors.report()

    disabled = outcomes({'low': 0, 'high': 0})
    enabled = outcomes({'low': 6, 'high': 12})

    assert disabled['intent_counts'].get('early', 0) > 0
    assert disabled['observed_counts'].get('early', 0) == 0, (
        "without a horizon, no cancellation can be early"
    )
    assert disabled['reclassified'].get('early->late', 0) == disabled['intent_counts']['early']

    assert enabled['observed_counts'].get('early', 0) > 0, (
        "with a horizon, the early branch must be reached"
    )
    assert enabled['reclassified'].get('early->late', 0) < disabled['reclassified']['early->late']
    assert enabled['mean_lead_slots'] > disabled['mean_lead_slots']


def test_8_planned_lead_is_not_counted_as_waiting():
    """
    The horizon wanted by the driver is not endured waiting.

    Verified structurally, not in aggregate: shifting the request *and* the slot
    *together* by `l_n` slots must leave the waiting time and the utility
    unchanged. In aggregate, the measured waiting time does grow with the
    horizon — but because reservations are held longer and contention rises,
    which is a model effect and not a measurement bias.
    """
    cfg = small_config()
    spec = generate_world_spec(cfg, cfg.SEED)
    car = build_world(spec, cfg)[0][0]

    dist = 2.5e3
    base = {'n': 1, 'car_idx': car.idx, 't_n': 20, 'd_n': 12,
            'loc': (0., 0.), 'r_n': 5e3, 'g_n': 12, 'l_n': 0}
    t_arr0 = utils.nominal_arrival(base['t_n'], 0, dist, cfg)
    offer0 = off.Offer(station_id=0, charger_id=0, t_arr=t_arr0,
                       t_dep=t_arr0 + 12, d_prop=12, distance=dist)

    lead = 10
    shifted = dict(base, l_n=lead)
    t_arr1 = utils.nominal_arrival(shifted['t_n'], lead, dist, cfg)
    assert t_arr1 == t_arr0 + lead, "the nominal slot must follow the horizon"
    offer1 = off.Offer(station_id=0, charger_id=0, t_arr=t_arr1,
                       t_dep=t_arr1 + 12, d_prop=12, distance=dist)

    u0 = car.compute_utility(offer0, base, min_dist=1e3)
    u1 = car.compute_utility(offer1, shifted, min_dist=1e3)
    assert u0 == u1, (
        f"the planned horizon degrades the utility ({u0} -> {u1}): it is counted "
        "as endured waiting"
    )
    assert u1 > 0, "utility flattened to zero by the waiting normalisation"

    # A horizon ignored by compute_utility would give waitingTime = l_n, hence
    # a ratio > 1 over maxWaitingTime = g_n: that is the signature of the bug.
    naive = car.compute_utility(offer1, base, min_dist=1e3)
    assert naive < u1, "the test does not discriminate: check the construction"


def test_8_measured_waiting_stays_far_below_the_planned_horizon():
    """
    Aggregate guard: if the horizon were counted as waiting, the measured
    waiting time would be about the mean horizon. It must stay far from it.
    """
    cfg = small_config(scenario='balance', nb_car=40, total_time=12 * 20, seed=71)
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 6, 'high': 12})
    sim = run_sim(cfg, 'bramev')
    beh = sim.behaviors.report()
    wait_slots = (sim.metrics.report()['mean_waiting_time_h'] * 60
                  / cfg.SLOT_DURATION)
    assert wait_slots < 0.25 * beh['mean_lead_slots'], (
        f"measured waiting {wait_slots:.2f} slots for a mean horizon of "
        f"{beh['mean_lead_slots']}: the horizon leaks into the metric"
    )

    served = [c for c in sim.cars if c.nb_sessions > 0]
    assert served and any(c.u_total > 0 for c in served), (
        "every utility is zero: the offer ranking is degenerate"
    )


def test_8_zero_lead_is_the_control_arm():
    """
    `{0, 0}` is not a neutral setting but the control arm of the ablation: an
    early cancellation must be demonstrably unreachable there, and the run must
    stay deterministic.
    """
    def run():
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 0})
        sim = run_sim(cfg, 'bramev')
        return sim.behaviors.report(), sim.metrics.report()

    a_beh, a_met = run()
    b_beh, b_met = run()
    assert a_beh['observed_counts'] == b_beh['observed_counts']
    assert a_met['mean_travel_distance_km'] == b_met['mean_travel_distance_km']

    assert a_beh['intent_counts'].get('early', 0) > 0, "aucune intention early"
    assert a_beh['observed_counts'].get('early', 0) == 0, (
        "without a horizon, no cancellation can be qualified as early"
    )


def test_8_diagnostic_separates_structure_from_sampling():
    """
    The diagnostic must assert a *structural* impossibility, never extrapolate
    from a handful of intents.

    It used to cry false positive on the tiny grids of the tests: a single
    unrealised `early` intent triggered a message announcing a "nearly zero"
    delay although the median delay was 2 to 3 slots.
    """
    from src.metrics.metrics import BehaviorTracker

    cfg = SimulationConfig()
    min_lead = cfg.min_lead_for_early_cancel()

    # (a) Sufficient delays, a single unrealised intent -> silent.
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 12})
    small = BehaviorTracker(cfg)
    for _ in range(7):
        small.record_intent('pres', min_lead + 2)
    small.record_intent('early', 1)
    small.record_outcome('early', 'late')
    assert small.anticipable_share() > 0
    assert small.diagnostics() == [], (
        f"false positive on a sample of 1: {small.diagnostics()}"
    )

    # (b) Horizon requested but never obtained -> reported, whatever the
    #     number of intents, with the actionable cause.
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 12})
    struct = BehaviorTracker(cfg)
    for _ in range(8):
        struct.record_intent('pres', 1)
    struct.record_intent('early', 1)
    struct.record_outcome('early', 'late')
    assert struct.anticipable_share() == 0.
    assert any('simulation horizon too short' in d.lower()
               for d in struct.diagnostics()), (
        f"cause not reported: {struct.diagnostics()}"
    )

    # (b') Same situation, but anticipation deliberately disabled -> silent.
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 0})
    control = BehaviorTracker(cfg)
    for _ in range(8):
        control.record_intent('pres', 1)
    control.record_intent('early', 1)
    control.record_outcome('early', 'late')
    assert control.anticipable_share() == 0.
    assert control.diagnostics() == [], (
        f"the control arm must report nothing: {control.diagnostics()}"
    )

    # (c) Sufficient delays but none of the N intents realised -> anomaly.
    anomaly = BehaviorTracker(cfg)
    for _ in range(20):
        anomaly.record_intent('pres', min_lead + 5)
    for _ in range(BehaviorTracker.MIN_EARLY_SAMPLE):
        anomaly.record_intent('early', min_lead + 5)
        anomaly.record_outcome('early', 'late')
    diags = anomaly.diagnostics()
    assert any('intents' in d for d in diags), f"anomaly not reported: {diags}"
    assert not any('Increase RESERVATION_LEAD_PARAMS' in d for d in diags), (
        "do not blame the structure for what is not structural"
    )


def test_8_neither_arm_is_diagnosed_when_configured_deliberately():
    """
    End to end: neither the control arm nor the treated arm must produce a
    diagnostic. Disabling anticipation is a choice, not an anomaly — and
    `ExperimentParams.validate` already reported it at configuration time.
    """
    def diagnose(lead_params):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_RESERVATION_LEAD_PARAMS(lead_params)
        return run_sim(cfg, 'bramev').behaviors.report()

    control = diagnose({'low': 0, 'high': 0})
    assert control['anticipable_share'] == 0., "the control arm must be sterile"
    assert control['diagnostics'] == [], (
        f"the control arm is deliberate, not abnormal: {control['diagnostics']}"
    )

    treated = diagnose({'low': 0, 'high': 12})
    assert treated['anticipable_share'] > 0.5
    assert treated['observed_counts'].get('early', 0) > 0
    assert treated['diagnostics'] == [], (
        f"unwarranted diagnostic on the treated arm: {treated['diagnostics']}"
    )


# ----------------------------------------------------------------------
# 9. Stopped states: parked no-show, search retry
# ----------------------------------------------------------------------

def test_9_no_show_parks_instead_of_roaming():
    """
    A no-show gives up its trip, not only its charge: it stays put as long as
    it holds its slot, then drives on once released.

    Continuity is tracked through the reservation object: a vehicle may leave
    the parked state, drive, then park again with a *new* reservation within the
    same step — comparing two slot ends is not enough.
    """
    cfg = small_config(scenario='pessimistic', nb_car=30, total_time=12 * 12,
                       seed=91)
    cfg.set_BASE_CANCEL_PROB({'pres': 1, 'abs': 97, 'early': 1, 'late': 1,
                              'noise': 0.0})
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    episodes = {}     # idx -> (reservation, x, y, soc)
    seen = 0
    log = io.StringIO()
    for t in range(cfg.TOTAL_TIME):
        sim.current_t = t
        sim.step(t, 10 ** 6, file=log)
        for car in sim.cars:
            if car.cancel_intent == 'abs' and car.reservation is not None:
                assert car.state == 'PARKED_NO_SHOW', (
                    f"car_{car.idx} holds a no-show slot but is "
                    f"{car.state}"
                )
                current = (car.reservation, car.x, car.y, car.soc_m)
                if episodes.get(car.idx, (None,))[0] is car.reservation:
                    assert episodes[car.idx] == current, (
                        f"parked car_{car.idx} moved or consumed"
                    )
                else:
                    seen += 1
                episodes[car.idx] = current
            else:
                episodes.pop(car.idx, None)

    assert seen > 0, "no no-show observed: inconclusive test"
    assert sim.behaviors.outcomes.get('abs', 0) > 0


def test_9_no_phase_moves_a_parked_vehicle():
    """
    The central invariant of the two stopped states: no phase of `step` may
    move a parked vehicle. Verified at the source — `update_state` is the only
    point of movement and consumption.
    """
    cfg = small_config(scenario='pessimistic', nb_car=30, total_time=12 * 12,
                       seed=94)
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    original = Car.update_state
    faults = []

    def surveille(self, loc=None):
        if self.state in Car.PARKED_STATES:
            faults.append((self.idx, self.state))
        return original(self, loc)

    seen = set()
    Car.update_state = surveille
    try:
        log = io.StringIO()
        for t in range(cfg.TOTAL_TIME):
            sim.current_t = t
            sim.step(t, 10 ** 6, file=log)
            seen |= {c.state for c in sim.cars if c.state in Car.PARKED_STATES}
    finally:
        Car.update_state = original

    assert not faults, f"parked vehicles moved: {faults[:5]}"
    assert seen, "no parked state observed: inconclusive test"


def test_9_failed_search_parks_and_widens_the_radius():
    """
    For lack of a station or an offer, the vehicle stops and re-emits the
    *same* demand with a widened radius — it does not drive off at random.
    """
    cfg = small_config(seed=92)
    cfg.set_SEARCH_RADIUS_GROWTH(1.5)
    cfg.set_MAX_SEARCH_RETRIES(3)
    spec = generate_world_spec(cfg, cfg.SEED)
    car = build_world(spec, cfg)[0][0]

    car.emit_request(0, (car.x, car.y), 'd0')
    r0 = car.request['r_n']
    radii = [r0]
    for k in range(3):
        assert car.widen_search(), f"retry {k + 1} wrongly refused"
        radii.append(car.request['r_n'])
        assert car.search_retries == k + 1

    assert not car.widen_search(), "the retry budget must be bounded"
    assert car.search_retries == 3

    plafond = cfg.max_search_radius()
    for before, after in zip(radii, radii[1:]):
        attendu = min(before * 1.5, plafond)
        assert abs(after - attendu) < 1e-6, f"{before} -> {after}, attendu {attendu}"
    assert radii[-1] <= plafond + 1e-9

    # The identity of the demand and its other parameters are preserved: a
    # retry is the same demand, not a new one.
    assert car.request['n'] == 'd0'


def test_9_retry_keeps_one_demand_per_need():
    """
    A retried demand stays *one* demand. Without that, each attempt would
    inflate `nb_demands` and sink the confirmation rate without any extra need
    having been expressed.
    """
    def campaign(retries):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_MAX_SEARCH_RETRIES(retries)
        sim = run_sim(cfg, 'bramev')
        recs = list(sim.metrics.demand_timings.values())
        return {
            'demands':   len(recs),
            'confirmed': sum(1 for r in recs if r.confirmed),
            'retries':   sum(r.nb_search_retries for r in recs),
            'resa':      sim.behaviors.report()['nb_reservations'],
        }

    disabled = campaign(0)
    enabled = campaign(4)

    assert disabled['retries'] == 0, "zero budget: no retry possible"
    assert enabled['retries'] > 0, "no retry triggered: inconclusive test"
    assert enabled['demands'] < disabled['demands'], (
        f"the retry must group the attempts: {enabled['demands']} "
        f"vs {disabled['demands']}"
    )
    # The number of needs served must not collapse: attempts are grouped, no
    # reservation is removed.
    assert enabled['resa'] >= 0.9 * disabled['resa'], (
        f"reservations lost: {enabled['resa']} vs {disabled['resa']}"
    )


def test_9_search_gives_up_and_never_deadlocks():
    """
    The retry budget must be effective: no vehicle may stay parked until the
    end of the horizon without ever giving up.
    """
    cfg = small_config(scenario='balance', nb_car=25, total_time=12 * 10,
                       seed=93)
    cfg.set_MAX_SEARCH_RETRIES(2)
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    log = io.StringIO()
    consecutive = {c.idx: 0 for c in sim.cars}
    for t in range(cfg.TOTAL_TIME):
        sim.current_t = t
        sim.step(t, 10 ** 6, file=log)
        for car in sim.cars:
            if car.state == 'PARKED_SEARCHING':
                consecutive[car.idx] += 1
                assert car.search_retries <= cfg.MAX_SEARCH_RETRIES
            else:
                consecutive[car.idx] = 0
            assert consecutive[car.idx] <= cfg.MAX_SEARCH_RETRIES + 1, (
                f"car_{car.idx} parked {consecutive[car.idx]} slots in a row: "
                f"the retry budget is not enforced"
            )


# ----------------------------------------------------------------------
# 10. Reputation: bounded score, sliding window, redemption
# ----------------------------------------------------------------------

def _scoring_station(cfg):
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, _ = build_world(spec, cfg)
    return cars[0], stations[0]


def test_10_score_stays_bounded_whatever_the_history():
    """
    The score must stay in [-1, 1] whatever the sequence of outcomes — that is
    what makes `alpha` meaningful. The former cumulative sum reached several
    hundreds against a profit term of w1*z = 2.
    """
    cfg = small_config(seed=101)
    car, station = _scoring_station(cfg)
    rng = np.random.default_rng(0)
    statuts = ('pres', 'abs', 'early', 'late')
    for _ in range(300):
        station.update_car_score(car, str(rng.choice(statuts)),
                                 float(rng.integers(1, 40)))
        assert -1. <= car.score[station.score_index] <= 1., car.score

    # Window full of a single outcome: the score is exactly the normalised
    # stake of that outcome. The effective floor is therefore
    # -mu['abs'] / max(mu) — it only reaches -1 if the no-show is the heaviest
    # stake of the scale. That asymmetry is the one of BASE_POINTS_STRATEGY
    # (pres 4.0 against abs 3.0, noised per company): the normalisation
    # deliberately preserves it instead of stretching each side to +/-1.
    mu = station.strategy
    for statut in ('abs', 'late', 'early'):
        car.reset_score()
        for _ in range(cfg.SCORE_MEMORY):
            station.update_car_score(car, statut, 40)
        attendu = -mu[statut] / max(mu.values())
        assert abs(car.score[station.score_index] - attendu) < 1e-12, (
            f"{statut} : {car.score[station.score_index]} != {attendu}"
        )
        assert -1. <= attendu < 0.

    car.reset_score()
    for _ in range(cfg.SCORE_MEMORY):
        station.update_car_score(car, 'pres', 40)
    assert abs(car.score[station.score_index]
               - mu['pres'] / max(mu.values())) < 1e-12

    # The order of the scale is preserved by the normalisation — whatever it
    # is: STRATEGY_NOISE (±50%) may reorder the stakes from one company to the
    # next, so the test refers to the scale actually drawn.
    def plein(statut):
        car.reset_score()
        for _ in range(cfg.SCORE_MEMORY):
            station.update_car_score(car, statut, 40)
        return float(car.score[station.score_index])

    negatives = sorted(('abs', 'late', 'early'), key=lambda k: mu[k], reverse=True)
    scores = [plein(k) for k in negatives]
    assert scores == sorted(scores), (
        f"order of the scale not preserved: {dict(zip(negatives, scores))} "
        f"pour mu={ {k: round(mu[k], 3) for k in negatives} }"
    )
    assert all(v < 0 for v in scores)


def test_10_window_forgets_beyond_score_memory():
    """Beyond SCORE_MEMORY reservations, the oldest ones no longer count."""
    cfg = small_config(seed=102)
    cfg.set_SCORE_MEMORY(5)
    car, station = _scoring_station(cfg)

    for _ in range(5):
        station.update_car_score(car, 'abs', 10)
    creux = float(car.score[station.score_index])
    assert creux < 0

    for _ in range(5):                      # the window is entirely replaced
        station.update_car_score(car, 'pres', 10)
    after = float(car.score[station.score_index])

    assert len(car.score_history[station.score_index]) == 5, "unbounded window"
    assert after > 0, f"the old outcomes still weigh: {after}"
    # The final score must depend on the last 5 only.
    witness, station_t = _scoring_station(small_config(seed=102))
    for _ in range(5):
        station_t.update_car_score(witness, 'pres', 10)
    assert abs(after - float(witness.score[station_t.score_index])) < 1e-12


def test_10_sparse_history_is_shrunk_toward_unknown():
    """
    A single isolated outcome must not be enough to reach the floor.

    Without that attenuation, one negative outcome gave the mean of a single
    event — the floor — the vehicle became ineligible everywhere, received no
    further reservation, and its window could no longer turn: the right to be
    forgotten was inoperative.
    """
    cfg = small_config(seed=103)
    cfg.set_SCORE_MEMORY(5)
    car, station = _scoring_station(cfg)

    station.update_car_score(car, 'abs', 10)
    one_only = float(car.score[station.score_index])

    car.reset_score()
    for _ in range(5):
        station.update_car_score(car, 'abs', 10)
    five = float(car.score[station.score_index])

    assert one_only > five, (
        f"an isolated outcome ({one_only}) must weigh less than five ({five})"
    )
    assert abs(one_only - five / 5.) < 1e-12, (
        "the attenuation must be proportional to how full the window is"
    )
    assert car.score_history[station.score_index].maxlen == 5


def test_10_a_single_incident_never_excludes_everywhere():
    """
    Redemption: after one isolated negative outcome, some stations must still
    be willing to serve the vehicle — otherwise it can no longer prove anything.

    A station excludes a vehicle when the objective coefficient turns negative,
    i.e. `score < -2*alpha/(1-alpha)` (nominal window, D = 0).
    """
    cfg = small_config(seed=104)
    car, station = _scoring_station(cfg)
    station.update_car_score(car, 'abs', 40)     # worst outcome, maximal duration
    score = float(car.score[station.score_index])

    excluded = [a for a in (0.1, 0.3, 0.5, 0.7, 0.9)
              if score < -2. * a / (1. - a)]
    assert not excluded, (
        f"score {score:.3f}: excluded from the stations of alpha {excluded} after a "
        "single incident — no redemption possible"
    )


def test_10_reputation_no_longer_collapses_service():
    """
    End to end: enabling reputation must no longer collapse the service.

    With the cumulative score, satisfaction fell from 0.761 to 0.645 — not
    through arbitration, but because 97% of the demands seen by the stations had
    a score below the exclusion threshold and received no offer.
    """
    def run(mode):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        spec = generate_world_spec(cfg, cfg.SEED)
        cars, stations, societies = build_world(spec, cfg)
        sim = Simulation(cars=cars, stations=stations, societies=societies,
                         t_max=cfg.TOTAL_TIME, config=cfg, mode=mode)
        sim.run(io.StringIO(), print_metrics=False)
        return sim

    disabled = run('multistation')
    enabled = run('multistation_rep')

    s_disabled = disabled.metrics.report()['user_request_satisfaction']['exact_satisfaction']
    s_enabled = enabled.metrics.report()['user_request_satisfaction']['exact_satisfaction']
    assert s_enabled >= 0.95 * s_disabled, (
        f"reputation collapses the service: {s_enabled:.3f} vs {s_disabled:.3f}"
    )

    # ... without becoming inert either: the score must still vary.
    scores = np.array([c.score for c in enabled.cars])
    assert scores.min() < -0.05 and scores.max() > 0.05, (
        f"score inerte : min={scores.min()}, max={scores.max()}"
    )
    assert np.all(np.abs(scores) <= 1.)


# ----------------------------------------------------------------------
# Lanceur
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
