# Ablation ladder — paired t-tests, Holm correction per contrast

Family = 9 configurations (3 scenarios × 3 fleets) × 3 service indicators = 27 tests per contrast. Paired on the seed (10 worlds). CIs are unadjusted.

## Multi-station search (greedy → multistation) — family of 27, 15 rejected at α = 0.05 after Holm

| Scenario | Fleet | Indicator | Mean Δ (pp) | 95% CI (pp) | p | p Holm | Significant |
|---|---:|---|---:|---|---:|---:|---|
| balance | 50 | Demands served (even partially) | -0.08 | [-0.21, +0.04] | 0.171 | 1 | no |
| balance | 50 | Demands fully satisfied | +0.31 | [-0.10, +0.72] | 0.121 | 1 | no |
| balance | 50 | Share of energy need met (all demands) | +0.04 | [-0.13, +0.22] | 0.583 | 1 | no |
| balance | 150 | Demands served (even partially) | +0.14 | [-0.14, +0.42] | 0.301 | 1 | no |
| balance | 150 | Demands fully satisfied | +6.90 | [+5.25, +8.56] | 5.83e-06 | 0.000117 | yes |
| balance | 150 | Share of energy need met (all demands) | +3.11 | [+2.32, +3.90] | 9.25e-06 | 0.000176 | yes |
| balance | 250 | Demands served (even partially) | +1.21 | [+0.66, +1.76] | 0.000791 | 0.0119 | yes |
| balance | 250 | Demands fully satisfied | +15.00 | [+12.64, +17.37] | 1.64e-07 | 3.94e-06 | yes |
| balance | 250 | Share of energy need met (all demands) | +8.68 | [+6.93, +10.44] | 1.37e-06 | 3.01e-05 | yes |
| optimistic | 50 | Demands served (even partially) | -0.08 | [-0.15, -0.00] | 0.0437 | 0.524 | no |
| optimistic | 50 | Demands fully satisfied | -0.06 | [-0.32, +0.19] | 0.588 | 1 | no |
| optimistic | 50 | Share of energy need met (all demands) | -0.02 | [-0.11, +0.06] | 0.572 | 1 | no |
| optimistic | 150 | Demands served (even partially) | +0.10 | [-0.14, +0.34] | 0.382 | 1 | no |
| optimistic | 150 | Demands fully satisfied | +6.71 | [+4.73, +8.69] | 3.06e-05 | 0.00052 | yes |
| optimistic | 150 | Share of energy need met (all demands) | +2.82 | [+1.64, +3.99] | 0.000412 | 0.00659 | yes |
| optimistic | 250 | Demands served (even partially) | +1.10 | [+0.49, +1.70] | 0.00268 | 0.0349 | yes |
| optimistic | 250 | Demands fully satisfied | +18.08 | [+15.31, +20.85] | 1.28e-07 | 3.33e-06 | yes |
| optimistic | 250 | Share of energy need met (all demands) | +9.56 | [+7.66, +11.45] | 1.18e-06 | 2.71e-05 | yes |
| pessimistic | 50 | Demands served (even partially) | +0.09 | [-0.20, +0.38] | 0.514 | 1 | no |
| pessimistic | 50 | Demands fully satisfied | +0.22 | [-0.20, +0.64] | 0.271 | 1 | no |
| pessimistic | 50 | Share of energy need met (all demands) | +0.09 | [-0.20, +0.38] | 0.501 | 1 | no |
| pessimistic | 150 | Demands served (even partially) | +0.24 | [-0.20, +0.68] | 0.248 | 1 | no |
| pessimistic | 150 | Demands fully satisfied | +4.86 | [+3.88, +5.85] | 1.41e-06 | 3.01e-05 | yes |
| pessimistic | 150 | Share of energy need met (all demands) | +2.37 | [+1.74, +3.00] | 1.28e-05 | 0.00023 | yes |
| pessimistic | 250 | Demands served (even partially) | +0.73 | [+0.38, +1.08] | 0.00106 | 0.0148 | yes |
| pessimistic | 250 | Demands fully satisfied | +9.20 | [+8.22, +10.18] | 5.52e-09 | 1.49e-07 | yes |
| pessimistic | 250 | Share of energy need met (all demands) | +5.64 | [+4.77, +6.51] | 1.4e-07 | 3.49e-06 | yes |

