import numpy as np
import pandas as pd


def check_station_metrics(station):
    """
    Check that every confirmed reservation received exactly one outcome.

    Two outcomes come on top of the four behavioural ones: `breakdown` (vehicle
    that broke down before its session, reservation released) and `unresolved`
    (reservation still open at the end of the horizon). Without them the
    invariant was structurally false as soon as a breakdown occurred or a
    reservation ran past the end of the simulation.
    """

    lhs = station.nb_reservations

    rhs = (
        station.nb_pres
        + station.nb_no_show
        + station.nb_early_canc
        + station.nb_late_canc
        + station.nb_breakdown_canc
        + station.nb_unresolved
    )

    assert lhs == rhs, (
        f"Station {station.m}: "
        f"{lhs} reservations != {rhs} outcomes "
        f"(pres={station.nb_pres}, abs={station.nb_no_show}, "
        f"early={station.nb_early_canc}, late={station.nb_late_canc}, "
        f"breakdown={station.nb_breakdown_canc}, "
        f"unresolved={station.nb_unresolved})"
    )

def create_station_occupancy_dataframe(societies):
    """
    Build a DataFrame holding the occupancy rate of every charger of every
    station.

    Columns:
    --------
    id_society
    id_station
    charger_1
    charger_2
    ...
    charger_6
    mean_occupancy_rate
    """

    rows = []

    for society in societies:

        for station in society.stations:

            # occupancy rate of each charger
            occupancy_rates = np.mean(
                station.schedule != -1,
                axis=1
            )

            row = {
                "id_society": society.f_id,
                "id_station": station.m,
            }

            # columns charger_1 ... charger_6
            for j in range(6):

                if j < len(occupancy_rates):
                    row[f"charger_{j+1}"] = occupancy_rates[j]
                else:
                    row[f"charger_{j+1}"] = np.nan

            # mean over the chargers of the station
            row["mean_occupancy_rate"] = np.mean(occupancy_rates)

            rows.append(row)

    df = pd.DataFrame(rows)

    return df


def create_station_reservation_dataframe(societies):
    """
    Build a DataFrame holding the reservation statistics of every station.

    Columns:
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

    The percentages are between 0 and 1.
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