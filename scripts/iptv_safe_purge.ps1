#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$canonical_root = 'C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid'
$repos_root = Join-Path $canonical_root 'repos'
$census_root = Join-Path $canonical_root 'report\active_progress\bundles\iptv_cleanup_census'
$run_id = Get-Date -Format 'yyyyMMdd_HHmmss'
$run_root = Join-Path $canonical_root ("report\active_progress\bundles\iptv_safe_purge\" + $run_id)
$log_path = Join-Path $run_root 'execution.log.txt'
$deleted_csv_path = Join-Path $run_root 'deleted_items.csv'
$summary_json_path = Join-Path $run_root 'deletion_summary.json'
$zip_path = Join-Path $canonical_root ("report\active_progress\exports\iptv_safe_purge_" + $run_id + ".zip")

function New-DirectorySafe {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-LogLine {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Message
    )
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = ('[{0}] {1}' -f $timestamp, $Message)
    Add-Content -LiteralPath $Path -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-LatestSafeJunkCsv {
    param([Parameter(Mandatory)][string]$Root)
    $files = Get-ChildItem -LiteralPath $Root -Recurse -Filter 'safe_junk_candidates.csv' -File | Sort-Object LastWriteTime -Descending
    if (-not $files) {
        throw 'No safe_junk_candidates.csv file was found under the cleanup census bundle path.'
    }
    return $files[0].FullName
}

function Assert-UnderReposRoot {
    param(
        [Parameter(Mandatory)][string]$TargetPath,
        [Parameter(Mandatory)][string]$ReposRoot
    )
    $full_target = [System.IO.Path]::GetFullPath($TargetPath)
    $full_root = [System.IO.Path]::GetFullPath($ReposRoot)
    if (-not $full_target.StartsWith($full_root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw ('Refusing to touch path outside repos root: {0}' -f $full_target)
    }
    return $full_target
}

New-DirectorySafe -Path $run_root
Set-Content -LiteralPath $log_path -Value '' -Encoding UTF8

Write-LogLine -Path $log_path -Message 'IPTV safe purge started.'
Write-LogLine -Path $log_path -Message ('Canonical root: {0}' -f $canonical_root)
Write-LogLine -Path $log_path -Message ('Repos root: {0}' -f $repos_root)

if (-not (Test-Path -LiteralPath $repos_root)) {
    throw ('Repos root not found: {0}' -f $repos_root)
}

if (-not (Test-Path -LiteralPath $census_root)) {
    throw ('Cleanup census bundle root not found: {0}' -f $census_root)
}

$safe_junk_csv = Get-LatestSafeJunkCsv -Root $census_root
Write-LogLine -Path $log_path -Message ('Using census file: {0}' -f $safe_junk_csv)

$rows = Import-Csv -LiteralPath $safe_junk_csv
if (-not $rows) {
    throw 'The safe junk candidates file is empty.'
}

$deleted_rows = New-Object System.Collections.Generic.List[object]
$deleted_files = 0
$deleted_dirs = 0
$missing_paths = 0
$error_count = 0

foreach ($row in $rows) {
    $relative_path = $row.relative_path
    $candidate_type = $row.candidate_type
    $repo_name = $row.repo_name

    $target_path = Join-Path $repos_root $relative_path
    $target_path = Assert-UnderReposRoot -TargetPath $target_path -ReposRoot $repos_root

    try {
        if (-not (Test-Path -LiteralPath $target_path)) {
            $missing_paths++
            Write-LogLine -Path $log_path -Message ('Missing, skipped: {0}' -f $relative_path)
            continue
        }

        $item = Get-Item -LiteralPath $target_path -Force
        $item_type = if ($item.PSIsContainer) { 'directory' } else { 'file' }

        if ($item.PSIsContainer) {
            Remove-Item -LiteralPath $target_path -Recurse -Force
            $deleted_dirs++
        }
        else {
            Remove-Item -LiteralPath $target_path -Force
            $deleted_files++
        }

        $deleted_rows.Add([pscustomobject]@{
            repo_name = $repo_name
            candidate_type = $candidate_type
            item_type = $item_type
            relative_path = $relative_path
            deleted_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        }) | Out-Null

        Write-LogLine -Path $log_path -Message ('Deleted {0}: {1}' -f $item_type, $relative_path)
    }
    catch {
        $error_count++
        Write-LogLine -Path $log_path -Message ('ERROR deleting {0}: {1}' -f $relative_path, $_.Exception.Message)
    }
}

if ($deleted_rows.Count -gt 0) {
    $deleted_rows | Export-Csv -LiteralPath $deleted_csv_path -NoTypeInformation -Encoding UTF8
}
else {
    Set-Content -LiteralPath $deleted_csv_path -Value '' -Encoding UTF8
}

$summary = [ordered]@{
    run_type = 'iptv_safe_purge'
    canonical_root = $canonical_root
    repos_root = $repos_root
    census_file_used = $safe_junk_csv
    deleted_file_count = $deleted_files
    deleted_directory_count = $deleted_dirs
    missing_path_count = $missing_paths
    error_count = $error_count
    deleted_items_csv = $deleted_csv_path
    log_path = $log_path
    overall_status = if ($error_count -eq 0) { 'passed' } else { 'partial' }
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summary_json_path -Encoding UTF8

if (Test-Path -LiteralPath $zip_path) {
    Remove-Item -LiteralPath $zip_path -Force
}
Compress-Archive -Path (Join-Path $run_root '*') -DestinationPath $zip_path -CompressionLevel Optimal -Force

Write-LogLine -Path $log_path -Message ('Deleted files: {0}' -f $deleted_files)
Write-LogLine -Path $log_path -Message ('Deleted directories: {0}' -f $deleted_dirs)
Write-LogLine -Path $log_path -Message ('Missing paths skipped: {0}' -f $missing_paths)
Write-LogLine -Path $log_path -Message ('Errors: {0}' -f $error_count)
Write-LogLine -Path $log_path -Message ('Deleted items CSV: {0}' -f $deleted_csv_path)
Write-LogLine -Path $log_path -Message ('Summary JSON: {0}' -f $summary_json_path)
Write-LogLine -Path $log_path -Message ('Zip export: {0}' -f $zip_path)
Write-LogLine -Path $log_path -Message 'IPTV safe purge completed.'

Write-Host ''
Write-Host 'Completion summary'
Write-Host ('Deleted files: {0}' -f $deleted_files)
Write-Host ('Deleted directories: {0}' -f $deleted_dirs)
Write-Host ('Missing paths skipped: {0}' -f $missing_paths)
Write-Host ('Errors: {0}' -f $error_count)
Write-Host ('Summary JSON: {0}' -f $summary_json_path)
Write-Host ('Zip export: {0}' -f $zip_path)
Read-Host 'Press Enter to close'
