"""Rank sweep results against the best Kelly variant at every horizon.

Usage:
    python notebooks/insurance_scan/analyze.py <results.json> [top_n]
"""

import json, sys
from collections import defaultdict

res = json.load(open(sys.argv[1]))
H = [1, 5, 10, 15]
by = defaultdict(dict)
for r in res:
    k = r["kwargs"]
    if r["cls"] == "Model":
        key = "Buy_Hold"
    elif r["cls"] == "KellyModel":
        key = f"Kelly {k['bond_frac']}/{k['rebalance_period']}"
    else:
        key = f"Ins prem={k['premium_rate']:.4f} ded={k['insurance_deductible']:.2f} cov={k['coverage_ratio']}"
    by[key][r["years"]] = r
kelly = [k for k in by if k.startswith("Kelly")]
best_k = {y: max(by[k][y]["mean_yearly"] for k in kelly) for y in H}
best_k_lose = {y: min(by[k][y]["losing"] for k in kelly) for y in H}
bh = by["Buy_Hold"]
print("horizon:            " + "".join(f"{y:>16}y" for y in H))
print("best Kelly mean:    " + "".join(f"{best_k[y]*100:16.2f}%" for y in H))
print("Buy&Hold mean:      " + "".join(f"{bh[y]['mean_yearly']*100:16.2f}%" for y in H))
print("min Kelly losing:   " + "".join(f"{best_k_lose[y]*100:16.1f}%" for y in H))
print("Buy&Hold losing:    " + "".join(f"{bh[y]['losing']*100:16.1f}%" for y in H))
ins = [k for k in by if k.startswith("Ins")]


def margin(k):
    return min(by[k][y]["mean_yearly"] - best_k[y] for y in H)


rows = sorted(ins, key=margin, reverse=True)
print(f"\n{'variant':42}{'min margin vs best Kelly':>26}   mean/losing at 1,5,10,15y")
for k in rows[: int(sys.argv[2]) if len(sys.argv) > 2 else 30]:
    cells = "  ".join(
        f"{by[k][y]['mean_yearly']*100:5.2f}/{by[k][y]['losing']*100:4.1f}" for y in H
    )
    flag = "BEATS" if margin(k) > 0 else ""
    print(f"{k:42}{margin(k)*100:+24.2f}pt  {cells} {flag}")
print(
    f"\n{sum(margin(k) > 0 for k in ins)} of {len(ins)} variants beat the best Kelly at every horizon"
)
