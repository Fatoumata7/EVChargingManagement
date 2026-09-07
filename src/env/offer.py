"""
offer.py — Charging offer issued by a station.

An offer is a *revocable commitment*: it is issued for a given slot, carries an
expiry date, and references the version of the charger calendar at the time it
was issued. The station revalidates all of these at confirmation time (see
`Station.validate_offer`), which makes it impossible to confirm an offer that has
expired or become inconsistent with the calendar.

Life cycle
----------
    PENDING ──confirm()──> CONFIRMED
       │
       ├──expire()───────> EXPIRED    (not retained by the vehicle, or TTL)
       └──reject(reason)─> REJECTED   (station revalidation failed)
"""


class Offer:

    def __init__(self, station_id, charger_id, t_arr, t_dep, d_prop, distance,
                 offer_id=None, t_issued=0, t_expire=None, charger_version=0,
                 station_load=0.):

        self.station_id = station_id
        self.charger_id = charger_id

        # *Future* occupancy rate of the station at issuing time: share of
        # charger-slots already booked from `t_issued` to the end of the
        # horizon. Carried by the offer — rather than read off the station — so
        # that offer ranking stays a pure function of what the vehicle actually
        # received (`load_aware` baseline, see `Car.rank_offers`).
        self.station_load = float(station_load)

        self.t_arr = t_arr
        self.t_dep = t_dep
        self.d_prop = d_prop

        self.distance = distance

        # ---- Confirmation safety
        self.offer_id        = offer_id if offer_id is not None else f"{station_id}:{charger_id}:{t_arr}"
        self.t_issued        = t_issued
        self.t_expire        = t_expire if t_expire is not None else t_issued + 1
        self.charger_version = charger_version

        self.status = 'PENDING'
        self.reject_reason = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def is_pending(self):
        return self.status == 'PENDING'

    def is_expired(self, t_c):
        """An offer is valid for the slots t_issued <= t_c < t_expire."""
        return t_c >= self.t_expire

    def is_contiguous(self):
        """The proposed duration must cover exactly the interval [t_arr, t_dep)."""
        return (self.t_dep - self.t_arr) == self.d_prop

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def confirm(self):
        self.status = 'CONFIRMED'

    def expire(self):
        """Voluntary drop (offer not retained) or TTL exceeded."""
        if self.status == 'PENDING':
            self.status = 'EXPIRED'

    def reject(self, reason):
        self.status = 'REJECTED'
        self.reject_reason = reason

    # ------------------------------------------------------------------

    def display_offer(self, file):

        print(f"offer_id   = {self.offer_id}", file=file)
        print(f"load       = {self.station_load:.3f}", file=file)
        print(f"station_id = {self.station_id}", file=file)
        print(f"charger_id = {self.charger_id}", file=file)

        print(f"t_arr = {self.t_arr}", file=file)
        print(f"t_dep = {self.t_dep}", file=file)
        print(f"d_prop = {self.d_prop}", file=file)

        print(f"distance = {self.distance * 1e-3:.2f}km", file=file)
        print(f"status = {self.status} (issued={self.t_issued}, "
              f"expire={self.t_expire}, v_charger={self.charger_version})", file=file)

    def __repr__(self):
        return (f"Offer({self.offer_id}, s={self.station_id}, j={self.charger_id}, "
                f"[{self.t_arr},{self.t_dep}) d={self.d_prop}, {self.status})")
