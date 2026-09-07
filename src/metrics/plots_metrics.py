"""
plots_metrics.py — Visualization functions for the simulation metrics

Usage:
    from plots_metrics import *
    
    plot_station_demand(metrics)
    plot_user_satisfaction(metrics)
    plot_travel_waiting(metrics)
    plot_response_times(metrics)
    plot_processing_times(metrics)
    plot_breakdowns(breakdown_tracker)
"""

import numpy as np
import math
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle


# ============================================================
# 0. Affichage de la grille 2D avec les stations
# ============================================================

import matplotlib.pyplot as plt

from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle


def plot_stations_2d(
    stations,
    sim_config,
    scenario_name,
    approach_name,
    nb_car,
    figsize=(8, 8),
    padding=5
):
    """
    Display the stations on a 2D grid.

    The stations belonging to the same company
    appear in the same color.

    Parameters
    ----------
    stations : List[Station]

    sim_config : SimulationConfig

    padding : float
        Margin around the grid
    """

    # --------------------------------------------------------
    # Companies present
    # --------------------------------------------------------

    society_ids = sorted({
        s.society_id for s in stations
    })

    # --------------------------------------------------------
    # Couleurs
    # --------------------------------------------------------

    cmap = plt.get_cmap("tab10")

    society_colors = {
        sid: cmap(i % 10)
        for i, sid in enumerate(society_ids)
    }

    # --------------------------------------------------------
    # Figure
    # --------------------------------------------------------

    fig, ax = plt.subplots(figsize=figsize)

    # --------------------------------------------------------
    # Plot stations
    # --------------------------------------------------------

    for s in stations:

        color = society_colors[s.society_id]

        ax.scatter(
            s.loc[0],
            s.loc[1],
            s=180,
            color=color,
            alpha=0.7,
            edgecolors='black'
        )

        # Label station
        ax.text(
            s.loc[0],
            s.loc[1] + 80,
            f"S{s.m}",
            ha='center',
            fontsize=9
        )

    # --------------------------------------------------------
    # Limites de la grille
    # --------------------------------------------------------

    grid_width = sim_config.C_GRID
    grid_height = sim_config.C_GRID

    grid_rect = Rectangle(
        (0, 0),
        grid_width,
        grid_height,
        linewidth=1,
        edgecolor='black',
        facecolor='none'
    )

    ax.add_patch(grid_rect)

    # --------------------------------------------------------
    # Axes
    # --------------------------------------------------------

    ax.set_xlim(
        -padding,
        grid_width + padding
    )

    ax.set_ylim(
        -padding,
        grid_height + padding
    )

    ax.set_aspect('equal')

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    scenario_tag = (
        f"[{scenario_name[:3].upper()}-"
        f"{approach_name.upper()}@{nb_car}]"
    )

    ax.set_title(
        f"{scenario_tag} Charging Stations on 2D Grid",
        fontweight='bold'
    )

    # --------------------------------------------------------
    # Grid
    # --------------------------------------------------------

    ax.grid(
        True,
        linestyle='--',
        alpha=0.3
    )

    # --------------------------------------------------------
    # Company legend
    # --------------------------------------------------------

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker='o',
            color='w',
            label=f"Company {sid}",
            markerfacecolor=society_colors[sid],
            markeredgecolor='black',
            markersize=10
        )
        for sid in society_ids
    ]

    ax.legend(
        handles=legend_elements,
        title="Societies"
    )

    plt.tight_layout()
    plt.show()
    plt.close()


# ============================================================
# 1. Energy demand per station
# ============================================================

