using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using Il2CppInterop.Runtime;
using Il2CppInterop.Runtime.InteropTypes.Arrays;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SeedSearch
{
    [BepInPlugin("granny.seedsearch", "Seed Search", "1.1.0")]
    public class SeedSearchPlugin : BasePlugin
    {
        public static ManualLogSource Log2;
        static Harmony harmony;

        public override void Load()
        {
            Log2 = Log;
            Log.LogInfo("SeedSearch ready. F10 = dump layout, F9 = scan seeds.");

            try
            {
                harmony = Harmony.CreateAndPatchAll(typeof(SeedManagerStartPatch));
                Log.LogInfo("patched SeedManager.Start");
            }
            catch (Exception e)
            {
                Log.LogError("harmony patch failed: " + e);
            }

            AddComponent<Runner>();
        }
    }

    [HarmonyPatch(typeof(SeedManager), "Start")]
    static class SeedManagerStartPatch
    {
        [HarmonyPostfix]
        static void Postfix(SeedManager __instance)
        {
            Runner.Captured = __instance;
            Runner.OnCaptured();
        }
    }

    public class Runner : MonoBehaviour
    {
        public Runner(IntPtr ptr) : base(ptr) { }

        const int SeedsPerFrame = 8;
        public static SeedManager Captured;
        static Runner instance;
        static ManualLogSource L => SeedSearchPlugin.Log2;

        SeedManager sm;
        bool dumped;
        bool scanning;
        bool scanDone;
        int scanFrom;
        int scanTo;
        int cursor;
        int currentSeed;
        DateTime scanStartUtc;
        readonly StringBuilder csv = new StringBuilder();

        // snapshot of true original state, taken once before any placement we trigger
        List<GameObject> snapshotItems;
        List<Vector3> snapshotPos;
        List<Quaternion> snapshotRot;
        List<bool> snapshotActive;
        List<string> candidateNames;
        DateTime lastRangeWrite;
        int frameCounter;
        int origGameSeed;
        int origRandomSeed;
        static int liveSeed;
        bool havePrefs;

        string OutDir => Path.Combine(Paths.BepInExRootPath, "SeedSearch");

        void Awake() { instance = this; }

        public static void OnCaptured()
        {
            L.LogInfo("SeedManager captured: seed=" + Captured.Seed + " randomize=" + Captured.RandomizeSeed);
            liveSeed = Captured.Seed;
        }

        void Update()
        {
            if (!EnsureManager()) return;

            if (!dumped)
            {
                dumped = true;
                try { DumpLayout("layout"); }
                catch (Exception e) { L.LogError("dump failed: " + e); }
                try { DumpScene("start"); }
                catch (Exception e) { L.LogError("scene dump failed: " + e); }
                CheckRangeFile();
            }

            bool f10 = false, f9 = false, f8 = false;
            try
            {
                f10 = Input.GetKeyDown(KeyCode.F10);
                f9 = Input.GetKeyDown(KeyCode.F9);
                f8 = Input.GetKeyDown(KeyCode.F8);
            }
            catch { }

            if (f8)
            {
                try { DumpScene("manual"); } catch (Exception e) { L.LogError("scene dump failed: " + e); }
            }

            if (f10)
            {
                try { DumpLayout("manual"); } catch (Exception e) { L.LogError("dump failed: " + e); }
            }

            if (f9 && !scanning)
                BeginScan(scanFrom, scanTo);

            if (scanning) StepScan();

            if (++frameCounter % 30 == 0) CheckRangeFile();
        }

        // Re-read range.txt when it changes, so consecutive scans need no restart.
        void CheckRangeFile()
        {
            if (scanning) return;
            try
            {
                string p = Path.Combine(OutDir, "range.txt");
                if (!File.Exists(p)) return;
                var t = File.GetLastWriteTimeUtc(p);
                if (t == lastRangeWrite) return;
                lastRangeWrite = t;
                TryAutoScan();
            }
            catch (Exception e) { L.LogWarning("range watch: " + e.Message); }
        }

        bool EnsureManager()
        {
            if (sm != null) return true;
            if (Captured == null) return false;
            sm = Captured;
            return true;
        }

        void TryAutoScan()
        {
            try
            {
                Directory.CreateDirectory(OutDir);
                string rangeFile = Path.Combine(OutDir, "range.txt");
                if (!File.Exists(rangeFile)) return;
                var parts = File.ReadAllText(rangeFile).Split(new[] { ' ', ',', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length < 2) return;
                int a = int.Parse(parts[0], CultureInfo.InvariantCulture);
                int b = int.Parse(parts[1], CultureInfo.InvariantCulture);
                BeginScan(a, b);
            }
            catch (Exception e) { L.LogError("range.txt: " + e.Message); }
        }

        void TakeSnapshot()
        {
            snapshotItems = new List<GameObject>();
            snapshotPos = new List<Vector3>();
            snapshotRot = new List<Quaternion>();
            snapshotActive = new List<bool>();

            var all = sm.allItems;
            for (int i = 0; i < all.Count; i++)
            {
                var go = all[i];
                if (go == null) continue;
                snapshotItems.Add(go);
                snapshotPos.Add(go.transform.position);
                snapshotRot.Add(go.transform.rotation);
                snapshotActive.Add(go.activeSelf);
            }
            L.LogInfo($"snapshot: {snapshotItems.Count} items");

            BuildCandidates();
        }

        // Every short name the game can refer to (escape items, puzzle keys, mandatory items).
        void BuildCandidates()
        {
            var set = new List<string>();
            void Add(string n)
            {
                if (string.IsNullOrEmpty(n)) return;
                for (int i = 0; i < set.Count; i++) if (set[i] == n) return;
                set.Add(n);
            }

            var req = sm.requiredEscapeItemNames;
            if (req != null) for (int i = 0; i < req.Count; i++) Add(req[i]);

            var puz = sm.puzzleDefs;
            if (puz != null)
            {
                for (int i = 0; i < puz.Count; i++)
                {
                    var pd = puz[i];
                    if (pd == null) continue;
                    var r = pd.requiredItemNames;
                    if (r != null) for (int j = 0; j < r.Count; j++) Add(r[j]);
                    var c = pd.containedItems;
                    if (c != null) for (int j = 0; j < c.Count; j++) Add(c[j]);
                }
            }

            var areas = sm.spawnAreas;
            for (int a = 0; a < areas.Length; a++)
            {
                var ar = areas[a];
                if (ar == null) continue;
                Add(ar.mandatoryItemName);
            }

            candidateNames = set;
            L.LogInfo($"candidate item names: {set.Count}");
        }

        void RestoreSnapshot()
        {
            for (int i = 0; i < snapshotItems.Count; i++)
            {
                var go = snapshotItems[i];
                if (go == null) continue;
                go.transform.position = snapshotPos[i];
                go.transform.rotation = snapshotRot[i];
                if (go.activeSelf != snapshotActive[i]) go.SetActive(snapshotActive[i]);
            }
        }

        void BeginScan(int from, int to)
        {
            try
            {
                Directory.CreateDirectory(OutDir);
                if (!EnsureManager()) { L.LogError("scan: SeedManager not captured yet"); return; }

                if (!havePrefs)
                {
                    origGameSeed = PlayerPrefs.GetInt("GameSeed", 0);
                    origRandomSeed = PlayerPrefs.GetInt("RandomSeed", 0);
                    havePrefs = true;
                }
                if (snapshotItems == null) TakeSnapshot();

                scanFrom = from; scanTo = to; cursor = from; scanDone = false;
                csv.Clear();
                csv.AppendLine("seed|live_seed|items");
                scanning = true;
                scanStartUtc = DateTime.UtcNow;
                L.LogInfo($"scan {from}..{to} started");
            }
            catch (Exception e) { L.LogError("begin scan: " + e); scanning = false; }
        }

        void StepScan()
        {
            for (int n = 0; n < SeedsPerFrame && cursor <= scanTo; n++)
            {
                currentSeed = cursor++;
                try { ScanOne(currentSeed); }
                catch (Exception e) { L.LogWarning($"seed {currentSeed}: {e.GetType().Name}: {e.Message}"); }
            }

            if (cursor > scanTo) EndScan();
        }

        void ScanOne(int seed)
        {
            RestoreSnapshot();

            PlayerPrefs.SetInt("RandomSeed", 0);
            PlayerPrefs.SetInt("GameSeed", seed);

            sm.GeneratePlacement();

            var sb = new StringBuilder();
            sb.Append(seed).Append('|').Append(sm.Seed).Append('|');

            var map = sm.itemsByName;
            for (int i = 0; i < candidateNames.Count; i++)
            {
                string name = candidateNames[i];
                if (i > 0) sb.Append(';');
                sb.Append(name).Append('@');
                GameObject go = null;
                if (map != null && map.ContainsKey(name)) go = map[name];
                if (go == null) { sb.Append("missing"); continue; }
                Vector3 p = go.transform.position;
                sb.Append(p.x.ToString("0.0", CultureInfo.InvariantCulture)).Append(',')
                  .Append(p.y.ToString("0.0", CultureInfo.InvariantCulture)).Append(',')
                  .Append(p.z.ToString("0.0", CultureInfo.InvariantCulture)).Append('@')
                  .Append(NearestArea(p));
            }
            csv.AppendLine(sb.ToString());
        }

        string NearestArea(Vector3 p)
        {
            // An item sitting exactly on a puzzle's spawn point is inside that puzzle, not on the floor.
            var puzzles = sm.puzzleDefs;
            if (puzzles != null)
            {
                for (int i = 0; i < puzzles.Count; i++)
                {
                    var pd = puzzles[i];
                    if (pd == null || pd.spawnPoint == null) continue;
                    if (Dist2(pd.spawnPoint.position, p) < 0.25f) return "in:" + pd.puzzleName;
                }
            }

            string best = "?";
            float bestD = float.MaxValue;
            var areas = sm.spawnAreas;
            for (int a = 0; a < areas.Length; a++)
            {
                var area = areas[a];
                if (area == null) continue;
                var spots = area.usedSpots;
                if (spots != null)
                {
                    for (int s = 0; s < spots.Count; s++)
                    {
                        var t = spots[s];
                        if (t == null) continue;
                        float d = Dist2(t.position, p);
                        if (d < bestD) { bestD = d; best = area.areaName; }
                    }
                }
                var free = area.freeSpots;
                if (free != null)
                {
                    for (int s = 0; s < free.Length; s++)
                    {
                        var t = free[s];
                        if (t == null) continue;
                        float d = Dist2(t.position, p);
                        if (d < bestD) { bestD = d; best = area.areaName; }
                    }
                }
            }
            if (bestD > 4f) return "unplaced";
            return best;
        }

        static string V(Vector3 p)
        {
            return p.x.ToString("0.0", CultureInfo.InvariantCulture) + "," +
                   p.y.ToString("0.0", CultureInfo.InvariantCulture) + "," +
                   p.z.ToString("0.0", CultureInfo.InvariantCulture);
        }

        static float Dist2(Vector3 a, Vector3 b)
        {
            float dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
            return dx * dx + dy * dy + dz * dz;
        }

        void EndScan()
        {
            scanning = false;
            if (scanDone) return;
            scanDone = true;
            double secs = (DateTime.UtcNow - scanStartUtc).TotalSeconds;
            int count = scanTo - scanFrom + 1;
            try
            {
                Directory.CreateDirectory(OutDir);
                string path = Path.Combine(OutDir, $"seeds-{scanFrom}-{scanTo}.csv");
                File.WriteAllText(path, csv.ToString());
                L.LogInfo($"scan done: {count} seeds in {secs:0.0}s ({count / Math.Max(0.01, secs):0.0} seeds/s) -> {path}");

                // Reproduce the player's real layout: manual mode with the live seed,
                // then put their original prefs back without re-placing.
                PlayerPrefs.SetInt("RandomSeed", 0);
                PlayerPrefs.SetInt("GameSeed", liveSeed);
                RestoreSnapshot();
                sm.GeneratePlacement();

                PlayerPrefs.SetInt("RandomSeed", origRandomSeed);
                PlayerPrefs.SetInt("GameSeed", origGameSeed);
                PlayerPrefs.Save();

                L.LogInfo($"restored layout for seed {liveSeed} (live seed field now {sm.Seed})");
                try { DumpLayout("restored"); } catch (Exception e2) { L.LogError("restored dump: " + e2); }
            }
            catch (Exception e) { L.LogError("end scan: " + e); }
        }

        string SafeSceneName()
        {
            try { return gameObject.transform.parent == null ? "?" : "?"; } catch { return "?"; }
        }

        void DumpLayout(string tag)
        {
            Directory.CreateDirectory(OutDir);
            if (!EnsureManager()) { L.LogError("dump: no SeedManager"); return; }

            var sb = new StringBuilder();
            sb.AppendLine("SeedManager dump " + DateTime.Now.ToString("s"));
            try { sb.AppendLine("scene: " + gameObject.scene.name); } catch { sb.AppendLine("scene: <unavailable>"); }
            sb.AppendLine("Seed=" + sm.Seed + "  RandomizeSeed=" + sm.RandomizeSeed +
                          "  MaxAttempts=" + SeedManager.MaxAttempts +
                          "  EscapeItemPuzzleChance=" + sm.EscapeItemPuzzleChance.ToString("0.00", CultureInfo.InvariantCulture) +
                          "  fillAllFreeSpawns=" + sm.fillAllFreeSpawns +
                          "  activatePlacedItems=" + sm.activatePlacedItems);
            sb.AppendLine();

            var req = sm.requiredEscapeItemNames;
            sb.AppendLine($"requiredEscapeItemNames ({req.Count}):");
            for (int i = 0; i < req.Count; i++) sb.AppendLine("  " + req[i]);
            sb.AppendLine();

            var areas = sm.spawnAreas;
            sb.AppendLine($"spawnAreas ({areas.Length}):");
            for (int a = 0; a < areas.Length; a++)
            {
                var ar = areas[a];
                if (ar == null) { sb.AppendLine("  <null>"); continue; }
                sb.AppendLine($"  [{a}] '{ar.areaName}' max={ar.maxItems} cur={ar.currentItems} mandatory='{ar.mandatoryItemName}' used={(ar.usedSpots == null ? 0 : ar.usedSpots.Count)} free={(ar.freeSpots == null ? 0 : ar.freeSpots.Length)}");
                if (ar.allowedItemNames != null && ar.allowedItemNames.Count > 0)
                {
                    sb.Append("        allowed: ");
                    for (int i = 0; i < ar.allowedItemNames.Count; i++) sb.Append(ar.allowedItemNames[i]).Append(i == ar.allowedItemNames.Count - 1 ? "" : ", ");
                    sb.AppendLine();
                }
                if (ar.usedSpots != null && ar.usedSpots.Count > 0)
                {
                    for (int s = 0; s < ar.usedSpots.Count; s++)
                    {
                        var t = ar.usedSpots[s];
                        if (t == null) continue;
                        var q = t.position;
                        sb.AppendLine($"        used[{s}] {V(q)}  '{t.name}' in '{PathOf(t)}'");
                    }
                }
                if (ar.freeSpots != null && ar.freeSpots.Length > 0)
                {
                    for (int s = 0; s < ar.freeSpots.Length; s++)
                    {
                        var t = ar.freeSpots[s];
                        if (t == null) continue;
                        var q = t.position;
                        sb.AppendLine($"        free[{s}] {V(q)}  '{t.name}' in '{PathOf(t)}'");
                    }
                }
            }
            sb.AppendLine();

            var items = sm.allItems;
            sb.AppendLine($"allItems ({items.Count}):");
            for (int i = 0; i < items.Count; i++)
            {
                var go = items[i];
                if (go == null) continue;
                var p = go.transform.position;
                sb.AppendLine("  " + go.name.PadRight(28) + " active=" + go.activeSelf.ToString().PadRight(5) + " pos=" + V(p) + " area=" + NearestArea(p));
            }
            sb.AppendLine();

            var shortMap = sm.itemsByName;
            if (shortMap != null)
            {
                if (candidateNames == null) BuildCandidates();
                sb.AppendLine($"itemsByName ({shortMap.Count}) short -> scene object:");
                for (int i = 0; i < candidateNames.Count; i++)
                {
                    string n = candidateNames[i];
                    sb.Append("  " + n.PadRight(18) + " -> ");
                    if (shortMap.ContainsKey(n) && shortMap[n] != null) sb.AppendLine(shortMap[n].name);
                    else sb.AppendLine("<not present>");
                }
                sb.AppendLine();
            }

            var puz = sm.puzzleDefs;
            if (puz != null)
            {
                sb.AppendLine($"puzzleDefs ({puz.Count}):");
                for (int i = 0; i < puz.Count; i++)
                {
                    var pd = puz[i];
                    if (pd == null) continue;
                    sb.Append("  " + pd.puzzleName + " prio=" + pd.Priority);
                    if (pd.spawnPoint != null) { var q = pd.spawnPoint.position; sb.Append($" at={V(q)}"); }
                    sb.Append(" req=[" + Join(pd.requiredItemNames) + "]");
                    sb.Append(" allowed=[" + Join(pd.allowedItemNames) + "]");
                    sb.Append(" contains=[" + Join(pd.containedItems) + "]");
                    sb.AppendLine();
                }
            }

            string path = Path.Combine(OutDir, $"dump-{tag}-{DateTime.Now:HHmmss}.txt");
            File.WriteAllText(path, sb.ToString());
            L.LogInfo("dump written: " + path);
        }

        static string Join(Il2CppSystem.Collections.Generic.List<string> l)
        {
            if (l == null) return "";
            var sb = new StringBuilder();
            for (int i = 0; i < l.Count; i++) { if (i > 0) sb.Append(", "); sb.Append(l[i]); }
            return sb.ToString();
        }

        static string PathOf(Transform t)
        {
            var sb = new StringBuilder();
            var cur = t;
            for (int depth = 0; cur != null && depth < 8; depth++)
            {
                if (sb.Length > 0) sb.Insert(0, "/");
                sb.Insert(0, cur.name);
                cur = cur.parent;
            }
            return sb.ToString();
        }

        // Every transform in the loaded scene: name, world position, hierarchy path.
        // The layout CSV only stores coordinates, so this is what lets us say which
        // piece of furniture an item sits on.
        void DumpScene(string tag)
        {
            try
            {
                Directory.CreateDirectory(OutDir);
                var sb = new StringBuilder();
                sb.AppendLine("scene dump " + DateTime.Now.ToString("s"));
                sb.AppendLine("scenes: " + SceneManager.sceneCount);

                try
                {
                    var player = GameObject.FindWithTag("Player");
                    if (player != null)
                        sb.AppendLine("player tag pos=" + V(player.transform.position) + " name=" + player.name +
                                      " in=" + PathOf(player.transform));
                }
                catch { }

                int count = 0;
                for (int si = 0; si < SceneManager.sceneCount; si++)
                {
                    var sc = SceneManager.GetSceneAt(si);
                    if (!sc.isLoaded) continue;
                    sb.AppendLine("### scene " + si + ": '" + sc.name + "' path='" + sc.path + "'");

                    GameObject[] roots;
                    try { roots = sc.GetRootGameObjects(); }
                    catch (Exception e) { sb.AppendLine("  <roots failed: " + e.GetType().Name + ">"); continue; }

                    var stack = new Stack<Transform>();
                    for (int i = roots.Length - 1; i >= 0; i--)
                        if (roots[i] != null) stack.Push(roots[i].transform);

                    while (stack.Count > 0 && count < 80000)
                    {
                        var t = stack.Pop();
                        if (t == null) continue;
                        count++;
                        sb.AppendLine(t.name + "\t" + V(t.position) + "\t" + PathOf(t));
                        for (int c = t.childCount - 1; c >= 0; c--)
                        {
                            var ch = t.GetChild(c);
                            if (ch != null) stack.Push(ch);
                        }
                    }
                }
                sb.AppendLine("total: " + count);

                string path = Path.Combine(OutDir, $"scene-{tag}-{DateTime.Now:HHmmss}.txt");
                File.WriteAllText(path, sb.ToString());
                L.LogInfo("scene dump written: " + path + " (" + count + " transforms)");
            }
            catch (Exception e) { L.LogError("scene dump failed: " + e); }
        }
    }
}
