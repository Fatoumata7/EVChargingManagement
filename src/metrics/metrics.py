"""
metrics.py — Métriques d'évaluation de la simulation
"""

import time
import numpy as np
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


# ------------------------------------------------------------------
# Structures de données pour la collecte
# ------------------------------------------------------------------

@dataclass
class AcceptanceRecord:
    """Enregistre chaque acceptation d'offre (n, m)."""
    car_id:      int
    station_id:  int
    distance_km: float   # d_{n,m} au moment de l'acceptation
    waiting_time_h: float  # w_{n,m} estimé (en heures)


@dataclass
class DemandLatencyRecord:
    """
    Chronologie complète d'une demande, pour la mesure de latence.

    Tous les horodatages sont des `time.perf_counter()` (secondes, monotone).
    Une demande peut n'avoir aucune offre (`offer_receptions` vide) ou ne jamais
    être confirmée (`t_confirmation == 0`) : les agrégats ignorent alors la
    demande pour l'étape concernée, au lieu de compter un zéro.

    Étapes mesurées :
      t_emission     émission de la requête par le véhicule
      offer_receptions  (station_id, t) pour *chaque* offre reçue
      t_last_offer   réception de la dernière offre
      t_selection    fin du classement des offres par le véhicule
      t_confirmation confirmation acceptée par la station
    """
    demand_id:   str
    car_id:      int = -1
    slot:        int = -1
    t_emission:  float = 0.0
    offer_receptions: List[Tuple[int, float]] = field(default_factory=list)
    t_selection: float = 0.0
    t_confirmation: float = 0.0
    nb_stations_contacted: int = 0
    nb_confirm_attempts: int = 0
    #: Relances de recherche (rayon élargi) consommées pour cette demande.
    #: Une demande relancée reste *une* demande : c'est un seul besoin de
    #: recharge, dont on mesure la latence de bout en bout.
    nb_search_retries: int = 0
    confirmed: bool = False

    # ---- dérivés
    @property
    def nb_offers_received(self) -> int:
        return len(self.offer_receptions)

    @property
    def t_first_offer(self) -> float:
        return min((t for _, t in self.offer_receptions), default=0.0)

    @property
    def t_last_offer(self) -> float:
        return max((t for _, t in self.offer_receptions), default=0.0)

    def _ms(self, t_end: float, t_start: Optional[float] = None) -> Optional[float]:
        t_start = self.t_emission if t_start is None else t_start
        if t_end <= 0 or t_start <= 0 or t_end < t_start:
            return None
        return (t_end - t_start) * 1000.0

    @property
    def first_offer_ms(self) -> Optional[float]:
        """Émission → première offre reçue."""
        return self._ms(self.t_first_offer)

    @property
    def last_offer_ms(self) -> Optional[float]:
        """Émission → dernière offre reçue (temps de réponse du réseau)."""
        return self._ms(self.t_last_offer)

    @property
    def selection_ms(self) -> Optional[float]:
        """Dernière offre → décision du véhicule."""
        return self._ms(self.t_selection, self.t_last_offer)

    @property
    def confirmation_ms(self) -> Optional[float]:
        """Décision → confirmation acceptée par la station."""
        return self._ms(self.t_confirmation, self.t_selection)

    @property
    def total_ms(self) -> Optional[float]:
        """Émission → confirmation (latence de bout en bout)."""
        return self._ms(self.t_confirmation)

    # ---- Compatibilité : anciens noms utilisés par plots_metrics
    @property
    def t_response(self) -> float:
        """Alias historique : horodatage de la DERNIÈRE offre reçue."""
        return self.t_last_offer

    @property
    def response_time_ms(self) -> float:
        """Alias historique : émission → dernière offre reçue (0. si aucune)."""
        return self.last_offer_ms or 0.0

    @property
    def per_offer_ms(self) -> List[float]:
        """Émission → réception, offre par offre."""
        return [(t - self.t_emission) * 1000.0
                for _, t in self.offer_receptions if t > 0]

    def as_row(self) -> dict:
        return {
            'demand_id':       self.demand_id,
            'car_id':          self.car_id,
            'slot':            self.slot,
            'nb_stations':     self.nb_stations_contacted,
            'search_retries':  self.nb_search_retries,
            'nb_offers':       self.nb_offers_received,
            'confirmed':       self.confirmed,
            'confirm_attempts': self.nb_confirm_attempts,
            'first_offer_ms':  self.first_offer_ms,
            'last_offer_ms':   self.last_offer_ms,
            'selection_ms':    self.selection_ms,
            'confirmation_ms': self.confirmation_ms,
            'total_ms':        self.total_ms,
        }


