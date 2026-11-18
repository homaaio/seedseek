# Granny Legacy seed search

Find item layouts that make an escape as fast as possible, then reproduce them on demand.

The game stores a `GameSeed` in PlayerPrefs. When a run starts, `SeedManager.GeneratePlacement()`
uses it to place items. Two properties make offline search possible:

* the seed only affects **item positions** (Granny/Grandpa AI, traps and doors are not seeded),
* placement is a pure function of the seed, so replaying a seed gives the identical layout
  (verified: in-game dump matched the harvested CSV for every tracked item at seed 12847).

The retry loop (`MaxAttempts = 50`, candidates `seed + attempt`) means different seeds can
converge on the same layout; the tools deduplicate by layout signature.

## Layout

```
seedseek/
  README.md  REPORT.md  .gitignore
  tools/         python query + scoring toolkit, plus index.json + dump.txt
  powershell/    build / launch / setseed / check_seed scripts
  plugin/        Plugin.cs, build.rsp, SeedSearch.dll (BepInEx plugin)
  data/          harvest (50k seeds) + layout/scene dumps
```

## First run after cloning

```
python tools\find.py --routes          # index.json is committed, works as-is
python tools\find.py door --nightstand --full --first --top 10 --set
python tools\compact.py door 10 --set  # items close together, on one line of travel
```

Needs only Python 3 (standard library). `data/` holds the harvest and the layout +
scene dumps; `tools/index.json` (16 MB) is the committed query cache, so nothing has
to be generated before querying. The PowerShell scripts take a `-Game` path and
default to `C:\Users\<you>\Desktop\Granny_Legacy`; pass another location on a
different machine, e.g. `.\powershell\setseed.ps1 -Seed 43653 -Game D:\Games\Granny_Legacy`.

## Pieces

| File | Purpose |
| --- | --- |
| `plugin/Plugin.cs` | BepInEx 6 IL2CPP plugin: harvests layouts, writes dumps/CSVs, restores your run afterwards |
| `powershell/build.ps1` | Compiles `plugin/SeedSearch.dll` with the Roslyn compiler shipped in the local .NET SDK |
| `powershell/launch.ps1` | Deploy + launch + click through the menu; optional `-RangeFrom/-RangeTo` to queue a scan |
| `powershell/setseed.ps1` | Start a run on a chosen manual seed (writes PlayerPrefs, because the game ignores synthetic keystrokes) |
| `tools/score.py` | Scores every seed under several item models (dependency-aware, priority DP) |
| `tools/mkindex.py` | Turns `ranking-50k.json` + the CSVs into the compact `index.json` query cache |
| `tools/find.py` | **Seed lookup:** "fastest door", "sewer under 10 m", "item in the wake-up room" |
| `tools/compact.py` | Top-N seeds whose items are close together *and* on one line of travel |
| `tools/analyze.py` | Top-N lists per model, cost distribution |
| `tools/detail.py` | Full per-seed breakdown |
| `tools/doors.py` | Door-route top lists (`door4` / `door5`) |
| `tools/verify.py` | Compare a live in-game dump with the harvested row for a seed |
| `tools/ranking-50k.json` | Scored layouts (`--out` of `score.py`), committed (111 MB, needs Git LFS to push to GitHub) |
| `tools/index.json` | Query cache built by `mkindex.py` (auto-built by `find.py`), committed |

## Harvesting

1. Close the game (the DLL is locked while it runs).
2. `powershell -File powershell\build.ps1` → `plugin/SeedSearch.dll`.
3. `powershell -File powershell\launch.ps1 -RangeFrom 0 -RangeTo 24999`
   * copies the DLL, clears `BepInEx/SeedSearch`, writes `range.txt`, launches, clicks PLAY/Continue.
   * The plugin re-reads `range.txt` every 30 frames, so consecutive ranges need no restart.
4. Results land in `BepInEx/SeedSearch/seeds-<from>-<to>.csv` (~60 seeds/s, 25k ≈ 7 min).

