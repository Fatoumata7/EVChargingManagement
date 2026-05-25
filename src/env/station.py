"""
station.py — Agent station de recharge
"""

import numpy as np
import random
from loguru import logger
from ortools.linear_solver import pywraplp

import src.env.utils as utils
import src.env.offer as off
import src.experiments.config as config


class Station:

    def __init__(self, m: int, society_id: int, config: config.SimulationConfig):
        self.m = m
        self.loc = utils.init_pos(config)
        self.society_id = society_id
        self.config = config
        self.nb_charg_spot = random.randint(
            config.NB_CHARG_SPOT['low'], config.NB_CHARG_SPOT['high'])

        self.strategy = None   # injecté par Society.add_station()
        self.alpha = random.uniform(0.3, 0.9)  # poids profit vs risque

        self.T = config.TOTAL_TIME
        self.schedule = np.full((self.nb_charg_spot, self.T), -1, dtype=int)

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def update_car_score(self, car_agent, status, d_n):
        """Met à jour la composante f du score du véhicule."""
        mu = self.strategy
        if status == 'pres':
            delta = +mu['pres'] * d_n
        elif status == 'early':
            delta = -mu['early'] * d_n
        elif status == 'late':
            delta = -mu['late'] * d_n
        else:  # 'abs'
            delta = -mu['abs'] * d_n
        car_agent.score[self.society_id] += delta

    # ------------------------------------------------------------------
    # Optimisation ILP
    # ------------------------------------------------------------------

    def process_demands(self, station_demands, t_c):
        """
        Résout le problème d'allocation et retourne une liste de (Car, Offer).
        """
        if not station_demands:
            return []

        solver = pywraplp.Solver.CreateSolver("SCIP")
        solver.SetTimeLimit(60000 * 5) # 60000 -> 1 min

        T = self.T
        n_list, cars = [], []
        t_hat_arr, t_hat_dep = {}, {}
        scores, distance, d_n, g_n = {}, {}, {}, {}

        for car, req in station_demands:
            n = req['n']
            n_list.append(n)
            cars.append(car)

            x_n, y_n = req['loc']
            x_m, y_m = self.loc
            #print('x_n, y_n = ', x_n, y_n)
            #print('x_m, y_m = ',x_m, y_m)
            dist = np.sqrt((x_m - x_n) ** 2 + (y_m - y_n) ** 2)
            #print('dist = ', dist)
            #print('t_slots = ', int(dist / self.config.CAR_SPEED))
            distance[n] = dist

            arr = req['t_n'] + dist / self.config.CAR_SPEED
            dep = arr + req['d_n']
            t_hat_arr[n] = int(arr)
            t_hat_dep[n] = int(dep)
            d_n[n] = req['d_n']
            g_n[n] = req['g_n']
            scores[n] = float(car.score[self.society_id])
            #logger.info(f'STATION {self.m}, DEMAND {n} -> t_hat_arr = {t_hat_arr[n]}, t_hat_dep = {t_hat_dep[n]}'
            #            f' d_n = {d_n[n]}, g_n = {g_n[n]}, scores = {scores[n]}')

        # Variables de décision
        a = {}
        for n in n_list:
            t_max_n = min(T, int(t_hat_arr[n] + g_n[n] + d_n[n]) + 1)
            for j in range(self.nb_charg_spot):
                for t in range(max(t_c, t_hat_arr[n]), t_max_n):
                    if self.schedule[j, t] == -1:
                        a[n, j, t] = solver.BoolVar(f"a_{n}_{j}_{t}")

        y = {}
        for n in n_list:
            for j in range(self.nb_charg_spot):
                y[n, j] = solver.BoolVar(f"y_{n}_{j}")

        # Contrainte : un seul chargeur par demande
        for n in n_list:
            solver.Add(solver.Sum(y[n, j] for j in range(self.nb_charg_spot)) <= 1)

        for (n, j, t), var in a.items():
            solver.Add(var <= y[n, j])

        # Contrainte capacité
        for j in range(self.nb_charg_spot):
            for t in range(t_c, T):
                solver.Add(
                    solver.Sum(a[n, j, t] for n in n_list if (n, j, t) in a) <= 1
                )

        # Contrainte durée (≤ d_n, pas = pour permettre offres partielles)
        for n in n_list:
            solver.Add(
                solver.Sum(
                    a[n, j, t]
                    for j in range(self.nb_charg_spot)
                    for t in range(T)
                    if (n, j, t) in a
                ) <= d_n[n]
            )

        # Objectif agrégé
        objective = solver.Objective()
        for (n, j, t), var in a.items():
            if t < t_hat_arr[n]:
                D = t_hat_arr[n] - t
            elif t > t_hat_dep[n]:
                D = t - t_hat_dep[n]
            else:
                D = 0
            profit  = self.config.w1 * self.config.z
            penalty = self.config.w2 * D
            risk    = scores[n]
            coef = self.alpha * (profit - penalty) + (1 - self.alpha) * risk
            objective.SetCoefficient(var, coef)
        objective.SetMaximization()

        status = solver.Solve()

        offers = []
        if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return offers

        for idx, n in enumerate(n_list):
            j_selected = next(
                (j for j in range(self.nb_charg_spot) if y[n, j].solution_value() > 0.5),
                None
            )
            if j_selected is None:
                continue

            times = [t for (nn, j, t), var in a.items()
                     if nn == n and j == j_selected and var.solution_value() > 0.5]
            if not times:
                continue

            offer = off.Offer(
                station_id=self.m,
                charger_id=j_selected,
                t_arr=min(times),
                t_dep=max(times) + 1,
                d_prop=len(times),
                distance=distance[n]
            )
            offers.append((cars[idx], offer))

        return offers

    # ------------------------------------------------------------------
    # Réservation & planning
    # ------------------------------------------------------------------

    def confirm_reservation(self, car_id, offer):
        """
        FIX : Offer est un objet — utilise les attributs, pas les clés dict.
        Remplit le planning avec l'id du véhicule sur les slots alloués.
        """
        assert offer.station_id == self.m, "Mauvaise station pour cette offre"
        j = offer.charger_id
        t_start = offer.t_arr
        t_end   = offer.t_dep
        if t_end > self.T:
            t_end = self.T
        self.schedule[j, t_start:t_end] = car_id

    def release_reservation(self, car_id, offer):
        """Libère les créneaux réservés (pour annulation ou fin de session)."""
        j = offer.charger_id
        mask = self.schedule[j, :] == car_id
        self.schedule[j, mask] = -1

    def get_current_charger_and_slot(self, car_id, t_c):
        """Retourne (j, True) si le véhicule doit être en charge à t_c."""
        for j in range(self.nb_charg_spot):
            if 0 <= t_c < self.T and self.schedule[j, t_c] == car_id:
                return j, True
        return None, False

    def is_session_finished(self, car_id, t_c):
        """Retourne True si le véhicule n'a plus de créneaux à partir de t_c."""
        for j in range(self.nb_charg_spot):
            if np.any(self.schedule[j, t_c:] == car_id):
                return False
        return True

    def total_nb_allocated_slot(self):
        return int(np.sum(self.schedule != -1))

    def display_parameters(self, file):
        print('--- AGENT STATION', file=file)
        print(f'  m             : {self.m}', file=file)
        print(f'  loc           : {self.loc}', file=file)
        print(f'  society_id    : {self.society_id}', file=file)
        print(f'  nb_charg_spot : {self.nb_charg_spot}', file=file)
        print(f'  alpha         : {self.alpha:.3f}', file=file)
        print(f'  strategy      : {self.strategy}', file=file)
        print(f'  schedule shape: {self.schedule.shape}', file=file)
