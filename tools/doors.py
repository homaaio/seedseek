import json
import sys

rows = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "ranking-50k.json", encoding="utf-8"))
for model in ("door4", "door5"):
    print(f"\n=== top 10 by {model} ===")
    for x in sorted(rows, key=lambda z: z[model]["cost"])[:10]:
        locs = "  ".join(f"{n}:{x['loc'].get(n)}" for n in x[model]["order"])
        print(f"{x['seed']:>8}  {model}={x[model]['cost']:6.1f}  puzzles={len(x[model]['puzzles'])}  {locs}")
