param(
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoPath = 'C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid'
$RunId = (Get-Date).ToString('yyyyMMdd_HHmmss')
$RunRoot = Join-Path $RepoPath ('reports\active_progress\bundles\git_sync\{0}' -f $RunId)
$ExecutionLog = Join-Path $RunRoot 'execution.log.txt'
$TranscriptStarted = $false
$HadError = $false
$FinalMessage = 'Completed'

New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null
Start-Transcript -Path $ExecutionLog -Force | Out-Null
$TranscriptStarted = $true

$StandardsRoot = 'C:\Users\andrew\.repo_standards\powershell'
$CommonPath = Join-Path $StandardsRoot 'powershell_common.ps1'
$NativePath = Join-Path $StandardsRoot 'native_process.ps1'
if ((Test-Path -LiteralPath $CommonPath) -and (Test-Path -LiteralPath $NativePath)) {
    . $CommonPath
    . $NativePath
}
else {
    function Write-TextFile {
        param(
            [Parameter(Mandatory = $true)][string]$Path,
            [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Content
        )
        $parent = Split-Path -Parent $Path
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        [System.IO.File]::WriteAllText($Path, [string]$Content, [System.Text.Encoding]::UTF8)
    }

    function New-ZipFromFolder {
        param(
            [Parameter(Mandatory = $true)][string]$SourceFolder,
            [Parameter(Mandatory = $true)][string]$ZipPath
        )
        if (Test-Path -LiteralPath $ZipPath) {
            Remove-Item -LiteralPath $ZipPath -Force
        }
        Compress-Archive -Path (Join-Path $SourceFolder '*') -DestinationPath $ZipPath -Force
    }

    function Invoke-NativeProcess {
        param(
            [Parameter(Mandatory = $true)][string]$FilePath,
            [Parameter()][string[]]$ArgumentList = @(),
            [Parameter()][string]$WorkingDirectory = '',
            [Parameter()][int[]]$AllowedExitCodes = @(0),
            [Parameter()][switch]$IgnoreExitCode
        )
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FilePath
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
            $psi.WorkingDirectory = $WorkingDirectory
        }
        foreach ($arg in @($ArgumentList)) {
            [void]$psi.ArgumentList.Add($arg)
        }
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $exitCode = [int]$process.ExitCode
        $succeeded = $IgnoreExitCode.IsPresent -or (@($AllowedExitCodes) -contains $exitCode)
        return [pscustomobject]@{
            FilePath = $FilePath
            ArgumentList = @($ArgumentList)
            WorkingDirectory = if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) { (Get-Location).Path } else { $WorkingDirectory }
            ExitCode = $exitCode
            StdOut = $stdout
            StdErr = $stderr
            Succeeded = [bool]$succeeded
        }
    }
}

function Write-RunLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    $line = '[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
}

