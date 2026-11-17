"""Build a compact query index (index.json) from the harvest + rankings.

The big files are expensive to parse on every query:
  ranking-50k.json   ~95 MB, per-model costs and pickup orders
  seeds-*.csv        ~30 MB, every seeded item's room and coordinates

index.json stores the same information as integer arrays, so `find.py` can
answer a query in well under a second.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, os.pardir, "data"))  # <repo>\data
RANKING = os.path.join(HERE, "ranking-50k.json")


def read_locations(csv_globs):
    """seed -> {item: (area, (x, y, z))} from the harvested CSVs."""
    out = {}
    for pattern in csv_globs:
        for path in glob.glob(pattern):
            with open(path, encoding="utf-8", errors="replace") as fh:
                fh.readline()
                for line in fh:
                    parts = line.rstrip("\n").split("|", 2)
                    if len(parts) < 3:
                        continue
                    seed = int(parts[0])
                    loc = {}
                    for chunk in parts[2].split(";"):
                        if not chunk:
                            continue
                        bits = chunk.split("@")
                        if len(bits) >= 3:
                            try:
                                xyz = tuple(round(float(v), 1)
                                            for v in bits[1].split(","))
                            except ValueError:
                                continue
                            if len(xyz) == 3:
                                loc[bits[0]] = (bits[2], xyz)
                    out[seed] = loc
    return out


def data_dir():
    """Where the harvested CSVs live (repo copy first, then the live game folder)."""
    for d in (os.path.join(HERE, "data"),
              r"C:\Users\k\Desktop\Granny_Legacy\BepInEx\SeedSearch"):
        if os.path.isdir(d) and glob.glob(os.path.join(d, "seeds-*.csv")):
            return d
    return None


def build(ranking=RANKING, csv_globs=None, out=os.path.join(HERE, "index.json")):
    if csv_globs is None:
        d = data_dir()
        if not d:
            sys.exit("no seeds-*.csv found")
        csv_globs = [os.path.join(d, "seeds-*.csv")]
    ranked = json.load(open(ranking, encoding="utf-8"))
    loc_by_seed = read_locations(csv_globs)
    print(f"ranked {len(ranked)}, seeded {len(loc_by_seed)}", file=sys.stderr)

    models = [k for k in ranked[0] if isinstance(ranked[0][k], dict) and "cost" in ranked[0][k]]
    items, areas_tab, areas_idx = [], [], {}
    spots, spots_idx = [], {}

    def spot_id(xyz):
        if xyz not in spots_idx:
            spots_idx[xyz] = len(spots)
            spots.append([xyz[0], xyz[1], xyz[2]])
        return spots_idx[xyz]

    rows = []
    for r in ranked:
        seed = r["seed"]
        loc = loc_by_seed.get(seed, {})
        # Area table is shared between rows: one id per distinct room string.
        loc_ids = []
        for name in sorted(loc):
            if name not in items:
                items.append(name)
            area, xyz = loc[name]
            if area not in areas_idx:
                areas_idx[area] = len(areas_tab)
                areas_tab.append(area)
            loc_ids.append([items.index(name), areas_idx[area], spot_id(xyz)])
        costs, orders = [], []
        for m in models:
            costs.append(round(r[m]["cost"], 1))
            orders.append([items.index(n) if n in items else -1 for n in r[m]["order"]])
        rows.append([seed, costs, orders, loc_ids])

    blob = {
        "models": models,
        "items": items,
        "areas": areas_tab,
        "spots": spots,
        "rows": rows,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, separators=(",", ":"))
    print(f"wrote {out} ({os.path.getsize(out)/1e6:.1f} MB), "
          f"{len(models)} models, {len(items)} items, {len(spots)} spots", file=sys.stderr)


if __name__ == "__main__":
    csvs = sys.argv[1:] or None
    build(csv_globs=csvs)
