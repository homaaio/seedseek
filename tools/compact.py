"""Rank seeds by whole-run walking with the items clustered on one line.

`find.py --full` answers "cheapest whole run".  This answers "cheapest whole run
that also feels like one smooth route": the pickups must be close to each other
(longest single hop), must not drag you back through a room you already cleared,
and must not send you up stairs and down again mid-run.

  python compact.py                 # top 10 door seeds, default filters
  python compact.py car 8           # top 8 car seeds
  python compact.py sewer --pool 4000 --maxhop 18
  python compact.py door --list --set

Columns
  run     bed -> pickups -> exit, straight-line metres (find.py --full)
  bed     bed -> first pickup
  spread  metres walked between the items themselves (run - bed - out)
  out     last pickup -> exit
  maxhop  longest single hop
  climb   total upward height walked (up stairs then back down = wasted time)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import find as F
from score import MODELS, closure, dp_cost_between, dist, parse_dump


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("route", nargs="?", default="door")
    ap.add_argument("count", nargs="?", type=int, default=10)
    ap.add_argument("--pool", type=int, default=2500,
                    help="layouts to re-solve, cheapest item-only first (default 2500)")
    ap.add_argument("--maxhop", type=float, default=26.0,
                    help="drop seeds whose longest single hop exceeds this")
    ap.add_argument("--maxclimb", type=float, default=8.0,
                    help="drop seeds with more upward walking than this")
    ap.add_argument("--maxspread", type=float, default=999.0)
    ap.add_argument("--puzzles", action="store_true",
                    help="allow seeds that must open a container first")
    ap.add_argument("--revisit", action="store_true",
                    help="allow routes that enter the same room twice")
    ap.add_argument("--list", action="store_true", help="pickup order + rooms only")
    ap.add_argument("--set", action="store_true", help="print setseed.ps1 lines")
    args = ap.parse_args()

    key = F.ALIAS.get(args.route.lower())
    if key is None:
        sys.exit(f"unknown route {args.route!r}; see find.py --routes")

    blob = F.load_index()
    models, rows = blob["models"], blob["rows"]
    if key not in models:
        sys.exit(f"{key} missing from index - run find.py --rebuild")
    i = models.index(key)
    puzzles = parse_dump(F.dump_path())[0]

    start, end = F.PLAYER_START, F.EXITS[key]
    direct = dist(start, end)
    cands = sorted(rows, key=lambda r: r[1][i])[: args.pool]
    items_by_seed = F.load_items([r[0] for r in cands])

    out = []
    for r in cands:
        items = items_by_seed.get(r[0])
        if not items:
            continue
        need, _ = closure(MODELS[key], items, puzzles)
        cost, order = dp_cost_between(need, items, puzzles, start, end)
        pts = [start] + [items[n]["pos"] for n in order] + [end]
        legs = [dist(a, b) for a, b in zip(pts, pts[1:])]
        rooms = []
        for n in order:
            a = items[n]["area"]
            if a.startswith("in:"):
                continue
            if not rooms or rooms[-1] != a:
                rooms.append(a)
        out.append(dict(
            seed=r[0], cost=cost, order=order, rooms=rooms, legs=legs,
            startleg=legs[0], endleg=legs[-1], maxhop=max(legs),
            spread=sum(legs[1:-1]),
            climb=sum(max(0.0, b[1] - a[1]) for a, b in zip(pts, pts[1:])),
            revisit=len(rooms) != len(set(rooms)),
            puzzles=len(need) - len(order) + sum(
                1 for n in need if items[n]["area"].startswith("in:"))))

    keep = [d for d in out
            if d["maxhop"] <= args.maxhop
            and d["climb"] <= args.maxclimb
            and d["spread"] <= args.maxspread
            and (args.revisit or not d["revisit"])
            and (args.puzzles or d["puzzles"] == 0)]
    keep.sort(key=lambda d: (d["cost"], d["maxhop"]))
    keep = keep[: args.count]

    print(f"{key} ({', '.join(MODELS[key])})")
    print(f"bed {F.PLAYER_START} -> exit {F.EXITS[key]} = {direct:.1f} m straight; "
          f"{len(out)} layouts solved from the top {args.pool} on item-only cost, "
          f"{len(keep)} kept")
    print("all metres are straight-line; no door, ladder or Granny time\n")
    print(f"{'seed':>7} {'run':>6} {'bed':>5} {'spread':>6} {'out':>5} "
          f"{'maxhop':>6} {'climb':>5}  route")
    print("-" * 100)
    for d in keep:
        print(f"{d['seed']:>7} {d['cost']:6.1f} {d['startleg']:5.1f} "
              f"{d['spread']:6.1f} {d['endleg']:5.1f} {d['maxhop']:6.1f} "
              f"{d['climb']:5.1f}  {' -> '.join(d['rooms'])}")
        print(f"{'':25}  pickups: {' -> '.join(d['order'])}")
        if not args.list:
            print(f"{'':25}  legs: " + ", ".join(f"{l:.1f}" for l in d["legs"]))
    print()
    if args.set:
        for d in keep:
            print(f".\\setseed.ps1 -Seed {d['seed']}")


if __name__ == "__main__":
    main()