function ConvertTo-GitArgumentString {
    param([Parameter()][string[]]$ArgumentList = @())
    if (Get-Command ConvertTo-NativeArgumentString -ErrorAction SilentlyContinue) {
        return ConvertTo-NativeArgumentString -ArgumentList $ArgumentList
    }
    $escaped = foreach ($arg in @($ArgumentList)) {
        if ($null -eq $arg) {
            '""'
        }
        else {
            $text = [string]$arg
            if ($text -eq '') {
                '""'
            }
            elseif ($text -match '[\s"]') {
                '"{0}"' -f (($text -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1')
            }
            else {
                $text
            }
        }
    }
    return ($escaped -join ' ')
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter()][string]$OutputFile = '',
        [Parameter()][int[]]$AllowedExitCodes = @(0),
        [Parameter()][switch]$IgnoreExitCode
)
    Write-RunLog ('git {0}' -f ($Arguments -join ' '))
    $stdoutPath = Join-Path $RunRoot ('git_stdout_{0}.tmp' -f ([guid]::NewGuid().ToString('N')))
    $stderrPath = Join-Path $RunRoot ('git_stderr_{0}.tmp' -f ([guid]::NewGuid().ToString('N')))
    $argumentString = ConvertTo-GitArgumentString -ArgumentList $Arguments
    $process = $null
    try {
        $process = Start-Process -FilePath 'git' -ArgumentList $argumentString -WorkingDirectory $RepoPath -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    }
    catch {
        throw ('Failed to start git command: git {0}. {1}' -f ($Arguments -join ' '), $_.Exception.Message)
    }
    $exitCode = [int]$process.ExitCode
    $stdoutText = if (Test-Path -LiteralPath $stdoutPath) { [System.IO.File]::ReadAllText($stdoutPath, [System.Text.Encoding]::UTF8).TrimEnd() } else { '' }
    $stderrText = if (Test-Path -LiteralPath $stderrPath) { [System.IO.File]::ReadAllText($stderrPath, [System.Text.Encoding]::UTF8).TrimEnd() } else { '' }
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    $succeeded = $IgnoreExitCode.IsPresent -or (@($AllowedExitCodes) -contains $exitCode)
    $result = [pscustomobject]@{
        FilePath = 'git'
        ArgumentList = @($Arguments)
        WorkingDirectory = $RepoPath
        ExitCode = $exitCode
        StdOut = $stdoutText
        StdErr = $stderrText
        Succeeded = [bool]$succeeded
    }
    $content = @(
        ('Command: git {0}' -f ($Arguments -join ' '))
        ('ExitCode: {0}' -f $result.ExitCode)
        ''
        'STDOUT:'
        $result.StdOut
        ''
        'STDERR:'
        $result.StdErr
    ) -join [Environment]::NewLine
    if (-not [string]::IsNullOrWhiteSpace($OutputFile)) {
        Write-TextFile -Path $OutputFile -Content $content
    }
    if (($exitCode -eq 0) -and -not [string]::IsNullOrWhiteSpace($stderrText)) {
        Write-RunLog ('Git warning on stderr; continuing because exit code is 0: {0}' -f ($stderrText -replace "`r?`n", ' | '))
    }
    if (-not $result.Succeeded) {
        throw ('Git command failed: git {0}. ExitCode={1}. Error={2}' -f ($Arguments -join ' '), $result.ExitCode, $result.StdErr)
    }
    return $result
}

function Save-GitOutput {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter()][switch]$IgnoreExitCode
    )
    $path = Join-Path $RunRoot $FileName
    $result = Invoke-Git -Arguments $Arguments -OutputFile $path -IgnoreExitCode:$IgnoreExitCode
    return $result
}

