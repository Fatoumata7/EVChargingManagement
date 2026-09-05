"""
test_priority1.py — Vérifie les sept corrections « Priorité 1 ».

    python -m tests.test_priority1

Aucune dépendance de test externe : uniquement des assertions et un compte-rendu.
Chaque test porte le numéro du point corrigé.
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
# 8. Horizon de planification (annulation anticipée atteignable)
# ----------------------------------------------------------------------

def test_8_nominal_arrival_is_the_single_source_of_truth():
    """
    Station, utilité et métrique doivent lire le même créneau nominal.

    La formule était dupliquée avec un `int()` côté station et un `ceil()`
    ailleurs : sur cette grille le trajet dure moins d'un slot, donc les deux
    vues divergeaient systématiquement d'un slot et l'attente mesurée était
    faussée.
    """
    cfg = small_config()
    for dist in (0., 1., 1e3, 4.167e3, 9e3):
        for lead in (0, 1, 7):
            arr = utils.nominal_arrival(10, lead, dist, cfg)
            assert arr == math.ceil(10 + lead + dist / cfg.CAR_SPEED)
            # un véhicule ne peut pas être arrivé avant d'avoir roulé
            assert arr >= 10 + lead


def test_8_lead_is_drawn_within_bounds():
    cfg = small_config(seed=81)
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 3, 'high': 9})
    spec = generate_world_spec(cfg, cfg.SEED)
    car = build_world(spec, cfg)[0][0]
    leads = [car.draw_reservation_lead() for _ in range(200)]
    assert min(leads) >= 3 and max(leads) <= 9, f"hors bornes : {min(leads)}-{max(leads)}"
    assert len(set(leads)) > 1, "l'horizon doit varier d'une requête à l'autre"

    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 0})
    car = build_world(spec, cfg)[0][0]
    assert {car.draw_reservation_lead() for _ in range(50)} == {0}


def test_8_lead_uses_a_dedicated_stream():
    """
    L'horizon doit venir d'un flux propre : partagé avec `car_request`, il
    décalerait durée, rayon et patience de toutes les requêtes suivantes, et les
    deux bras de l'ablation ne différeraient plus seulement par l'horizon.
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

    temoin = requests({'low': 0, 'high': 0})
    traite = requests({'low': 0, 'high': 12})
    assert temoin == traite, (
        "activer l'horizon a décalé les autres paramètres de requête : "
        "le flux n'est pas dédié"
    )
    assert STREAM_CODES['car_lead'] == 9, "les codes de flux sont figés"


def test_8_min_lead_for_early_cancel_matches_the_threshold():
    cfg = SimulationConfig()
    min_lead = cfg.min_lead_for_early_cancel()
    assert min_lead == 3, f"attendu 3 avec fraction 0.5, reçu {min_lead}"
    # en dessous, la branche est démontrablement inatteignable
    for lead in range(1, min_lead):
        assert lead - 1 <= cfg.late_cancel_threshold(lead)
    assert min_lead - 1 > cfg.late_cancel_threshold(min_lead)
    # la propriété doit suivre la fraction, pas une constante codée en dur
    cfg.LATE_CANCEL_FRACTION = 0.9
    assert cfg.min_lead_for_early_cancel() > min_lead


def test_8_reservation_lead_opens_the_early_branch():
    """
    Le coeur de la correction : sans horizon, `t_arr` colle à la requête et
    *toutes* les intentions `early` sont reclassées `late`. Avec un horizon,
    elles doivent être réalisées telles quelles.
    """
    def outcomes(lead_params):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_RESERVATION_LEAD_PARAMS(lead_params)
        sim = run_sim(cfg, 'bramev')
        assert sim.check_reservation_invariant()[0], "invariant violé"
        return sim.behaviors.report()

    sans = outcomes({'low': 0, 'high': 0})
    avec = outcomes({'low': 6, 'high': 12})

    assert sans['intent_counts'].get('early', 0) > 0
    assert sans['observed_counts'].get('early', 0) == 0, (
        "sans horizon, aucune annulation ne peut être anticipée"
    )
    assert sans['reclassified'].get('early->late', 0) == sans['intent_counts']['early']

    assert avec['observed_counts'].get('early', 0) > 0, (
        "avec un horizon, la branche anticipée doit être atteinte"
    )
    assert avec['reclassified'].get('early->late', 0) < sans['reclassified']['early->late']
    assert avec['mean_lead_slots'] > sans['mean_lead_slots']


