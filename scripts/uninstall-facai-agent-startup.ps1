$ErrorActionPreference = "Continue"

$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunName = "FacaiAgentWatchdog"

Remove-ItemProperty -Path $RunKey -Name $RunName -ErrorAction SilentlyContinue

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match "python|cmd|wscript" -and
        $_.CommandLine -match "facai_agent_service|start-facai-agent-service|facai-agent-startup|main:app"
    }

foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Facai Agent startup entry removed and current local service stopped."