function Ensure-GitIgnorePatterns {
    param([Parameter(Mandatory = $true)][string]$GitIgnorePath)

    $requiredPatterns = @(
        '__pycache__/'
        '*.py[cod]'
        '*.pyo'
        '*.pyd'
        '.pytest_cache/'
        '.mypy_cache/'
        '.ruff_cache/'
        '.cache/'
        '.venv/'
        'venv/'
        'env/'
        'node_modules/'
        '.parcel-cache/'
        '.vite/'
        '.next/'
        '.nuxt/'
        'build/'
        'dist/'
        'tmp/'
        'temp/'
        '.tmp/'
        '.temp/'
        '*.log'
        '*.log.txt'
        '*.tmp'
        '*.bak'
        '*.old'
        '*.orig'
        '*.sqlite-shm'
        '*.sqlite-wal'
        '.DS_Store'
        'Thumbs.db'
        '_cleanup_quarantine/'
        'reports/active_progress/bundles/**/*.zip'
        'repos/'
        'report/active_progress/'
        'reports/active_progress/bundles/'
        'reports/active_progress/exports/'
        '*.zip'
        '*.7z'
        '*.rar'
        '*.tar'
        '*.gz'
        '**/*step*.m3u'
        '**/*step*.m3u8'
        '**/*step*.xml'
        '**/*step*.xmltv'
        '**/*step*.xml.gz'
        '**/*steps*.m3u'
        '**/*steps*.m3u8'
        '**/*steps*.xml'
        '**/*steps*.xmltv'
        '**/*steps*.xml.gz'
    )

    $forbiddenPatterns = @(
        '*.m3u'
        '*.m3u8'
        '*.xml'
        '*.xmltv'
        '*.xml.gz'
        '*.json'
        '*.csv'
        '*.html'
        '*.md'
    )

    $existingLines = @()
    if (Test-Path -LiteralPath $GitIgnorePath) {
        $existingLines = @(Get-Content -LiteralPath $GitIgnorePath -Encoding UTF8)
    }
    $existingSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $existingLines) {
        $trimmed = [string]$line
        if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
            [void]$existingSet.Add($trimmed.Trim())
        }
    }

    $missing = New-Object 'System.Collections.Generic.List[string]'
    foreach ($pattern in $requiredPatterns) {
        if (-not $existingSet.Contains($pattern)) {
            [void]$missing.Add($pattern)
        }
    }

    $forbiddenPresent = New-Object 'System.Collections.Generic.List[string]'
    foreach ($pattern in $forbiddenPatterns) {
        if ($existingSet.Contains($pattern)) {
            [void]$forbiddenPresent.Add($pattern)
        }
    }

    $addedText = ''
    if ($missing.Count -gt 0) {
        $block = @(
            ''
            '# Emergency git sync stabilization'
            '# Python cache/runtime'
            '__pycache__/'
            '*.py[cod]'
            '*.pyo'
            '*.pyd'
            '.pytest_cache/'
            '.mypy_cache/'
            '.ruff_cache/'
            '.cache/'
            ''
            '# Virtual environments'
            '.venv/'
            'venv/'
            'env/'
            ''
            '# Node/frontend cache/runtime'
            'node_modules/'
            '.parcel-cache/'
            '.vite/'
            '.next/'
            '.nuxt/'
            ''
            '# Build/dist/temp'
            'build/'
            'dist/'
            'tmp/'
            'temp/'
            '.tmp/'
            '.temp/'
            ''
            '# Logs and local runtime files'
            '*.log'
            '*.log.txt'
            '*.tmp'
            '*.bak'
            '*.old'
            '*.orig'
            '*.sqlite-shm'
            '*.sqlite-wal'
            '.DS_Store'
            'Thumbs.db'
            ''
            '# Cleanup quarantine'
            '_cleanup_quarantine/'
            ''
            '# Generated report bundles'
            'reports/active_progress/bundles/**/*.zip'
            'reports/active_progress/bundles/'
            'reports/active_progress/exports/'
            ''
            '# Bulk copied/generated IPTV workspaces'
            'repos/'
            'report/active_progress/'
            ''
            '# Archive/compressed artifacts'
            '*.zip'
            '*.7z'
            '*.rar'
            '*.tar'
            '*.gz'
            ''
            '# Generated IPTV workflow leftovers'
            '**/*step*.m3u'
            '**/*step*.m3u8'
            '**/*step*.xml'
            '**/*step*.xmltv'
            '**/*step*.xml.gz'
            '**/*steps*.m3u'
            '**/*steps*.m3u8'
            '**/*steps*.xml'
            '**/*steps*.xmltv'
            '**/*steps*.xml.gz'
        )
        $blockToAppend = New-Object 'System.Collections.Generic.List[string]'
        foreach ($line in $block) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                [void]$blockToAppend.Add($line)
            }
            elseif ($line.StartsWith('#')) {
                [void]$blockToAppend.Add($line)
            }
            elseif ($missing.Contains($line)) {
                [void]$blockToAppend.Add($line)
            }
        }
        $addedText = ($blockToAppend -join [Environment]::NewLine)
        if (-not $ValidateOnly.IsPresent) {
            Add-Content -LiteralPath $GitIgnorePath -Encoding UTF8 -Value $addedText
        }
    }

    $report = @(
        ('Gitignore path: {0}' -f $GitIgnorePath)
        ('ValidateOnly: {0}' -f $ValidateOnly.IsPresent)
        ''
        'Missing required patterns that will be/were added:'
        (($missing | ForEach-Object { '- {0}' -f $_ }) -join [Environment]::NewLine)
        ''
        'Forbidden broad patterns currently present:'
        (($forbiddenPresent | ForEach-Object { '- {0}' -f $_ }) -join [Environment]::NewLine)
        ''
        'Added block:'
        $addedText
    ) -join [Environment]::NewLine
    Write-TextFile -Path (Join-Path $RunRoot 'gitignore_update.txt') -Content $report

    if ($forbiddenPresent.Count -gt 0) {
        Write-RunLog ('Warning: forbidden broad ignore patterns already exist: {0}' -f ($forbiddenPresent -join ', '))
    }

    return [pscustomobject]@{
        MissingCount = $missing.Count
        ForbiddenPresent = @($forbiddenPresent)
        AddedText = $addedText
    }
}

