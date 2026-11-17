"""Find Granny Legacy seeds by escape route and cost.

Cost is metres of walking in the cheapest pickup order for that route's items
(items locked inside a puzzle first require that puzzle's keys, expanded
recursively) plus 3 m per puzzle that must be opened.  It is a layout-quality
number, not a run time: a seed cannot make a run take 1.3 minutes, it can only
put the route's items close together.

Examples
  python find.py --routes                 # what each route means + best cost
  python find.py door                     # 10 fastest door seeds
  python find.py door 25                  # door seeds costing 25 m or less
  python find.py sewer --max 10 --top 5
  python find.py car --at 24              # seeds closest to 24 m (either side)
  python find.py door5 --min 35 --max 40 --detail

  python find.py car --nightstand          # a car part on the wake-up nightstand
  python find.py door --nightstand --simple --top 20
  python find.py door --nightstand --rooms 3   # at most 3 rooms in the route
  python find.py door --nightstand --full --first --top 10
                                           # cabinet item first, then straight out

"Nightstand" means a spawn point a few metres from where you wake up.  The scene
dump puts the player at (13.8, 21.0, -7.2); every spawn point within --within
metres of that is offered as a "wake-up room" spot (today: Spot (51) and
Spot (52), the two shelves of the big drawers/cabinet, 4.8 m away).  The dump has
no room volumes, so "same room" is inferred from distance/furniture, not proven.

By default the cost is item-to-item walking only.  --full adds the two legs a
real run always pays: bed -> first pickup and last pickup -> that route's exit
(door / car / sewer), so a seed can no longer look cheap by ignoring a long walk.
"""

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.json")
RANKING = os.path.join(HERE, "ranking-50k.json")
DATA_CANDIDATES = [
    os.path.join(HERE, "data"),                                # flat checkout
    os.path.normpath(os.path.join(HERE, os.pardir, "data")),   # repo: tools/../data
    r"C:\Users\k\Desktop\Granny_Legacy\BepInEx\SeedSearch",    # live game harvest
]

ROUTES = {
    "door4": (["door", "door4", "front", "main"], "front door",
              "MasterKey PDKey Pliers CarBattery"),
    "door5": (["door5"], "front door + spider key",
              "MasterKey PDKey Pliers CarBattery SPKey"),
    "car5": (["car", "car5"], "car", "CarKey CarBattery Engine Gas SparkPlug"),
    "sewer": (["sewer", "pipe", "cellar"], "sewer pipe (EX_Pipe)",
              "SPKey Winch Pliers"),
    "sewer2": (["sewer2", "pipe2"], "sewer pipe, crank not needed", "SPKey Pliers"),
    "tools6": (["tools", "tools6"], "door with tools",
               "Pliers MasterKey PDKey Hammer SafeKey Wrench"),
    "route2": (["keys", "route2"], "door keys only", "MasterKey PDKey"),
    "full11": (["full", "full11"], "every escape item",
               "all 11 requiredEscapeItemNames"),
}

ALIAS = {a: m for m, (aliases, _, _) in ROUTES.items() for a in aliases}

# Scene dump (scene-start-*.txt): PlayerStuff/PlayerStartPos, the spot the
# player stands up from when the run begins.  Spawn points near it are in the
# same bedroom, i.e. the "nightstand" the user asked about.
PLAYER_START = (13.8, 21.0, -7.2)

# Where each ending happens (scene dump):
#   door  -> Granny's House/ExitDoor/ExitDoorCollEscape
#   car   -> Granny's House/Granny_SomeOthers/Garage/Car
#   sewer -> sewer room under the cellar (Spider Cellar)
EXITS = {
    "door4": (-0.5, 13.3, 13.9),
    "door5": (-0.5, 13.3, 13.9),
    "tools6": (-0.5, 13.3, 13.9),
    "route2": (-0.5, 13.3, 13.9),
    "full11": (-0.5, 13.3, 13.9),
    "car5": (2.8, 3.1, 0.0),
    "sewer": (-6.5, 9.7, -39.8),
    "sewer2": (-6.5, 9.7, -39.8),
}


def data_dir():
    for d in DATA_CANDIDATES:
        if os.path.isdir(d) and glob.glob(os.path.join(d, "seeds-*.csv")):
            return d
    return None


def dump_path():
    local = os.path.join(HERE, "dump.txt")
    if os.path.exists(local):
        return local
    if data_dir():
        found = sorted(glob.glob(os.path.join(data_dir(), "dump-layout-*.txt")),
                       key=os.path.getmtime)
        if found:
            return found[-1]
    return None