def plot_station_demand(metrics, societies, scenario_name, \
                        approach_name, nb_car, figsize=(10, 5)):
    """
    Display the energy demand (kWh) per station.

    The stations belonging to the same company
    appear in the same color.

    Parameters
    ----------
    metrics : MetricsCollector
    societies : List[Society]
    """

    demand = metrics.station_demand()

    # --------------------------------------------------------
    # Mapping station -> society
    # --------------------------------------------------------

    station_to_society = {}

    for soc in societies:
        for s in soc.stations:
            station_to_society[s.m] = soc.f_id

    # --------------------------------------------------------
    # Company colors
    # --------------------------------------------------------

    unique_societies = sorted({
        soc.f_id for soc in societies
    })

    cmap = plt.get_cmap("tab10")

    society_colors = {
        sid: cmap(i % 10)
        for i, sid in enumerate(unique_societies)
    }

    # --------------------------------------------------------
    # Plotting data
    # --------------------------------------------------------

    station_ids = list(demand.keys())
    energies = list(demand.values())

    colors = [
        society_colors.get(
            station_to_society.get(station_id, -1),
            "gray"
        )
        for station_id in station_ids
    ]

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    fig, ax = plt.subplots(figsize=figsize)

    bars = ax.bar(
        station_ids,
        energies,
        color=colors,
        alpha=0.7
    )
    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"

    ax.set_title(f"{scenario_tag} Station Demand", fontweight='bold')
    ax.set_xlabel("Station ID")
    ax.set_ylabel("Energy Demand (kWh)", fontweight='bold')
    ax.set_ylim(top=max(energies)*1.15)

    # Valeurs au-dessus des barres
    for bar, val in zip(bars, energies):
        if val > 0.0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{val:.0f}",
                ha='center',
                va='bottom'
            )

    # --------------------------------------------------------
    # Company legend
    # --------------------------------------------------------

    legend_elements = [
        Patch(
            facecolor=society_colors[sid],
            label=f"Company {sid}"
        )
        for sid in unique_societies
    ]

    ax.legend(
        handles=legend_elements,
        title="Societies"
    )

    plt.tight_layout()
    plt.show()


# ============================================================
# 2. Satisfaction utilisateur
# ============================================================

def plot_user_satisfaction(metrics, scenario_name, approach_name, nb_car,\
                           figsize=(6, 5)):
    """
    Display the user satisfaction metrics.
    """

    sat = metrics.user_request_satisfaction()

    labels = [
        "Exact Satisfaction",
        "Needs Satisfaction"
    ]

    values = [
        sat["exact_satisfaction"] * 100,
        sat["needs_satisfaction"] * 100
    ]

    fig, ax = plt.subplots(figsize=figsize)

    bars = ax.bar(labels, values, color=['blue', 'green'], alpha=0.7)
    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"

    ax.set_ylim(0, 100)
    ax.set_ylabel("Satisfaction (%)", fontweight='bold')
    ax.set_title(f"{scenario_tag} User Request Satisfaction", fontweight='bold')

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val / 2,
            f"{val:.1f}%",
            ha='center',
            va='bottom',
            color='white',
            fontweight='bold'
        )

    plt.tight_layout()
    plt.show()


# ============================================================
# 3. Distance & temps d'attente
# ============================================================

def plot_travel_waiting(metrics, scenario_name, approach_name, nb_car, \
                        bins=20, figsize=(12, 5)):
    """
    Histogrammes :
        - distances parcourues
        - temps d'attente
    """

    if not metrics.acceptance_records:
        print("Aucune acceptance_record disponible.")
        return

    distances = [
        r.distance_km
        for r in metrics.acceptance_records
    ]

    waiting_times = [
        r.waiting_time_h * 60.0
        for r in metrics.acceptance_records
    ]

    fig, axes = plt.subplots(1, 2, figsize=figsize)
    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"

    # Distance
    axes[0].hist(distances, bins=bins)
    axes[0].set_title(f"{scenario_tag} Travel Distance Distribution", fontweight='bold')
    axes[0].set_xlabel("Distance (km)", fontweight='bold')
    axes[0].set_ylabel("#Count")

    # Waiting
    axes[1].hist(waiting_times, bins=bins)
    axes[1].set_title(f"{scenario_tag} Waiting Time Distribution", fontweight='bold')
    axes[1].set_xlabel("Waiting Time (min)", fontweight='bold')
    axes[1].set_ylabel("#Count")

    plt.tight_layout()
    plt.show()


# ============================================================
# 4. Demand response times
# ============================================================

def plot_response_times(metrics, scenario_name, approach_name, \
                        nb_car, figsize=(10, 5)):
    """
    Response time for each demand.
    """

    records = [
        r for r in metrics.demand_timings.values()
        if r.t_response > 0
    ]

    if not records:
        print("No response timing available.")
        return

    demand_ids = [r.demand_id for r in records]
    response_times = [r.response_time_ms for r in records]

    fig, ax = plt.subplots(figsize=figsize)

    ax.plot(
        demand_ids,
        response_times,
        marker='o'
    )

    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"
    ax.set_title(f"{scenario_tag} Demand Response Times", fontweight='bold')
    ax.set_xlabel("Demand ID")
    ax.set_ylabel("Response Time (ms)", fontweight='bold')

    plt.tight_layout()
    plt.show()