function Ensure-GitAttributes {
    param([Parameter(Mandatory = $true)][string]$GitAttributesPath)

    $requiredContent = @(
        '* text=auto'
        '*.ps1 text eol=crlf'
        '*.psm1 text eol=crlf'
        '*.psd1 text eol=crlf'
        '*.py text eol=lf'
        '*.json text eol=lf'
        '*.csv text eol=lf'
        '*.html text eol=lf'
        '*.md text eol=lf'
        '*.txt text eol=lf'
        '*.m3u text eol=lf'
        '*.m3u8 text eol=lf'
        '*.xml text eol=lf'
        '*.xmltv text eol=lf'
    ) -join [Environment]::NewLine

    $currentContent = ''
    if (Test-Path -LiteralPath $GitAttributesPath) {
        $currentContent = [System.IO.File]::ReadAllText($GitAttributesPath, [System.Text.Encoding]::UTF8).Trim()
    }

    if ($currentContent -ne $requiredContent.Trim()) {
        if (-not $ValidateOnly.IsPresent) {
            Write-TextFile -Path $GitAttributesPath -Content ($requiredContent + [Environment]::NewLine)
        }
        Write-TextFile -Path (Join-Path $RunRoot 'gitattributes_update.txt') -Content ('Updated/required .gitattributes content:{0}{1}' -f [Environment]::NewLine, $requiredContent)
        return $true
    }

    Write-TextFile -Path (Join-Path $RunRoot 'gitattributes_update.txt') -Content '.gitattributes already matched required content.'
    return $false
}

function Ensure-OriginRemote {
    $remoteResult = Invoke-Git -Arguments @('remote', '-v') -OutputFile (Join-Path $RunRoot 'git_remote_before_fix.txt') -IgnoreExitCode
    $remoteText = ($remoteResult.StdOut + [Environment]::NewLine + $remoteResult.StdErr).Trim()
    if ([string]::IsNullOrWhiteSpace($remoteText)) {
        if ($ValidateOnly.IsPresent) {
            Write-TextFile -Path (Join-Path $RunRoot 'git_remote_fix.txt') -Content 'ValidateOnly mode: origin remote would be added as https://github.com/AJPnKW/IPTV_Manager_Hybrid.git'
        }
        else {
            Invoke-Git -Arguments @('remote', 'add', 'origin', 'https://github.com/AJPnKW/IPTV_Manager_Hybrid.git') | Out-Null
            Write-TextFile -Path (Join-Path $RunRoot 'git_remote_fix.txt') -Content 'Added origin remote: https://github.com/AJPnKW/IPTV_Manager_Hybrid.git'
        }
        return $true
    }

    Write-TextFile -Path (Join-Path $RunRoot 'git_remote_fix.txt') -Content 'Remote already configured; no change made.'
    return $false
}

function Remove-BulkPathsFromIndex {
    $bulkPaths = @(
        'repos'
        'report/active_progress'
        'reports/active_progress/bundles'
        'reports/active_progress/exports'
        'ouput'
    )
    $lines = New-Object 'System.Collections.Generic.List[string]'
    foreach ($bulkPath in $bulkPaths) {
        [void]$lines.Add(('git rm -r --cached --ignore-unmatch {0}' -f $bulkPath))
        if (-not $ValidateOnly.IsPresent) {
            $result = Invoke-Git -Arguments @('rm', '-r', '--cached', '--ignore-unmatch', '--', $bulkPath) -IgnoreExitCode
            [void]$lines.Add(('ExitCode: {0}' -f $result.ExitCode))
            if (-not [string]::IsNullOrWhiteSpace($result.StdErr)) {
                [void]$lines.Add(('STDERR: {0}' -f $result.StdErr))
            }
        }
        else {
            [void]$lines.Add('ValidateOnly mode: not run')
        }
    }
    Write-TextFile -Path (Join-Path $RunRoot 'bulk_index_removal.txt') -Content ($lines -join [Environment]::NewLine)
}

