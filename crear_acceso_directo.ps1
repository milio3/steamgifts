# Script de PowerShell para generar el acceso directo en el Escritorio de Windows (compatible con OneDrive)
$WshShell = New-Object -ComObject WScript.Shell

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ProjectDir) {
    $ProjectDir = (Get-Location).Path
}

$TargetBat = Join-Path $ProjectDir "ejecutar_bot.bat"

# Detectar posibles rutas del Escritorio (estándar y OneDrive)
$RutasEscritorio = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $Home "OneDrive\Desktop"),
    (Join-Path $Home "OneDrive\Escritorio")
) | Where-Object { Test-Path $_ } | Select-Object -Unique

foreach ($Desktop in $RutasEscritorio) {
    $ShortcutPath = Join-Path $Desktop "SteamGifts Bot.lnk"
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetBat
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.Description = "Ejecutar SteamGifts Bot"
    $Shortcut.IconLocation = "shell32.dll,24"
    $Shortcut.Save()
    Write-Host "✅ Acceso directo creado en: $ShortcutPath" -ForegroundColor Green
}
