param(
    [Parameter(Mandatory = $true)][int]$Seed,
    [switch]$NoRelaunch,
    [switch]$Random,
    [string]$Game = "C:\Users\k\Desktop\Granny_Legacy"
)

# Start a run with an explicit manual seed.
#
# The game ignores synthetic keystrokes in the "Current Seed" field (it reads raw
# input), so this writes Unity's PlayerPrefs straight to the registry and lets the
# options screen read the value back.  The two value names are Unity's stable
# per-key hashes, discovered on this machine:
#   GameSeed   -> GameSeed_h510350364
#   RandomSeed -> RandomSeed_h3548222249
# If the game is updated these hashes can change; re-run
#   reg query "HKCU\Software\Omega Mega Gigal Intel\Granny: Legacy" /s /f Seed

$ErrorActionPreference = 'Stop'
$g = $Game
$prefs = "HKCU:\Software\Omega Mega Gigal Intel\Granny: Legacy"
$gameSeedValue = "GameSeed_h510350364"
$randomSeedValue = "RandomSeed_h3548222249"

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class UI {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool at);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
}
'@

function Click($x, $y) {
    [UI]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds 250
    [UI]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 70
    [UI]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 400
}

function FocusGame($h) {
    for ($i = 0; $i -lt 8; $i++) {
        [UI]::ShowWindow($h, 5) | Out-Null
        [UI]::SetWindowPos($h, [IntPtr]::new(-1), 0, 0, 0, 0, 0x0001 -bor 0x0002 -bor 0x0040) | Out-Null
        [UI]::BringWindowToTop($h) | Out-Null
        if ([UI]::GetForegroundWindow() -eq $h) { return $true }
        $ftid = 0
        [UI]::GetWindowThreadProcessId([UI]::GetForegroundWindow(), [ref]$ftid) | Out-Null
        $my = [UI]::GetCurrentThreadId()
        [UI]::AttachThreadInput($my, $ftid, $true) | Out-Null
        [UI]::SetForegroundWindow($h) | Out-Null
        [UI]::AttachThreadInput($my, $ftid, $false) | Out-Null
        Start-Sleep -Milliseconds 500
        if ([UI]::GetForegroundWindow() -eq $h) { return $true }
    }
    return $false
}

if (-not $NoRelaunch) {
    Get-Process -Name "Granny Legacy" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3
} elseif (Get-Process -Name "Granny Legacy" -ErrorAction SilentlyContinue) {
    throw "game is still running; prefs are flushed on exit, so close it first"
}

Set-ItemProperty -Path $prefs -Name $gameSeedValue -Value $Seed -Type DWord
Set-ItemProperty -Path $prefs -Name $randomSeedValue -Value $(if ($Random) { 1 } else { 0 }) -Type DWord
"prefs: GameSeed=$Seed RandomSeed=$(if ($Random) { 1 } else { 0 })"

Start-Process -FilePath "$g\Granny Legacy.exe" -WorkingDirectory $g
Start-Sleep -Seconds 24

$p = Get-Process -Name "Granny Legacy"
"focused: " + (FocusGame $p.MainWindowHandle)

Click 378 543      # PLAY
Start-Sleep -Seconds 4
Click 1660 986     # Continue -> loads the run with the prefs seed
Start-Sleep -Seconds 16
Click 1100 985     # tips Continue (away from the volume flyout)
Start-Sleep -Seconds 28

"--- log tail ---"
Get-Content "$g\BepInEx\LogOutput.log" -ErrorAction SilentlyContinue | Select-Object -Last 6
"--- dumps ---"
Get-ChildItem "$g\BepInEx\SeedSearch" -Filter "dump-layout-*" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime | Select-Object -Last 1 |
    ForEach-Object { "  {0}  {1}" -f $_.Name, $_.Length }
