"""
offer.py — Offre de recharge émise par une station.

Une offre est un *engagement révocable* : elle est émise pour un slot courant,
porte une date d'expiration, et référence la version du calendrier de la borne
au moment de l'émission. La station revalide ces éléments à la confirmation
(cf. `Station.validate_offer`), ce qui interdit de confirmer une offre périmée
ou devenue incohérente avec le calendrier.

Cycle de vie
------------
    PENDING ──confirm()──> CONFIRMED
       │
       ├──expire()───────> EXPIRED    (non retenue par le véhicule, ou TTL)
       └──reject(reason)─> REJECTED   (revalidation station en échec)
"""


class Offer:

    def __init__(self, station_id, charger_id, t_arr, t_dep, d_prop, distance,
                 offer_id=None, t_issued=0, t_expire=None, charger_version=0,
                 station_load=0.):

        self.station_id = station_id
        self.charger_id = charger_id

        # Taux d'occupation *futur* de la station au moment de l'émission :
        # part des créneaux-bornes déjà réservés de `t_issued` à la fin de
        # l'horizon. Porté par l'offre — et non lu sur la station — pour que le
        # classement des offres reste une fonction pure de ce que le véhicule a
        # reçu (baseline `load_aware`, cf. `Car.rank_offers`).
        self.station_load = float(station_load)

        self.t_arr = t_arr
        self.t_dep = t_dep
        self.d_prop = d_prop

        self.distance = distance

        # ---- Sécurisation de la confirmation
        self.offer_id        = offer_id if offer_id is not None else f"{station_id}:{charger_id}:{t_arr}"
        self.t_issued        = t_issued
        self.t_expire        = t_expire if t_expire is not None else t_issued + 1
        self.charger_version = charger_version

        self.status = 'PENDING'
        self.reject_reason = None

    # ------------------------------------------------------------------
    # État
    # ------------------------------------------------------------------

    def is_pending(self):
        return self.status == 'PENDING'

    def is_expired(self, t_c):
        """Une offre est valable pour les slots t_issued <= t_c < t_expire."""
        return t_c >= self.t_expire

    def is_contiguous(self):
        """La durée proposée doit couvrir exactement l'intervalle [t_arr, t_dep)."""
        return (self.t_dep - self.t_arr) == self.d_prop

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def confirm(self):
        self.status = 'CONFIRMED'

    def expire(self):
        """Abandon volontaire (offre non retenue) ou dépassement du TTL."""
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
