# IPTV Channel Studio – Project Status (Baseline + Staged Updates)

## 📂 Project Folder Structure

```
IPTV-ChannelStudio/
├── channelstudio.yaml
├── pipeline.ps1
├── compare.ps1
├── README.md
├── requirements.txt
├── .venv/
├── logs/                         # runtime and debug logs
├── outputs/
│   ├── playlists/                # final curated .m3u playlists
│   ├── reports/                  # validation reports, summaries
│   └── epg/                      # processed EPG XML/JSON outputs
├── data/
│   ├── raw/                      # raw ingested source files
│   │   ├── inbox/                # new / incoming M3U/EPG
│   │   └── Processed/            # archived after initial handling
│   └── processed/
│       ├── epg/                  # normalized EPG
│       ├── registry/             # processed channel registry
│       │   └── curated/          # filtered / deduped registry
│       └── translations/         # new – mapping rules for names, groups
├── results/                      # final export-ready artifacts
└── src/
    ├── ChannelStudio.pyw         # main GUI
    ├── portal.py                 # optional web-style portal
    ├── harvest_channel_ids.py
    ├── filter_registry.py
    ├── build_playlist.py
    ├── epg_compare.py
    ├── utils/                    # helpers (logging, configs, translations)
    │   ├── logger.py
    │   ├── config_manager.py
    │   └── translation_manager.py
    └── gui/                      # future: modular GUI widgets
```

---

## ✅ Work Completed (Steps 1–5)

1. **Config Manager**  
   - Centralized defaults (countries, groups, naming rules).  
   - Saves/reapplies user configs.

2. **Logging Framework**  
   - Logs to both console + `logs/` with rotation.  
   - Consistent logging across scripts.

3. **Country/Group Filtering**  
   - Default: `US, CA, GB, AU, NZ`.  
   - Configurable via GUI + YAML.  
   - Group exclude/include functionality added.

4. **Translation Manager**  
   - Manages channel name mapping (e.g., “CTV Toronto” → “CTV”).  
   - Supports reapplying mappings after refresh.  
   - Stores translation configs.

5. **GUI Enhancements**  
   - Added selection controls for country + groups.  
   - Hooks into Config Manager + Pipeline.  
   - Previews curated registry with name, country, language.

---

## 🚧 Outstanding / Next Steps

- **Wireframes & UX polish** – design confirmation for full GUI flow.  
- **Dynamic Portal** – hyperlink explorer for all outputs + logs.  
- **Translation Reports** – export human-readable CSV of manual mappings.  
- **EPG ↔ Playlist Matching** – confirm framework for reconciliation.  
- **Baseline Reset** – lock current staged design as “Baseline v2”.  
