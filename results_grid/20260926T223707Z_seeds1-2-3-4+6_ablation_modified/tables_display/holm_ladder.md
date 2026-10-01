# Ablation ladder — paired t-tests, Holm correction per contrast

Family = 9 configurations (3 scenarios × 3 fleets) × 3 service endpoints (S_del, S_full, E_tot) = 27 two-sided paired t-tests per contrast; the three contrasts are separate families. Paired on the seed (10 worlds). CIs are unadjusted.

## Multi-station search (greedy → multistation) — family of 27, 17 rejected at α = 0.05 after Holm

| Scenario | Fleet | Endpoint | Mean Δ | 95% CI | Unit | p | p Holm | Significant |
|---|---:|---|---:|---|---|---:|---:|---|
| balance | 50 | S_del | +0.04 | [-0.13, +0.22] | pp | 0.583 | 1 | no |
| balance | 50 | S_full | +0.31 | [-0.10, +0.72] | pp | 0.121 | 0.97 | no |
| balance | 50 | E_tot | +24.15 | [-5.30, +53.60] | kWh | 0.0966 | 0.869 | no |
| balance | 150 | S_del | +3.11 | [+2.32, +3.90] | pp | 9.25e-06 | 0.000167 | yes |
| balance | 150 | S_full | +6.90 | [+5.25, +8.56] | pp | 5.83e-06 | 0.000111 | yes |
| balance | 150 | E_tot | +753.77 | [+502.64, +1004.89] | kWh | 8e-05 | 0.00104 | yes |
| balance | 250 | S_del | +8.68 | [+6.93, +10.44] | pp | 1.37e-06 | 3.01e-05 | yes |
| balance | 250 | S_full | +15.00 | [+12.64, +17.37] | pp | 1.64e-07 | 3.94e-06 | yes |
| balance | 250 | E_tot | +4865.70 | [+3608.95, +6122.45] | kWh | 1.07e-05 | 0.000181 | yes |
| optimistic | 50 | S_del | -0.02 | [-0.11, +0.06] | pp | 0.572 | 1 | no |
| optimistic | 50 | S_full | -0.06 | [-0.32, +0.19] | pp | 0.588 | 1 | no |
| optimistic | 50 | E_tot | -1.36 | [-4.68, +1.97] | kWh | 0.38 | 1 | no |
| optimistic | 150 | S_del | +2.82 | [+1.64, +3.99] | pp | 0.000412 | 0.00453 | yes |
| optimistic | 150 | S_full | +6.71 | [+4.73, +8.69] | pp | 3.06e-05 | 0.000428 | yes |
| optimistic | 150 | E_tot | +449.51 | [+153.26, +745.75] | kWh | 0.00748 | 0.0748 | no |
| optimistic | 250 | S_del | +9.56 | [+7.66, +11.45] | pp | 1.18e-06 | 2.71e-05 | yes |
| optimistic | 250 | S_full | +18.08 | [+15.31, +20.85] | pp | 1.28e-07 | 3.33e-06 | yes |
| optimistic | 250 | E_tot | +3434.04 | [+2218.38, +4649.71] | kWh | 0.000127 | 0.00152 | yes |
| pessimistic | 50 | S_del | +0.09 | [-0.20, +0.38] | pp | 0.501 | 1 | no |
| pessimistic | 50 | S_full | +0.22 | [-0.20, +0.64] | pp | 0.271 | 1 | no |
| pessimistic | 50 | E_tot | -12.84 | [-83.44, +57.77] | kWh | 0.69 | 1 | no |
| pessimistic | 150 | S_del | +2.37 | [+1.74, +3.00] | pp | 1.28e-05 | 0.000204 | yes |
| pessimistic | 150 | S_full | +4.86 | [+3.88, +5.85] | pp | 1.41e-06 | 3.01e-05 | yes |
| pessimistic | 150 | E_tot | +1063.78 | [+767.18, +1360.39] | kWh | 1.98e-05 | 0.000297 | yes |
| pessimistic | 250 | S_del | +5.64 | [+4.77, +6.51] | pp | 1.4e-07 | 3.49e-06 | yes |
| pessimistic | 250 | S_full | +9.20 | [+8.22, +10.18] | pp | 5.52e-09 | 1.49e-07 | yes |
| pessimistic | 250 | E_tot | +5598.71 | [+4435.64, +6761.77] | kWh | 1.75e-06 | 3.51e-05 | yes |

## Reputation (multistation → multistation_rep) — family of 27, 0 rejected at α = 0.05 after Holm