Hotkeys in game: **F10** = dump layout, **F9** = re-run the current range,
**F8** = dump every scene transform (name, world position, hierarchy path) to
`scene-<tag>-HHMMSS.txt`; that is where furniture/room facts come from.

After a scan the plugin re-places the layout with the seed the run actually started with and
restores the original prefs, so gameplay is untouched (byte-identical dump before/after).

CSV row: `seed|live_seed|Name@x,y,z@Area;Name@…` where `Area` is the nearest spawn area, or
`in:<Puzzle>` when the item spawned inside a puzzle container.

## Scoring

`score.py --dump <dump.txt> --csv "seeds-*.csv" --refine 300 --out ranking.json`

* Requirements are expanded recursively: an item inside `Safe` needs `SafeKey`, which may itself
  be inside another puzzle.
* Route cost = shortest precedence-respecting path in metres (exact bitmask DP, greedy first pass
  over all layouts then exact DP on the finalists) plus 3 m per puzzle that must be opened.
* Models:
  * `car5` — `CarKey`, `CarBattery`, `Engine`, `Gas`, `SparkPlug`: the car ending, verified 5-item route.
  * `route2` — `MasterKey`, `PDKey`: if the front door only needs its two locks.
  * `tools6` — the six tools plausibly needed for the door.
  * `door4` / `door5` — the door's four required items, optionally plus `SPKey`.
  * `sewer` — `SPKey` (hatch: *"I need a spider key"*), `Winch` (wheel crank),
    `Pliers` (chains: *"I need a chain cutter"*); `sewer2` drops the crank.
  * `full11` — all `requiredEscapeItemNames`.
* `combo` weights `car5` fully with the others as tie-breakers.

The front door (`PickRay.ExitDoorCollEscape` → `Escapes.EscapeDoor`) needs `MasterKey` *and*
six progress flags (padlock key, two cut wires → Pliers, code, battery, extreme switch), so
`car5` is the smallest provable route; `route2`/`tools6` cover the door case.

## Looking up a seed

`find.py` answers "which seed should I play for route X at cost Y". Cost is metres of
pickup walking, so it is a *layout quality* number, not minutes: the seed cannot set a
run time, it can only put the required items close together.

```
python tools\find.py --routes              # routes, item sets, best / p10 / median cost
python tools\find.py door                  # 10 fastest door seeds
python tools\find.py door 25               # door seeds at 25 m or less
python tools\find.py sewer --max 10 --top 5
python tools\find.py car --at 24           # closest to 24 m, either side
python tools\find.py door5 --min 35 --max 40 --detail
python tools\find.py sewer --max 10 --set  # ... plus ready-made setseed.ps1 lines
python tools\find.py car --nightstand      # a needed item in the wake-up room
python tools\find.py door --spot 51        # ... on that specific spawn point
python tools\find.py sewer --nightstand --rooms 2 --simple   # 2 rooms, fewest rooms first
python tools\find.py door --nightstand --full --first --set  # bed -> cabinet -> exit
python tools\find.py door --full --detail --seed 43653       # score named seeds
```

Aliases: `door`/`door4`/`front`, `door5`, `car`/`car5`, `sewer`/`pipe`/`cellar`,
`sewer2`/`pipe2`, `tools`/`tools6`, `keys`/`route2`, `full`/`full11`.

Each candidate is re-solved with the exact DP (or the deterministic greedy pass for
the 11+ item sets), so the costs it prints do not depend on which seeds happened to
be refined when the ranking was written. `--greedy` skips that re-solve.

### Wake-up room / "nightstand" filter

`--nightstand` keeps only seeds where one of the route's **needed** items spawned on
a spawn point near where you wake up. The spot comes from the scene dump:
`PlayerStuff/PlayerStartPos` is (13.8, 21.0, −7.2), and every spawn point within
`--within` metres (default 6.0) of it is offered — today `Spot (51)`
(13.5, 21.9, −11.9) and `Spot (52)` (12.6, 20.9, −11.9), the two shelves of the
big drawers/cabinet, 4.8 m from the player. The next closest spawn point is already
a floor down in the Kitchen (6.9 m), so these are the only early-grab candidates.

