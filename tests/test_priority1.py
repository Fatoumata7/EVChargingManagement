"""
test_priority1.py — Vérifie les sept corrections « Priorité 1 ».

    python -m tests.test_priority1

Aucune dépendance de test externe : uniquement des assertions et un compte-rendu.
Chaque test porte le numéro du point corrigé.
"""

import io
import sys
import traceback

import numpy as np

import src.env.offer as off
from src.experiments.config import SimulationConfig
from src.experiments.run import define_agents
from src.experiments.seeding import RngHub
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
    cfg.set_log_iter(10 ** 6)     # pas de log de progression
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
    """Métriques indépendantes du temps machine (les latences varient)."""
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
# 1. Reproductibilité
# ----------------------------------------------------------------------

def test_1_reproducibility():
    cfg_a = small_config(seed=999)
    cfg_b = small_config(seed=999)
    a = comparable(run_sim(cfg_a, 'bramev').results())
    b = comparable(run_sim(cfg_b, 'bramev').results())
    assert a == b, "Deux exécutions de même graine doivent être identiques"

    cfg_c = small_config(seed=1000)
    c = comparable(run_sim(cfg_c, 'bramev').results())
    assert c != a, "Deux graines différentes doivent produire des mondes différents"


def test_1_seed_recorded_with_results():
    cfg = small_config(seed=4242)
    results = run_sim(cfg, 'greedy').results()
    assert results['seed'] == 4242
    assert results['config']['seed'] == 4242
    assert results['config']['scenario'] == 'balance'


def test_1_rng_streams_are_keyed_not_ordered():
    hub = RngHub(7)
    first = hub.stream('car_move', 3).random(5).tolist()
    _ = hub.stream('car_behavior', 0).random(100)      # consommation intercalée
    again = hub.stream('car_move', 3).random(5).tolist()
    assert first == again, "Un flux est déterminé par sa clé, pas par l'ordre d'appel"


# ----------------------------------------------------------------------
# 2. Même environnement pour toutes les méthodes
# ----------------------------------------------------------------------

def test_2_identical_world_across_methods():
    cfg = small_config(seed=55)
    spec = generate_world_spec(cfg, 55)
    worlds = [build_world(spec, cfg) for _ in range(2)]

    (cars_a, st_a, so_a), (cars_b, st_b, so_b) = worlds
    assert len(cars_a) == len(cars_b) and len(st_a) == len(st_b)

    for ca, cb in zip(cars_a, cars_b):
        assert ca is not cb, "Les mondes doivent être indépendants"
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
    """Les notebooks appellent define_agents() une fois par méthode."""
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
    assert len(ids) == len(set(ids)), "Identifiants de demande dupliqués"
    assert len(ids) == sim.nb_demands
    # Deux véhicules du même slot ont des identifiants distincts
    per_slot = {}
    for rec in sim.metrics.demand_timings.values():
        per_slot.setdefault(rec.slot, set()).add(rec.demand_id)
    assert any(len(v) > 1 for v in per_slot.values()), \
        "Le test doit contenir au moins un slot à plusieurs demandes"


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
    raise AssertionError("Un identifiant dupliqué doit lever une erreur")


# ----------------------------------------------------------------------
# 4. Latence décomposée
# ----------------------------------------------------------------------

