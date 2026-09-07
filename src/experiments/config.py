"""
config.py — Simulation parameters (realistic)
"""
import numpy as np


class SimulationConfig:

    # ------------------------------------------------------------------ GRID
    # 3×3 km: reasonable size for a dense urban area.
    C_GRID = 3 * 1e3            # 9 km^2 (1/10th of Paris)

    # ------------------------------------------------------------------ TIME
    SLOT_DURATION = 5               # 5 minutes, must divide 60
    NB_SLOTS_IN_ONE_HOUR = 12       # 60 / SLOT_DURATION

    # ------------------------------------------------------------------ VISUALIZATION
    VIS_DELAY = 1

    # ------------------------------------------------------------------ LEARNING
    GAMMA = 0.1

    # ------------------------------------------------------------------ CAR
    # Initial SoC: between 0.3 and 1.0 (no nearly empty car at the start)
    CAR_INIT_SOC = {'low': 0.30, 'high': 0.80}

    # Charging trigger threshold: mean 20%, max 35%
    # → a car never looks for a charge above 35% of battery
    CAR_SOC_THRESHOLD_PARAMS = {
        'mean': 0.35,
        'sd':   0.06,
        'low':  0.25,
        'high': 0.70
    }

    # Realistic autonomy: 300-500 km (electric city cars)
    CAR_AUTONOMY_PARAMS_KM = {
        'mean': 400,
        'sd':    60,
        'low':  300,
        'high': 500
    }

    LATE_CANCEL_REF = 12    # late cancellation if < 1h = 12 slots

    # Energy consumption: 10 kWh / 100 km
    ENERGY_CONSUMPTION = {
        'quantity_kW':     10,          # kWh (5)
        'distance_unit_m': 100 * 1e3    # 100 km in meters (1000e3)
    }

    # ------------------------------------------------------------------ BREAKDOWN
    # Threshold below which the car counts as broken down (soc ≈ 0)
    SOC_BREAKDOWN_THRESHOLD = 3 * 1e3   # 1% → ~3 km left

    # ------------------------------------------------------------------ SCENARIOS
    # Single source of truth for the behaviour probabilities.
    # Notebooks must call `set_scenario(name)` instead of redefining
    # BASE_CANCEL_PROB locally (which is what produced diverging parameter sets
    # between the notebooks and the report).
    #
    # Convention:
    #   pres  : shows up and honours the reservation
    #   abs   : complete no-show (slot never released before t_dep)
    #   early : early cancellation  (> LATE_CANCEL_REF slots before arrival)
    #   late  : late cancellation   (<= LATE_CANCEL_REF slots before arrival)
    #
    # Severity grows from `optimistic` to `pessimistic` on the two dimensions
    # that cost the operator (`abs` and `late`), and `noise` is identical
    # everywhere so that scenarios differ only by their probabilities.
    SCENARIOS = {
        'optimistic':  {'pres': 75, 'abs': 10, 'early':  9, 'late':  6, 'noise': 0.15},
        'balance':     {'pres': 60, 'abs': 20, 'early': 12, 'late':  8, 'noise': 0.15},
        'pessimistic': {'pres': 40, 'abs': 25, 'early': 15, 'late': 20, 'noise': 0.15},
    }


    def __init__(self):

        self.TOTAL_TIME = 12 * 4 # 12 * 24 * 5        # 12 slots of 5 min in one hour, 4 hours

        # ------------------------------------------------------------------ REPRODUCIBILITY
        # Single seed of the experiment. Set through set_seed(); recorded with
        # every result by the pipeline (src/pipeline).
        self.SEED = None
        self.SCENARIO_NAME = 'custom'      # filled in by set_scenario()

        # ------------------------------------------------------------------ OFFER PROTOCOL
        # Validity of an offer, in slots. 1 = the offer expires at the end of
        # the issuing slot (an offer not confirmed immediately is lost).
        self.OFFER_TTL_SLOTS = 1

        # Share of the request → arrival delay below which a cancellation counts
        # as late, when that delay is shorter than LATE_CANCEL_REF
        # (see late_cancel_threshold).
        self.LATE_CANCEL_FRACTION = 0.5

        # ------------------------------------------------------------------ PLANNING HORIZON
        # Number of slots between the emission of a request and the targeted
        # slot (`request['l_n']`, drawn per request in `Car.emit_request`). The
        # driver no longer asks to "charge now" but to "charge in l_n slots":
        # the nominal slot becomes t_n + l_n + travel
        # (see `utils.nominal_arrival`).
        #
        # Reachability of the early cancellation: it fires at the earliest at
        # t_n + 1, so slots_left = lead - 1, to be compared with the threshold
        # late_cancel_threshold(lead). An effective delay >= 3 slots is required
        # (see min_lead_for_early_cancel), and that delay is l_n + ceil(travel),
        # i.e. l_n + 1 on this grid: l_n >= 2 is therefore enough here. Beyond
        # 24 the gain is nil — the ILP window is capped by the patience g_n.
        #
        # `low = 0` is deliberate: part of the requests stay "charge now"
        # (driver already short on autonomy), which keeps a non-anticipable
        # control group in every execution and keeps the `early -> late`
        # reclassification observable.
        #
        # {'low': 0, 'high': 0} disables the horizon: that is the control arm of
        # the ablation, the one where an early cancellation is unreachable.
        self.RESERVATION_LEAD_PARAMS = {'low': 12, 'high': 48}

        self.VISUALIZE = True

        self.NB_CARS       = 50
        self.NB_SOCIETIES  = 5
        self.NB_STATIONS   = 40

        self.w1 = 1.0    # profit weight in the station objective
        self.w2 = 1.0    # weight of the temporal-distance penalty
        self.z  = 2.0    # profit priority constant (z > 1)

        # Common alpha value for the methods whose `alpha_mode == 'fixed'`
        # (`bramev_fixed_alpha` variant, see src/experiments/methods.py).
        # No effect on the other methods, where alpha is drawn per station.
        self.ALPHA_FIXED = 0.5

        self.NB_CHARG_SPOT = {'low': 4, 'high': 6}      # number of chargers per station
        self.SOCIETY_UPDATE_INTERVAL = 12 * 2          # strategy update every <nb_slot>, 2 hours

        # Reduced speed: 50 km/h in a dense urban area
        # 50 km/h × (5/60) h/slot = 4.167 km/slot = 4.167 m/slot
        self.CAR_SPEED = 4.167e3             # m / slot

        # Search radius for the emission of a demand
        self.MIN_RAY_SEARCH = 0        # minimal search radius for a station (5km)
        self.MAX_RAY_SEARCH = 1 * 1e3
        self.COEFF_MAX_DIST = 0.5            # coefficient of the max distance defined as max_ray_search

        # ------------------------------------------------------------------ SEARCH RETRY
        # A vehicle that finds neither an eligible station, nor an offer, nor a
        # confirmation does not drive off at random: it stops
        # (PARKED_SEARCHING) and re-emits the same demand with a widened radius.
        # Stopping avoids consuming energy during an unsuccessful search, and
        # avoids drifting away from the very stations it is trying to reach.
        #
        # The widening deliberately exceeds MAX_RAY_SEARCH: that cap bounds the
        # *routine* search, not the exceptional widening. The radius stays
        # bounded by the grid diagonal (see `max_search_radius`), beyond which
        # it can no longer discover anything.
        self.SEARCH_RADIUS_GROWTH = 1.5
        # Retry budget per demand. Beyond it the vehicle gives up and drives on
        # in DRIVING: without that guard, a vehicle stopped in an area with no
        # charger would stay parked indefinitely, never breaking down since it
        # no longer consumes, and would bias the service rates.
        self.MAX_SEARCH_RETRIES = 4

        self.REDUCE_SPEED_FACTORS = [1.05, 1.25]  # reduction factors for a non-present behaviour

        # Behaviour probabilities
        self.BASE_CANCEL_PROB = {
            'pres':  75,    # present and honours the reservation
            'abs':   10,    # complete no-show
            'early':  9,    # early cancellation (> 2h before)
            'late':   6,    # late cancellation (< 2h before)
            'noise':  0.15  # noise ±15%
        }
        assert (self.BASE_CANCEL_PROB['pres'] + self.BASE_CANCEL_PROB['abs'] +
                self.BASE_CANCEL_PROB['early'] + self.BASE_CANCEL_PROB['late']) == 100

        # Requested charging duration: mostly "full charge"
        self.CHARGING_DURATION_PARAMS = [
            (0.9, (0.8, 1.0)),   # nearly full charge -> 90% of the vehicles ask for 80-100% of battery
            (0.1, (0.6, 0.8)),   # partial charge     -> 10% of the vehicles ask for 60-80% of battery
        ]

        # ------------------------------------------------------------------ COMPANY
        self.BASE_POINTS_STRATEGY = {
            'pres':  4.0,
            'abs':   3.0,
            'late':  1.0,
            'early': 0.5,
        }
        self.STRATEGY_NOISE = 0.5

        # ------------------------------------------------------------------ REPUTATION
        # Number of reservations retained in a vehicle's score: beyond it, the
        # oldest ones leave the window (right to be forgotten).
        #
        # The score is no longer a cumulative sum but the weighted mean of the
        # normalised stakes of that window, hence bounded in [-1, 1]
        # (see `Car.record_score_event`). That is what makes `alpha` meaningful
        # again: the former sum reached ±380 against a profit term of w1*z = 2,
        # and the profit/risk trade-off was purely nominal — any vehicle with a
        # single incident became permanently ineligible.
        self.SCORE_MEMORY = 5

        self.log_iter = 10

    def set_TOTAL_TIME(self, value: int) -> None:
        """
        Set the total simulation time.

        Parameters
        ----------
        value : int
            Total number of slots (> 0)
        """
        if not isinstance(value, int):
            raise TypeError(
                f"TOTAL_TIME must be an integer, got: {type(value).__name__}"
            )
        if value <= 0:
            raise ValueError(
                f"TOTAL_TIME must be strictly positive, got: {value}"
            )
        self.TOTAL_TIME = value
        

    def set_VISUALIZE(self, value: bool) -> None:
        """
        Enable or disable the visualization.
        """
        if type(value) is not bool:
            raise TypeError(
                f"VISUALIZE must be a bool, got: {type(value).__name__}"
            )
        self.VISUALIZE = value


    def set_NB_CARS(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"NB_CARS must be an int, got: {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"NB_CARS must be > 0, got: {value}"
            )

        self.NB_CARS = value


    def set_NB_SOCIETIES(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"NB_SOCIETIES must be an int, got: {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"NB_SOCIETIES must be > 0, got: {value}"
            )

        self.NB_SOCIETIES = value


    def set_NB_STATIONS(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"NB_STATIONS must be an int, got: {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"NB_STATIONS must be > 0, got: {value}"
            )

        self.NB_STATIONS = value


    def set_CAR_SPEED(self, value: float) -> None:

        if not isinstance(value, (int, float)):
            raise TypeError(
                f"CAR_SPEED must be numeric, got: {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"CAR_SPEED must be > 0, got: {value}"
            )

        self.CAR_SPEED = float(value)


    def set_BASE_CANCEL_PROB(self, value: dict) -> None:

        required_keys = {
            'pres',
            'abs',
            'early',
            'late',
            'noise'
        }

        if not isinstance(value, dict):
            raise TypeError(
                f"BASE_CANCEL_PROB must be a dict, got: {type(value).__name__}"
            )

        missing = required_keys - set(value.keys())

        if missing:
            raise ValueError(
                f"Missing keys: {missing}"
            )

        total = (
            value['pres']
            + value['abs']
            + value['early']
            + value['late']
        )

        if total != 100:
            raise ValueError(
                f"The probabilities must sum to 100, got: {total}"
            )

        if value['noise'] < 0:
            raise ValueError(
                "noise must be >= 0"
            )

        self.BASE_CANCEL_PROB = value.copy()


    def set_BASE_POINTS_STRATEGY(self, value: dict) -> None:

        required_keys = {
            'pres',
            'abs',
            'late',
            'early'
        }

        if not isinstance(value, dict):
            raise TypeError(
                f"BASE_POINTS_STRATEGY must be a dict, got: {type(value).__name__}"
            )

        missing = required_keys - set(value.keys())

        if missing:
            raise ValueError(
                f"Missing keys: {missing}"
            )

        for k, v in value.items():

            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"The value associated with '{k}' must be numeric"
                )

            if v <= 0:
                raise ValueError(
                    f"The value associated with '{k}' must be > 0"
                )

        self.BASE_POINTS_STRATEGY = value.copy()


    def set_STRATEGY_NOISE(self, value: float) -> None:

        if not isinstance(value, (int, float)):
            raise TypeError(
                f"STRATEGY_NOISE must be numeric, got: {type(value).__name__}"
            )

        if value < 0:
            raise ValueError(
                "STRATEGY_NOISE must be >= 0"
            )

        self.STRATEGY_NOISE = float(value)


    def set_NB_CHARG_SPOT(self, value: dict) -> None:

        required_keys = {'low', 'high'}

        if not isinstance(value, dict):
            raise TypeError(
                f"NB_CHARG_SPOT must be a dict, got: {type(value).__name__}"
            )

        missing = required_keys - set(value.keys())

        if missing:
            raise ValueError(
                f"Missing keys: {missing}"
            )

        low = value['low']
        high = value['high']

        if type(low) is not int or type(high) is not int:
            raise TypeError(
                "low and high must be ints"
            )

        if low <= 0 or high <= 0:
            raise ValueError(
                "low and high must be > 0"
            )

        if low > high:
            raise ValueError(
                "low must be <= high"
            )

        self.NB_CHARG_SPOT = value.copy()


    def set_SEARCH_RADIUS(
        self,
        min_ray: float,
        max_ray: float
    ) -> None:

        if not isinstance(min_ray, (int, float)):
            raise TypeError("min_ray must be numeric")

        if not isinstance(max_ray, (int, float)):
            raise TypeError("max_ray must be numeric")

        if min_ray < 0:
            raise ValueError("min_ray must be >= 0")

        if max_ray <= 0:
            raise ValueError("max_ray must be > 0")

        if min_ray > max_ray:
            raise ValueError(
                "min_ray must be <= max_ray"
            )

        self.MIN_RAY_SEARCH = float(min_ray)
        self.MAX_RAY_SEARCH = float(max_ray)

    def set_log_iter(self, value):

        self.log_iter = value


    def set_seed(self, value: int) -> None:
        """
        Set the seed of the experiment.

        Does not seed the generators: `RngHub(seed)` does that (see
        src/experiments/seeding.py), called by `define_agents`.
        """
        if not isinstance(value, int):
            raise TypeError(
                f"SEED must be an integer, got: {type(value).__name__}"
            )
        if value < 0:
            raise ValueError(f"SEED must be >= 0, got: {value}")
        self.SEED = value


    def set_scenario(self, name: str) -> None:
        """
        Apply the behaviour probabilities of a named scenario.

        Parameters
        ----------
        name : {'optimistic', 'balance', 'pessimistic'}
        """
        if name not in self.SCENARIOS:
            raise ValueError(
                f"Unknown scenario: {name!r}. "
                f"Expected one of {sorted(self.SCENARIOS)}"
            )
        self.set_BASE_CANCEL_PROB(self.SCENARIOS[name])
        self.SCENARIO_NAME = name


    def set_ALPHA_FIXED(self, value: float) -> None:
        """
        Common alpha value imposed on the fixed-alpha variants.

        Parameters
        ----------
        value : float
            Profit/risk trade-off in [0, 1]. The per-station alphas are drawn in
            [0.1, 0.9]: staying inside that interval keeps the variant
            comparable with the rest of the grid.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(
                f"ALPHA_FIXED must be a number, got: {type(value).__name__}"
            )
        if not 0. <= float(value) <= 1.:
            raise ValueError(f"ALPHA_FIXED must be in [0, 1], got: {value}")
        self.ALPHA_FIXED = float(value)

    def set_OFFER_TTL_SLOTS(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"OFFER_TTL_SLOTS must be an int, got: {type(value).__name__}"
            )
        if value < 1:
            raise ValueError(f"OFFER_TTL_SLOTS must be >= 1, got: {value}")
        self.OFFER_TTL_SLOTS = value


    def set_RESERVATION_LEAD_PARAMS(self, value: dict) -> None:
        """
        Bounds of the planning-horizon draw, in slots.

        Parameters
        ----------
        value : dict
            `{'low': int, 'high': int}`, inclusive bounds with 0 <= low <= high.
            `{'low': 0, 'high': 0}` reproduces the historical behaviour
            (reservation for the immediate slot).
        """
        if not isinstance(value, dict):
            raise TypeError(
                f"RESERVATION_LEAD_PARAMS must be a dict, got: "
                f"{type(value).__name__}"
            )

        missing = {'low', 'high'} - set(value)
        if missing:
            raise ValueError(f"Missing keys: {missing}")

        low, high = value['low'], value['high']
        for name, v in (('low', low), ('high', high)):
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(
                    f"RESERVATION_LEAD_PARAMS['{name}'] must be an int, "
                    f"got: {type(v).__name__}"
                )
            if v < 0:
                raise ValueError(
                    f"RESERVATION_LEAD_PARAMS['{name}'] must be >= 0, got: {v}"
                )
        if low > high:
            raise ValueError(
                f"RESERVATION_LEAD_PARAMS: low ({low}) must be <= high ({high})"
            )

        self.RESERVATION_LEAD_PARAMS = {'low': int(low), 'high': int(high)}


    def late_cancel_threshold(self, lead: int) -> int:
        """
        Threshold (in slots before the planned arrival) separating an early from
        a late cancellation, for a reservation whose request → arrival delay is
        `lead`.

        `LATE_CANCEL_REF` (1 h = 12 slots) assumes a reservation taken well in
        advance. Here the delay is often only a few slots (the trip to the
        station is short): applied as is, the absolute threshold classified
        *every* cancellation as late and made the "early" branch unreachable.
        The threshold is therefore bounded by a fraction of the actual delay,
        which guarantees that both regimes exist.
        """
        lead = max(0, int(lead))
        relative = int(lead * self.LATE_CANCEL_FRACTION)
        return max(1, min(self.LATE_CANCEL_REF, relative))


    def max_search_radius(self) -> float:
        """
        Cap of the widened radius: the grid diagonal.

        Beyond it, every station of the world is already eligible — widening
        further cannot discover anything more.
        """
        return float(self.C_GRID) * np.sqrt(2.)


    def set_SCORE_MEMORY(self, value: int) -> None:
        """Number of reservations retained in the reputation score (>= 1)."""
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(
                f"SCORE_MEMORY must be an int, got: {type(value).__name__}"
            )
        if value < 1:
            raise ValueError(f"SCORE_MEMORY must be >= 1, got: {value}")
        self.SCORE_MEMORY = int(value)


    def set_SEARCH_RADIUS_GROWTH(self, value: float) -> None:
        """Widening factor of the radius at each retry (> 1)."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(
                f"SEARCH_RADIUS_GROWTH must be a number, got: "
                f"{type(value).__name__}"
            )
        if float(value) <= 1.:
            raise ValueError(
                f"SEARCH_RADIUS_GROWTH must be > 1 (otherwise the retry "
                f"widens nothing), got: {value}"
            )
        self.SEARCH_RADIUS_GROWTH = float(value)


    def set_MAX_SEARCH_RETRIES(self, value: int) -> None:
        """Retry budget per demand. 0 = no retry."""
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(
                f"MAX_SEARCH_RETRIES must be an int, got: "
                f"{type(value).__name__}"
            )
        if value < 0:
            raise ValueError(f"MAX_SEARCH_RETRIES must be >= 0, got: {value}")
        self.MAX_SEARCH_RETRIES = int(value)


    def min_lead_for_early_cancel(self) -> int:
        """
        Smallest request → arrival delay allowing a cancellation to be *observed*
        as early.

        An early cancellation fires at the earliest at the slot following the
        reservation (`t_c = reservation_slot + 1`, see
        `Simulation._process_cancellations`), hence `slots_left = lead - 1`.
        It is qualified as `early` only if `slots_left > late_cancel_threshold(lead)`.
        Below that threshold, an `early` intent is necessarily realised as
        `late`: the branch is unreachable, which was the behaviour observed on
        the whole grid (`reclassified` saturated at 100%).

        Equals 3 with `LATE_CANCEL_FRACTION = 0.5`. Returns -1 if no delay fits
        (fraction too close to 1).

        The effective delay is `l_n + ceil(travel)`: on a grid where the trip
        takes less than one slot it equals `l_n + 1`, so `l_n >= 2` is enough.
        """
        for lead in range(1, 3 * self.LATE_CANCEL_REF + 2):
            if lead - 1 > self.late_cancel_threshold(lead):
                return lead
        return -1


    def summary(self) -> dict:
        """
        Parameters to record with every result (traceability).
        """
        return {
            'seed':                  self.SEED,
            'scenario':              self.SCENARIO_NAME,
            'total_time':            self.TOTAL_TIME,
            'slot_duration_min':     self.SLOT_DURATION,
            'nb_cars':               self.NB_CARS,
            'nb_stations':           self.NB_STATIONS,
            'nb_societies':          self.NB_SOCIETIES,
            'nb_charg_spot':         dict(self.NB_CHARG_SPOT),
            'grid_m':                self.C_GRID,
            'car_speed_m_per_slot':  self.CAR_SPEED,
            'base_cancel_prob':      dict(self.BASE_CANCEL_PROB),
            'base_points_strategy':  dict(self.BASE_POINTS_STRATEGY),
            'score_memory':          self.SCORE_MEMORY,
            'strategy_noise':        self.STRATEGY_NOISE,
            'w1': self.w1, 'w2': self.w2, 'z': self.z,
            'gamma':                 self.GAMMA,
            'society_update_interval': self.SOCIETY_UPDATE_INTERVAL,
            'min_ray_search':        self.MIN_RAY_SEARCH,
            'max_ray_search':        self.MAX_RAY_SEARCH,
            'coeff_max_dist':        self.COEFF_MAX_DIST,
            'search_radius_growth':  self.SEARCH_RADIUS_GROWTH,
            'max_search_retries':    self.MAX_SEARCH_RETRIES,
            'late_cancel_ref':       self.LATE_CANCEL_REF,
            'late_cancel_fraction':  self.LATE_CANCEL_FRACTION,
            'reservation_lead':      dict(self.RESERVATION_LEAD_PARAMS),
            'offer_ttl_slots':       self.OFFER_TTL_SLOTS,
            'alpha_fixed':           self.ALPHA_FIXED,
        }

    

if __name__ == "__main__":
    
    c = SimulationConfig()
    slot_h = c.SLOT_DURATION / 60
    dist_slot = c.CAR_SPEED          # m/slot
    autonomy_mean = c.CAR_AUTONOMY_PARAMS_KM['mean']
    conso = c.ENERGY_CONSUMPTION['quantity_kW'] / c.ENERGY_CONSUMPTION['distance_unit_m']
    delta_soc = dist_slot * conso / (c.ENERGY_CONSUMPTION['quantity_kW'] * autonomy_mean / 100)

    print(f"Grid              : {c.C_GRID/1e3:.1f} km × {c.C_GRID/1e3:.1f} km")
    print(f"Speed             : {c.CAR_SPEED} m/slot  ({c.CAR_SPEED/1000/slot_h:.0f} km/h)")
    print(f"ΔSoC / slot       : {delta_soc:.5f}  ({1/delta_soc:.0f} slots to empty)")
    print(f"Mean autonomy     : {autonomy_mean} km")
    print(f"Max grid distance crossed with soc=0.10 : {0.10*autonomy_mean:.0f} km >> {c.C_GRID/1e3:.1f} km ✓")
