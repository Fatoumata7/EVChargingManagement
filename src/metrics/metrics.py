"""
metrics.py — Evaluation metrics of the simulation
"""

import time
import numpy as np
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


# ------------------------------------------------------------------
# Data structures for the collection
# ------------------------------------------------------------------

@dataclass
class AcceptanceRecord:
    """Records each offer acceptance (n, m)."""
    car_id:      int
    station_id:  int
    distance_km: float   # d_{n,m} at acceptance time
    waiting_time_h: float  # estimated w_{n,m} (in hours)


@dataclass
class DemandLatencyRecord:
    """
    Complete timeline of a demand, for the latency measurement.

    Every timestamp is a `time.perf_counter()` (seconds, monotonic). A demand
    may receive no offer (`offer_receptions` empty) or never be confirmed
    (`t_confirmation == 0`): the aggregates then ignore the demand for the stage
    concerned, instead of counting a zero.

    Stages measured:
      t_emission     emission of the request by the vehicle
      offer_receptions  (station_id, t) for *each* offer received
      t_last_offer   reception of the last offer
      t_selection    end of the offer ranking by the vehicle
      t_confirmation confirmation accepted by the station
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
    #: Search retries (widened radius) consumed by this demand.
    #: A retried demand stays *one* demand: it is a single charging need, whose
    #: end-to-end latency is being measured.
    nb_search_retries: int = 0
    confirmed: bool = False

    # ---- derived
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
        """Emission → first offer received."""
        return self._ms(self.t_first_offer)

    @property
    def last_offer_ms(self) -> Optional[float]:
        """Emission → last offer received (network response time)."""
        return self._ms(self.t_last_offer)

    @property
    def selection_ms(self) -> Optional[float]:
        """Last offer → decision of the vehicle."""
        return self._ms(self.t_selection, self.t_last_offer)

    @property
    def confirmation_ms(self) -> Optional[float]:
        """Decision → confirmation accepted by the station."""
        return self._ms(self.t_confirmation, self.t_selection)

    @property
    def total_ms(self) -> Optional[float]:
        """Emission → confirmation (end-to-end latency)."""
        return self._ms(self.t_confirmation)

    # ---- Compatibility: former names used by plots_metrics
    @property
    def t_response(self) -> float:
        """Historical alias: timestamp of the LAST offer received."""
        return self.t_last_offer

    @property
    def response_time_ms(self) -> float:
        """Historical alias: emission → last offer received (0. if none)."""
        return self.last_offer_ms or 0.0

    @property
    def per_offer_ms(self) -> List[float]:
        """Emission → reception, offer by offer."""
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


# Kept for compatibility with the former name.
DemandTimingRecord = DemandLatencyRecord


@dataclass
class StationTimingRecord:
    """Records the ILP processing time per station."""
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
# Central collector (to be attached to Simulation)
# ------------------------------------------------------------------

class MetricsCollector:

    def __init__(self, cars, stations, config):
        self.cars     = cars
        self.stations = stations
        self.config   = config

        # For User Request Satisfaction
        # schedule_demand[car_id] = binary np.array (TOTAL_TIME,)  already in car.schedule_requested
        # schedule_offer[car_id]  = binary np.array (TOTAL_TIME,)
        self.schedule_offer: Dict[int, np.ndarray] = {
            c.idx: np.zeros(config.TOTAL_TIME, dtype=int)
            for c in cars
        }

        # For Station Demand
        # station_charging_log[station_id] = list of (car_id, t_start, t_end, d_prop)
        self.station_charging_log: Dict[int, List[Tuple]] = {
            s.m: [] for s in stations
        }

        # For Mean Relative Travel Distance & Waiting Time
        self.acceptance_records: List[AcceptanceRecord] = []

        # For scalability / latency
        self.demand_timings: Dict[str, DemandLatencyRecord] = {}
        self.station_timings: List[StationTimingRecord]    = []

    # ------------------------------------------------------------------
    # Recording methods (called from Simulation)
    # ------------------------------------------------------------------

    def record_offer_accepted(self, car, offer, waiting_time_slots: float):
        """
        Called when a vehicle accepts an offer.
        waiting_time_slots : offer.t_arr - t_hat_arr (in slots)
        """
        # Offer schedule
        t_s = min(offer.t_arr, self.config.TOTAL_TIME)
        t_e = min(offer.t_dep, self.config.TOTAL_TIME)
        self.schedule_offer[car.idx][t_s:t_e] = 1

        # Distance in km (grid in meters)
        dist_km = offer.distance / 1000.0

        # Waiting time in hours
        wait_h = max(0., waiting_time_slots) * self.config.SLOT_DURATION / 60.0

        self.acceptance_records.append(AcceptanceRecord(
            car_id=car.idx,
            station_id=offer.station_id,
            distance_km=dist_km,
            waiting_time_h=wait_h
        ))

        # Station charging log
        self.station_charging_log[offer.station_id].append(
            (car.idx, offer.t_arr, offer.t_dep, offer.d_prop)
        )

    # ---- Latency ------------------------------------------------------

    def record_demand_emitted(self, demand_id, car_id: int = -1, slot: int = -1,
                              nb_stations_contacted: int = 0):
        if demand_id in self.demand_timings:
            raise ValueError(
                f"Demand identifier already used: {demand_id!r}. "
                "Identifiers must be unique for the latency to be measurable "
                "demand by demand."
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
        """Reception of an offer. Called once per offer, not per demand."""
        rec = self.demand_timings.get(demand_id)
        if rec is not None:
            rec.offer_receptions.append((station_id, time.perf_counter()))

    def record_demand_retry(self, demand_id, nb_stations_contacted: int = 0):
        """
        Retry of a demand with a widened radius.

        The demand is not recreated: its retry counter is incremented and the
        number of stations finally contacted is kept. `t_emission` stays the one
        of the first attempt, so that the latency measures the time to satisfy
        the need, retries included.
        """
        rec = self.demand_timings.get(demand_id)
        if rec is None:
            raise ValueError(
                f"Retry of an unknown demand: {demand_id!r}. A retry must keep "
                "the identifier of the original demand."
            )
        rec.nb_search_retries += 1
        rec.nb_stations_contacted = nb_stations_contacted
        return rec

    def record_demand_selection(self, demand_id):
        """The vehicle has finished ranking the offers received."""
        rec = self.demand_timings.get(demand_id)
        if rec is not None:
            rec.t_selection = time.perf_counter()

    def record_demand_confirmation(self, demand_id, confirmed: bool,
                                   nb_attempts: int = 1):
        """Outcome of the confirmation phase with the station."""
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
        P_n : charging power in kW (charging_power in km/slot → kW via consumption)
        d_n : allocated duration in hours
        """
        car_power = {}  # car_id → power in kW
        for car in self.cars:
            # charging_power in km/slot, consumption = 10 kWh/100 km
            kw = car.charging_power * \
                (self.config.ENERGY_CONSUMPTION['quantity_kW'] / \
                 (self.config.ENERGY_CONSUMPTION['distance_unit_m'] * 1e-3))  # kWh per slot → kW (slot = 5 min = 1/12 h)
            car_power[car.idx] = kw

        result = {}
        for s in self.stations:
            e_m = 0.0
            for (car_id, t_start, t_end, d_prop) in self.station_charging_log[s.m]:
                p_n = car_power.get(car_id, 0.)
                d_h = d_prop * self.config.SLOT_DURATION / 60.0  # slots → hours
                e_m += p_n * d_h
            result[s.m] = round(e_m, 3)
        return result

    # ------------------------------------------------------------------
    # 2. User Request Satisfaction
    # ------------------------------------------------------------------

    def user_request_satisfaction(self) -> Dict[str, float]:
        """
        Return the mean exact satisfaction and the mean needs satisfaction.
        """
        exact_list, needs_list = [], []

        for car in self.cars:
            s_demand = car.schedule_requested          # np.array (T,)
            s_offer  = self.schedule_offer[car.idx]    # np.array (T,)

            demand_slots = int(np.sum(s_demand))
            if demand_slots == 0:
                continue  # the vehicle never emitted a demand

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
        Mean distance (km) driven by the vehicles to reach a station.
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
        Mean waiting time (hours) estimated at the station.
        """
        if not self.acceptance_records:
            return 0.
        waits = [r.waiting_time_h for r in self.acceptance_records]
        return round(float(np.mean(waits)), 4)

    # ------------------------------------------------------------------
    # 5. Scalability — latency
    # ------------------------------------------------------------------

    def mean_response_time_ms(self) -> float:
        """
        Mean time between the emission of a demand and the reception of the LAST
        offer. Covers only the demands that received at least one offer (a
        demand with no answer has no response time).
        """
        value = _mean(r.last_offer_ms for r in self.demand_timings.values())
        return value if value is not None else 0.

    def latency_report(self) -> dict:
        """
        Complete decomposition of the latency, stage by stage.

        Each stage is aggregated independently over the demands for which it is
        defined; `nb_*` gives the corresponding count.
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
            # emission → offer, all offers taken together
            'offer_ms_mean':         _mean(per_offer),
            'offer_ms_p95':          _pct(per_offer, 95),
            # emission → first / last offer
            'first_offer_ms_mean':   _mean(r.first_offer_ms for r in recs),
            'last_offer_ms_mean':    _mean(r.last_offer_ms for r in recs),
            'last_offer_ms_p95':     _pct([r.last_offer_ms for r in recs], 95),
            # last offer → selection
            'selection_ms_mean':     _mean(r.selection_ms for r in recs),
            # selection → confirmation
            'confirmation_ms_mean':  _mean(r.confirmation_ms for r in recs),
            # end to end
            'total_ms_mean':         _mean(r.total_ms for r in recs),
            'total_ms_p95':          _pct([r.total_ms for r in recs], 95),
            'mean_confirm_attempts': round(float(np.mean(
                [r.nb_confirm_attempts for r in answered])), 3) if answered else None,
        }

    def latency_rows(self) -> List[dict]:
        """Per-demand detail (CSV export / fine-grained analysis)."""
        return [r.as_row() for r in self.demand_timings.values()]

    # ------------------------------------------------------------------
    # 6. Scalability — Mean processing time per station (ms)
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
    # Complete report
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
        print("\n========== METRICS ==========")

        print("\n--- Station Demand (kWh) ---")
        for sid, e in r['station_demand_kWh'].items():
            print(f"  Station {sid}: {e:.2f} kWh")

        print("\n--- User Request Satisfaction ---")
        sat = r['user_request_satisfaction']
        print(f"  Exact satisfaction : {sat['exact_satisfaction']*100:.1f}%")
        print(f"  Needs satisfaction : {sat['needs_satisfaction']*100:.1f}%")
        print(f"  Vehicles evaluated : {sat['nb_cars_evaluated']}")

        print("\n--- Travel & Waiting ---")
        print(f"  Mean distance : {r['mean_travel_distance_km']:.3f} km")
        print(f"  Mean waiting  : {r['mean_waiting_time_h']*60:.1f} min")

        lat = r['latency']
        print("\n--- Scalability / latency ---")
        print(f"  Demands                  : {lat['nb_demands']} "
              f"(with an offer: {lat['nb_demands_answered']}, "
              f"confirmed: {lat['nb_demands_confirmed']})")
        print(f"  Offers received / demand : {lat['mean_offers_per_demand']:.2f}")
        print(f"  Emission → 1st offer     : {_fmt(lat['first_offer_ms_mean'])}")
        print(f"  Emission → last offer    : {_fmt(lat['last_offer_ms_mean'])}"
              f"  (p95 {_fmt(lat['last_offer_ms_p95'])})")
        print(f"  Last offer → selection   : {_fmt(lat['selection_ms_mean'])}")
        print(f"  Selection → confirmation : {_fmt(lat['confirmation_ms_mean'])}")
        print(f"  End to end               : {_fmt(lat['total_ms_mean'])}"
              f"  (p95 {_fmt(lat['total_ms_p95'])})")
        print("  Processing time / station :")
        for sid, ms in r['mean_processing_time_ms'].items():
            print(f"    Station {sid}: {ms:.2f} ms")
        print("================================")