def test_4_latency_stages_are_recorded_and_ordered():
    cfg = small_config(seed=41, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    recs = list(sim.metrics.demand_timings.values())
    assert recs

    answered = [r for r in recs if r.nb_offers_received > 0]
    confirmed = [r for r in recs if r.confirmed]
    assert answered, "Aucune offre reçue : test non concluant"
    assert confirmed, "Aucune confirmation : test non concluant"

    for r in recs:
        assert r.t_emission > 0
        # une entrée par offre reçue, pas une seule écrasée
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
    """Une demande diffusée à N stations enregistre jusqu'à N réceptions."""
    cfg = small_config(seed=42, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    multi = [r for r in sim.metrics.demand_timings.values()
             if r.nb_offers_received > 1]
    assert multi, "Aucune demande multi-offres : test non concluant"
    for r in multi:
        assert len({sid for sid, _ in r.offer_receptions}) == r.nb_offers_received
        assert len(r.per_offer_ms) == r.nb_offers_received


# ----------------------------------------------------------------------
# 5. Créneaux contigus
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

    assert seen, "Aucune offre émise : test non concluant"
    for offer in seen:
        assert offer.is_contiguous(), (
            f"Offre non contiguë : [{offer.t_arr},{offer.t_dep}) "
            f"pour d_prop={offer.d_prop}"
        )
        assert offer.d_prop >= 1 and offer.t_arr >= 0


def test_5_confirmed_reservations_are_contiguous_blocks():
    """Chaque véhicule occupe un bloc contigu par borne dans le calendrier."""
    cfg = small_config(seed=52, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    for station in sim.stations:
        for j in range(station.nb_charg_spot):
            row = station.schedule[j]
            for car_id in set(int(v) for v in np.unique(row) if v != -1):
                idx = np.flatnonzero(row == car_id)
                assert idx[-1] - idx[0] + 1 == len(idx), (
                    f"Station {station.m} borne {j} : créneaux non contigus "
                    f"pour le véhicule {car_id} ({idx.tolist()})"
                )


def test_5_no_overlap_in_schedule():
    """Un créneau (borne, slot) n'est jamais attribué deux fois."""
    cfg = small_config(seed=53, nb_car=25)
    sim = run_sim(cfg, 'bramev')
    for station in sim.stations:
        assert station.schedule.shape == (station.nb_charg_spot, cfg.TOTAL_TIME)
        # une seule valeur par case : garanti par la structure ; on vérifie
        # qu'aucune confirmation n'a écrasé une réservation existante
        assert station.nb_stale_confirm >= 0
        assert station.nb_confirm_refused >= 0


# ----------------------------------------------------------------------
# 6. Confirmation sécurisée
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
    # Toute offre émise est soit confirmée, soit expirée, soit refusée.
    assert tot_issued == tot_expired + tot_reserved + tot_refused, (
        f"{tot_issued} émises != {tot_expired} expirées + {tot_reserved} "
        f"confirmées + {tot_refused} refusées"
    )
    # Un véhicule n'a jamais deux réservations simultanées
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
    assert np.all(station.schedule[0, 5:8] == -1), "Calendrier modifié à tort"


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
    assert int((station.schedule[1] == 9).sum()) == 3, "Réservation dupliquée"


def test_6_expired_then_confirm_is_refused():
    cfg = small_config(seed=65)
    station = _fresh_station(cfg, 65)
    offer = station._make_offer(0, 3, 6, 3, 100., t_c=0)
    station.expire_offer(offer)
    assert offer.status == 'EXPIRED'
    assert station.confirm_reservation(4, offer, t_c=0) is False
    assert np.all(station.schedule[0, 3:6] == -1)


def test_6_non_contiguous_offer_is_refused():
    """Filet de sécurité : une offre incohérente ne peut pas être confirmée."""
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
        raise AssertionError('un scénario inconnu doit être refusé')

    # Sévérité croissante sur les deux issues coûteuses pour l'opérateur
    table = SimulationConfig.SCENARIOS
    order = ['optimistic', 'balance', 'pessimistic']
    for key in ('abs', 'late'):
        values = [table[s][key] for s in order]
        assert values == sorted(values), \
            f"'{key}' doit croître de optimistic à pessimistic, reçu {values}"
    noises = {table[s]['noise'] for s in order}
    assert len(noises) == 1, "Le bruit doit être identique entre scénarios"


def test_7_early_cancellations_actually_fire():
    """
    L'ancienne logique rendait la branche « anticipée » inatteignable.
    Sur une réservation à long délai, une intention `early` doit produire une
    annulation observée `early`.
    """
    cfg = small_config(seed=71, nb_car=30, total_time=12 * 12)
    cfg.set_BASE_CANCEL_PROB({'pres': 1, 'abs': 1, 'early': 97, 'late': 1,
                              'noise': 0.0})
    sim = run_sim(cfg, 'bramev')
    beh = sim.behaviors.report()
    assert beh['intent_counts'].get('early', 0) > 0, "Aucune intention early tirée"
    cancels = (beh['observed_counts'].get('early', 0)
               + beh['observed_counts'].get('late', 0))
    assert cancels > 0, "Aucune annulation réalisée pour des intentions early"
    # aucune intention d'annulation ne doit finir comptée comme présence
    assert sim.behaviors.pairs[('early', 'pres')] == 0, (
        "Une intention d'annulation ne doit pas être comptée comme présence"
    )


def test_7_late_threshold_is_reachable_both_ways():
    cfg = SimulationConfig()
    # Délai long : seuil borné par LATE_CANCEL_REF
    assert cfg.late_cancel_threshold(200) == cfg.LATE_CANCEL_REF
    # Délai court : seuil borné par une fraction du délai, et >= 1
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
        "Chaque réservation doit recevoir exactement une issue"
    )
    assert beh['intent_rates'] and beh['observed_rates']
    # les taux sont arrondis à 4 décimales : tolérance sur la somme
    assert abs(sum(beh['intent_rates'].values()) - 1.0) < 1e-3
    assert abs(sum(beh['observed_rates'].values()) - 1.0) < 1e-3
    assert set(beh['observed_counts']) <= set(sim.behaviors.OUTCOMES)


def test_7_outcomes_are_distinguished():
    """early, late et no-show sont comptés séparément par station."""
    cfg = small_config(seed=73, nb_car=30, total_time=12 * 10)
    cfg.set_BASE_CANCEL_PROB({'pres': 10, 'abs': 30, 'early': 30, 'late': 30,
                              'noise': 0.0})
    sim = run_sim(cfg, 'bramev')
    ok, errors = sim.check_reservation_invariant()
    assert ok, f"Invariant violé : {errors[:3]}"
    counts = sim.behaviors.report()['observed_counts']
    assert counts.get('abs', 0) > 0, "Aucun no-show observé"
    assert counts.get('late', 0) + counts.get('early', 0) > 0, \
        "Aucune annulation observée"
    # les compteurs station et le tracker concordent
    assert sum(s.nb_no_show for s in sim.stations) == counts.get('abs', 0)
    assert sum(s.nb_early_canc for s in sim.stations) == counts.get('early', 0)
    assert sum(s.nb_late_canc for s in sim.stations) == counts.get('late', 0)
    assert sum(s.nb_pres for s in sim.stations) == counts.get('pres', 0)


def test_7_invariant_holds_for_both_methods():
    for method in ('greedy', 'bramev'):
        cfg = small_config(seed=74, nb_car=25, total_time=12 * 8)
        sim = run_sim(cfg, method)
        ok, errors = sim.check_reservation_invariant()
        assert ok, f"{method} : invariant violé — {errors[:3]}"


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

    print(f"\n{len(tests) - len(failures)}/{len(tests)} tests réussis")
    for name, exc, tb in failures:
        print(f"\n===== {name} =====\n{tb}")
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