# ============================================================
# 5. Temps de traitement par station
# ============================================================

def plot_processing_times(metrics, scenario_name, approach_name, nb_car, figsize=(10, 5)):
    """
    Temps moyen de traitement ILP par station.
    """

    proc = metrics.mean_processing_time_per_station()

    if not proc:
        print("Aucun temps de traitement disponible.")
        return

    station_ids = list(proc.keys())
    times = list(proc.values())

    fig, ax = plt.subplots(figsize=figsize)

    bars = ax.bar(station_ids, times)

    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"
    ax.set_title(f"{scenario_tag} Mean Processing Time per Station", fontweight='bold')
    ax.set_xlabel("Station ID")
    ax.set_ylabel("Processing Time (ms)", fontweight='bold')

    for bar, val in zip(bars, times):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{val:.0f}",
            ha='center',
            va='bottom'
        )

    plt.tight_layout()
    plt.show()


# ============================================================
# 6. Breakdown visualization
# ============================================================

def plot_breakdowns(breakdown_tracker, figsize=(7, 7)):
    """
    Display the positions of the breakdowns.
    """

    data = breakdown_tracker.breakdowns

    if not data:
        print("No breakdown recorded.")
        return

    xs = [b["x"] for b in data]
    ys = [b["y"] for b in data]

    fig, ax = plt.subplots(figsize=figsize)

    ax.scatter(xs, ys, s=80)

    for i, b in enumerate(data):
        ax.text(
            b["x"],
            b["y"],
            f"Car {b['car_id']}"
        )

    ax.set_title("Breakdown Locations")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")

    ax.grid(True)

    plt.tight_layout()
    plt.show()

# ============================================================
# 7. Station strategy (alpha_m)
# ============================================================

def plot_station_strategies(societies, sim_config, scenario_name, approach_name, nb_car):

    total_time = sim_config.TOTAL_TIME
    update_time = sim_config.SOCIETY_UPDATE_INTERVAL

    n_societies = len(societies)

    ncols = 2
    nrows = math.ceil(n_societies / ncols)

    fig, axs = plt.subplots(
        nrows,
        ncols,
        figsize=(10, 4 * nrows)
    )

    axs = np.array(axs).flatten()

    for idx, society in enumerate(societies):

        ax = axs[idx]

        for st in society.stations:

            alpha_values = st.alpha_save

            x_values = [
                (i * (update_time / 12))
                for i in range(len(alpha_values))
            ]

            ax.plot(
                x_values,
                alpha_values,
                marker='o',
                linewidth=2,
                markersize=5,
                label=f"S{st.m}"
            )

        ax.set_title(
            f"Company {society.f_id}",
            fontweight="bold"
        )

        ax.set_xlabel("Time (h)")
        ax.set_ylabel(r"$\alpha_m$")
        ax.set_ylim(0., 1.)

        ax.legend()

    # hide the unused axes
    for idx in range(n_societies, len(axs)):
        axs[idx].set_visible(False)

    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"
    fig.suptitle(
        f"{scenario_tag} Station Strategy Evolution ($\\alpha_m$)",
        fontsize=14,
        fontweight="bold"
    )

    plt.tight_layout()
    plt.show()
    plt.close()


# ============================================================
# 7. Dashboard complet
# ============================================================

def plot_all_metrics(metrics, breakdown_tracker=None):
    """
    Lance toutes les visualisations.
    """

    plot_station_demand(metrics)

    plot_user_satisfaction(metrics)

    plot_travel_waiting(metrics)

    plot_response_times(metrics)

    plot_processing_times(metrics)

    if breakdown_tracker is not None:
        plot_breakdowns(breakdown_tracker)

# ============================================================
# 7. Other metrics
# ============================================================


