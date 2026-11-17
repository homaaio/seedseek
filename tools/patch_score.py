import io

p = r"C:\Users\k\AppData\Local\Temp\opencode\seedsearch\score.py"
s = io.open(p, encoding="utf-8").read()

old = 'r["combo"] = r["tools6"]["cost"] + 0.35 * r["route2"]["cost"] + 0.05 * r["full11"]["cost"]'
new = 'r["combo"] = combo_of(r)'
assert s.count(old) == 2, s.count(old)
s = s.replace(old, new)

helper = '''def combo_of(r):
    """Primary weight on the car route (fewest verified items), door routes as tie-breakers."""
    return (r["car5"]["cost"]
            + 0.30 * r["tools6"]["cost"]
            + 0.10 * r["route2"]["cost"]
            + 0.02 * r["full11"]["cost"])


def score_seed('''
assert s.count("def score_seed(") == 1
s = s.replace("def score_seed(", helper, 1)

hdr_old = """print(f"\\n{'seed':>10} {'combo':>7} {'route2':>7} {'tools6':>7} {'full11':>7}  {'puzzles':>7}  key locations")"""
hdr_new = """print(f"\\n{'seed':>10} {'combo':>7} {'car5':>7} {'route2':>7} {'tools6':>7} {'full11':>7}  car-part locations")"""
assert hdr_old in s
s = s.replace(hdr_old, hdr_new)

row_old = """        locs = "  ".join(
            f"{n}:{r['items'][n]['area'].replace('in:', '@')}" for n in r["tools6"]["order"][:6]
        )
        print(f"{r['seed']:>10} {r['combo']:7.1f} {r['route2']['cost']:7.1f} "
              f"{r['tools6']['cost']:7.1f} {r['full11']['cost']:7.1f}  "
              f"{len(r['full11']['puzzles']):>7}  {locs}")"""
row_new = """        locs = "  ".join(
            f"{n}:{r['items'][n]['area'].replace('in:', '@')}" for n in r["car5"]["order"][:5]
        )
        print(f"{r['seed']:>10} {r['combo']:7.1f} {r['car5']['cost']:7.1f} "
              f"{r['route2']['cost']:7.1f} {r['tools6']['cost']:7.1f} "
              f"{r['full11']['cost']:7.1f}  {locs}")"""
assert row_old in s
s = s.replace(row_old, row_new)

assert 'for model in ("route2", "tools6", "full11"):' in s
s = s.replace('for model in ("route2", "tools6", "full11"):', "for model in MODELS:")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched score.py")
