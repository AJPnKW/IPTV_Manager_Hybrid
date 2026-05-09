# Open EPG fetch and merge (XMLTV) for open-epg.com

## Overview

This project fetches multiple XMLTV EPG feeds from open-epg.com, prefers `.xml.gz` with automatic fallback to `.xml`, merges them into a single deduplicated XMLTV file (`open-epg.xml`), and produces a compact per-region summary (`summary.json`). It’s designed for resilience, visibility, and easy automation.

## Goals

- **Reliable ingestion:** Prefer compressed feeds, fallback gracefully.
- **Fast processing:** Multithreaded downloads with clear progress.
- **Clean output:** Deduplicated channels and programmes.
- **Validation:** Structural checks and anomaly reporting.
- **Monitoring:** Per-region summary JSON to spot regressions quickly.
- **Ops-friendly:** Rich logging, interactive menu, safe file handling.

## Repository structure

- **scripts/**: PowerShell script `Get-OpenEPG.ps1`.
- **data/downloads/**: Raw downloaded files (`.gz` or `.xml`).
- **data/work/**: Decompressed working `.xml` files.
- **data/output/**:
  - `open-epg.xml`: Final merged XMLTV file.
  - `summary.json`: Per-region counts of channels and programmes.
- **logs/**:
  - `open-epg.log.txt`: Timestamped run logs.

## Usage

- **Requirements:** PowerShell 7+
- **Run:**
  - Open PowerShell
  - `cd C:\Users\Lenovo\PROJECTS\get-epg-open-epg.com\get-epg-open-epg.com\scripts`
  - `./Get-OpenEPG.ps1`
  - Choose from the interactive menu:
    - **Normal Run:** Fetch → decompress → merge → validate → summarize.
    - **Clean Run:** Same as Normal Run, but cleans temp folders first.
    - **Advanced Settings:** Adjust `MaxParallel` and toggle `VerboseMode`.
    - **View Log:** Opens log in Notepad.
    - **Exit:** Quit the menu.

## Best practices implemented

- **Logging:** Timestamped levels (INFO/WARN/ERROR/DEBUG) to `.log.txt`.
- **Progress:** Spinner and ongoing console logs; never “silent”.
- **Fallback:** `.xml.gz` preferred; `.xml` backup if needed.
- **Safe paths:** No writes to root of `C:`; explicit project structure.
- **Dedup logic:** Channel by `id`; programme by `channel|start|stop|title|desc`.
- **Validation:** Checks for `<tv>`, required programme attributes, time sanity.
- **Resilience:** Continues processing on individual source errors.

## Workflow tips

- **When feeds fail:** Review `logs/open-epg.log.txt` for WARN/ERROR lines, then rerun a **Clean Run**.
- **Parallelism:** Start with `MaxParallel = 8`. Increase if network/CPU allows; decrease if I/O is constrained.
- **Verbose mode:** Useful for triage; turn off for quieter output.

## Scheduling nightly runs

You can automate a nightly run that fetches, merges, and pushes results to GitHub.

1. **Add a simple wrapper script (optional):**
   ```powershell
   # scripts\Run-Nightly.ps1
   $scriptPath = "C:\Users\Lenovo\PROJECTS\get-epg-open-epg.com\get-epg-open-epg.com\scripts\Get-OpenEPG.ps1"
   pwsh -File $scriptPath # Menu is interactive; for scheduled runs, use Clean Run via non-interactive wrapper if desired
