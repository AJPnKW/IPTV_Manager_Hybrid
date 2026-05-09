# get_xmltvlisting

Purpose: pull + normalize + analyze XMLTVListings lineups (XMLTV) so **your IPTV devices don't each consume the daily download quota**.

This patch includes **local analysis first** (no API calls required) so you can work with the sample XML files you already downloaded.

## Folder map (expected)

- `sample_download_XML.TV.Listings/` (your sample XML files)
- `tools/_lineups.py` (single source of truth for lineup IDs, names, labels, and defaults)
- `tools/` (PowerShell launchers + XMLTV fetch scripts)
- `src/get_xmltvlisting/` (Python code)
- `out/` (generated reports; gitignored)

## Rule

- Do not duplicate lineup IDs in workflow files, docs, or multiple scripts.
- Update `tools/_lineups.py` only if lineup IDs ever change.

## Step 1 (local overlap analysis)

Run:

```powershell
Set-Location "C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting"
powershell -ExecutionPolicy Bypass -File .\tools\run_local_analysis.ps1
```

Outputs will be written under `out\analysis\<timestamp>\`.