# Conservé pour compatibilité avec l'ancien nom.
DemandTimingRecord = DemandLatencyRecord


@dataclass
class StationTimingRecord:
    """Enregistre le temps de traitement ILP par station."""
    station_id:   int
    demand_id:    str
    t_start:      float
    t_end:        float = 0.0
    nb_demands:   int = 0

    @property
    def processing_time_ms(self) -> float:
        return (self.t_end - self.t_start) * 1000.0


def _mean(values) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(float(np.mean(vals)), 3) if vals else None


def _pct(values, q) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(float(np.percentile(vals, q)), 3) if vals else None


# ------------------------------------------------------------------
# Collecteur central (à attacher à Simulation)
# ------------------------------------------------------------------

class MetricsCollector:

    def __init__(self, cars, stations, config):
        self.cars     = cars
        self.stations = stations
        self.config   = config

        # Pour User Request Satisfaction
        # schedule_demand[car_id] = np.array binaire (TOTAL_TIME,)  déjà dans car.schedule_requested
        # schedule_offer[car_id]  = np.array binaire (TOTAL_TIME,)
        self.schedule_offer: Dict[int, np.ndarray] = {
            c.idx: np.zeros(config.TOTAL_TIME, dtype=int)
            for c in cars
        }

        # Pour Station Demand
        # station_charging_log[station_id] = liste de (car_id, t_start, t_end, d_prop)
        self.station_charging_log: Dict[int, List[Tuple]] = {
            s.m: [] for s in stations
        }

        # Pour Mean Relative Travel Distance & Waiting Time
        self.acceptance_records: List[AcceptanceRecord] = []

        # Pour scalabilité / latence
        self.demand_timings: Dict[str, DemandLatencyRecord] = {}
        self.station_timings: List[StationTimingRecord]    = []

    # ------------------------------------------------------------------
    # Méthodes d'enregistrement (appelées depuis Simulation)
    # ------------------------------------------------------------------

    def record_offer_accepted(self, car, offer, waiting_time_slots: float):
        """
        Appelé quand un véhicule accepte une offre.
        waiting_time_slots : offer.t_arr - t_hat_arr (en slots)
        """
        # Planning offre
        t_s = min(offer.t_arr, self.config.TOTAL_TIME)
        t_e = min(offer.t_dep, self.config.TOTAL_TIME)
        self.schedule_offer[car.idx][t_s:t_e] = 1

        # Distance en km (grille en mètres)
        dist_km = offer.distance / 1000.0

        # Temps d'attente en heures
        wait_h = max(0., waiting_time_slots) * self.config.SLOT_DURATION / 60.0

        self.acceptance_records.append(AcceptanceRecord(
            car_id=car.idx,
            station_id=offer.station_id,
            distance_km=dist_km,
            waiting_time_h=wait_h
        ))

        # Log recharge station
        self.station_charging_log[offer.station_id].append(
            (car.idx, offer.t_arr, offer.t_dep, offer.d_prop)
        )

    # ---- Latence ------------------------------------------------------

    def record_demand_emitted(self, demand_id, car_id: int = -1, slot: int = -1,
                              nb_stations_contacted: int = 0):
        if demand_id in self.demand_timings:
            raise ValueError(
                f"Identifiant de demande déjà utilisé : {demand_id!r}. "
                "Les identifiants doivent être uniques pour que la latence soit "
                "mesurable demande par demande."
            )
        self.demand_timings[demand_id] = DemandLatencyRecord(
            demand_id=demand_id,
            car_id=car_id,
            slot=slot,
            t_emission=time.perf_counter(),
            nb_stations_contacted=nb_stations_contacted
        )
        return self.demand_timings[demand_id]

    def record_demand_responded(self, demand_id, station_id: int):
        """Réception d'une offre. Appelé une fois par offre, pas par demande."""
        rec = self.demand_timings.get(demand_id)
        if rec is not None:
            rec.offer_receptions.append((station_id, time.perf_counter()))

    def record_demand_retry(self, demand_id, nb_stations_contacted: int = 0):
        """
        Relance d'une demande avec un rayon élargi.

        La demande n'est pas recréée : on incrémente son compteur de relances et
        on retient le nombre de stations finalement contactées. `t_emission`
        reste celui de la première tentative, pour que la latence mesure le
        temps de satisfaction du besoin, relances comprises.
        """
        rec = self.demand_timings.get(demand_id)
        if rec is None:
            raise ValueError(
                f"Relance d'une demande inconnue : {demand_id!r}. Une relance "
                "doit conserver l'identifiant de la demande d'origine."
            )
        rec.nb_search_retries += 1
        rec.nb_stations_contacted = nb_stations_contacted
        return rec

    def record_demand_selection(self, demand_id):
        """Le véhicule a fini de classer les offres reçues."""
        rec = self.demand_timings.get(demand_id)
        if rec is not None:
            rec.t_selection = time.perf_counter()

    def record_demand_confirmation(self, demand_id, confirmed: bool,
                                   nb_attempts: int = 1):
        """Issue de la phase de confirmation auprès de la station."""
        rec = self.demand_timings.get(demand_id)
        if rec is not None:
            rec.nb_confirm_attempts = nb_attempts
            rec.confirmed = confirmed
            if confirmed:
                rec.t_confirmation = time.perf_counter()

    def record_station_processing_start(self, station_id: int, demand_id,
                                        nb_demands: int = 0) -> StationTimingRecord:
        rec = StationTimingRecord(
            station_id=station_id,
            demand_id=str(demand_id),
            t_start=time.perf_counter(),
            nb_demands=nb_demands
        )
        self.station_timings.append(rec)
        return rec

    # ------------------------------------------------------------------
    # 1. Station Demand
    # ------------------------------------------------------------------

    def station_demand(self) -> Dict[int, float]:
        """
        E_m = sum_{n in N_m} P_n * d_n
        P_n : puissance de recharge en kW (charging_power en km/slot → kW via conso)
        d_n : durée allouée en heures
        """
        car_power = {}  # car_id → puissance kW
        for car in self.cars:
            # charging_power en km/slot, consommation = 10 kWh/100 km
            kw = car.charging_power * \
                (self.config.ENERGY_CONSUMPTION['quantity_kW'] / \
                 (self.config.ENERGY_CONSUMPTION['distance_unit_m'] * 1e-3))  # kWh par slot → kW (slot = 5 min = 1/12 h)
            car_power[car.idx] = kw

        result = {}
        for s in self.stations:
            e_m = 0.0
            for (car_id, t_start, t_end, d_prop) in self.station_charging_log[s.m]:
                p_n = car_power.get(car_id, 0.)
                d_h = d_prop * self.config.SLOT_DURATION / 60.0  # slots → heures
                e_m += p_n * d_h
            result[s.m] = round(e_m, 3)
        return result

    # ------------------------------------------------------------------
    # 2. User Request Satisfaction
    # ------------------------------------------------------------------

    def user_request_satisfaction(self) -> Dict[str, float]:
        """
        Retourne la satisfaction exacte moyenne et la satisfaction des besoins moyenne.
        """
        exact_list, needs_list = [], []

        for car in self.cars:
            s_demand = car.schedule_requested          # np.array (T,)
            s_offer  = self.schedule_offer[car.idx]    # np.array (T,)

            demand_slots = int(np.sum(s_demand))
            if demand_slots == 0:
                continue  # véhicule n'a jamais émis de demande

            offer_slots = int(np.sum(s_offer))
            inter_slots = int(np.sum((s_demand == 1) & (s_offer == 1)))

            exact = inter_slots / demand_slots
            needs = 1.0 - (demand_slots - offer_slots) / demand_slots
            needs = max(0., min(1., needs))  # clip [0,1]

            exact_list.append(exact)
            needs_list.append(needs)

        return {
            'exact_satisfaction':  round(np.mean(exact_list),  4) if exact_list  else 0.,
            'needs_satisfaction':  round(np.mean(needs_list),  4) if needs_list  else 0.,
            'nb_cars_evaluated':   len(exact_list)
        }

    # ------------------------------------------------------------------
    # 3. Mean Relative Travel Distance
    # ------------------------------------------------------------------

    def mean_relative_travel_distance(self) -> float:
        """
        Distance moyenne (km) parcourue par les véhicules pour rejoindre une station.
        """
        if not self.acceptance_records:
            return 0.
        distances = [r.distance_km for r in self.acceptance_records]
        return round(float(np.mean(distances)), 4)

    # ------------------------------------------------------------------
    # 4. Mean Relative Waiting Time
    # ------------------------------------------------------------------

    def mean_relative_waiting_time(self) -> float:
        """
        Temps d'attente moyen (heures) estimé à la station.
        """
        if not self.acceptance_records:
            return 0.
        waits = [r.waiting_time_h for r in self.acceptance_records]
        return round(float(np.mean(waits)), 4)

    # ------------------------------------------------------------------
    # 5. Scalabilité — latence
    # ------------------------------------------------------------------

    def mean_response_time_ms(self) -> float:
        """
        Temps moyen entre l'émission d'une demande et la réception de la
        DERNIÈRE offre. Ne porte que sur les demandes ayant reçu au moins une
        offre (une demande sans réponse n'a pas de temps de réponse).
        """
        value = _mean(r.last_offer_ms for r in self.demand_timings.values())
        return value if value is not None else 0.

    def latency_report(self) -> dict:
        """
        Décomposition complète de la latence, étape par étape.

        Chaque étape est agrégée indépendamment sur les demandes pour lesquelles
        elle est définie ; `nb_*` indique l'effectif correspondant.
        """
        recs = list(self.demand_timings.values())
        answered = [r for r in recs if r.nb_offers_received > 0]
        confirmed = [r for r in recs if r.confirmed]

        per_offer = [ms for r in recs for ms in r.per_offer_ms]

        return {
            'nb_demands':            len(recs),
            'nb_demands_answered':   len(answered),
            'nb_demands_confirmed':  len(confirmed),
            'nb_offers_received':    sum(r.nb_offers_received for r in recs),
            'answer_rate':           round(len(answered) / len(recs), 4) if recs else 0.,
            'confirm_rate':          round(len(confirmed) / len(recs), 4) if recs else 0.,
            'mean_offers_per_demand': round(float(np.mean(
                [r.nb_offers_received for r in recs])), 3) if recs else 0.,
            # émission → offre, toutes offres confondues
            'offer_ms_mean':         _mean(per_offer),
            'offer_ms_p95':          _pct(per_offer, 95),
            # émission → première / dernière offre
            'first_offer_ms_mean':   _mean(r.first_offer_ms for r in recs),
            'last_offer_ms_mean':    _mean(r.last_offer_ms for r in recs),
            'last_offer_ms_p95':     _pct([r.last_offer_ms for r in recs], 95),
            # dernière offre → sélection
            'selection_ms_mean':     _mean(r.selection_ms for r in recs),
            # sélection → confirmation
            'confirmation_ms_mean':  _mean(r.confirmation_ms for r in recs),
            # bout en bout
            'total_ms_mean':         _mean(r.total_ms for r in recs),
            'total_ms_p95':          _pct([r.total_ms for r in recs], 95),
            'mean_confirm_attempts': round(float(np.mean(
                [r.nb_confirm_attempts for r in answered])), 3) if answered else None,
        }

    def latency_rows(self) -> List[dict]:
        """Détail par demande (export CSV / analyse fine)."""
        return [r.as_row() for r in self.demand_timings.values()]

    # ------------------------------------------------------------------
    # 6. Scalabilité — Temps de traitement moyen par station (ms)
    # ------------------------------------------------------------------

    def mean_processing_time_per_station(self) -> Dict[int, float]:
        buckets = defaultdict(list)
        for rec in self.station_timings:
            if rec.t_end > 0:
                buckets[rec.station_id].append(rec.processing_time_ms)
        return {
            sid: round(float(np.mean(times)), 3)
            for sid, times in buckets.items()
        }

    # ------------------------------------------------------------------
    # Rapport complet
    # ------------------------------------------------------------------

    def report(self) -> dict:
        sat   = self.user_request_satisfaction()
        proc  = self.mean_processing_time_per_station()

        return {
            'station_demand_kWh':           self.station_demand(),
            'user_request_satisfaction':    sat,
            'mean_travel_distance_km':      self.mean_relative_travel_distance(),
            'mean_waiting_time_h':          self.mean_relative_waiting_time(),
            'mean_response_time_ms':        self.mean_response_time_ms(),
            'mean_processing_time_ms':      proc,
            'latency':                      self.latency_report(),
        }

    def print_report(self):
        r = self.report()
        print("\n========== MÉTRIQUES ==========")

        print("\n--- Station Demand (kWh) ---")
        for sid, e in r['station_demand_kWh'].items():
            print(f"  Station {sid}: {e:.2f} kWh")

        print("\n--- User Request Satisfaction ---")
        sat = r['user_request_satisfaction']
        print(f"  Satisfaction exacte  : {sat['exact_satisfaction']*100:.1f}%")
        print(f"  Satisfaction besoins : {sat['needs_satisfaction']*100:.1f}%")
        print(f"  Véhicules évalués    : {sat['nb_cars_evaluated']}")

        print("\n--- Travel & Waiting ---")
        print(f"  Distance moy. : {r['mean_travel_distance_km']:.3f} km")
        print(f"  Attente moy.  : {r['mean_waiting_time_h']*60:.1f} min")

        lat = r['latency']
        print("\n--- Scalabilité / latence ---")
        print(f"  Demandes                 : {lat['nb_demands']} "
              f"(avec offre : {lat['nb_demands_answered']}, "
              f"confirmées : {lat['nb_demands_confirmed']})")
        print(f"  Offres reçues / demande  : {lat['mean_offers_per_demand']:.2f}")
        print(f"  Émission → 1re offre     : {_fmt(lat['first_offer_ms_mean'])}")
        print(f"  Émission → dern. offre   : {_fmt(lat['last_offer_ms_mean'])}"
              f"  (p95 {_fmt(lat['last_offer_ms_p95'])})")
        print(f"  Dern. offre → sélection  : {_fmt(lat['selection_ms_mean'])}")
        print(f"  Sélection → confirmation : {_fmt(lat['confirmation_ms_mean'])}")
        print(f"  Bout en bout             : {_fmt(lat['total_ms_mean'])}"
              f"  (p95 {_fmt(lat['total_ms_p95'])})")
        print("  Temps traitement / station :")
        for sid, ms in r['mean_processing_time_ms'].items():
            print(f"    Station {sid}: {ms:.2f} ms")
        print("================================")