def plot_society_station_occupancy(societies, scenario_name,
                 approach_name, nb_car):
    """
    Display, for each company, the mean occupancy rate of each of its
    stations.

    - 4 subplots (2x2)
    - one bar = one station
    - red line = mean over the stations of the company
    - same visual bar width on every subplot
    - y axis between 0 and 1.1
    """

    # Largest number of stations across the companies
    max_nb_stations = max(
        len(society.stations)
        for society in societies
    )

    fig, axs = plt.subplots(
        2,
        2,
        figsize=(12, 10)
    )

    axs = axs.flatten()

    for idx, society in enumerate(societies):

        ax = axs[idx]

        station_ids = []
        station_occ = []

        # --------------------------------------------
        # Taux moyen d'occupation par station
        # --------------------------------------------

        for station in society.stations:

            occ_rate = np.mean(
                station.schedule != -1
            )

            station_ids.append(station.m)
            station_occ.append(occ_rate)

        if len(station_occ) == 0:
            continue

        mean_society_occ = np.mean(station_occ)

        # --------------------------------------------
        # Barres
        # --------------------------------------------

        x_pos = np.arange(len(station_ids))

        bars = ax.bar(
            x_pos,
            station_occ,
            width=0.6,
            alpha=0.8
        )

        # Same horizontal scale for all
        ax.set_xlim(
            -0.5,
            max_nb_stations - 0.5
        )

        # Station IDs as tick labels
        ax.set_xticks(x_pos)

        ax.set_xticklabels(
            [f"S{sid}" for sid in station_ids],
            rotation=45
        )

        # --------------------------------------------
        # Ligne moyenne
        # --------------------------------------------

        ax.axhline(
            mean_society_occ,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Mean = {mean_society_occ:.2f}"
        )

        # --------------------------------------------
        # Valeurs sur les barres
        # --------------------------------------------

        for bar in bars:

            height = bar.get_height()

            if height > 0:

                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 0.02,
                    f"{height:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold"
                )

        # --------------------------------------------
        # Mise en forme
        # --------------------------------------------

        society_id = getattr(
            society,
            "society_id",
            getattr(society, "f_id", idx)
        )

        ax.set_title(
            f"Company {society_id}",
            fontweight="bold"
        )

        ax.set_xlabel("Station")
        ax.set_ylabel("Mean Occupancy Rate")

        ax.set_ylim(0, 1.1)

        ax.grid(
            axis="y",
            linestyle="--",
            alpha=0.3
        )

        ax.legend()

    # Hide the unused subplots
    for idx in range(len(societies), len(axs)):
        axs[idx].set_visible(False)

    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"
    fig.suptitle(
        f"{scenario_tag} Average Charger Occupancy Rate per Station",
        fontsize=14,
        fontweight="bold"
    )

    plt.tight_layout()
    plt.show()
    plt.close()


def plot_station_no_show(
    societies,
    scenario_name,
    approach_name,
    nb_car
):
    """
    Bar chart of the number of no-shows per station.

    - The stations of the same company share the same color.
    - The legend also shows the mean number of no-shows
      over the stations of each company.
    """

    fig, ax = plt.subplots(figsize=(14, 6))

    cmap = plt.get_cmap("tab10")

    x_pos = []
    labels = []
    colors = []
    no_show_values = []

    society_means = {}

    current_x = 0

    # --------------------------------------------------
    # Building the data
    # --------------------------------------------------

    for soc_idx, society in enumerate(societies):

        color = cmap(soc_idx)

        station_values = []

        for station in society.stations:

            x_pos.append(current_x)
            labels.append(f"S{station.m}")
            colors.append(color)

            no_show_values.append(station.nb_no_show)
            station_values.append(station.nb_no_show)

            current_x += 1

        society_means[society.f_id] = (
            np.mean(station_values)
            if len(station_values) > 0 else 0
        )

        # visual gap between companies
        current_x += 1

    # --------------------------------------------------
    # Diagramme en barres
    # --------------------------------------------------

    bars = ax.bar(
        x_pos,
        no_show_values,
        color=colors,
        alpha=0.8,
        width=0.8
    )

    # Valeurs sur les barres
    for bar in bars:

        height = bar.get_height()

        if height > 0:

            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height + 0.05,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold"
            )

    # --------------------------------------------------
    # Mise en forme
    # --------------------------------------------------

    ax.set_xticks(x_pos)

    ax.set_xticklabels(
        labels,
        rotation=45
    )

    ax.set_xlabel("Station ID")
    ax.set_ylabel("Number of No-Shows")

    scenario_tag = (
        f"[{scenario_name[:3].upper()}-"
        f"{approach_name.upper()}@{nb_car}]"
    )

    ax.set_title(
        f"{scenario_tag} Number of No-Shows per Station",
        fontweight="bold"
    )

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.3
    )

    # --------------------------------------------------
    # Company legend + mean
    # --------------------------------------------------

    legend_elements = []

    for soc_idx, society in enumerate(societies):

        mean_val = society_means[society.f_id]

        legend_elements.append(
            Line2D(
                [0],
                [0],
                color=cmap(soc_idx),
                lw=6,
                label=f"C{society.f_id} (mean={mean_val:.2f})"
            )
        )

    ax.legend(
        handles=legend_elements,
        title="Companies"
    )

    plt.tight_layout()
    plt.show()
    plt.close()


