import glob
import sys

target = int(sys.argv[1])
base = r"C:\Users\k\Desktop\Granny_Legacy\BepInEx\SeedSearch"


def items_of(line):
    parts = line.rstrip("\n").split("|", 2)
    if len(parts) < 3:
        return None, None
    d = {}
    for chunk in parts[2].split(";"):
        if not chunk:
            continue
        b = chunk.split("@")
        if len(b) >= 3:
            d[b[0]] = b[2] + " " + b[1]
    return int(parts[0]), tuple(sorted(d.items()))


sig = None
rows = []
for path in glob.glob(base + r"\seeds-*.csv"):
    with open(path, encoding="utf-8", errors="replace") as fh:
        fh.readline()
        for line in fh:
            seed, s = items_of(line)
            if seed is None:
                continue
            if seed == target:
                sig = s
            rows.append((seed, s))
if sig is None:
    print("target not found in CSVs")
    sys.exit(1)
dupes = sorted({seed for seed, s in rows if s == sig})
print(f"seed {target}: {len(dupes)} seeds share this exact item layout")
print("  " + ", ".join(map(str, dupes[:25])))