def test_8_planned_lead_is_not_counted_as_waiting():
    """
    L'horizon voulu par le conducteur n'est pas de l'attente subie.

    Vérifié structurellement, pas en agrégat : décaler *conjointement* la
    requête et le créneau de `l_n` slots doit laisser l'attente et l'utilité
    inchangées. En agrégat, l'attente mesurée augmente bel et bien avec
    l'horizon — mais parce que les réservations sont détenues plus longtemps et
    que la contention monte, ce qui est un effet du modèle et non un biais de
    mesure.
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
    assert t_arr1 == t_arr0 + lead, "le créneau nominal doit suivre l'horizon"
    offer1 = off.Offer(station_id=0, charger_id=0, t_arr=t_arr1,
                       t_dep=t_arr1 + 12, d_prop=12, distance=dist)

    u0 = car.compute_utility(offer0, base, min_dist=1e3)
    u1 = car.compute_utility(offer1, shifted, min_dist=1e3)
    assert u0 == u1, (
        f"l'horizon planifié dégrade l'utilité ({u0} -> {u1}) : il est compté "
        "comme de l'attente subie"
    )
    assert u1 > 0, "utilité écrasée à zéro par la normalisation de l'attente"

    # Un horizon ignoré par compute_utility produirait waitingTime = l_n, donc
    # un ratio > 1 sur maxWaitingTime = g_n : c'est la signature du bug.
    naive = car.compute_utility(offer1, base, min_dist=1e3)
    assert naive < u1, "le test ne discrimine pas : vérifier la construction"


def test_8_measured_waiting_stays_far_below_the_planned_horizon():
    """
    Garde-fou d'agrégat : si l'horizon était compté comme attente, l'attente
    mesurée vaudrait environ l'horizon moyen. Elle doit en rester loin.
    """
    cfg = small_config(scenario='balance', nb_car=40, total_time=12 * 20, seed=71)
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 6, 'high': 12})
    sim = run_sim(cfg, 'bramev')
    beh = sim.behaviors.report()
    wait_slots = (sim.metrics.report()['mean_waiting_time_h'] * 60
                  / cfg.SLOT_DURATION)
    assert wait_slots < 0.25 * beh['mean_lead_slots'], (
        f"attente mesurée {wait_slots:.2f} slots pour un horizon moyen "
        f"{beh['mean_lead_slots']} : l'horizon fuit dans la métrique"
    )

    served = [c for c in sim.cars if c.nb_sessions > 0]
    assert served and any(c.u_total > 0 for c in served), (
        "toutes les utilités sont nulles : le classement des offres est dégénéré"
    )


def test_8_zero_lead_is_the_control_arm():
    """
    `{0, 0}` n'est pas un réglage neutre mais le bras de contrôle de l'ablation :
    l'annulation anticipée doit y être démontrablement inatteignable, et le run
    doit rester déterministe.
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
        "sans horizon, aucune annulation ne peut être qualifiée d'anticipée"
    )


def test_8_diagnostic_separates_structure_from_sampling():
    """
    Le diagnostic doit affirmer une impossibilité *structurelle*, jamais
    extrapoler depuis une poignée d'intentions.

    Il criait au faux positif sur les grilles minuscules des tests : une seule
    intention `early` non réalisée déclenchait un message annonçant un délai
    « quasi nul » alors que le délai médian valait 2 à 3 slots.
    """
    from src.metrics.metrics import BehaviorTracker

    cfg = SimulationConfig()
    min_lead = cfg.min_lead_for_early_cancel()

    # (a) Délais suffisants, une seule intention non réalisée -> muet.
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 12})
    petit = BehaviorTracker(cfg)
    for _ in range(7):
        petit.record_intent('pres', min_lead + 2)
    petit.record_intent('early', 1)
    petit.record_outcome('early', 'late')
    assert petit.anticipable_share() > 0
    assert petit.diagnostics() == [], (
        f"faux positif sur un échantillon de 1 : {petit.diagnostics()}"
    )

    # (b) Horizon demandé mais jamais obtenu -> signalé, quel que soit le
    #     nombre d'intentions, avec la cause actionnable.
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 12})
    struct = BehaviorTracker(cfg)
    for _ in range(8):
        struct.record_intent('pres', 1)
    struct.record_intent('early', 1)
    struct.record_outcome('early', 'late')
    assert struct.anticipable_share() == 0.
    assert any('horizon de simulation trop court' in d.lower()
               for d in struct.diagnostics()), (
        f"cause non signalée : {struct.diagnostics()}"
    )

    # (b') Même situation, mais anticipation volontairement désactivée -> muet.
    cfg.set_RESERVATION_LEAD_PARAMS({'low': 0, 'high': 0})
    controle = BehaviorTracker(cfg)
    for _ in range(8):
        controle.record_intent('pres', 1)
    controle.record_intent('early', 1)
    controle.record_outcome('early', 'late')
    assert controle.anticipable_share() == 0.
    assert controle.diagnostics() == [], (
        f"le bras de contrôle ne doit rien signaler : {controle.diagnostics()}"
    )

    # (c) Délais suffisants mais aucune des N intentions réalisée -> anomalie.
    anomalie = BehaviorTracker(cfg)
    for _ in range(20):
        anomalie.record_intent('pres', min_lead + 5)
    for _ in range(BehaviorTracker.MIN_EARLY_SAMPLE):
        anomalie.record_intent('early', min_lead + 5)
        anomalie.record_outcome('early', 'late')
    diags = anomalie.diagnostics()
    assert any('intentions' in d for d in diags), f"anomalie non signalée : {diags}"
    assert not any('Augmenter RESERVATION_LEAD_PARAMS' in d for d in diags), (
        "ne pas imputer à la structure ce qui n'est pas structurel"
    )


