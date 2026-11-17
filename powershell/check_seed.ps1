param(
    [int]$Seed = 42986,
    [string]$Game = "C:\Users\k\Desktop\Granny_Legacy"
)

$ErrorActionPreference = 'Stop'
$root  = Split-Path -Parent $PSScriptRoot
$g     = $Game
$build = $PSScriptRoot
$prefs = "HKCU:\Software\Omega Mega Gigal Intel\Granny: Legacy"

Get-Process -Name "Granny Legacy" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Set-ItemProperty -Path $prefs -Name "GameSeed_h510350364" -Value $Seed -Type DWord
Set-ItemProperty -Path $prefs -Name "RandomSeed_h3548222249" -Value 0 -Type DWord
"prefs: GameSeed=$Seed"

powershell -ExecutionPolicy Bypass -File "$build\relaunch.ps1" 2>&1 | Select-Object -Last 8

Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
'@

function Shot($name) {
    $p = Get-Process -Name "Granny Legacy"
    $r = New-Object W+RECT
    [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left
    $h = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    $gfx.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
    $out = Join-Path $build $name
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    $gfx.Dispose(); $bmp.Dispose()
    "saved $out ($w x $h)"
}

Start-Sleep -Seconds 5
Shot "wake1.png"
Start-Sleep -Seconds 12
Shot "wake2.png"
