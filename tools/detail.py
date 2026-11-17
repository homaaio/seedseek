import json
import sys

from score import MODELS

path = sys.argv[1] if len(sys.argv) > 1 else "ranking.json"
want = [int(x) for x in sys.argv[2].split(",")]
rows = {x["seed"]: x for x in json.load(open(path, encoding="utf-8"))}
for s in want:
    x = rows.get(s)
    if not x:
        print(f"seed {s}: not in ranking (duplicate layout or out of range)")
        continue
    print(f"\n=== seed {s} ===")
    for m in MODELS:
        print(f"  {m:<7} cost {x[m]['cost']:6.1f}   puzzles: {', '.join(x[m]['puzzles']) or '-'}")
        print(f"          order: {' -> '.join(x[m]['order'])}")
    print("  locations:")
    for n, a in sorted(x["loc"].items()):
        print(f"    {n:<12} {a}")
