# get_xmltvlisting — XMLTV Fetch And Publish

## Current active outputs
- Provider-scoped lineup XMLTV files in `IPTV/`:
  - `Broadcast_LosAngeles_CA_US_xmltv_10272.xml`
  - `Rogers_Toronto_ON_CA_xmltv_10270.xml`
  - `Telus_Optik_Vancouver_BC_CA_xmltv_10269.xml`
  - `Verizon_FIOS_NewYork_NY_US_xmltv_10273.xml`
  - `Xfinity_Chicago_IL_US_xmltv_10271.xml`
- Country-scoped EPG exports:
  - `IPTV/EPG_CA_Canada.xml.gz`
  - `IPTV/EPG_UK_UnitedKingdom.xml.gz`
  - `IPTV/EPG_AU_Australia.xml.gz`
  - `IPTV/EPG_US_UnitedStates.xml.gz`

## Keep policy
- Treat all channels in the active provider lineup XMLTV files above as in-scope keep candidates.
- Scope and filtering decisions should be applied in review tooling, not by deleting provider channels from source lineup files.

## Multi-target publish

Use this when you want the repo synced to:
- local working copy
- GitHub
- HP920 local git clone
- HP920 LAN-hosted static XMLTV folder at `http://192.168.1.73:8011/iptv-epg/`

Run:

```powershell
Set-Location "C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting"
powershell -ExecutionPolicy Bypass -File .\tools\publish_sync_targets.ps1
```

What it does:
- installs the HP920 GitHub-sync helper
- pushes the current `main` branch to GitHub
- refreshes local plain `EPG_*.xml` files from the current `EPG_*.xml.gz` files
- tells HP920 to clone or pull the repo from GitHub into `~/sites/iptv-sync/get_xmltvlisting`
- HP920 then publishes the repo `IPTV/` folder into `/srv/my_tv_movie/app/iptv-epg`

Notes:
- HP920 currently has an active Python static web server on port `8011`
- `Gitea` was not found running on HP920 during setup, so HP920 sync uses a local clone refreshed from GitHub instead
- large files over GitHub's single-file limit should be published as `.gz` assets for GitHub compatibility
- the plain local `EPG_*.xml` copies are convenience mirrors of the compressed assets

## Archived CBC/Olympics assets
- Older CBC-specific pack outputs and CBC/Olympics helper assets are retired and may be kept under archive paths for reference only.
- They are no longer the primary workflow for this repo.

## Extended input review and scope outputs

Rebuild the review dataset directly from the source HTML:

```powershell
Set-Location "C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting"
powershell -ExecutionPolicy Bypass -File .\tools\run_build_extended_input_review.ps1
```

Build first-pass or decision-driven country scope outputs:

```powershell
Set-Location "C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting"
powershell -ExecutionPolicy Bypass -File .\tools\run_build_scope_outputs.ps1
```

If you exported decisions from `INPUT_SCOPE_CHANNEL_REVIEW.html`, use:

```powershell
Set-Location "C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting"
powershell -ExecutionPolicy Bypass -File .\tools\run_build_scope_outputs.ps1 -DecisionsJson "C:\path\to\input_scope_channel_review.json"
```

Generated scope outputs are written to:
- `IPTV/scope_outputs/SCOPE_OUTPUTS_INDEX.html`
- `IPTV/scope_outputs/UK_allowlist.json`
- `IPTV/scope_outputs/AU_allowlist.json`
- `IPTV/scope_outputs/UK_playlist_template.m3u`
- `IPTV/scope_outputs/AU_playlist_template.m3u`
- `IPTV/scope_outputs/UK_channels.xml`
- `IPTV/scope_outputs/AU_channels.xml`
