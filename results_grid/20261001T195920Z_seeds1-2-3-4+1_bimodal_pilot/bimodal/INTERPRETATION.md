# Bimodal pilot — interpretation (exploratory, 5 seeds)

**Setup.**
- Population: 125 high-presence (H) and 125 low-presence (L) vehicles.
- Network: 40 two-charger stations.
- Matched comparisons: within seed.
- All solves were certified optimal and all 20 runs passed the implementation
  checks.

**Reputation effect.**
- Adding reputation to multi-station search raises mean S_del by
  +0.45 points (95% CI [-0.04, +0.94]; positive in 4 of 5 seeds).
- It raises S_full by +1.35 points ([+0.34, +2.35]; 4 of 5 seeds).
- It leaves E_tot unchanged: +0.05 MWh, [-0.19, +0.28].
- After Holm adjustment over the three service endpoints, no effect is
  significant (adjusted p = 0.13, 0.061 and 0.62).
- The S_full gain is consistent across seeds, but it is not established at
  the family level.
- These effects are larger than in the main campaign, where all
  reputation-effect intervals on S_del lie within ±0.41 points. They remain
  small relative to the offer-selection rule.

**Adaptation effect.** Adaptation adds nothing measurable:

| Endpoint | Effect | 95% CI | Holm-adjusted p |
|---|---|---|---|
| S_del | −0.04 points | [−0.67, +0.60] | 1 |
| S_full | −0.28 points | [−1.35, +0.79] | 1 |
| E_tot | −0.10 MWh | [−0.37, +0.16] | 1 |

**Comparison with Load-aware (descriptive).** Load-aware exceeds BRAM-EV on
all three endpoints, in both profiles:

| Endpoint | BRAM-EV − Load-aware | 95% CI |
|---|---|---|
| S_del | −1.25 points | [−2.07, −0.43] |
| S_full | −3.32 points | [−4.70, −1.94] |
| E_tot | −0.42 MWh | [−0.82, −0.03] |

**Score separation.**
- Within every operator, the scores of H and L vehicles with a non-empty
  history separate from the first day.
- The H − L gap grows from about 0.19 on day 1 to about 0.37 on day 5.
- A random H score exceeds a random L score with probability 0.79–0.88.
- The scores therefore carry information about the profiles. They remain
  signed historical evidence, not calibrated attendance probabilities.

**Why the separation changes allocation so little.**
- L scores stay near zero: the mean is between −0.06 and +0.01 depending on
  the operator and the day.
- Zero is also the score of a vehicle with no history.
- This follows from the outcome magnitudes. With presence +1, absence −3/4,
  late cancellation −1/4 and early cancellation −1/8 (normalised), the
  expected per-outcome value of an L vehicle is −0.02 on the base scale. Over
  the 20 perturbed operator scales it ranges from −0.23 to +0.13. For H it is
  +0.85.
- Reputation therefore rewards H vehicles but barely penalises L vehicles.
  Stations offered to L requests as often as to H requests:
  - offer rate 89.2% for L against 87.8% for H with reputation;
  - 88.6% for L against 85.0% for H without it;
  - same offered share of the requested duration (about 70%).
- The service gap between profiles (S_del about 77% for H against 25% for L)
  comes from the drivers' own cancellations and no-shows, not from allocation.

**Scope.**
- Five seeds, one regime and one capacity.
- A control under the balanced regime with the same capacity and seeds would
  be needed to attribute the difference with earlier results to heterogeneity
  alone.
- Non-significance does not establish equivalence.