def plot_society_station_occupancy(societies, scenario_name,
                 approach_name, nb_car):
    """
    Display, for each company, the mean occupancy rate of each of its
    stations.

    - 4 subplots (2x2)
    - one bar = one station
    - red line = mean over the stations of the company
    - same visual bar width on every subplot
    - y axis between 0 and 1.1
    """

    # Largest number of stations across the companies
    max_nb_stations = max(
        len(society.stations)
        for society in societies
    )

    fig, axs = plt.subplots(
        2,
        2,
        figsize=(12, 10)
    )

    axs = axs.flatten()

    for idx, society in enumerate(societies):

        ax = axs[idx]

        station_ids = []
        station_occ = []

        # --------------------------------------------
        # Taux moyen d'occupation par station
        # --------------------------------------------

        for station in society.stations:

            occ_rate = np.mean(
                station.schedule != -1
            )

            station_ids.append(station.m)
            station_occ.append(occ_rate)

        if len(station_occ) == 0:
            continue

        mean_society_occ = np.mean(station_occ)

        # --------------------------------------------
        # Barres
        # --------------------------------------------

        x_pos = np.arange(len(station_ids))

        bars = ax.bar(
            x_pos,
            station_occ,
            width=0.6,
            alpha=0.8
        )

        # Same horizontal scale for all
        ax.set_xlim(
            -0.5,
            max_nb_stations - 0.5
        )

        # Station IDs as tick labels
        ax.set_xticks(x_pos)

        ax.set_xticklabels(
            [f"S{sid}" for sid in station_ids],
            rotation=45
        )

        # --------------------------------------------
        # Ligne moyenne
        # --------------------------------------------

        ax.axhline(
            mean_society_occ,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Mean = {mean_society_occ:.2f}"
        )

        # --------------------------------------------
        # Valeurs sur les barres
        # --------------------------------------------

        for bar in bars:

            height = bar.get_height()

            if height > 0:

                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 0.02,
                    f"{height:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold"
                )

        # --------------------------------------------
        # Mise en forme
        # --------------------------------------------

        society_id = getattr(
            society,
            "society_id",
            getattr(society, "f_id", idx)
        )

        ax.set_title(
            f"Company {society_id}",
            fontweight="bold"
        )

        ax.set_xlabel("Station")
        ax.set_ylabel("Mean Occupancy Rate")

        ax.set_ylim(0, 1.1)

        ax.grid(
            axis="y",
            linestyle="--",
            alpha=0.3
        )

        ax.legend()

    # Hide the unused subplots
    for idx in range(len(societies), len(axs)):
        axs[idx].set_visible(False)

    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"
    fig.suptitle(
        f"{scenario_tag} Average Charger Occupancy Rate per Station",
        fontsize=14,
        fontweight="bold"
    )

    plt.tight_layout()
    plt.show()
    plt.close()