def _fmt(value):
    return "n/a" if value is None else f"{value:.2f} ms"


# ------------------------------------------------------------------
# Breakdown metric (to be called from Simulation.step)
# ------------------------------------------------------------------

class BreakdownTracker:
    """
    Tracking of the breakdowns (empty battery).
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
        print("\n--- Breakdowns ---")
        print(f"  Number of breakdowns : {self.count}")
        print(f"  Vehicles concerned   : {self.nb_unique_cars}")


# ------------------------------------------------------------------
# Behaviours: drawn intent vs. actually observed outcome
# ------------------------------------------------------------------

class BehaviorTracker:
    """
    Compare the intent drawn at reservation time with the outcome observed.

    Motivation: the intent (`theta`) and the outcome may legitimately differ. An
    "early cancellation" intent on a reservation taken 3 slots before arrival
    *cannot* be early: it is realised as a late cancellation. Without this
    tracking, the gap between the scenario probabilities and the measured rates
    was invisible — and wrongly attributed to the model.

    Possible outcomes
    -----------------
    pres       the vehicle showed up and charged
    abs        no-show: slot occupied until t_dep, vehicle never came
    early      cancellation > threshold before the planned arrival (slot given back in time)
    late       cancellation <= threshold before the planned arrival
    breakdown  empty battery before the session (reservation released)
    unresolved reservation still open at the end of the horizon
    """

    OUTCOMES = ('pres', 'abs', 'early', 'late', 'breakdown', 'unresolved')

    #: Below this number of `early` intents, the absence of an observed early
    #: cancellation is not interpretable: it is a sample, not a symptom. The
    #: diagnostic stays silent.
    MIN_EARLY_SAMPLE = 5

    def __init__(self, config=None):
        self.intents = Counter()      # behaviour drawn at reservation time
        self.outcomes = Counter()     # observed outcome
        self.pairs = Counter()        # (intent, outcome)
        self.reclassified = Counter() # intents realised otherwise
        self.leads = []               # request → arrival delay (slots)
        # Used by the diagnostics: the minimal delay making an early
        # cancellation reachable is derived from LATE_CANCEL_FRACTION, it cannot
        # be hard-coded here.
        self.config = config

    def record_intent(self, intent: str, lead: int | None = None):
        self.intents[intent] += 1
        if lead is not None:
            self.leads.append(int(lead))

    def record_outcome(self, intent: str | None, outcome: str):
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Unknown outcome: {outcome!r}")
        self.outcomes[outcome] += 1
        self.pairs[(intent, outcome)] += 1
        if intent is not None and intent != outcome and outcome in ('early', 'late', 'abs', 'pres'):
            self.reclassified[(intent, outcome)] += 1

    # ------------------------------------------------------------------
    def min_lead_for_early(self) -> int:
        """Minimal delay making an early cancellation reachable."""
        if self.config is None:
            return 3    # value for LATE_CANCEL_FRACTION = 0.5
        return self.config.min_lead_for_early_cancel()

    def _anticipation_requested(self) -> bool:
        """
        Did the experimenter ask for a horizon capable of producing early
        cancellations?

        Separates the control arm — anticipation deliberately disabled, nothing
        to report — from the case where the horizon is requested but never
        obtained. The effective delay is `l_n + ceil(travel)`, i.e. at least
        `l_n + 1`.
        """
        if self.config is None:
            return True
        high = self.config.RESERVATION_LEAD_PARAMS['high']
        return high + 1 >= self.min_lead_for_early()

    def anticipable_share(self) -> float | None:
        """
        Share of the reservations whose delay allowed an early cancellation.

        This is the measure that separates a structural impossibility (zero
        share: no reservation had any lead to lose) from a mere sampling
        accident.
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
        Report the structural gaps between the scenario and the observed outcomes.

        Its purpose is to avoid interpreting as a model effect what is in fact a
        physical impossibility of the parameter set.
        """
        warnings = []
        nb = sum(self.intents.values())
        if nb == 0:
            return warnings

        early_intent = self.intents.get('early', 0)
        early_obs = self.outcomes.get('early', 0)
        share = self.anticipable_share()
        min_lead = self.min_lead_for_early()

        # 1. Horizon requested but never obtained. Only the gap between what the
        #    experimenter intended and the result is reported: disabling
        #    anticipation (control arm) is a deliberate choice, not an anomaly —
        #    `ExperimentParams.validate` already reported it at configuration
        #    time. Message without a counter: it is identical for every case of
        #    a campaign (grouped on output).
        if share == 0. and early_intent > 0 and self._anticipation_requested():
            warnings.append(
                "Planning horizon requested but no reservation obtained a "
                f"sufficient delay (>= {min_lead} slots): the early / late "
                "distinction is not measurable and the 'early' probability of "
                "the scenario is necessarily realised as 'late'. Likely cause: "
                "simulation horizon too short against RESERVATION_LEAD_PARAMS "
                "+ charging duration — the targeted slots fall outside the "
                "window. See 'median_lead_slots'."
            )

        # 2. Sample anomaly — the parameter set allowed it, but no intent was
        #    realised. Silent below MIN_EARLY_SAMPLE: on a handful of intents,
        #    the absence of an `early` outcome is noise, not a symptom.
        elif (early_intent >= self.MIN_EARLY_SAMPLE and early_obs == 0
                and share):
            warnings.append(
                f"None of the {early_intent} 'early' intents was realised as "
                f"such, although {share:.0%} of the reservations had a "
                f"sufficient delay (>= {min_lead} slots). Gap to examine: see "
                "'reclassified'."
            )

        if (self.leads and float(np.mean(self.leads)) < 1.0
                and self._anticipation_requested()):
            warnings.append(
                "Mean request → planned arrival delay < 1 slot although a "
                "horizon is requested: search radius small against the speed "
                "per slot."
            )

        unresolved = self.outcomes.get('unresolved', 0)
        if unresolved > 0.05 * nb:
            warnings.append(
                f"{unresolved}/{nb} reservations unresolved at the end of the "
                "horizon: simulation duration probably too short."
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
        print("\n--- Behaviours (drawn intent vs. observed outcome) ---")
        print(f"  Confirmed reservations : {r['nb_reservations']}"
              f"  |  outcomes recorded : {r['nb_resolved']}")
        if r['mean_lead_slots'] is not None:
            print(f"  Request → arrival delay : {r['mean_lead_slots']:.2f} slots (mean)")

        header = f"  {'':<11}{'scenario':>10}{'intent':>12}{'observed':>12}"
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
            print("  Intents realised otherwise:")
            for label, n in sorted(r['reclassified'].items(), key=lambda kv: -kv[1]):
                print(f"    {label} : {n}")

        for warning in r['diagnostics']:
            print(f"  /!\\ {warning}")