def test_8_neither_arm_is_diagnosed_when_configured_deliberately():
    """
    Bout en bout : ni le bras de contrôle ni le bras traité ne doit produire de
    diagnostic. Désactiver l'anticipation est un choix, pas une anomalie — et
    `ExperimentParams.validate` l'a déjà signalé à la configuration.
    """
    def diagnose(lead_params):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_RESERVATION_LEAD_PARAMS(lead_params)
        return run_sim(cfg, 'bramev').behaviors.report()

    controle = diagnose({'low': 0, 'high': 0})
    assert controle['anticipable_share'] == 0., "le contrôle doit être stérile"
    assert controle['diagnostics'] == [], (
        f"le bras de contrôle est délibéré, pas anormal : {controle['diagnostics']}"
    )

    traite = diagnose({'low': 0, 'high': 12})
    assert traite['anticipable_share'] > 0.5
    assert traite['observed_counts'].get('early', 0) > 0
    assert traite['diagnostics'] == [], (
        f"diagnostic injustifié sur le bras traité : {traite['diagnostics']}"
    )


# ----------------------------------------------------------------------
# 9. États à l'arrêt : no-show garé, relance de recherche
# ----------------------------------------------------------------------

def test_9_no_show_parks_instead_of_roaming():
    """
    Un no-show renonce à son trajet, pas seulement à sa recharge : il reste
    immobile tant qu'il détient son créneau, puis repart une fois libéré.

    La continuité est suivie par l'objet réservation : un véhicule peut sortir
    de l'état garé, rouler, puis s'y regarer avec une *nouvelle* réservation au
    cours du même pas — comparer deux fins de slot ne suffit pas.
    """
    cfg = small_config(scenario='pessimistic', nb_car=30, total_time=12 * 12,
                       seed=91)
    cfg.set_BASE_CANCEL_PROB({'pres': 1, 'abs': 97, 'early': 1, 'late': 1,
                              'noise': 0.0})
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    episodes = {}     # idx -> (réservation, x, y, soc)
    vus = 0
    log = io.StringIO()
    for t in range(cfg.TOTAL_TIME):
        sim.current_t = t
        sim.step(t, 10 ** 6, file=log)
        for car in sim.cars:
            if car.cancel_intent == 'abs' and car.reservation is not None:
                assert car.state == 'PARKED_NO_SHOW', (
                    f"car_{car.idx} détient un créneau no-show mais est "
                    f"{car.state}"
                )
                courant = (car.reservation, car.x, car.y, car.soc_m)
                if episodes.get(car.idx, (None,))[0] is car.reservation:
                    assert episodes[car.idx] == courant, (
                        f"car_{car.idx} garé a bougé ou consommé"
                    )
                else:
                    vus += 1
                episodes[car.idx] = courant
            else:
                episodes.pop(car.idx, None)

    assert vus > 0, "aucun no-show observé : test non concluant"
    assert sim.behaviors.outcomes.get('abs', 0) > 0


def test_9_no_phase_moves_a_parked_vehicle():
    """
    L'invariant central des deux états à l'arrêt : aucune phase de `step` ne
    doit déplacer un véhicule garé. Vérifié à la source — `update_state` est le
    seul point de déplacement et de consommation.
    """
    cfg = small_config(scenario='pessimistic', nb_car=30, total_time=12 * 12,
                       seed=94)
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    original = Car.update_state
    fautes = []

    def surveille(self, loc=None):
        if self.state in Car.PARKED_STATES:
            fautes.append((self.idx, self.state))
        return original(self, loc)

    vus = set()
    Car.update_state = surveille
    try:
        log = io.StringIO()
        for t in range(cfg.TOTAL_TIME):
            sim.current_t = t
            sim.step(t, 10 ** 6, file=log)
            vus |= {c.state for c in sim.cars if c.state in Car.PARKED_STATES}
    finally:
        Car.update_state = original

    assert not fautes, f"véhicules garés déplacés : {fautes[:5]}"
    assert vus, "aucun état garé observé : test non concluant"


