"""
simulation.py — Boucle principale avec collecte des métriques

Une seule classe couvre les deux méthodes comparées ; elles ne diffèrent que par
trois interrupteurs (cf. `Simulation.MODES`) :

    broadcast            la requête part vers toutes les stations éligibles
                         (BRAM-EV) ou vers la plus proche seulement (Greedy)
    use_reputation       les stations mettent à jour le score comportemental
    collective_learning  les sociétés propagent l'alpha de leur meilleure station

Le reste du protocole (émission, PLI, confirmation, annulations, métriques) est
partagé : un correctif profite ainsi aux deux méthodes, et la comparaison ne
peut plus diverger par recopie de code.

Ordre d'un slot
---------------
1. décisions d'annulation (début de slot, avant tout déplacement)
2. déplacements (vers station, puis libres)
3. détection des pannes
4. émission des requêtes
5. optimisation PLI par station
6. sélection puis confirmation sécurisée
7. recharge active
8. apprentissage collectif
"""

import math
import time
import numpy as np
from loguru import logger

import src.experiments.config as cfg
from src.metrics.metrics import MetricsCollector, BreakdownTracker, BehaviorTracker


class Simulation:

    MODES = {
        'bramev': {'broadcast': True,  'use_reputation': True,  'collective_learning': True},
        'greedy': {'broadcast': False, 'use_reputation': False, 'collective_learning': False},
    }

    def __init__(self, cars, stations, societies, t_max, config: cfg.SimulationConfig,
                 mode: str = 'bramev'):
        if mode not in self.MODES:
            raise ValueError(
                f"Mode inconnu : {mode!r}. Attendu parmi {sorted(self.MODES)}"
            )
        self.mode      = mode
        flags          = self.MODES[mode]
        self.broadcast           = flags['broadcast']
        self.use_reputation      = flags['use_reputation']
        self.collective_learning = flags['collective_learning']

        self.t_max     = t_max
        self.current_t = 0
        self.cars      = cars
        self.stations  = stations
        self.societies = societies
        self.config    = config
        self.nb_demands = 0

        # Index O(1) : `next(...)` sur toute la liste à chaque accès était le
        # point chaud de la boucle pour 250 véhicules × 40 stations.
        self._car_by_idx     = {c.idx: c for c in cars}
        self._station_by_id  = {s.m: s for s in stations}

        # La fenêtre pygame n'est ouverte que si la visualisation est demandée :
        # indispensable pour exécuter la grille d'expériences sans affichage.
        self.viz = None
        if getattr(config, 'VISUALIZE', False):
            from src.env.visualizer import Visualizer
            self.viz = Visualizer(config)

        self._driving_to_station = {}
        self.metrics = MetricsCollector(cars, stations, config)

        self.breakdowns = BreakdownTracker()
        self.behaviors  = BehaviorTracker()
        self._broken_cars = set()   # car.idx des voitures actuellement en panne

    # ------------------------------------------------------------------
    def run(self, file, print_metrics=True):
        for t in range(self.t_max):
            self.current_t = t
            self.step(t, self.config.log_iter, file=file)
        self._finalize(file)
        print(f"\n\n=== Simulation terminée ({self.t_max} slots) ===", file=file)
        if print_metrics:
            self.metrics.print_report()
            self.breakdowns.print_report()
            self.behaviors.print_report(self.config.BASE_CANCEL_PROB)
    # ------------------------------------------------------------------

    def step(self, t_c: int, log_iter: int, file):

        str_log_tmp = f'\n--------------------------------------------- INSTANT {t_c}/{self.config.TOTAL_TIME} ' + \
            '---------------------------------------------\n'
        file.write(str_log_tmp)
        if (((t_c + 1) % log_iter) == 0) or ((t_c + 1) == self.config.TOTAL_TIME):
            logger.info(f'INSTANT {t_c + 1}/{self.config.TOTAL_TIME}')

        # 1. Annulations — décidées en début de slot, avant tout déplacement.
        #    (auparavant en fin de slot : un véhicule devant annuler tardivement
        #     avait déjà atteint la station et était compté comme présent)
        self._process_cancellations(t_c, file=file)

        # 2.a Déplacement vers station
        arrived = []
        for car_idx, target_station in list(self._driving_to_station.items()):
            car = self._get_car(car_idx)
            dist = self._get_distance(car, target_station)
            print(f'\ncar_{car.idx} (soc: {car.soc_m:.2f} -> {(car.soc_m / car.autonomy) * 100:.2f}km) '
                  f'{car.state} station_{target_station.m} REMAINING DISTANCE {dist * 1e-3:.2f}km', file=file)
            if car.update_state(target_station.loc):
                arrived.append(car_idx)
                print(f'\ncar_{car.idx} ARRIVED station_{target_station.m}', file=file)
        for car_idx in arrived:
            del self._driving_to_station[car_idx]

        # 2.b Déplacement libre
        for car in self.cars:
            if car.state == 'DRIVING':
                car.update_state()

        # 3. Pannes & gestion
        self._step_breakdown_detection(t_c, file=file)

        # 4. Émission des requêtes
        demands   = {s.m: [] for s in self.stations}
        eligibles = {c.idx: None for c in self.cars}
        min_dists = {}

        for car in self.cars:

            # Véhicule déjà lié à une réservation
            if car.reservation is not None:
                continue

            if not car.needs_charging():
                continue

            # Identifiant de demande unique : (slot, véhicule). Auparavant
            # `t_c * len(cars)`, identique pour tous les véhicules d'un même
            # slot — les enregistrements de latence s'écrasaient mutuellement.
            id_demand = self._demand_id(t_c, car.idx)

            print(f'\ncar_{car.idx} NEED CHARGING (soc:{car.soc_m * 1e-3:.2f}km < {car.soc_threshold_m * 1e-3:.2f}km)', file=file)
            req = car.emit_request(t_c, (car.x, car.y), id_demand)
            print(f'\n-> REQUEST {req['n']}'
                  f' | DURATION: {req['d_n']} slots '
                  f'-> {req['d_n'] // self.config.NB_SLOTS_IN_ONE_HOUR}H '
                  f'{(req['d_n'] % self.config.NB_SLOTS_IN_ONE_HOUR) * self.config.SLOT_DURATION}min'
                  f' | RAY: {req['r_n']*1e-3:.2f}km'
                  f' | PATIENCE: {req['g_n']*5:.2f}min', file=file)
            car.set_state('REQUESTING')

            eligible, min_d, min_s = self._get_eligible_stations(
                req['loc'][0], req['loc'][1], req['r_n']
            )
            eligibles[car.idx] = eligible
            min_dists[car.idx] = min_d
            print(f'\n-> MIN_DIST = {min_d*1e-3:.2f}km, station {min_s.m if min_s else None}', file=file)
            print(f'\n-> {len(eligible)} ELIGIBLE STATION', file=file)

            # Stations effectivement contactées : toutes les éligibles (BRAM-EV)
            # ou la plus proche seulement (Greedy).
            targets = eligible if self.broadcast else ([min_s] if min_s else [])

            self.metrics.record_demand_emitted(
                id_demand, car_id=car.idx, slot=t_c,
                nb_stations_contacted=len(targets)
            )
            self.nb_demands += 1

            # --- fix: si rayon de recherche trop petit et pas d'eligible station,
            #     le véhicule continue de rouler
            if not targets:
                self.metrics.record_demand_selection(id_demand)
                self.metrics.record_demand_confirmation(id_demand, False, 0)
                car.set_state('DRIVING')
                continue

            car.update_schedule_requested(min_d)
            for s in targets:
                demands[s.m].append((car, req))

        # 5. Optimisation ILP par station
        car_offers = {car.idx: [] for car in self.cars}

        for s in self.stations:
            if not demands[s.m]:
                continue

            batch_id = f"t{t_c}-s{s.m}"
            timing_rec = self.metrics.record_station_processing_start(
                s.m, batch_id, nb_demands=len(demands[s.m]))
            offers = s.process_demands(demands[s.m], t_c)
            timing_rec.t_end = time.perf_counter()

            for c, offer in offers:
                car_offers[c.idx].append(offer)
                self.metrics.record_demand_responded(c.request['n'], s.m)

        # 6. Sélection de l'offre puis confirmation sécurisée
        for car in self.cars:
            if car.state != 'REQUESTING':
                continue
            self._select_and_confirm(car, car_offers[car.idx],
                                     eligibles.get(car.idx) or [],
                                     min_dists.get(car.idx, 0.), t_c, file)

        # 7. Recharge active
        for car in self.cars:

            if car.state not in ('AT_STATION', 'CHARGING', 'WAITING') or car.reservation is None:
                continue
            target_station = self._get_station(car.reservation.station_id)
            _, charging_now = target_station.get_current_charger_and_slot(car.idx, t_c)

            if charging_now:
                car.set_state('CHARGING')
                car.charge_one_slot()

            elif car.state == 'AT_STATION':
                car.set_state('WAITING')

            if target_station.is_session_finished(car.idx, t_c + 1) or car.soc_m >= 0.99 * car.autonomy:
                target_station.nb_pres += 1
                if self.use_reputation:
                    target_station.update_car_score(car, 'pres', car.reservation.d_prop)
                self.behaviors.record_outcome(car.cancel_intent, 'pres')
                target_station.release_reservation(car.idx, car.reservation)
                car.set_state('DRIVING')
                car.clear_reservation()

        # 8. Mise à jour sociétés
        if (self.collective_learning and t_c > 0
                and t_c % self.config.SOCIETY_UPDATE_INTERVAL == 0):
            logger.info('-> UPDATE SOCIETY STRATEGY')
            for society in self.societies:
                society.update_strategy(file=file)

        # --- VISUALISATION
        if self.viz is not None:
            time.sleep(self.config.VIS_DELAY)
            self.viz.draw(self.cars, self.stations, t_c)

    # ------------------------------------------------------------------
    # Sélection & confirmation
    # ------------------------------------------------------------------

    def _select_and_confirm(self, car, offers, eligible, min_d, t_c, file):
        """
        Le véhicule classe les offres reçues et n'en confirme **qu'une**.

        Garanties :
          * une seule offre confirmée par demande ;
          * toutes les autres passent explicitement en EXPIRED — elles ne
            pourront plus être confirmées, même par erreur ;
          * la station revalide l'offre (TTL, contiguïté, créneaux réellement
            libres) avant d'écrire au calendrier ; en cas de refus, le véhicule
            se rabat sur l'offre suivante au lieu de renoncer.
        """
        demand_id = car.request['n']
        car.nb_offers_received += len(offers)
        car.nb_rejected += max(0, len(eligible) - len(offers))

        if not offers:
            self.metrics.record_demand_selection(demand_id)
            self.metrics.record_demand_confirmation(demand_id, False, 0)
            car.set_state('DRIVING')
            return

        ranked = car.rank_offers(offers, car.request, min_d)
        self.metrics.record_demand_selection(demand_id)

        chosen, chosen_u, attempts = None, None, 0
        for offer, u in ranked:
            station = self._get_station(offer.station_id)
            attempts += 1
            if station.confirm_reservation(car.idx, offer, t_c):
                chosen, chosen_u = offer, u
                break
            car.nb_confirm_failed += 1
            print(f'\ncar_{car.idx} CONFIRM REFUSED {offer.offer_id} '
                  f'({offer.reject_reason})', file=file)

        # Les offres non retenues expirent immédiatement.
        for offer, _ in ranked:
            if offer is not chosen:
                self._get_station(offer.station_id).expire_offer(offer)

        self.metrics.record_demand_confirmation(demand_id, chosen is not None, attempts)

        if chosen is None:
            car.set_state('DRIVING')
            return

        print(f'\n----- CHOOSEN OFFER:', file=file)
        chosen.display_offer(file=file)

        target_station = self._get_station(chosen.station_id)

        behavior = car.draw_behavior()
        car.set_behavior(behavior)
        car.set_reservation(chosen)
        car.cancel_intent    = behavior
        car.reservation_slot = car.request['t_n']
        car.reservation_lead = max(0, chosen.t_arr - car.request['t_n'])
        self.behaviors.record_intent(behavior, car.reservation_lead)

        if behavior == 'abs':
            # La réservation reste active dans le planning : le créneau est
            # perdu jusqu'à t_dep. Le véhicule ne se présentera jamais.
            car.set_state('DRIVING')
            return

        t_hat_arr     = math.ceil(car.request['t_n'] + chosen.distance / self.config.CAR_SPEED)
        waiting_slots = max(0, chosen.t_arr - t_hat_arr)
        self.metrics.record_offer_accepted(car, chosen, waiting_slots)

        car.nb_sessions += 1
        car.u_total += chosen_u
        car.update_car_speed()
        car.set_state('DRIVING_TO_STATION')
        self._driving_to_station[car.idx] = target_station

    # ------------------------------------------------------------------
    # Annulations
    # ------------------------------------------------------------------

    def _process_cancellations(self, t_c, file=None):
        """
        Réalise les intentions d'annulation tirées à la réservation.

        Correction apportée
        -------------------
        L'ancienne logique reclassait d'abord l'intention selon le temps
        restant, puis exigeait que la classe recalculée corresponde à
        l'intention. Comme le délai requête → arrivée est presque toujours
        inférieur à LATE_CANCEL_REF (24 slots = 2 h) alors que le trajet ne dure
        que quelques slots, tout était classé « tardif » et la branche
        « anticipé » était **inatteignable** : un véhicule d'intention `early`
        n'annulait jamais et finissait compté comme présent.

        Nouvelle logique : l'intention détermine *quand* l'annulation a lieu,
        et l'issue observée est déduite du temps réellement restant.

          early  → annule dès le slot suivant la réservation (au plus tôt)
          late   → annule quand il reste <= seuil slots avant l'arrivée prévue

        Le seuil est `config.late_cancel_threshold(lead)` : borné à la fois par
        LATE_CANCEL_REF et par une fraction du délai réel, de sorte que les deux
        régimes soient atteignables. L'issue observée peut donc différer de
        l'intention (une intention `early` sur une réservation à très court
        délai est réalisée comme `late`) : `BehaviorTracker` enregistre les deux.
        """

        # --------------------------------------------------
        # No-show (absence) : créneau occupé jusqu'à t_dep
        # --------------------------------------------------
        for car in self.cars:

            if car.cancel_intent != 'abs' or car.reservation is None:
                continue

            if t_c < car.reservation.t_dep:
                continue

            s = self._get_station(car.reservation.station_id)
            s.release_reservation(car.idx, car.reservation)
            s.nb_no_show += 1
            if self.use_reputation:
                s.update_car_score(car, 'abs', car.reservation.d_prop)
            self.behaviors.record_outcome(car.cancel_intent, 'abs')

            self._driving_to_station.pop(car.idx, None)
            car.clear_reservation()
            if car.state not in ('BREAKDOWN',):
                car.set_state('DRIVING')

        # --------------------------------------------------
        # Annulation anticipée / tardive
        # --------------------------------------------------
        for car in self.cars:
            if car.reservation is None or car.cancel_intent not in ('early', 'late'):
                continue
            # Une session déjà commencée ne s'annule plus.
            if car.state == 'CHARGING':
                continue

            offer = car.reservation
            threshold  = self.config.late_cancel_threshold(car.reservation_lead or 0)
            slots_left = offer.t_arr - t_c

            if car.cancel_intent == 'early':
                trigger = t_c > car.reservation_slot
            else:
                trigger = slots_left <= threshold

            if not trigger:
                continue

            observed = 'early' if slots_left > threshold else 'late'

            s = self._get_station(offer.station_id)
            s.release_reservation(car.idx, offer)
            if observed == 'early':
                s.nb_early_canc += 1
            else:
                s.nb_late_canc += 1
            if self.use_reputation:
                s.update_car_score(car, observed, offer.d_prop)
            self.behaviors.record_outcome(car.cancel_intent, observed)

            if file is not None:
                print(f'\ncar_{car.idx} CANCEL {observed} (intention={car.cancel_intent}, '
                      f'slots_left={slots_left}, seuil={threshold}) station_{s.m}', file=file)

            self._driving_to_station.pop(car.idx, None)
            car.clear_reservation()
            car.set_state('DRIVING')

    # ------------------------------------------------------------------
    # Clôture
    # ------------------------------------------------------------------

    def _finalize(self, file=None):
        """
        Résout les réservations encore ouvertes à la fin de l'horizon.

        Sans cette étape, toute réservation dont `t_dep` dépasse l'horizon reste
        comptée comme confirmée sans jamais recevoir d'issue : l'invariant
        `nb_reservations == somme des issues` était faux et les taux de no-show
        sous-estimés.
        """
        for car in self.cars:
            if car.reservation is None:
                continue
            s = self._get_station(car.reservation.station_id)
            if car.cancel_intent == 'abs':
                s.nb_no_show += 1
                self.behaviors.record_outcome('abs', 'abs')
            else:
                s.nb_unresolved += 1
                self.behaviors.record_outcome(car.cancel_intent, 'unresolved')
            s.release_reservation(car.idx, car.reservation)
            self._driving_to_station.pop(car.idx, None)
            car.clear_reservation()

        ok, errors = self.check_reservation_invariant()
        if not ok and file is not None:
            for err in errors:
                print(f'\n[INVARIANT] {err}', file=file)
        return ok

    def check_reservation_invariant(self):
        """
        Vérifie, station par station, que chaque réservation confirmée a reçu
        exactement une issue.
        """
        errors = []
        for s in self.stations:
            outcomes = (s.nb_pres + s.nb_no_show + s.nb_early_canc
                        + s.nb_late_canc + s.nb_breakdown_canc + s.nb_unresolved)
            if outcomes != s.nb_reservations:
                errors.append(
                    f"Station {s.m}: {s.nb_reservations} réservations != "
                    f"{outcomes} issues (pres={s.nb_pres}, abs={s.nb_no_show}, "
                    f"early={s.nb_early_canc}, late={s.nb_late_canc}, "
                    f"breakdown={s.nb_breakdown_canc}, unresolved={s.nb_unresolved})"
                )
        return (not errors), errors

    # ------------------------------------------------------------------
    # Résultats
    # ------------------------------------------------------------------

    def results(self) -> dict:
        """Résultat complet et sérialisable d'une exécution."""
        ok, errors = self.check_reservation_invariant()
        return {
            'mode':             self.mode,
            'seed':             self.config.SEED,
            'scenario':         self.config.SCENARIO_NAME,
            'config':           self.config.summary(),
            'nb_demands':       self.nb_demands,
            'metrics':          self.metrics.report(),
            'breakdowns':       {k: v for k, v in self.breakdowns.report().items()
                                 if k != 'records'},
            'behaviors':        self.behaviors.report(),
            'stations':         [s.outcomes_report() for s in self.stations],
            'invariant_ok':     ok,
            'invariant_errors': errors,
        }

    # ------------------------------------------------------------------
    def _demand_id(self, t_c, car_idx):
        """Identifiant unique d'une demande : un véhicule émet au plus une
        requête par slot (garde `car.reservation is None` + état DRIVING)."""
        return f"t{t_c:05d}-c{car_idx:05d}"

    def _get_car(self, idx):
        return self._car_by_idx[idx]

    def _get_station(self, sid):
        return self._station_by_id[sid]

    def _get_distance(self, car, station):
        xc, yc = car.x, car.y
        xs, ys = station.loc
        return np.sqrt((xc - xs)**2 + (yc - ys)**2)

    def _get_eligible_stations(self, x_n, y_n, r_n):
        """Retourne (stations éligibles, distance minimale, station la plus proche)."""
        eligible, min_dist = [], float('inf')
        min_stat = None
        for s in self.stations:
            x_m, y_m = s.loc
            d = np.sqrt((x_n - x_m)**2 + (y_n - y_m)**2)
            if d <= r_n:
                eligible.append(s)
                if d < min_dist:
                    min_dist = d
                    min_stat = s
        return eligible, (min_dist if eligible else 0.), min_stat

    def _step_breakdown_detection(self, t_c, file):

        """Phase 3 — détecte les nouvelles pannes et gère la reprise."""

        for car in self.cars:

            # ── Nouvelle panne ──────────────────────────────────────────
            if (car.state == 'BREAKDOWN'
                    and car.idx not in self._broken_cars):
                self._broken_cars.add(car.idx)
                self.breakdowns.record(car, t_c)
                print(f"\n  [PANNE] car_{car.idx} tombe en panne "
                    f"(soc={car.soc_m:.3f}) pos=({car.x:.0f},{car.y:.0f})", file=file)

                # Libère la réservation si elle existait
                if car.reservation is not None:
                    s = self._get_station(car.reservation.station_id)
                    s.release_reservation(car.idx, car.reservation)
                    s.nb_breakdown_canc += 1
                    if self.use_reputation:
                        s.update_car_score(car, 'abs', car.reservation.d_prop)
                    self.behaviors.record_outcome(car.cancel_intent, 'breakdown')
                    self._driving_to_station.pop(car.idx, None)
                    car.clear_reservation()

            # ── Reprise après recharge complète ─────────────────────────
            # Une voiture en BREAKDOWN peut redémarrer si son soc a remonté
            # (cas où elle a quand même atteint une station malgré soc~0)
            if (car.state == 'BREAKDOWN'
                    and car.soc_m > self.config.SOC_BREAKDOWN_THRESHOLD * 5):
                car.set_state('DRIVING')
                self._broken_cars.discard(car.idx)
                print(f"\n  [REPRISE] car_{car.idx} redémarre (soc={car.soc_m:.3f})", file=file)
