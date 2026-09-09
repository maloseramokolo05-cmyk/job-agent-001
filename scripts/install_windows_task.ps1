$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $Root "scripts\run_agent.bat"
$Action = New-ScheduledTaskAction -Execute $Script -WorkingDirectory $Root
$Triggers = @("07:00","13:00","18:00") | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
Register-ScheduledTask -TaskName "Tumelo Job Agent" -Action $Action -Trigger $Triggers -Description "Search and prepare job applications locally" -Force
Write-Host "Scheduled Tumelo Job Agent at 07:00, 13:00 and 18:00."