def plot_society_station_rejected_request(societies, scenario_name,
                 approach_name, nb_car):
    """
    Display, for each company, the mean occupancy rate of each of its
    stations.

    - 4 subplots (2x2)
    - one bar = one station
    - red line = mean over the stations of the company
    - same visual bar width on every subplot
    - y axis between 0 and 1.1
    """

    # Largest number of stations across the companies
    max_nb_stations = max(
        len(society.stations)
        for society in societies
    )

    fig, axs = plt.subplots(
        2,
        2,
        figsize=(12, 10)
    )

    axs = axs.flatten()

    for idx, society in enumerate(societies):

        ax = axs[idx]

        station_ids = []
        station_nb_rej_req = []

        # --------------------------------------------
        # Taux moyen d'occupation par station
        # --------------------------------------------

        for station in society.stations:

            station_ids.append(station.m)
            station_nb_rej_req.append(station.nb_station_level_rejections)

        if len(station_nb_rej_req) == 0:
            continue

        mean_society_occ = np.mean(station_nb_rej_req)

        # --------------------------------------------
        # Barres
        # --------------------------------------------

        x_pos = np.arange(len(station_ids))

        bars = ax.bar(
            x_pos,
            station_nb_rej_req,
            width=0.6,
            alpha=0.8
        )

        # Same horizontal scale for all
        ax.set_xlim(
            -0.5,
            max_nb_stations - 0.5
        )

        # Station IDs as tick labels
        ax.set_xticks(x_pos)

        ax.set_xticklabels(
            [f"S{sid}" for sid in station_ids],
            rotation=45
        )

        # --------------------------------------------
        # Ligne moyenne
        # --------------------------------------------

        ax.axhline(
            mean_society_occ,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Mean = {mean_society_occ:.2f}"
        )

        # --------------------------------------------
        # Valeurs sur les barres
        # --------------------------------------------

        for bar in bars:

            height = bar.get_height()

            if height > 0:

                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 0.02,
                    f"{height:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold"
                )

        # --------------------------------------------
        # Mise en forme
        # --------------------------------------------

        society_id = getattr(
            society,
            "society_id",
            getattr(society, "f_id", idx)
        )

        ax.set_title(
            f"Company {society_id}",
            fontweight="bold"
        )

        ax.set_xlabel("Station")
        ax.set_ylabel("#Rejected Requests")

        ax.set_ylim(0, 40)

        ax.grid(
            axis="y",
            linestyle="--",
            alpha=0.3
        )

        ax.legend()

    # Hide the unused subplots
    for idx in range(len(societies), len(axs)):
        axs[idx].set_visible(False)

    scenario_tag = f"[{scenario_name[:3].upper()}-{approach_name.upper()}@{nb_car}]"
    fig.suptitle(
        f"{scenario_tag} Number of rejected requests per Station",
        fontsize=14,
        fontweight="bold"
    )

    plt.tight_layout()
    plt.show()
    plt.close()



def plot_car_rejected(
    cars,
    scenario_name,
    approach_name,
    nb_car
):
    """
    Bar chart of the number of rejected demands per vehicle.

    - One bar per vehicle (car.nb_rejected).
    - A horizontal line showing the global mean.
    """
    if not cars:
        print("The vehicle list is empty.")
        return

    fig, ax = plt.subplots(figsize=(14, 6))

    # --------------------------------------------------
    # Building the data
    # --------------------------------------------------
    x_pos = []
    labels = []
    rejected_values = []

    for idx, car in enumerate(cars):
        x_pos.append(idx)
        # Assumes the car object has an id; otherwise the index idx is used
        car_id = getattr(car, 'id', idx)
        labels.append(f"Car {car_id}")
        rejected_values.append(getattr(car, 'nb_rejected', 0))

    # Calcul de la moyenne globale
    mean_rejected = np.mean(rejected_values) if rejected_values else 0

    # --------------------------------------------------
    # Diagramme en barres
    # --------------------------------------------------
    bars = ax.bar(
        x_pos,
        rejected_values,
        color="skyblue",
        alpha=0.8,
        width=0.8,
        edgecolor="black",
        linewidth=0.5
    )

    # Affichage des valeurs exactes au-dessus des barres
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height + 0.05,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold"
            )

    # --------------------------------------------------
    # Ligne de moyenne globale
    # --------------------------------------------------
    ax.axhline(
        mean_rejected, 
        color="red", 
        linestyle="--", 
        linewidth=1.5, 
        label=f"Global Mean ({mean_rejected:.2f})"
    )

    # --------------------------------------------------
    # Mise en forme
    # --------------------------------------------------
    ax.set_xticks(x_pos)
    ax.set_xticklabels(
        labels,
        rotation=45,
        ha="right"
    )

    ax.set_xlabel("Vehicle ID")
    ax.set_ylabel("Number of Rejected Requests")

    scenario_tag = (
        f"[{scenario_name[:3].upper()}-"
        f"{approach_name.upper()}@{nb_car}]"
    )

    ax.set_title(
        f"{scenario_tag} Number of Rejected Requests per Vehicle",
        fontweight="bold"
    )

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.3
    )

    # Legend entry for the mean line
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.show()
    plt.close()



