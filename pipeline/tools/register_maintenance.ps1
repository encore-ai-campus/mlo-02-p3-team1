param([string]$Python = (Get-Command python).Source)
$ErrorActionPreference = 'Stop'
$pipelineRoot = Split-Path -Parent $PSScriptRoot
$jobPath = Join-Path $PSScriptRoot 'maintenance_job.py'
$logPath = Join-Path $pipelineRoot 'results\maintenance\latest.log'
$action = New-ScheduledTaskAction -Execute $Python -Argument ('"' + $jobPath + '" --execute --log "' + $logPath + '"')
$trigger = New-ScheduledTaskTrigger -Daily -At '03:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'NODEVERSE-Pipeline-Maintenance' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Daily local 03:00 Delta maintenance; validate rows, resume Spark, publish failures.' -Force
Get-ScheduledTaskInfo -TaskName 'NODEVERSE-Pipeline-Maintenance'
