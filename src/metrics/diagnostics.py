"""
diagnostics.py — Structured record of the allocation decisions of a run.

The run tables (`latency`, `stations`, ...) say what happened to each request;
they do not say what each station saw when it decided. This recorder keeps,
for one case:

`decisions`    one row per (request, attempt, station) a station received —
               including the requests it did not serve — with the score it
               read before deciding, the length of the history behind that
               score, the weight (alpha) it used, and the durations requested
               and offered. Attempts with no eligible station get a row too,
               with an empty station.
`ilp_batches`  one row per local solve: batch size, free candidate capacity,
               solver status, objective value, best bound, solve time.
`offers`       one row per issued offer and its fate (confirmed, expired,
               refused), linked to the unique request and to the vehicle's
               ranking and confirmation attempts.
`scores`       the score and history length of every (vehicle, operator)
               pair at initialisation and at the end of every simulated day,
               withdrawn vehicles included.

Recording is read-only: it draws no random number and changes no state, so a
run gives the same result with or without it. It is off by default
(`SimulationConfig.DIAGNOSTICS`), the tables being large.
"""

from __future__ import annotations

from ortools.linear_solver import pywraplp

STATUS_NAMES = {
    pywraplp.Solver.OPTIMAL:    'OPTIMAL',
    pywraplp.Solver.FEASIBLE:   'FEASIBLE',
    pywraplp.Solver.INFEASIBLE: 'INFEASIBLE',
    pywraplp.Solver.UNBOUNDED:  'UNBOUNDED',
    pywraplp.Solver.ABNORMAL:   'ABNORMAL',
    pywraplp.Solver.NOT_SOLVED: 'NOT_SOLVED',
}


class DecisionRecorder:
    """Collects the diagnostic tables of one simulation."""

    def __init__(self):
        self.decisions: list[dict] = []
        self.batches: list[dict] = []
        self._offers: dict[str, dict] = {}       # offer_id -> row
        self._offer_objects: dict[str, object] = {}
        self.scores: list[dict] = []

    # ------------------------------------------------------------------
    # Stations
    # ------------------------------------------------------------------

    def record_batch(self, station, t_c: int, batch: list, nb_candidate_slots: int,
                     status: int, objective, bound, solve_ms: float) -> str:
        batch_id = f't{t_c}-s{station.m}'
        self.batches.append({
            'batch_id':           batch_id,
            't':                  t_c,
            'station_id':         station.m,
            'operator':           station.society_id,
            'nb_chargers':        station.nb_charg_spot,
            'nb_requests':        len(batch),
            'free_candidate_slots': nb_candidate_slots,
            'status':             STATUS_NAMES.get(status, str(status)),
            'objective':          objective,
            'best_bound':         bound,
            'solve_ms':           solve_ms,
            'alpha':              float(station.alpha),
        })
        return batch_id

    def record_decision(self, station, t_c: int, batch_id: str, car, req: dict,
                        score: float, offer=None, reason: str = 'offer') -> None:
        index = station.score_index
        self.decisions.append({
            'request_id':      req['n'],
            'attempt':         int(car.search_retries),
            't':               t_c,
            'car_id':          car.idx,
            'station_id':      station.m,
            'operator':        station.society_id,
            'score_index':     index,
            'score_before':    score,
            'history_length':  len(car.score_history[index]),
            'alpha':           float(station.alpha),
            'duration_requested': int(req['d_n']),
            'duration_offered':   int(offer.d_prop) if offer is not None else 0,
            'offer_id':        offer.offer_id if offer is not None else '',
            'outcome':         reason,
            'batch_id':        batch_id,
        })
        if offer is not None:
            self._offer_objects[offer.offer_id] = offer
            self._offers[offer.offer_id] = {
                'offer_id':      offer.offer_id,
                'request_id':    req['n'],
                'attempt':       int(car.search_retries),
                'car_id':        car.idx,
                'station_id':    station.m,
                'operator':      station.society_id,
                't_issued':      offer.t_issued,
                't_arr':         offer.t_arr,
                't_dep':         offer.t_dep,
                'duration_requested': int(req['d_n']),
                'duration_offered':   int(offer.d_prop),
                'rank':          None,
                'utility':       None,
                'tried':         False,
            }

    def record_no_station(self, t_c: int, car, req: dict) -> None:
        """An attempt that reached no station: no station decision exists."""
        self.decisions.append({
            'request_id': req['n'], 'attempt': int(car.search_retries), 't': t_c,
            'car_id': car.idx, 'station_id': '', 'operator': '',
            'score_index': '', 'score_before': '', 'history_length': '',
            'alpha': '', 'duration_requested': int(req['d_n']),
            'duration_offered': 0, 'offer_id': '',
            'outcome': 'no_eligible_station', 'batch_id': '',
        })

    # ------------------------------------------------------------------
    # Vehicles
    # ------------------------------------------------------------------

    def record_ranking(self, ranked: list, nb_tried: int) -> None:
        """Rank and utility of each offer, and whether confirmation was tried."""
        for rank, (offer, utility) in enumerate(ranked, start=1):
            row = self._offers.get(offer.offer_id)
            if row is None:
                continue
            row['rank'] = rank
            row['utility'] = float(utility) if utility is not None else None
            row['tried'] = rank <= nb_tried

    def snapshot_scores(self, t: int, day: int, cars, nb_operators: int,
                        withdrawn: dict) -> None:
        for car in cars:
            for f in range(nb_operators):
                self.scores.append({
                    'day':            day,
                    't':              t,
                    'car_id':         car.idx,
                    'operator':       f,
                    'score':          float(car.score[f]),
                    'history_length': len(car.score_history[f]),
                    'withdrawn':      car.idx in withdrawn,
                })

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def offer_rows(self) -> list[dict]:
        rows = []
        for offer_id, row in self._offers.items():
            offer = self._offer_objects[offer_id]
            rows.append(dict(row, status=offer.status,
                             reject_reason=offer.reject_reason or ''))
        return rows

    def tables(self) -> dict[str, list[dict]]:
        return {
            'decisions':   self.decisions,
            'ilp_batches': self.batches,
            'offers':      self.offer_rows(),
            'scores':      self.scores,
        }
