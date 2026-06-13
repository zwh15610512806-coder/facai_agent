$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StartupScript = Join-Path $Root "scripts\facai-agent-startup.vbs"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunName = "FacaiAgentWatchdog"
$RunValue = "wscript.exe `"$StartupScript`""

if (!(Test-Path -LiteralPath $StartupScript)) {
    throw "Startup script not found: $StartupScript"
}

New-ItemProperty -Path $RunKey -Name $RunName -Value $RunValue -PropertyType String -Force | Out-Null

$running = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match "python" -and
        $_.CommandLine -match "facai_agent_service.py"
    }
if (!$running) {
    Start-Process -FilePath "wscript.exe" -ArgumentList @($StartupScript) -WindowStyle Hidden
}

Write-Host ""
Write-Host "Facai Agent startup entry installed and started."
Write-Host "Run key: HKCU\Software\Microsoft\Windows\CurrentVersion\Run\$RunName"
Write-Host "Local URL: http://localhost:8001/app"
