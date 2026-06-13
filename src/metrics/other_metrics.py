import numpy as np
import pandas as pd

import numpy as np
import pandas as pd


def check_station_metrics(station):

    lhs = station.nb_reservations

    rhs = (
        station.nb_pres
        + station.nb_no_show
        + station.nb_early_canc
        + station.nb_late_canc
    )

    assert lhs == rhs, (
        f"Station {station.m}: "
        f"{lhs} reservations != {rhs} outcomes"
    )

def create_station_occupancy_dataframe(societies):
    """
    Crée un DataFrame contenant le taux d'occupation
    de chaque borne de chaque station.

    Colonnes :
    ----------
    id_society
    id_station
    borne_1
    borne_2
    ...
    borne_6
    mean_occupancy_rate
    """

    rows = []

    for society in societies:

        for station in society.stations:

            # taux d'occupation de chaque borne
            occupancy_rates = np.mean(
                station.schedule != -1,
                axis=1
            )

            row = {
                "id_society": society.f_id,
                "id_station": station.m,
            }

            # colonnes borne_1 ... borne_6
            for j in range(6):

                if j < len(occupancy_rates):
                    row[f"borne_{j+1}"] = occupancy_rates[j]
                else:
                    row[f"borne_{j+1}"] = np.nan

            # moyenne des bornes de la station
            row["mean_occupancy_rate"] = np.mean(occupancy_rates)

            rows.append(row)

    df = pd.DataFrame(rows)

    return df


def create_station_reservation_dataframe(societies):
    """
    Crée un DataFrame contenant les statistiques de réservation
    de chaque station.

    Colonnes :
        - id_society
        - id_station
        - nb_reservation
        - nb_pres
        - nb_abs
        - nb_early
        - nb_late
        - p_pres
        - p_abs
        - p_early
        - p_late

    Les pourcentages sont compris entre 0 et 1.
    """

    rows = []

    for society in societies:

        for station in society.stations:

            nb_res = station.nb_reservations
            nb_pres = station.nb_pres
            nb_abs = station.nb_no_show
            nb_early = station.nb_early_canc
            nb_late = station.nb_late_canc

            if nb_res > 0:

                p_pres = nb_pres / nb_res
                p_abs = nb_abs / nb_res
                p_early = nb_early / nb_res
                p_late = nb_late / nb_res

            else:

                p_pres = np.nan
                p_abs = np.nan
                p_early = np.nan
                p_late = np.nan

            rows.append({
                "id_society": society.f_id,
                "id_station": station.m,
                "nb_reservation": nb_res,
                "nb_pres": nb_pres,
                "nb_abs": nb_abs,
                "nb_early": nb_early,
                "nb_late": nb_late,
                "p_pres": p_pres,
                "p_abs": p_abs,
                "p_early": p_early,
                "p_late": p_late
            })

    df = pd.DataFrame(rows)

    return df