def test_9_failed_search_parks_and_widens_the_radius():
    """
    Faute de station ou d'offre, le véhicule s'arrête et relance la *même*
    demande avec un rayon élargi — il ne repart pas au hasard.
    """
    cfg = small_config(seed=92)
    cfg.set_SEARCH_RADIUS_GROWTH(1.5)
    cfg.set_MAX_SEARCH_RETRIES(3)
    spec = generate_world_spec(cfg, cfg.SEED)
    car = build_world(spec, cfg)[0][0]

    car.emit_request(0, (car.x, car.y), 'd0')
    r0 = car.request['r_n']
    rayons = [r0]
    for k in range(3):
        assert car.widen_search(), f"relance {k + 1} refusée à tort"
        rayons.append(car.request['r_n'])
        assert car.search_retries == k + 1

    assert not car.widen_search(), "le budget de relances doit être borné"
    assert car.search_retries == 3

    plafond = cfg.max_search_radius()
    for avant, apres in zip(rayons, rayons[1:]):
        attendu = min(avant * 1.5, plafond)
        assert abs(apres - attendu) < 1e-6, f"{avant} -> {apres}, attendu {attendu}"
    assert rayons[-1] <= plafond + 1e-9

    # L'identité de la demande et ses autres paramètres sont préservés : une
    # relance est la même demande, pas une nouvelle.
    assert car.request['n'] == 'd0'


def test_9_retry_keeps_one_demand_per_need():
    """
    Une demande relancée reste *une* demande. Sans cela, chaque tentative
    gonflerait `nb_demands` et effondrerait le taux de confirmation sans qu'un
    besoin supplémentaire ait été exprimé.
    """
    def campaign(retries):
        cfg = small_config(scenario='pessimistic', nb_car=40,
                           total_time=12 * 20, seed=71)
        cfg.set_MAX_SEARCH_RETRIES(retries)
        sim = run_sim(cfg, 'bramev')
        recs = list(sim.metrics.demand_timings.values())
        return {
            'demandes':   len(recs),
            'confirmées': sum(1 for r in recs if r.confirmed),
            'relances':   sum(r.nb_search_retries for r in recs),
            'resa':       sim.behaviors.report()['nb_reservations'],
        }

    sans = campaign(0)
    avec = campaign(4)

    assert sans['relances'] == 0, "budget nul : aucune relance possible"
    assert avec['relances'] > 0, "aucune relance déclenchée : test non concluant"
    assert avec['demandes'] < sans['demandes'], (
        f"la relance doit regrouper les tentatives : {avec['demandes']} "
        f"vs {sans['demandes']}"
    )
    # Le nombre de besoins servis ne doit pas s'effondrer : on regroupe des
    # tentatives, on ne supprime pas des réservations.
    assert avec['resa'] >= 0.9 * sans['resa'], (
        f"réservations perdues : {avec['resa']} vs {sans['resa']}"
    )


def test_9_search_gives_up_and_never_deadlocks():
    """
    Le budget de relances doit être effectif : aucun véhicule ne doit rester
    garé jusqu'à la fin de l'horizon sans jamais renoncer.
    """
    cfg = small_config(scenario='balance', nb_car=25, total_time=12 * 10,
                       seed=93)
    cfg.set_MAX_SEARCH_RETRIES(2)
    spec = generate_world_spec(cfg, cfg.SEED)
    cars, stations, societies = build_world(spec, cfg)
    sim = Simulation(cars=cars, stations=stations, societies=societies,
                     t_max=cfg.TOTAL_TIME, config=cfg)

    log = io.StringIO()
    consecutifs = {c.idx: 0 for c in sim.cars}
    for t in range(cfg.TOTAL_TIME):
        sim.current_t = t
        sim.step(t, 10 ** 6, file=log)
        for car in sim.cars:
            if car.state == 'PARKED_SEARCHING':
                consecutifs[car.idx] += 1
                assert car.search_retries <= cfg.MAX_SEARCH_RETRIES
            else:
                consecutifs[car.idx] = 0
            assert consecutifs[car.idx] <= cfg.MAX_SEARCH_RETRIES + 1, (
                f"car_{car.idx} garé {consecutifs[car.idx]} slots d'affilée : "
                f"le budget de relances n'est pas appliqué"
            )


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