* `--spot N` requires the item on that one spawn point instead.
* `--rooms K` keeps routes whose items touch at most K rooms.
* `--simple` ranks by fewest rooms first, then cost.
* `--full` ranks by the run-shaped cost: straight-line walk from the bed to every
  pickups in precedence order, then to that route's exit (front door −0.5, 13.3, 13.9;
  car 2.8, 3.1, 0.0; sewer −6.5, 9.7, −39.8). Use it whenever you care about the
  whole run — a seed can have two items 1 m apart and still cost 40 m of walking
  out of the bedroom.
* `--first` (with `--nightstand`) keeps only orders whose first pickup is the
  wake-up-room item.
* `--seed N` (repeatable) scores named seeds regardless of the top/max filters.
* The printed `rooms` column counts distinct rooms; `pz` counts puzzles (items
  inside a container).

The game has no nightstand object (bedroom furniture is merged) and no spawn point
beside the bed, so "on the nightstand" is not achievable exactly — these filters
give the closest real layouts: an item on a shelf 4.8 m from where you stand. The
dump has no room volumes, so "same room" is inferred from distance/furniture, not
proven. See `REPORT.md` for the seed lists.

`index.json` (16 MB) is built automatically from `ranking-50k.json` plus the CSVs
the first time you query; `--rebuild` forces it. It stores item → (room, spawn
spot) as integers, which is what makes the nightstand/room filters instant.

### One compact route (`compact.py`)

`find.py --full` finds the cheapest whole run but says nothing about whether the
pickups are bunched together or strung across the house. `compact.py` re-solves
the cheapest 2500 layouts and keeps only those that behave like a single line of
travel:

```
python tools\compact.py door 10 --set        # 10 best front-door seeds
python tools\compact.py car 8                # car ending
python tools\compact.py sewer --pool 6000 --maxhop 18
```

Filters: longest single hop (`--maxhop`, default 26 m), upward walking
(`--maxclimb`, default 8 m), item-to-item walking (`--maxspread`), and by
default no room entered twice and no container to open (`--revisit`,
`--puzzles` relax those). Columns: `run` (bed → pickups → exit), `bed`, `spread`
(items only), `out`, `maxhop`, `climb`.

## Rebuilding

`index.json` and `ranking-50k.json` are both committed, so queries and `find.py --rebuild`
work on a fresh clone. `ranking-50k.json` is ~110 MB and derivable; if you drop it,
regenerate it before `find.py --rebuild`:

```
python tools\score.py --dump tools\dump.txt --csv data\seeds-*.csv --refine 300 --out tools\ranking-50k.json
python tools\find.py --rebuild
```

`score.py` reads the CSVs + a layout dump, so a new harvest only needs:

```
# after a scan, copy the new CSVs next to the old ones
copy ..\Granny_Legacy\BepInEx\SeedSearch\seeds-*.csv data\
python tools\score.py --dump tools\dump.txt --csv data\seeds-*.csv --refine 300 --out tools\ranking-50k.json
python tools\mkindex.py            # or just: python tools\find.py --rebuild
```

## Reproducing a seed

In game: options → **Current Seed**, type the number, press Enter (`*ENTER to Save*` appears),
untick **Random**, Continue.

Or run `powershell -File powershell\setseed.ps1 -Seed 12847`, which writes:
`HKCU\Software\Omega Mega Gigal Intel\Granny: Legacy` → `GameSeed_h510350364 = seed`,
`RandomSeed_h3548222249 = 0`. (Unity hashes the pref names; re-discover them with
`reg query ... /s /f Seed` if a game update changes them.)

The options screen then shows the seed, and the plugin dumps the layout so you can compare it
with `detail.py`.
