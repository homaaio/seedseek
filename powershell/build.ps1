param(
    [string]$Game   = "C:\Users\k\Desktop\Granny_Legacy",
    [string]$DotNet = "C:\Users\k\AppData\Local\Temp\opencode\dotnet"
)

$ErrorActionPreference = 'Stop'

$root   = Split-Path -Parent $PSScriptRoot     # <repo>
$plugin = Join-Path $root "plugin"
$dotnet = $DotNet
$csc    = "$dotnet\sdk\6.0.428\Roslyn\bincore\csc.dll"
$refdir = "$dotnet\packs\Microsoft.NETCore.App.Ref\6.0.36\ref\net6.0"
$g      = $Game
$src    = $plugin

foreach ($p in @($csc, $refdir, "$g\BepInEx\interop\Assembly-CSharp.dll")) {
    if (-not (Test-Path $p)) { throw "missing: $p" }
}

$refs = New-Object System.Collections.Generic.List[string]
Get-ChildItem $refdir -Filter *.dll | ForEach-Object { $refs.Add($_.FullName) }
foreach ($n in @("BepInEx.Core","BepInEx.Unity.IL2CPP","BepInEx.Unity.Common","Il2CppInterop.Runtime","Il2CppInterop.Common","0Harmony")) {
    $refs.Add("$g\BepInEx\core\$n.dll")
}
Get-ChildItem "$g\BepInEx\interop" -Filter *.dll | ForEach-Object { $refs.Add($_.FullName) }

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("-target:library")
$lines.Add("-nologo")
$lines.Add("-nostdlib+")
$lines.Add("-noconfig")
$lines.Add("-langversion:latest")
$lines.Add("-optimize+")
$lines.Add("-deterministic+")
$lines.Add("-warn:1")
$lines.Add("-out:`"$src\SeedSearch.dll`"")
$lines.Add("-define:IL2CPP")
foreach ($r in $refs) { $lines.Add("-r:`"$r`"") }
$lines.Add("`"$src\Plugin.cs`"")

$rsp = "$src\build.rsp"
Set-Content -Path $rsp -Value $lines -Encoding UTF8
"references: $($refs.Count)"

Remove-Item "$src\SeedSearch.dll" -Force -ErrorAction SilentlyContinue
& "$dotnet\dotnet.exe" exec $csc "@$rsp"
"exit code: $LASTEXITCODE"
if (Test-Path "$src\SeedSearch.dll") {
    "built: $((Get-Item "$src\SeedSearch.dll").Length) bytes"
} else {
    "BUILD FAILED"
}