def _fmt(value):
    return "n/a" if value is None else f"{value:.2f} ms"


# ------------------------------------------------------------------
# Métrique panne sèche (à appeler depuis Simulation.step)
# ------------------------------------------------------------------

class BreakdownTracker:
    """
    Suivi des pannes sèches.
    """

    def __init__(self):
        self.records = []

    def record(self, car, slot: int):
        self.records.append({
            'car_id':   car.idx,
            'slot':     slot,
            'soc_m':    float(car.soc_m),
            'x':        float(car.x),
            'y':        float(car.y),
        })

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def nb_unique_cars(self) -> int:
        return len({r['car_id'] for r in self.records})

    def report(self) -> dict:
        return {
            'nb_breakdowns':  self.count,
            'nb_unique_cars': self.nb_unique_cars,
            'records':        self.records,
        }

    def print_report(self):
        print("\n--- Pannes sèches ---")
        print(f"  Nombre de pannes      : {self.count}")
        print(f"  Véhicules concernés   : {self.nb_unique_cars}")


# ------------------------------------------------------------------
# Comportements : intention tirée vs. issue réellement observée
# ------------------------------------------------------------------

class BehaviorTracker:
    """
    Compare l'intention tirée à la réservation et l'issue réellement observée.

    Motivation : l'intention (`theta`) et l'issue peuvent différer légitimement.
    Une intention « annulation anticipée » sur une réservation prise 3 slots
    avant l'arrivée ne *peut pas* être anticipée : elle est réalisée comme une
    annulation tardive. Sans ce suivi, l'écart entre les probabilités du scénario
    et les taux mesurés était invisible — et attribué à tort au modèle.

    Issues possibles
    ----------------
    pres       le véhicule s'est présenté et a chargé
    abs        no-show : créneau occupé jusqu'à t_dep, véhicule jamais venu
    early      annulation > seuil avant l'arrivée prévue (créneau rendu à temps)
    late       annulation <= seuil avant l'arrivée prévue
    breakdown  panne sèche avant la session (réservation libérée)
    unresolved réservation encore ouverte à la fin de l'horizon
    """

    OUTCOMES = ('pres', 'abs', 'early', 'late', 'breakdown', 'unresolved')

    #: En dessous de ce nombre d'intentions `early`, l'absence d'annulation
    #: anticipée observée n'est pas interprétable : c'est un échantillon, pas un
    #: symptôme. Le diagnostic reste muet.
    MIN_EARLY_SAMPLE = 5

    def __init__(self, config=None):
        self.intents = Counter()      # comportement tiré à la réservation
        self.outcomes = Counter()     # issue observée
        self.pairs = Counter()        # (intention, issue)
        self.reclassified = Counter() # intentions réalisées autrement
        self.leads = []               # délai requête → arrivée (slots)
        # Sert aux diagnostics : le délai minimal rendant l'annulation
        # anticipée atteignable se déduit de LATE_CANCEL_FRACTION, il ne peut
        # pas être codé en dur ici.
        self.config = config

    def record_intent(self, intent: str, lead: int | None = None):
        self.intents[intent] += 1
        if lead is not None:
            self.leads.append(int(lead))

    def record_outcome(self, intent: str | None, outcome: str):
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Issue inconnue : {outcome!r}")
        self.outcomes[outcome] += 1
        self.pairs[(intent, outcome)] += 1
        if intent is not None and intent != outcome and outcome in ('early', 'late', 'abs', 'pres'):
            self.reclassified[(intent, outcome)] += 1

    # ------------------------------------------------------------------
    def min_lead_for_early(self) -> int:
        """Délai minimal rendant l'annulation anticipée atteignable."""
        if self.config is None:
            return 3    # valeur pour LATE_CANCEL_FRACTION = 0.5
        return self.config.min_lead_for_early_cancel()

    def _anticipation_requested(self) -> bool:
        """
        L'expérimentateur a-t-il demandé un horizon capable de produire des
        annulations anticipées ?

        Sépare le bras de contrôle — anticipation volontairement désactivée,
        rien à signaler — du cas où l'horizon est demandé mais jamais obtenu.
        Le délai effectif vaut `l_n + ceil(trajet)`, soit au moins `l_n + 1`.
        """
        if self.config is None:
            return True
        high = self.config.RESERVATION_LEAD_PARAMS['high']
        return high + 1 >= self.min_lead_for_early()

    def anticipable_share(self) -> float | None:
        """
        Part des réservations dont le délai autorisait une annulation anticipée.

        C'est la mesure qui sépare une impossibilité structurelle (part nulle :
        aucune réservation n'avait d'avance à perdre) d'un simple aléa
        d'échantillonnage.
        """
        if not self.leads:
            return None
        threshold = self.min_lead_for_early()
        if threshold < 0:
            return 0.
        return sum(1 for l in self.leads if l >= threshold) / len(self.leads)

    # ------------------------------------------------------------------
    def _rates(self, counter: Counter) -> dict:
        total = sum(counter.values())
        if total == 0:
            return {}
        return {k: round(v / total, 4) for k, v in sorted(counter.items(),
                                                          key=lambda kv: -kv[1])}

    def diagnostics(self) -> list:
        """
        Signale les écarts structurels entre scénario et issues observées.

        Sert à ne pas interpréter comme un effet du modèle ce qui est en réalité
        une impossibilité physique du paramétrage.
        """
        warnings = []
        nb = sum(self.intents.values())
        if nb == 0:
            return warnings

        early_intent = self.intents.get('early', 0)
        early_obs = self.outcomes.get('early', 0)
        share = self.anticipable_share()
        min_lead = self.min_lead_for_early()

        # 1. Horizon demandé mais jamais obtenu. On ne signale que l'écart entre
        #    l'intention de l'expérimentateur et le résultat : désactiver
        #    l'anticipation (bras de contrôle) est un choix délibéré, pas une
        #    anomalie — `ExperimentParams.validate` l'a déjà signalé au moment
        #    de la configuration. Message sans compteur : il est identique pour
        #    tous les cas d'une campagne (regroupement en sortie).
        if share == 0. and early_intent > 0 and self._anticipation_requested():
            warnings.append(
                "Horizon de planification demandé mais aucune réservation n'a "
                f"obtenu un délai suffisant (>= {min_lead} slots) : la "
                "distinction anticipé / tardif n'est pas mesurable et la "
                "probabilité 'early' du scénario se réalise nécessairement en "
                "'late'. Cause probable : horizon de simulation trop court "
                "devant RESERVATION_LEAD_PARAMS + durée de recharge — les "
                "créneaux visés tombent hors de la fenêtre. Voir "
                "'median_lead_slots'."
            )

        # 2. Anomalie d'échantillon — le paramétrage le permettait, mais aucune
        #    intention ne s'est réalisée. Muet en dessous de MIN_EARLY_SAMPLE :
        #    sur une poignée d'intentions, l'absence d'issue `early` est du
        #    bruit, pas un symptôme.
        elif (early_intent >= self.MIN_EARLY_SAMPLE and early_obs == 0
                and share):
            warnings.append(
                f"Aucune des {early_intent} intentions 'early' n'a été réalisée "
                f"comme telle, alors que {share:.0%} des réservations avaient un "
                f"délai suffisant (>= {min_lead} slots). Écart à examiner : voir "
                "'reclassified'."
            )

        if (self.leads and float(np.mean(self.leads)) < 1.0
                and self._anticipation_requested()):
            warnings.append(
                "Délai moyen requête → arrivée prévue < 1 slot alors qu'un "
                "horizon est demandé : rayon de recherche petit devant la "
                "vitesse par slot."
            )

        unresolved = self.outcomes.get('unresolved', 0)
        if unresolved > 0.05 * nb:
            warnings.append(
                f"{unresolved}/{nb} réservations non résolues à la fin de "
                "l'horizon : durée de simulation probablement trop courte."
            )
        return warnings

    def report(self) -> dict:
        return {
            'nb_reservations':   sum(self.intents.values()),
            'nb_resolved':       sum(self.outcomes.values()),
            'intent_counts':     dict(self.intents),
            'intent_rates':      self._rates(self.intents),
            'observed_counts':   dict(self.outcomes),
            'observed_rates':    self._rates(self.outcomes),
            'reclassified':      {f"{i}->{o}": n for (i, o), n in self.reclassified.items()},
            'mean_lead_slots':   round(float(np.mean(self.leads)), 3) if self.leads else None,
            'median_lead_slots': round(float(np.median(self.leads)), 3) if self.leads else None,
            'anticipable_share': (round(self.anticipable_share(), 4)
                                  if self.anticipable_share() is not None else None),
            'diagnostics':       self.diagnostics(),
        }

    def print_report(self, theta_config: dict | None = None):
        r = self.report()
        print("\n--- Comportements (intention tirée vs. issue observée) ---")
        print(f"  Réservations confirmées : {r['nb_reservations']}"
              f"  |  issues enregistrées : {r['nb_resolved']}")
        if r['mean_lead_slots'] is not None:
            print(f"  Délai requête → arrivée : {r['mean_lead_slots']:.2f} slots (moyenne)")

        header = f"  {'':<11}{'scénario':>10}{'intention':>12}{'observé':>12}"
        print(header)
        keys = ('pres', 'abs', 'early', 'late', 'breakdown', 'unresolved')
        for k in keys:
            target = ''
            if theta_config and k in theta_config:
                total = sum(theta_config[kk] for kk in ('pres', 'abs', 'early', 'late'))
                target = f"{theta_config[k] / total:.3f}"
            intent = r['intent_rates'].get(k)
            obs = r['observed_rates'].get(k)
            print(f"  {k:<11}{target:>10}"
                  f"{('' if intent is None else f'{intent:.3f}'):>12}"
                  f"{('' if obs is None else f'{obs:.3f}'):>12}")

        if r['reclassified']:
            print("  Intentions réalisées autrement :")
            for label, n in sorted(r['reclassified'].items(), key=lambda kv: -kv[1]):
                print(f"    {label} : {n}")

        for warning in r['diagnostics']:
            print(f"  /!\\ {warning}")
