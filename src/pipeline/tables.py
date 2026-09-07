"""
tables.py — Extraction of tidy tables from a simulation.

The figures never read the simulation objects: they consume these tables,
written to disk at the end of every case. Practical consequence: a chart can be
fixed and regenerated without re-running a single simulation (`cli.py report`).

One table = a list of flat dictionaries, all carrying the identity of the case
(scenario, fleet, method), so that the tables of several cases concatenate with
no loss of information.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import src.experiments.methods as methods
from src.pipeline.params import CaseParams

# Columns of summary.csv, in display order.
SUMMARY_FIELDS: tuple[str, ...] = (
    # identity
    'scenario', 'nb_cars', 'method', 'seed', 'world_seed', 'grid_seed',
    'nb_stations', 'nb_societies', 'total_time', 'wall_time_s',
    # ablation plan: the active flags, so that summary.csv reads on its own
    'method_label', 'method_family', 'broadcast', 'reputation', 'adaptation',
    'offer_choice', 'alpha_mode', 'reputation_scope', 'score_weighting',
    # satisfaction
    'exact_satisfaction', 'needs_satisfaction', 'nb_cars_evaluated',
    'mean_travel_distance_km', 'mean_waiting_time_min',
    # demands & latency
    'nb_demands', 'nb_demands_answered', 'nb_demands_confirmed',
    'answer_rate', 'confirm_rate', 'mean_offers_per_demand',
    'first_offer_ms_mean', 'last_offer_ms_mean', 'last_offer_ms_p95',
    'selection_ms_mean', 'confirmation_ms_mean', 'total_ms_mean', 'total_ms_p95',
    'mean_confirm_attempts', 'mean_processing_ms',
    # reservation outcomes
    'nb_reservations', 'nb_pres', 'nb_no_show', 'nb_early_canc', 'nb_late_canc',
    'nb_breakdown_canc', 'nb_unresolved',
    'rate_pres', 'rate_abs', 'rate_early', 'rate_late',
    'intent_pres', 'intent_abs', 'intent_early', 'intent_late',
    'early_intent_realized_late', 'mean_lead_slots',
    # offer protocol & stations
    'nb_offer_issued', 'nb_offer_expired', 'nb_confirm_refused',
    'nb_stale_confirm', 'nb_station_level_rejections', 'nb_station_requests',
    'mean_occupancy_rate', 'mean_service_rate', 'nb_slots_reserved',
    'nb_slots_served', 'slot_waste_rate', 'total_station_demand_kwh',
    # health of the run
    'nb_breakdowns', 'nb_diagnostics', 'invariant_ok',
)


def _waste_rate(stations: Sequence[Mapping[str, Any]]) -> float | None:
    """Share of the reserved charger-slots that were never used. `None` if none."""
    reserved = sum(s.get('nb_slots_reserved', 0) for s in stations)
    served = sum(s.get('nb_slots_served', 0) for s in stations)
    if reserved <= 0:
        return None
    return round(1. - served / reserved, 4)


def _identity(result: Mapping[str, Any]) -> dict:
    cfg = result['config']
    return {
        'scenario':        result['scenario'],
        'nb_cars':         cfg['nb_cars'],
        'method':          result['mode'],
        'seed':            result['seed'],
        'world_seed':      result.get('world_seed'),
        'grid_seed':       result.get('grid_seed'),
    }


def method_flags(result: Mapping[str, Any]) -> dict:
    """
    Flags of the method of a case, ready to join `summary.csv`.

    Results have carried `method_flags` since the ablation study was
    introduced; for an earlier run, the flags are recovered from the registry
    using the method name alone. An old campaign therefore stays analysable with
    the current tools.
    """
    stored = result.get('method_flags')
    if stored:
        spec = methods.MethodSpec(**stored)
    else:
        spec = methods.resolve(result['mode'])
    return spec.flags()


def summary_row(result: Mapping[str, Any]) -> dict:
    """Aggregate the result of a case into one row of `summary.csv`."""
    cfg = result['config']
    met = result['metrics']
    sat = met['user_request_satisfaction']
    lat = met['latency']
    beh = result['behaviors']
    stations = result['stations']

    def total(key: str) -> int:
        return sum(s.get(key, 0) for s in stations)

    nb_stations = max(1, len(stations))
    proc = met.get('mean_processing_time_ms') or {}

    row = _identity(result)
    row.update(method_flags(result))
    row.update({
        'nb_stations':  cfg['nb_stations'],
        'nb_societies': cfg['nb_societies'],
        'total_time':   cfg['total_time'],
        'wall_time_s':  result.get('wall_time_s'),

        'exact_satisfaction':      sat['exact_satisfaction'],
        'needs_satisfaction':      sat['needs_satisfaction'],
        'nb_cars_evaluated':       sat['nb_cars_evaluated'],
        'mean_travel_distance_km': met['mean_travel_distance_km'],
        'mean_waiting_time_min':   round(met['mean_waiting_time_h'] * 60, 4),
        'mean_processing_ms':      (round(sum(proc.values()) / len(proc), 3)
                                    if proc else None),

        'nb_reservations':             total('nb_reservations'),
        'nb_pres':                     total('nb_pres'),
        'nb_no_show':                  total('nb_no_show'),
        'nb_early_canc':               total('nb_early_canc'),
        'nb_late_canc':                total('nb_late_canc'),
        'nb_breakdown_canc':           total('nb_breakdown_canc'),
        'nb_unresolved':               total('nb_unresolved'),
        'nb_offer_issued':             total('nb_offer_issued'),
        'nb_offer_expired':            total('nb_offer_expired'),
        'nb_confirm_refused':          total('nb_confirm_refused'),
        'nb_stale_confirm':            total('nb_stale_confirm'),
        'nb_station_level_rejections': total('nb_station_level_rejections'),
        'nb_station_requests':         total('nb_request'),
        'mean_occupancy_rate': round(
            sum(s['occupancy_rate'] for s in stations) / nb_stations, 4),
        'mean_service_rate': round(
            sum(s.get('service_rate', 0.) for s in stations) / nb_stations, 4),
        'nb_slots_reserved': total('nb_slots_reserved'),
        'nb_slots_served':   total('nb_slots_served'),
        # Share of the slots booked and then never used: the direct cost of
        # no-shows and late cancellations for the operator.
        'slot_waste_rate':   _waste_rate(stations),
        'total_station_demand_kwh': round(
            sum(met['station_demand_kWh'].values()), 3),

        'early_intent_realized_late': beh['reclassified'].get('early->late', 0),
        'mean_lead_slots':            beh.get('mean_lead_slots'),
        'nb_diagnostics':             len(beh.get('diagnostics', [])),
        'nb_breakdowns':              result['breakdowns']['nb_breakdowns'],
        'invariant_ok':               result['invariant_ok'],
    })

    for key in ('nb_demands', 'nb_demands_answered', 'nb_demands_confirmed',
                'answer_rate', 'confirm_rate', 'mean_offers_per_demand',
                'first_offer_ms_mean', 'last_offer_ms_mean', 'last_offer_ms_p95',
                'selection_ms_mean', 'confirmation_ms_mean',
                'total_ms_mean', 'total_ms_p95', 'mean_confirm_attempts'):
        row[key] = lat.get(key)

    for outcome in ('pres', 'abs', 'early', 'late'):
        row[f'rate_{outcome}'] = beh['observed_rates'].get(outcome)
        row[f'intent_{outcome}'] = beh['intent_rates'].get(outcome)

    return row


# ----------------------------------------------------------------------
# Detailed tables
# ----------------------------------------------------------------------

def station_table(result: Mapping[str, Any]) -> list[dict]:
    """One row per station: capacity, outcomes, occupancy, energy."""
    identity = _identity(result)
    demand_kwh = result['metrics']['station_demand_kWh']
    rows = []
    for station in result['stations']:
        row = dict(identity)
        row.update(station)
        row['demand_kwh'] = demand_kwh.get(str(station['station_id']),
                                          demand_kwh.get(station['station_id'], 0.))
        rows.append(row)
    return rows


def latency_table(metrics, result: Mapping[str, Any]) -> list[dict]:
    """One row per demand: complete decomposition of the latency."""
    identity = _identity(result)
    return [dict(identity, **row) for row in metrics.latency_rows()]


def acceptance_table(metrics, result: Mapping[str, Any]) -> list[dict]:
    """One row per accepted offer: distance driven, waiting time."""
    identity = _identity(result)
    return [
        dict(identity,
             car_id=record.car_id,
             station_id=record.station_id,
             distance_km=round(record.distance_km, 4),
             waiting_time_min=round(record.waiting_time_h * 60, 4))
        for record in metrics.acceptance_records
    ]


def alpha_table(societies: Sequence, result: Mapping[str, Any]) -> list[dict]:
    """Trajectory of the alpha parameter (profit / risk trade-off) per station."""
    identity = _identity(result)
    rows = []
    for society in societies:
        for station in society.stations:
            for step, alpha in enumerate(station.alpha_save):
                rows.append(dict(identity,
                                 society_id=society.f_id,
                                 station_id=station.m,
                                 update_step=step,
                                 alpha=round(float(alpha), 6)))
    return rows


def behavior_table(result: Mapping[str, Any]) -> list[dict]:
    """One row per (intent, outcome): the rates actually observed."""
    identity = _identity(result)
    beh = result['behaviors']
    rows = []
    for outcome, count in sorted(beh['observed_counts'].items()):
        rows.append(dict(identity, kind='observed', label=outcome, count=count,
                         rate=beh['observed_rates'].get(outcome)))
    for intent, count in sorted(beh['intent_counts'].items()):
        rows.append(dict(identity, kind='intent', label=intent, count=count,
                         rate=beh['intent_rates'].get(intent)))
    for label, count in sorted(beh['reclassified'].items()):
        rows.append(dict(identity, kind='reclassified', label=label,
                         count=count, rate=None))
    return rows


def case_tables(sim, result: Mapping[str, Any], *,
                with_latency: bool = True) -> dict[str, list[dict]]:
    """
    Every table of a case, ready to be written.

    `with_latency` isolates the only bulky table (one row per demand).
    """
    tables = {
        'stations':  station_table(result),
        'behaviors': behavior_table(result),
        'acceptances': acceptance_table(sim.metrics, result),
        'alpha':     alpha_table(sim.societies, result),
    }
    if with_latency:
        tables['latency'] = latency_table(sim.metrics, result)
    return {name: rows for name, rows in tables.items() if rows}


# ----------------------------------------------------------------------
# Campaign tables: the shared grid and fleets
# ----------------------------------------------------------------------
# Written once per run, before any simulation. They carry `grid_m` so that a
# figure can be drawn from the CSV alone, without re-reading the configuration
# nor the JSON specs.

def grid_station_table(grid) -> list[dict]:
    """One row per station: position, owning company, chargers, alpha."""
    strategies = {s['f_id']: s['strategy'] for s in grid.societies}
    rows = []
    for station in grid.stations:
        society_id = station['society_id']
        row = {
            'grid_seed':     grid.seed,
            'grid_m':        grid.grid_m,
            'station_id':    station['m'],
            'society_id':    society_id,
            'x_m':           station['loc'][0],
            'y_m':           station['loc'][1],
            'nb_charg_spot': station['nb_charg_spot'],
            'alpha_init':    station['alpha'],
        }
        # The strategy belongs to the company: copying it here avoids a join
        # for the most frequent read (a station and its strategy).
        for key, value in sorted(strategies.get(society_id, {}).items()):
            row[f'strategy_{key}'] = value
        rows.append(row)
    return rows


def grid_society_table(grid) -> list[dict]:
    """One row per company: position, point strategy, stations owned."""
    rows = []
    for society in grid.societies:
        owned = grid.stations_of(society['f_id'])
        row = {
            'grid_seed':      grid.seed,
            'grid_m':         grid.grid_m,
            'society_id':     society['f_id'],
            'x_m':            society['loc'][0],
            'y_m':            society['loc'][1],
            'nb_stations':    len(owned),
            'nb_charg_spot':  sum(s['nb_charg_spot'] for s in owned),
        }
        for key, value in sorted(society['strategy'].items()):
            row[f'strategy_{key}'] = value
        rows.append(row)
    return rows


def fleet_table(fleet) -> list[dict]:
    """
    One row per vehicle: initial position and static attributes.

    `theta` is absent from it: it depends on the scenario and is found in the
    behaviour tables of each case.
    """
    rows = []
    for car in fleet.cars:
        row = {
            'fleet_seed':      fleet.seed,
            'grid_m':          fleet.grid_m,
            'nb_cars':         fleet.nb_cars,
            'car_id':          car['idx'],
            'x_m':             car['loc'][0],
            'y_m':             car['loc'][1],
            'soc_init':        car['soc_init'],
            'autonomy_km':     car['autonomy'] / 1e3,
            'soc_threshold_km': car['soc_threshold_m'] / 1e3,
            'charging_power':  car['charging_power'],
        }
        for key, value in sorted(car['pref'].items()):
            row[f'pref_{key}'] = value
        for key, value in car['behavior_noise'].items():
            row[f'noise_{key}'] = value
        rows.append(row)
    return rows