def load_index(rebuild=False):
    stale = False
    if os.path.exists(INDEX) and os.path.exists(RANKING):
        stale = os.path.getmtime(INDEX) < os.path.getmtime(RANKING)
    if rebuild or not os.path.exists(INDEX) or stale:
        import mkindex
        d = data_dir()
        if not d:
            sys.exit("no seeds-*.csv found")
        if not os.path.exists(RANKING):
            sys.exit(f"{os.path.basename(RANKING)} is missing - build it first:\n"
                     "  python score.py --dump data\\dump.txt --csv data\\seeds-*.csv "
                     "--refine 300 --out ranking-50k.json\n"
                     "  python find.py --rebuild")
        mkindex.build(csv_globs=[os.path.join(d, "seeds-*.csv")])
    with open(INDEX, encoding="utf-8") as fh:
        return json.load(fh)


def load_items(seeds):
    """seed -> {item: {'pos': (x, y, z), 'area': room}} from the harvested CSVs."""
    want, out = set(seeds), {}
    for path in glob.glob(os.path.join(data_dir() or ".", "seeds-*.csv")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            fh.readline()
            for line in fh:
                parts = line.rstrip("\n").split("|", 2)
                if len(parts) < 3 or int(parts[0]) not in want:
                    continue
                items = {}
                for chunk in parts[2].split(";"):
                    bits = chunk.split("@")
                    if len(bits) == 3:
                        items[bits[0]] = {"pos": tuple(float(v) for v in bits[1].split(",")),
                                          "area": bits[2]}
                out[int(parts[0])] = items
    return out


def exact(route, items, puzzles):
    """Re-solve one route exactly (bitmask DP; falls back to greedy when huge)."""
    from score import MODELS, closure, dp_cost
    need, _ = closure(MODELS[route], items, puzzles)
    return dp_cost(need, items, puzzles, exact=True)


def describe(items, order):
    out = []
    for n in order:
        it = items.get(n)
        if not it:
            out.append(f"{n} MISSING")
            continue
        room = it["area"]
        out.append(f"{n} in {room[3:]}" if room.startswith("in:") else f"{n}@{room}")
    return " -> ".join(out)


def row_metrics(blob, row, i, night_ids):
    """Rooms, containers and nightstand hits for one seed under route i.

    The index stores, per item, (item id, area id, spawn-spot id), so this is
    pure lookups - no CSV parsing.
    """
    loc = {it: (a, s) for it, a, s in row[3]}
    need = [n for n in row[2][i] if n >= 0]
    rooms, puzzles, night = [], [], []
    for n in need:
        a, s = loc.get(n, (None, None))
        if a is None:
            continue
        area = blob["areas"][a]
        if area.startswith("in:"):
            p = area[3:]
            if p not in puzzles:
                puzzles.append(p)
        elif area not in rooms:
            rooms.append(area)
        if s in night_ids:
            night.append(blob["items"][n])
    return rooms, puzzles, night


def spot_names():
    """(x, y, z) rounded like the index -> 'Spot (51)' from a SeedManager dump."""
    pat = re.compile(r"\s+(?:used|free)\[\d+\]\s+(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)\s+'([^']*)'")
    paths = []
    if os.path.exists(os.path.join(HERE, "dump.txt")):
        paths.append(os.path.join(HERE, "dump.txt"))
    for d in (HERE, data_dir()):
        if d:
            paths += sorted(glob.glob(os.path.join(d, "dump-layout-*.txt")),
                            key=os.path.getmtime, reverse=True)
    for path in paths:
        out = {}
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = pat.match(line)
                    if m:
                        out[tuple(round(float(m.group(k)), 1) for k in (1, 2, 3))] = m.group(4)
        except OSError:
            continue
        if out:                       # older dumps have no spot names
            return out
    return {}


def wake_spots(blob, within):
    """Spawn points inside the room the player wakes in, nearest first."""
    names, out = spot_names(), []
    for sid, xyz in enumerate(blob.get("spots", [])):
        d = sum((a - b) ** 2 for a, b in zip(xyz, PLAYER_START)) ** 0.5
        if d <= within:
            out.append((sid, names.get(tuple(xyz), "Spot@%.1f,%.1f,%.1f" % tuple(xyz)), d))
    out.sort(key=lambda t: t[2])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("route", nargs="?", default="door",
                    help="door | door5 | car | sewer | sewer2 | tools6 | keys | full11")
    ap.add_argument("target", nargs="?", type=float, help="shorthand for --max (metres)")
    ap.add_argument("--route", dest="route_opt")
    ap.add_argument("--max", type=float, help="keep seeds at or below this cost (metres)")
    ap.add_argument("--min", type=float, help="keep seeds at or above this cost (metres)")
    ap.add_argument("--at", type=float, help="seeds closest to this cost, either side")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--routes", action="store_true", help="list routes and how cheap they get")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the index first")
    ap.add_argument("--set", action="store_true", help="print setseed.ps1 command lines")
    ap.add_argument("--detail", action="store_true", help="also list exact coordinates")
    ap.add_argument("--greedy", action="store_true", help="skip the exact re-solve")
    ap.add_argument("--nightstand", action="store_true",
                    help="require a needed item on a spawn point near the player start")
    ap.add_argument("--spot", type=int,
                    help="require a needed item on this numbered spawn spot "
                         "(e.g. 51; implies --nightstand)")
    ap.add_argument("--within", type=float, default=6.0,
                    help="metres from the player start that count as wake-up room "
                         "(default 6.0)")
    ap.add_argument("--rooms", type=int,
                    help="keep seeds whose route touches at most this many rooms")
    ap.add_argument("--simple", action="store_true",
                    help="rank by fewest rooms first, then cost")
    ap.add_argument("--full", action="store_true",
                    help="run-shaped cost: walk from the bed, collect every item, "
                         "then walk to that route's exit")
    ap.add_argument("--first", action="store_true",
                    help="with --nightstand: the wake-up-room item must be the "
                         "first pickup")
    ap.add_argument("--seed", type=int, action="append",
                    help="score these seeds regardless of cost/top filters")
    args = ap.parse_args()

    name = (args.route_opt or args.route).lower()
    key = ALIAS.get(name)
    if key is None:
        sys.exit(f"unknown route {name!r}; try --routes")

    blob = load_index(args.rebuild)
    models, rows = blob["models"], blob["rows"]
    if key not in models:
        sys.exit(f"{key} missing from index - run with --rebuild")
    i = models.index(key)

    spots = wake_spots(blob, args.within)
    if args.spot is not None:
        want = f"Spot ({args.spot})"
        hits = [s for s in spots if s[1] == want]
        if not hits:
            names = spot_names()
            for sid, xyz in enumerate(blob.get("spots", [])):
                if names.get(tuple(xyz)) == want:
                    d = sum((a - b) ** 2 for a, b in zip(xyz, PLAYER_START)) ** 0.5
                    hits = [(sid, want, d)]
                    break
        if not hits:
            sys.exit(f"no spawn spot named {want!r} in the index")
        spots = hits
        args.nightstand = True
    night_ids = {sid for sid, _, _ in spots}

    if args.routes:
        from score import parse_dump
        dump = dump_path()
        puzzles = parse_dump(dump)[0] if dump else None
        print(f"{'route':8} {'alias':14} {'best':>6} {'p10':>6} {'median':>7}  meaning")
        for m, (aliases, meaning, items) in ROUTES.items():
            if m not in models:
                continue
            j = models.index(m)
            v = sorted(r[1][j] for r in rows)
            n = len(v)
            best = v[0]
            if puzzles:
                cand = sorted(rows, key=lambda r: r[1][j])[:25]
                its = load_items([r[0] for r in cand])
                for r in cand:
                    it = its.get(r[0])
                    if it:
                        best = min(best, exact(m, it, puzzles)[0])
            alias = "/".join(a for a in aliases if a != m)
            print(f"{m:8} {alias:14} {best:6.1f} {v[int(.1*n)]:6.1f} {v[n//2]:7.1f}  {meaning}")
        print(f"\n{len(rows)} distinct layouts from 50,000 seeds; costs are metres of pickup walking.")
        print("add --nightstand to require a needed item in the wake-up room.")
        return

    if args.target is not None:
        args.max = args.target if args.max is None else args.max

    # Filter on the cached costs first (greedy is an upper bound, so allow slack
    # when a ceiling is given, then re-solve the survivors exactly).  Room count
    # and the wake-up-room hits come from the index, so they cost nothing.
    cands = []
    for r in rows:
        rooms, pzs, night = row_metrics(blob, r, i, night_ids)
        if args.nightstand and not night and not args.seed:
            continue
        if args.rooms is not None and len(rooms) > args.rooms and not args.seed:
            continue
        cands.append((r[1][i], len(rooms), r, rooms, pzs, night))

    slack = 0.0 if args.greedy else 25.0
    if args.seed:
        want = set(args.seed)
        pool = [c for c in cands if c[2][0] in want]
        missing = want - {c[2][0] for c in pool}
        if missing:
            print("not in the index: " + ", ".join(str(s) for s in sorted(missing)))
    elif args.full:
        # The cached number is items only; a run-shaped cost adds the walk off
        # the bed and the walk out, so keep a much wider pool before solving.
        slack += 60.0
        cands.sort(key=lambda t: (t[0], t[1]))
        if args.max is not None:
            cands = [c for c in cands if c[0] <= args.max + slack]
        pool = cands[: max(args.top * 40, 600)]
    elif args.at is not None:
        cands.sort(key=lambda t: (abs(t[0] - args.at), t[1]))
        pool = cands[: max(args.top * 4, 40)]
    else:
        if args.max is not None:
            cands = [c for c in cands if c[0] <= args.max + slack]
        if args.min is not None:
            cands = [c for c in cands if c[0] >= args.min]
        if args.simple:
            cands.sort(key=lambda t: (t[1], t[0]))
        else:
            cands.sort(key=lambda t: (t[0], t[1]))
        pool = cands[: max(args.top * 4, 40)]

    puzzles = None
    if not args.greedy:
        from score import parse_dump
        dump = dump_path()
        if dump:
            puzzles = parse_dump(dump)[0]
    if args.full:
        if not puzzles:
            sys.exit("--full needs a layout dump for the puzzle rules (dump.txt)")
        if key not in EXITS:
            sys.exit(f"no exit coordinate known for {key}")
    start, end = PLAYER_START, EXITS.get(key)
    items_by_seed = load_items([c[2][0] for c in pool]) if pool else {}

    solved = []
    for cost, nrooms, r, rooms, pzs, night in pool:
        order = [blob["items"][n] for n in r[2][i] if n >= 0]
        items = items_by_seed.get(r[0])
        if puzzles and items:
            if args.full:
                from score import MODELS, closure, dp_cost_between
                need, _ = closure(MODELS[key], items, puzzles)
                cost, order = dp_cost_between(need, items, puzzles, start, end)
            else:
                cost, order = exact(key, items, puzzles)
        if args.first and night and order and order[0] not in night:
            continue
        solved.append((cost, r, order, rooms, pzs, night))

    if args.at is not None:
        solved.sort(key=lambda t: (abs(t[0] - args.at), len(t[3])))
    elif args.simple:
        solved.sort(key=lambda t: (len(t[3]), t[0]))
    else:
        solved.sort(key=lambda t: (t[0], len(t[3])))
    if args.max is not None:
        solved = [s for s in solved if s[0] <= args.max]
    if args.min is not None:
        solved = [s for s in solved if s[0] >= args.min]
    if not args.seed:
        solved = solved[: args.top]

    _, meaning, item_list = ROUTES[key]
    if not solved:
        best_seed = min(rows, key=lambda r: r[1][i])
        best_cost = best_seed[1][i]
        if puzzles:
            it = load_items([best_seed[0]]).get(best_seed[0], {})
            if it:
                best_cost = exact(key, it, puzzles)[0]
        why = ""
        if args.nightstand:
            why = " with a wake-up-room item"
        if args.rooms is not None:
            why += f" in <= {args.rooms} rooms"
        sys.exit(f"no {key} seed matches{why} ({item_list}); "
                 f"cheapest without those filters is {best_cost:.1f} m")

    print(f"{key} - {meaning} ({item_list})")
    if spots:
        print("nearest spawn points to the player start (<= %.1f m): %s"
              % (args.within, ", ".join(f"{lab} {d:.1f} m" for _, lab, d in spots)))
    if args.full:
        sx, sy, sz = PLAYER_START
        ex, ey, ez = EXITS[key]
        print("cost = bed (%.1f,%.1f,%.1f) -> pickups -> exit (%.1f,%.1f,%.1f)"
              % (sx, sy, sz, ex, ey, ez))
        print("straight-line metres, no door/climb time; layout quality only")
    print()
    print(f"{'seed':>7} {'cost':>6} {'rooms':>5} {'pz':>3}  {'nightstand':<20} pickup order\n")
    for cost, r, order, rooms, pzs, night in solved:
        tag = ", ".join(night) if night else "-"
        print(f"{r[0]:>7} {cost:6.1f} {len(rooms):5} {len(pzs):3}  {tag:<20} "
              f"{describe(items_by_seed.get(r[0]) or {}, order)}")
        print(f"{'':25}{'':22}rooms: {' -> '.join(rooms) if rooms else '-'}")
    print()

    if args.detail and items_by_seed:
        from score import MODELS
        for cost, r, order, rooms, pzs, night in solved:
            print(f"seed {r[0]}  ({cost:.1f} m, {key}, {len(rooms)} rooms, "
                  f"puzzles: {', '.join(pzs) or '-'})")
            for n in MODELS[key]:
                it = items_by_seed.get(r[0], {}).get(n)
                if it:
                    x, y, z = it["pos"]
                    print(f"    {n:<11} {x:7.1f},{y:6.1f},{z:7.1f}  {it['area']}")
                else:
                    print(f"    {n:<11} {'MISSING':>20}")
            print()

    if args.set:
        for cost, r, order, rooms, pzs, night in solved:
            print(f".\\powershell\\setseed.ps1 -Seed {r[0]}")


if __name__ == "__main__":
    main()