function Clear-StagedIndex {
    if ($ValidateOnly.IsPresent) {
        Write-TextFile -Path (Join-Path $RunRoot 'clear_staged_index.txt') -Content 'ValidateOnly mode: git restore --staged -- . was not run.'
        return
    }
    $result = Invoke-Git -Arguments @('restore', '--staged', '--', '.') -IgnoreExitCode
    $fallbackResult = $null
    $emptyIndexResult = $null
    if (($result.ExitCode -ne 0) -and ($result.StdErr -match "could not resolve 'HEAD'")) {
        Write-RunLog 'No resolvable HEAD yet; clearing index with git rm --cached fallback.'
        $fallbackResult = Invoke-Git -Arguments @('rm', '-r', '--cached', '--ignore-unmatch', '--', '.') -IgnoreExitCode
        if ($fallbackResult.ExitCode -eq 0) {
            $result = $fallbackResult
        }
        else {
            Write-RunLog 'git rm --cached fallback failed; clearing unborn-branch index with git read-tree --empty.'
            $emptyIndexResult = Invoke-Git -Arguments @('read-tree', '--empty') -IgnoreExitCode
            if ($emptyIndexResult.ExitCode -eq 0) {
                $result = $emptyIndexResult
            }
        }
    }
    $content = @(
        'Command: git restore --staged -- .'
        ('ExitCode: {0}' -f $result.ExitCode)
        ''
        'STDOUT:'
        $result.StdOut
        ''
        'STDERR:'
        $result.StdErr
        ''
        'Fallback: git rm -r --cached --ignore-unmatch -- .'
        $(if ($null -ne $fallbackResult) { ('FallbackExitCode: {0}' -f $fallbackResult.ExitCode) } else { 'Fallback not used' })
        $(if ($null -ne $fallbackResult) { ('FallbackStdErr: {0}' -f $fallbackResult.StdErr) } else { '' })
        ''
        'Fallback: git read-tree --empty'
        $(if ($null -ne $emptyIndexResult) { ('EmptyIndexExitCode: {0}' -f $emptyIndexResult.ExitCode) } else { 'Empty index fallback not used' })
        $(if ($null -ne $emptyIndexResult) { ('EmptyIndexStdErr: {0}' -f $emptyIndexResult.StdErr) } else { '' })
    ) -join [Environment]::NewLine
    Write-TextFile -Path (Join-Path $RunRoot 'clear_staged_index.txt') -Content $content
    if ($result.ExitCode -ne 0) {
        throw ('Failed to clear staged index before safe staging. {0}' -f $result.StdErr)
    }
}

function Get-StagedFiles {
    $result = Invoke-Git -Arguments @('diff', '--cached', '--name-only') -IgnoreExitCode
    return @(
        $result.StdOut -split "`r?`n" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim() }
    )
}

function Assert-StagedFilesAreSafe {
    $allowed = @(
        '.gitignore'
        '.gitattributes'
        'scripts/run_git_sync_iptv_manager_hybrid.ps1'
    )
    $allowedSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($item in $allowed) {
        [void]$allowedSet.Add($item)
    }
    $staged = @(Get-StagedFiles)
    $unsafe = @($staged | Where-Object { -not $allowedSet.Contains($_) })
    Write-TextFile -Path (Join-Path $RunRoot 'staged_files_before_commit.txt') -Content ($staged -join [Environment]::NewLine)
    if ($unsafe.Count -gt 0) {
        Write-TextFile -Path (Join-Path $RunRoot 'unsafe_staged_files.txt') -Content ($unsafe -join [Environment]::NewLine)
        throw ('Refusing to commit because staged files are not limited to safe control files. Unsafe count: {0}' -f $unsafe.Count)
    }
    return $staged
}