def plot_station_requests(
    stations,
    scenario_name,
    approach_name,
    nb_car
):
    """
    Bar chart of the number of requests per station.

    - One bar per station (station.nb_request).
    - A horizontal line showing the global mean of the requests.
    """
    if not stations:
        print("The station list is empty.")
        return

    fig, ax = plt.subplots(figsize=(14, 6))

    # --------------------------------------------------
    # Building the data
    # --------------------------------------------------
    x_pos = []
    labels = []
    request_values = []

    for idx, station in enumerate(stations):
        x_pos.append(idx)
        # Utilise l'attribut m de la station (comme dans ton code initial), sinon son id ou l'index
        station_id = getattr(station, 'm', getattr(station, 'id', idx))
        labels.append(f"Station {station_id}")
        request_values.append(getattr(station, 'nb_request', 0))

    # Calcul de la moyenne globale
    mean_requests = np.mean(request_values) if request_values else 0

    # --------------------------------------------------
    # Diagramme en barres
    # --------------------------------------------------
    bars = ax.bar(
        x_pos,
        request_values,
        color="lightgreen",
        alpha=0.8,
        width=0.8,
        edgecolor="black",
        linewidth=0.5
    )

    # Affichage des valeurs exactes au-dessus des barres
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height + 0.05,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold"
            )

    # --------------------------------------------------
    # Ligne de moyenne globale
    # --------------------------------------------------
    ax.axhline(
        mean_requests, 
        color="red", 
        linestyle="--", 
        linewidth=1.5, 
        label=f"Global Mean ({mean_requests:.2f})"
    )

    # --------------------------------------------------
    # Mise en forme
    # --------------------------------------------------
    ax.set_xticks(x_pos)
    ax.set_xticklabels(
        labels,
        rotation=45,
        ha="right"
    )

    ax.set_xlabel("Station ID")
    ax.set_ylabel("Number of Requests")

    scenario_tag = (
        f"[{scenario_name[:3].upper()}-"
        f"{approach_name.upper()}@{nb_car}]"
    )

    ax.set_title(
        f"{scenario_tag} Number of Requests per Station",
        fontweight="bold"
    )

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.3
    )

    # Legend entry for the mean line
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.show()
    plt.close()



def plot_car_rejected_hist(
    cars,
    scenario_name,
    approach_name,
    nb_car
):
    """
    Histogram of the number of rejected demands per vehicle.
    Suited to a large number of vehicles (e.g. 250).
    """
    if not cars:
        print("The vehicle list is empty.")
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    # --------------------------------------------------
    # Extracting the data
    # --------------------------------------------------
    rejected_values = [getattr(car, 'nb_rejected', 0) for car in cars]
    
    # Computing the statistics
    mean_rejected = np.mean(rejected_values) if rejected_values else 0
    max_rejected = max(rejected_values) if rejected_values else 0

    # --------------------------------------------------
    # Building the histogram
    # --------------------------------------------------
    # Dynamic definition of the bins (histogram bars)
    # For integer values, bins of width 1 or 2 avoid empty gaps
    bins_edges = np.arange(0, max_rejected + 2, max(1, max_rejected // 15))

    counts, bins, patches = ax.hist(
        rejected_values,
        bins=bins_edges,
        color="skyblue",
        alpha=0.8,
        edgecolor="black",
        linewidth=0.8,
        label="Vehicles distribution"
    )

    # --------------------------------------------------
    # Ligne de moyenne globale
    # --------------------------------------------------
    ax.axvline(
        mean_rejected, 
        color="red", 
        linestyle="--", 
        linewidth=2, 
        label=f"Global Mean ({mean_rejected:.2f})"
    )

    # --------------------------------------------------
    # Mise en forme
    # --------------------------------------------------
    ax.set_xlabel("Number of Rejected Requests", fontsize=11)
    ax.set_ylabel("Number of Vehicles (Frequency)", fontsize=11)

    scenario_tag = (
        f"[{scenario_name[:3].upper()}-"
        f"{approach_name.upper()}@{nb_car}]"
    )

    ax.set_title(
        f"{scenario_tag} Distribution of Rejected Requests per Vehicle (N={len(cars)})",
        fontweight="bold",
        fontsize=13
    )

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.3
    )

    # Legend placement
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.show()
    plt.close()