param(
    [int]$RangeFrom = -1,
    [int]$RangeTo = -1,
    [switch]$KeepLogs,
    [string]$Game = "C:\Users\k\Desktop\Granny_Legacy"
)

$ErrorActionPreference = 'Stop'
$root  = Split-Path -Parent $PSScriptRoot
$g     = $Game
$build = Join-Path $root "plugin"

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class U {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@

function Click($x, $y) {
    [U]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds 300
    [U]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [U]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 400
}

# Windows blocks SetForegroundWindow from a background process, so verify and,
# if needed, click once on a harmless spot to hand focus to the game.
function FocusGame($h) {
    for ($i = 0; $i -lt 6; $i++) {
        [U]::SetForegroundWindow($h) | Out-Null
        Start-Sleep -Milliseconds 400
        if ((Get-Process -Name "Granny Legacy").MainWindowHandle -eq $h) {
            if ([U]::GetForegroundWindow() -eq $h) { return $true }
        }
        Click 960 540
    }
    return $false
}

Get-Process -Name "Granny Legacy" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Copy-Item "$build\SeedSearch.dll" "$g\BepInEx\plugins\SeedSearch.dll" -Force
if (-not $KeepLogs) { Remove-Item "$g\BepInEx\*.log" -Force -ErrorAction SilentlyContinue }
Remove-Item "$g\BepInEx\SeedSearch" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$g\BepInEx\SeedSearch" | Out-Null

if ($RangeFrom -ge 0 -and $RangeTo -ge 0) {
    Set-Content "$g\BepInEx\SeedSearch\range.txt" "$RangeFrom $RangeTo" -Encoding ascii
    "range: $RangeFrom..$RangeTo"
}

Start-Process -FilePath "$g\Granny Legacy.exe" -WorkingDirectory $g
Start-Sleep -Seconds 22

$p = Get-Process -Name "Granny Legacy"
"focused: " + (FocusGame $p.MainWindowHandle)
Click 378 497      # PLAY
Start-Sleep -Seconds 4
Click 1660 983     # Continue (options)
Start-Sleep -Seconds 14
Click 963 983      # Continue (game tips)
Start-Sleep -Seconds 25

"--- log tail ---"
Get-Content "$g\BepInEx\LogOutput.log" -ErrorAction SilentlyContinue | Select-Object -Last 25
"--- SeedSearch dir ---"
Get-ChildItem "$g\BepInEx\SeedSearch" -ErrorAction SilentlyContinue | ForEach-Object { "  " + $_.Name + "  " + $_.Length }