function Write-Summary {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [Parameter(Mandatory = $true)][string]$Result,
        [Parameter()][string]$Extra = ''
    )
    $summary = @(
        'IPTV_Manager_Hybrid Emergency Git Sync'
        ('RunId: {0}' -f $RunId)
        ('RepoPath: {0}' -f $RepoPath)
        ('RunRoot: {0}' -f $RunRoot)
        ('ValidateOnly: {0}' -f $ValidateOnly.IsPresent)
        ('Result: {0}' -f $Result)
        ('Message: {0}' -f $Message)
        ''
        'Safety boundaries:'
        '- Does not touch C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting.'
        '- Does not force push.'
        '- Does not reset or rewrite history.'
        '- Uses git rm --cached only for tracked ignored files; files remain on disk.'
        ''
        $Extra
    ) -join [Environment]::NewLine
    Write-TextFile -Path (Join-Path $RunRoot 'summary.txt') -Content $summary
}

try {
    Write-RunLog 'Emergency Git sync script started'
    Write-RunLog ('Run folder: {0}' -f $RunRoot)

    $gitCommand = Get-Command git -ErrorAction Stop
    Write-RunLog ('Git found: {0}' -f $gitCommand.Source)

    if (-not (Test-Path -LiteralPath $RepoPath)) {
        throw ('Repo path does not exist: {0}' -f $RepoPath)
    }
    $resolvedRepoPath = (Resolve-Path -LiteralPath $RepoPath).Path
    if ($resolvedRepoPath -ne $RepoPath) {
        Write-RunLog ('Resolved repo path: {0}' -f $resolvedRepoPath)
    }

    $inside = Invoke-Git -Arguments @('rev-parse', '--is-inside-work-tree')
    if ($inside.StdOut.Trim() -ne 'true') {
        throw ('Path is not a Git repository: {0}' -f $RepoPath)
    }

    Save-GitOutput -Arguments @('status', '--short') -FileName 'git_status_before.txt' | Out-Null
    Save-GitOutput -Arguments @('status', '--branch') -FileName 'git_status_branch_before.txt' | Out-Null
    Save-GitOutput -Arguments @('branch', '--show-current') -FileName 'git_branch.txt' | Out-Null
    Save-GitOutput -Arguments @('remote', '-v') -FileName 'git_remote.txt' | Out-Null
    Ensure-OriginRemote | Out-Null

    $gitIgnorePath = Join-Path $RepoPath '.gitignore'
    Ensure-GitIgnorePatterns -GitIgnorePath $gitIgnorePath | Out-Null
    $gitAttributesPath = Join-Path $RepoPath '.gitattributes'
    Ensure-GitAttributes -GitAttributesPath $gitAttributesPath | Out-Null

    Save-GitOutput -Arguments @('status', '--ignored', '--short') -FileName 'git_ignored_files.txt' -IgnoreExitCode | Out-Null

    Invoke-Git -Arguments @('ls-files', '-ci', '--exclude-standard') -OutputFile (Join-Path $RunRoot 'git_tracked_ignored_files_before.txt') -IgnoreExitCode | Out-Null

    if ($ValidateOnly.IsPresent) {
        Write-TextFile -Path (Join-Path $RunRoot 'git_pull_result.txt') -Content 'ValidateOnly mode: git pull --rebase --autostash was not run.'
        Write-TextFile -Path (Join-Path $RunRoot 'git_push_result.txt') -Content 'ValidateOnly mode: git push was not run.'
        Write-TextFile -Path (Join-Path $RunRoot 'git_tracked_ignored_files_after.txt') -Content 'ValidateOnly mode: tracked ignored files were not removed from Git tracking.'
        Remove-BulkPathsFromIndex
        Save-GitOutput -Arguments @('status', '--short') -FileName 'git_status_after.txt' | Out-Null
        Write-Summary -Result 'validation_passed' -Message 'Validation completed without pull, push, commit, or Git index changes.'
        Write-RunLog 'ValidateOnly mode completed'
    }
    else {
        Clear-StagedIndex
        Remove-BulkPathsFromIndex
        $trackedIgnoredCurrent = Invoke-Git -Arguments @('ls-files', '-ci', '--exclude-standard') -OutputFile (Join-Path $RunRoot 'git_tracked_ignored_files_after_index_clear.txt') -IgnoreExitCode
        $trackedIgnored = @(
            $trackedIgnoredCurrent.StdOut -split "`r?`n" |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
        if ($trackedIgnored.Count -gt 0) {
            $batch = New-Object 'System.Collections.Generic.List[string]'
            foreach ($trackedPath in $trackedIgnored) {
                [void]$batch.Add($trackedPath)
                if ($batch.Count -ge 100) {
                    $arguments = @('rm', '-r', '--cached', '--ignore-unmatch', '--') + @($batch)
                    Invoke-Git -Arguments $arguments | Out-Null
                    $batch.Clear()
                }
            }
            if ($batch.Count -gt 0) {
                $arguments = @('rm', '-r', '--cached', '--ignore-unmatch', '--') + @($batch)
                Invoke-Git -Arguments $arguments | Out-Null
                $batch.Clear()
            }
        }
        else {
            Write-RunLog 'No tracked ignored files found'
        }

        Invoke-Git -Arguments @('ls-files', '-ci', '--exclude-standard') -OutputFile (Join-Path $RunRoot 'git_tracked_ignored_files_after.txt') -IgnoreExitCode | Out-Null

        $stageTargets = @(
            '.gitignore'
            '.gitattributes'
            'scripts/run_git_sync_iptv_manager_hybrid.ps1'
        )
        foreach ($target in $stageTargets) {
            $fullPath = Join-Path $RepoPath $target
            if (Test-Path -LiteralPath $fullPath) {
                Invoke-Git -Arguments @('add', '--', $target) | Out-Null
            }
        }

        $stagedSafeFiles = @(Assert-StagedFilesAreSafe)
        if ($stagedSafeFiles.Count -gt 0) {
            Invoke-Git -Arguments @('commit', '-m', 'Stabilize IPTV Manager git sync and ignore bulk generated files') | Out-Null
        }
        else {
            Write-RunLog 'No staged changes to commit'
        }

        $pullResult = Invoke-Git -Arguments @('pull', '--rebase', '--autostash') -OutputFile (Join-Path $RunRoot 'git_pull_result.txt') -IgnoreExitCode
        if ($pullResult.ExitCode -ne 0) {
            throw ('Pull failed. No push attempted. See git_pull_result.txt. {0}' -f $pullResult.StdErr)
        }

        $pushResult = Invoke-Git -Arguments @('push', '-u', 'origin', 'main') -OutputFile (Join-Path $RunRoot 'git_push_result.txt') -IgnoreExitCode
        if ($pushResult.ExitCode -ne 0) {
            throw ('Push failed. No force push attempted. See git_push_result.txt. {0}' -f $pushResult.StdErr)
        }

        Save-GitOutput -Arguments @('status', '--short') -FileName 'git_status_after.txt' | Out-Null
        Write-Summary -Result 'sync_completed' -Message 'Commit, pull --rebase --autostash, and push completed.'
        Write-RunLog 'Emergency Git sync completed'
    }
}
catch {
    $HadError = $true
    $FinalMessage = $_.Exception.Message
    Write-RunLog ('ERROR: {0}' -f $FinalMessage)
    try {
        Save-GitOutput -Arguments @('status', '--short') -FileName 'git_status_after.txt' -IgnoreExitCode | Out-Null
    }
    catch {}
    Write-Summary -Result 'failed' -Message $FinalMessage -Extra ($_.ScriptStackTrace)
}
finally {
    $ZipPath = Join-Path (Split-Path -Parent $RunRoot) ('{0}.zip' -f $RunId)
    if ($TranscriptStarted) {
        Stop-Transcript | Out-Null
        $TranscriptStarted = $false
    }
    try {
        if (Test-Path -LiteralPath $ZipPath) {
            Remove-Item -LiteralPath $ZipPath -Force
        }
        Compress-Archive -Path (Join-Path $RunRoot '*') -DestinationPath $ZipPath -Force
        Write-RunLog ('Run zip created: {0}' -f $ZipPath)
    }
    catch {
        Write-RunLog ('Failed to create run zip: {0}' -f $_.Exception.Message)
    }
}

if ($HadError) {
    throw $FinalMessage
}