| Scenario | Fleet | Endpoint | Mean Δ | 95% CI | Unit | p | p Holm | Significant |
|---|---:|---|---:|---|---|---:|---:|---|
| balance | 50 | S_del | +0.11 | [-0.03, +0.24] | pp | 0.109 | 1 | no |
| balance | 50 | S_full | +0.03 | [-0.18, +0.24] | pp | 0.746 | 1 | no |
| balance | 50 | E_tot | +3.45 | [-9.11, +16.01] | kWh | 0.549 | 1 | no |
| balance | 150 | S_del | +0.04 | [-0.14, +0.22] | pp | 0.653 | 1 | no |
| balance | 150 | S_full | +0.18 | [-0.43, +0.78] | pp | 0.525 | 1 | no |
| balance | 150 | E_tot | -21.18 | [-74.12, +31.76] | kWh | 0.389 | 1 | no |
| balance | 250 | S_del | +0.01 | [-0.15, +0.18] | pp | 0.875 | 1 | no |
| balance | 250 | S_full | +0.14 | [-0.23, +0.51] | pp | 0.411 | 1 | no |
| balance | 250 | E_tot | +18.39 | [-57.15, +93.93] | kWh | 0.595 | 1 | no |
| optimistic | 50 | S_del | +0.04 | [-0.03, +0.10] | pp | 0.222 | 1 | no |
| optimistic | 50 | S_full | +0.05 | [-0.25, +0.34] | pp | 0.736 | 1 | no |
| optimistic | 50 | E_tot | -0.84 | [-4.64, +2.95] | kWh | 0.627 | 1 | no |
| optimistic | 150 | S_del | +0.02 | [-0.09, +0.13] | pp | 0.678 | 1 | no |
| optimistic | 150 | S_full | +0.06 | [-0.31, +0.43] | pp | 0.728 | 1 | no |
| optimistic | 150 | E_tot | -7.43 | [-29.23, +14.36] | kWh | 0.46 | 1 | no |
| optimistic | 250 | S_del | +0.12 | [-0.17, +0.41] | pp | 0.385 | 1 | no |
| optimistic | 250 | S_full | +0.22 | [-0.23, +0.68] | pp | 0.295 | 1 | no |
| optimistic | 250 | E_tot | -6.37 | [-58.03, +45.28] | kWh | 0.786 | 1 | no |
| pessimistic | 50 | S_del | -0.06 | [-0.10, -0.01] | pp | 0.0188 | 0.507 | no |
| pessimistic | 50 | S_full | -0.15 | [-0.30, +0.00] | pp | 0.0553 | 1 | no |
| pessimistic | 50 | E_tot | +3.46 | [-21.78, +28.70] | kWh | 0.764 | 1 | no |
| pessimistic | 150 | S_del | +0.01 | [-0.12, +0.13] | pp | 0.931 | 1 | no |
| pessimistic | 150 | S_full | +0.14 | [-0.06, +0.35] | pp | 0.15 | 1 | no |
| pessimistic | 150 | E_tot | -55.79 | [-169.84, +58.25] | kWh | 0.297 | 1 | no |
| pessimistic | 250 | S_del | -0.05 | [-0.17, +0.08] | pp | 0.423 | 1 | no |
| pessimistic | 250 | S_full | +0.11 | [-0.25, +0.47] | pp | 0.51 | 1 | no |
| pessimistic | 250 | E_tot | +40.58 | [-77.80, +158.96] | kWh | 0.458 | 1 | no |

## Cross-station adaptation (multistation_rep → bramev) — family of 27, 0 rejected at α = 0.05 after Holm

| Scenario | Fleet | Endpoint | Mean Δ | 95% CI | Unit | p | p Holm | Significant |
|---|---:|---|---:|---|---|---:|---:|---|
| balance | 50 | S_del | -0.00 | [-0.19, +0.19] | pp | 0.987 | 1 | no |
| balance | 50 | S_full | +0.00 | [-0.20, +0.21] | pp | 0.961 | 1 | no |
| balance | 50 | E_tot | +4.47 | [-0.71, +9.64] | kWh | 0.0828 | 1 | no |
| balance | 150 | S_del | -0.08 | [-0.24, +0.08] | pp | 0.277 | 1 | no |
| balance | 150 | S_full | -0.12 | [-0.62, +0.39] | pp | 0.616 | 1 | no |
| balance | 150 | E_tot | -6.67 | [-42.01, +28.67] | kWh | 0.679 | 1 | no |
| balance | 250 | S_del | -0.08 | [-0.21, +0.05] | pp | 0.183 | 1 | no |
| balance | 250 | S_full | -0.32 | [-0.73, +0.10] | pp | 0.119 | 1 | no |
| balance | 250 | E_tot | +14.04 | [-70.64, +98.72] | kWh | 0.716 | 1 | no |
| optimistic | 50 | S_del | -0.03 | [-0.07, +0.01] | pp | 0.121 | 1 | no |
| optimistic | 50 | S_full | -0.06 | [-0.20, +0.07] | pp | 0.309 | 1 | no |
| optimistic | 50 | E_tot | +1.27 | [-1.35, +3.89] | kWh | 0.302 | 1 | no |
| optimistic | 150 | S_del | +0.01 | [-0.03, +0.05] | pp | 0.661 | 1 | no |
| optimistic | 150 | S_full | -0.06 | [-0.39, +0.28] | pp | 0.72 | 1 | no |
| optimistic | 150 | E_tot | -1.32 | [-17.38, +14.73] | kWh | 0.856 | 1 | no |
| optimistic | 250 | S_del | -0.05 | [-0.24, +0.13] | pp | 0.539 | 1 | no |
| optimistic | 250 | S_full | -0.01 | [-0.51, +0.49] | pp | 0.956 | 1 | no |
| optimistic | 250 | E_tot | +8.74 | [-32.08, +49.55] | kWh | 0.64 | 1 | no |
| pessimistic | 50 | S_del | -0.00 | [-0.07, +0.07] | pp | 0.996 | 1 | no |
| pessimistic | 50 | S_full | +0.15 | [-0.05, +0.36] | pp | 0.116 | 1 | no |
| pessimistic | 50 | E_tot | -0.86 | [-11.39, +9.67] | kWh | 0.857 | 1 | no |
| pessimistic | 150 | S_del | -0.01 | [-0.22, +0.20] | pp | 0.893 | 1 | no |
| pessimistic | 150 | S_full | -0.09 | [-0.45, +0.27] | pp | 0.575 | 1 | no |
| pessimistic | 150 | E_tot | +54.18 | [-16.23, +124.59] | kWh | 0.116 | 1 | no |
| pessimistic | 250 | S_del | -0.01 | [-0.19, +0.17] | pp | 0.917 | 1 | no |
| pessimistic | 250 | S_full | +0.03 | [-0.36, +0.41] | pp | 0.882 | 1 | no |
| pessimistic | 250 | E_tot | -41.73 | [-216.67, +133.22] | kWh | 0.603 | 1 | no |