## Reputation (multistation → multistation_rep) — family of 27, 0 rejected at α = 0.05 after Holm

| Scenario | Fleet | Indicator | Mean Δ (pp) | 95% CI (pp) | p | p Holm | Significant |
|---|---:|---|---:|---|---:|---:|---|
| balance | 50 | Demands served (even partially) | +0.15 | [+0.03, +0.27] | 0.0221 | 0.576 | no |
| balance | 50 | Demands fully satisfied | +0.03 | [-0.18, +0.24] | 0.746 | 1 | no |
| balance | 50 | Share of energy need met (all demands) | +0.11 | [-0.03, +0.24] | 0.109 | 1 | no |
| balance | 150 | Demands served (even partially) | +0.05 | [-0.11, +0.20] | 0.52 | 1 | no |
| balance | 150 | Demands fully satisfied | +0.18 | [-0.43, +0.78] | 0.525 | 1 | no |
| balance | 150 | Share of energy need met (all demands) | +0.04 | [-0.14, +0.22] | 0.653 | 1 | no |
| balance | 250 | Demands served (even partially) | -0.07 | [-0.21, +0.07] | 0.274 | 1 | no |
| balance | 250 | Demands fully satisfied | +0.14 | [-0.23, +0.51] | 0.411 | 1 | no |
| balance | 250 | Share of energy need met (all demands) | +0.01 | [-0.15, +0.18] | 0.875 | 1 | no |
| optimistic | 50 | Demands served (even partially) | +0.01 | [-0.04, +0.06] | 0.604 | 1 | no |
| optimistic | 50 | Demands fully satisfied | +0.05 | [-0.25, +0.34] | 0.736 | 1 | no |
| optimistic | 50 | Share of energy need met (all demands) | +0.04 | [-0.03, +0.10] | 0.222 | 1 | no |
| optimistic | 150 | Demands served (even partially) | -0.03 | [-0.13, +0.08] | 0.559 | 1 | no |
| optimistic | 150 | Demands fully satisfied | +0.06 | [-0.31, +0.43] | 0.728 | 1 | no |
| optimistic | 150 | Share of energy need met (all demands) | +0.02 | [-0.09, +0.13] | 0.678 | 1 | no |
| optimistic | 250 | Demands served (even partially) | +0.05 | [-0.08, +0.18] | 0.414 | 1 | no |
| optimistic | 250 | Demands fully satisfied | +0.22 | [-0.23, +0.68] | 0.295 | 1 | no |
| optimistic | 250 | Share of energy need met (all demands) | +0.12 | [-0.17, +0.41] | 0.385 | 1 | no |
| pessimistic | 50 | Demands served (even partially) | -0.03 | [-0.15, +0.08] | 0.516 | 1 | no |
| pessimistic | 50 | Demands fully satisfied | -0.15 | [-0.30, +0.00] | 0.0553 | 1 | no |
| pessimistic | 50 | Share of energy need met (all demands) | -0.06 | [-0.10, -0.01] | 0.0188 | 0.507 | no |
| pessimistic | 150 | Demands served (even partially) | +0.01 | [-0.15, +0.17] | 0.899 | 1 | no |
| pessimistic | 150 | Demands fully satisfied | +0.14 | [-0.06, +0.35] | 0.15 | 1 | no |
| pessimistic | 150 | Share of energy need met (all demands) | +0.01 | [-0.12, +0.13] | 0.931 | 1 | no |
| pessimistic | 250 | Demands served (even partially) | +0.05 | [-0.12, +0.21] | 0.521 | 1 | no |
| pessimistic | 250 | Demands fully satisfied | +0.11 | [-0.25, +0.47] | 0.51 | 1 | no |
| pessimistic | 250 | Share of energy need met (all demands) | -0.05 | [-0.17, +0.08] | 0.423 | 1 | no |

