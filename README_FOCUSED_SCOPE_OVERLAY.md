# IPTV Manager Hybrid — Focused Scope Overlay

## Contents

- `scripts/m3u_channel_inventory_gui.py`
- `data/channel_scope/focused_channels.csv`
- `data/channel_scope/focused_channels.json`
- `docs/channel_scope/index.html`
- `docs/channel_scope/focused_channels_summary.csv`

## Workflow

1. Extract this ZIP into `C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid`.
2. Run `scripts\m3u_channel_inventory_gui.py` using the repo `.venv` Python.
3. Click `Get M3U + EPG`.
4. Click `Parse + Publish Focused Files`.
5. Click `Git Commit + Push Published Files`.

## Stable published files

- `docs/feeds/latest_focused_playlist.m3u8`
- `docs/feeds/latest_focused_epg.xml`
- `docs/feeds/latest_scoped_playlist.m3u8`
- `docs/feeds/latest_scoped_epg.xml`
- `docs/feeds/feed_manifest.json`
- `docs/feeds/index.html`

## Scope data source

The focused channel data source was generated from the reviewed in-scope inventory CSV. It contains 148 focused channel records and intentionally excludes raw provider stream URLs.
