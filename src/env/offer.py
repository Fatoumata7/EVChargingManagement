"""
offer.py
"""

class Offer:

    def __init__(self, station_id, charger_id, t_arr, t_dep, d_prop, distance):

        self.station_id = station_id
        self.charger_id = charger_id

        self.t_arr = t_arr
        self.t_dep = t_dep
        self.d_prop = d_prop

        self.distance = distance

    def display_offer(self, file):

        print(f"station_id = {self.station_id}", file=file)
        print(f"charger_id = {self.charger_id}", file=file)

        print(f"t_arr = {self.t_arr}", file=file)
        print(f"t_dep = {self.t_dep}", file=file)
        print(f"d_prop = {self.d_prop}", file=file)

        print(f"distance = {self.distance * 1e-3:.2f}km", file=file)

    