"""
metrics.py — Métriques d'évaluation de la simulation
"""

import time
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Dict


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
class DemandTimingRecord:
    """Enregistre les timestamps pour la scalabilité."""
    demand_id:    int
    t_emission:   float  # time.perf_counter() à l'émission
    t_response:   float = 0.0  # time.perf_counter() à la réception
    station_id:   int   = -1

    @property
    def response_time_ms(self) -> float:
        return (self.t_response - self.t_emission) * 1000.0


@dataclass
class StationTimingRecord:
    """Enregistre le temps de traitement ILP par station."""
    station_id:   int
    demand_id:    int
    t_start:      float
    t_end:        float = 0.0

    @property
    def processing_time_ms(self) -> float:
        return (self.t_end - self.t_start) * 1000.0


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
        # station_charging_log[station_id] = liste de (car_id, t_start, t_end)
        self.station_charging_log: Dict[int, List[Tuple]] = {
            s.m: [] for s in stations
        }

        # Pour Mean Relative Travel Distance & Waiting Time
        self.acceptance_records: List[AcceptanceRecord] = []

        # Pour scalabilité
        self.demand_timings: Dict[int, DemandTimingRecord] = {}
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

    def record_demand_emitted(self, demand_id: int):
        self.demand_timings[demand_id] = DemandTimingRecord(
            demand_id=demand_id,
            t_emission=time.perf_counter()
        )

    def record_demand_responded(self, demand_id: int, station_id: int):
        if demand_id in self.demand_timings:
            self.demand_timings[demand_id].t_response = time.perf_counter()
            self.demand_timings[demand_id].station_id = station_id

    def record_station_processing_start(self, station_id: int, demand_id: int) -> StationTimingRecord:
        rec = StationTimingRecord(
            station_id=station_id,
            demand_id=demand_id,
            t_start=time.perf_counter()
        )
        self.station_timings.append(rec)
        return rec  # l'appelant set rec.t_end = time.perf_counter() après process_demands()

    # ------------------------------------------------------------------
    # 1. Station Demand (kWh par station)
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
    # 5. Scalabilité — Temps de réponse moyen (ms)
    # ------------------------------------------------------------------

    def mean_response_time_ms(self) -> float:
        times = [
            r.response_time_ms
            for r in self.demand_timings.values()
            if r.t_response > 0
        ]
        return round(float(np.mean(times)), 3) if times else 0.

    # ------------------------------------------------------------------
    # 6. Scalabilité — Temps de traitement moyen par station (ms)
    # ------------------------------------------------------------------

    def mean_processing_time_per_station(self) -> Dict[int, float]:
        from collections import defaultdict
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

        print("\n--- Scalabilité ---")
        print(f"  Temps réponse moy.     : {r['mean_response_time_ms']:.2f} ms")    # temps total moyen entre l'émission d'une demande et la réception de la dernière réponse station.
        print("  Temps traitement / station :")
        for sid, ms in r['mean_processing_time_ms'].items():
            print(f"    Station {sid}: {ms:.2f} ms")
        print("================================")


# ------------------------------------------------------------------
# Métrique panne sèche (à appeler depuis Simulation.step)
# ------------------------------------------------------------------

class BreakdownTracker:
    """
    Suit les pannes sèches (soc <= SOC_BREAKDOWN_THRESHOLD en état DRIVING).
    À instancier dans MetricsCollector ou directement dans Simulation.
    """

    def __init__(self):
        self.breakdowns = []   # liste de dicts {car_id, slot, x, y, soc}

    def record(self, car, slot: int):
        self.breakdowns.append({
            'car_id': car.idx,
            'slot':   slot,
            'x':      round(car.x, 1),
            'y':      round(car.y, 1),
            'soc':    round(car.soc_m, 4),
        })

    @property
    def count(self) -> int:
        return len(self.breakdowns)

    @property
    def nb_unique_cars(self) -> int:
        return len({b['car_id'] for b in self.breakdowns})

    def report(self) -> dict:
        return {
            'total_breakdowns':  self.count,
            'unique_cars':       self.nb_unique_cars,
            'details':           self.breakdowns,
        }

    def print_report(self):
        r = self.report()
        print("\n--- Pannes sèches ---")
        print(f"  Total          : {r['total_breakdowns']}")
        #print(f"  Voitures uniques: {r['unique_cars']}")
        for b in r['details']:
            print(f"  Car {b['car_id']:>2} | slot {b['slot']:>3} | "
                  f"pos ({b['x']:.0f}, {b['y']:.0f}) | soc {b['soc']:.3f}")
