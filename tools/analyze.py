import json
import sys

from score import MODELS

path = sys.argv[1] if len(sys.argv) > 1 else "ranking.json"
topn = int(sys.argv[2]) if len(sys.argv) > 2 else 8
rows = json.load(open(path, encoding="utf-8"))
print("layouts scored:", len(rows))

for model in MODELS:
    print(f"\n=== top {topn} by {model} ===")
    for x in sorted(rows, key=lambda z: z[model]["cost"])[:topn]:
        locs = "  ".join(f"{n}:{x['loc'].get(n)}" for n in x[model]["order"][:6])
        print(f"{x['seed']:>8}  {model}={x[model]['cost']:6.1f}  "
              f"puzzles={len(x[model]['puzzles'])}  {locs}")

print(f"\n=== top {topn} by combined (combo) ===")
for x in sorted(rows, key=lambda z: z["combo"])[:topn]:
    print(f"{x['seed']:>8}  combo={x['combo']:6.1f}  car5={x['car5']['cost']:5.1f}  "
          f"r2={x['route2']['cost']:5.1f}  t6={x['tools6']['cost']:5.1f}  "
          f"f11={x['full11']['cost']:6.1f}")

print("\n=== car5 cost distribution ===")
buckets = {}
for x in rows:
    b = int(x["car5"]["cost"] // 5) * 5
    buckets[b] = buckets.get(b, 0) + 1
for b in sorted(buckets)[:12]:
    print(f"  {b:>3}-{b+4:<3} {buckets[b]:>6}")