## Cross-station adaptation (multistation_rep → bramev) — family of 27, 0 rejected at α = 0.05 after Holm

| Scenario | Fleet | Indicator | Mean Δ (pp) | 95% CI (pp) | p | p Holm | Significant |
|---|---:|---|---:|---|---:|---:|---|
| balance | 50 | Demands served (even partially) | -0.02 | [-0.14, +0.10] | 0.712 | 1 | no |
| balance | 50 | Demands fully satisfied | +0.00 | [-0.20, +0.21] | 0.961 | 1 | no |
| balance | 50 | Share of energy need met (all demands) | -0.00 | [-0.19, +0.19] | 0.987 | 1 | no |
| balance | 150 | Demands served (even partially) | -0.01 | [-0.13, +0.11] | 0.823 | 1 | no |
| balance | 150 | Demands fully satisfied | -0.12 | [-0.62, +0.39] | 0.616 | 1 | no |
| balance | 150 | Share of energy need met (all demands) | -0.08 | [-0.24, +0.08] | 0.277 | 1 | no |
| balance | 250 | Demands served (even partially) | +0.03 | [-0.11, +0.17] | 0.596 | 1 | no |
| balance | 250 | Demands fully satisfied | -0.32 | [-0.73, +0.10] | 0.119 | 1 | no |
| balance | 250 | Share of energy need met (all demands) | -0.08 | [-0.21, +0.05] | 0.183 | 1 | no |
| optimistic | 50 | Demands served (even partially) | -0.01 | [-0.06, +0.04] | 0.604 | 1 | no |
| optimistic | 50 | Demands fully satisfied | -0.06 | [-0.20, +0.07] | 0.309 | 1 | no |
| optimistic | 50 | Share of energy need met (all demands) | -0.03 | [-0.07, +0.01] | 0.121 | 1 | no |
| optimistic | 150 | Demands served (even partially) | +0.06 | [-0.03, +0.14] | 0.162 | 1 | no |
| optimistic | 150 | Demands fully satisfied | -0.06 | [-0.39, +0.28] | 0.72 | 1 | no |
| optimistic | 150 | Share of energy need met (all demands) | +0.01 | [-0.03, +0.05] | 0.661 | 1 | no |
| optimistic | 250 | Demands served (even partially) | -0.08 | [-0.20, +0.04] | 0.175 | 1 | no |
| optimistic | 250 | Demands fully satisfied | -0.01 | [-0.51, +0.49] | 0.956 | 1 | no |
| optimistic | 250 | Share of energy need met (all demands) | -0.05 | [-0.24, +0.13] | 0.539 | 1 | no |
| pessimistic | 50 | Demands served (even partially) | -0.04 | [-0.09, +0.01] | 0.101 | 1 | no |
| pessimistic | 50 | Demands fully satisfied | +0.15 | [-0.05, +0.36] | 0.116 | 1 | no |
| pessimistic | 50 | Share of energy need met (all demands) | -0.00 | [-0.07, +0.07] | 0.996 | 1 | no |
| pessimistic | 150 | Demands served (even partially) | -0.03 | [-0.17, +0.11] | 0.634 | 1 | no |
| pessimistic | 150 | Demands fully satisfied | -0.09 | [-0.45, +0.27] | 0.575 | 1 | no |
| pessimistic | 150 | Share of energy need met (all demands) | -0.01 | [-0.22, +0.20] | 0.893 | 1 | no |
| pessimistic | 250 | Demands served (even partially) | -0.10 | [-0.30, +0.11] | 0.311 | 1 | no |
| pessimistic | 250 | Demands fully satisfied | +0.03 | [-0.36, +0.41] | 0.882 | 1 | no |
| pessimistic | 250 | Share of energy need met (all demands) | -0.01 | [-0.19, +0.17] | 0.917 | 1 | no |
