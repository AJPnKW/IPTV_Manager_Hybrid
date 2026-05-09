# High-Level Design: Personalized EPG Explorer

## 1. Architecture Overview
- **Frontend:** Electron + React
- **Backend:** Node.js
- **Storage:** Local JSON files
- **API Integration:** TVMedia.ca REST API

## 2. Modules

### A. Channel Discovery
- Filter by country, language, genre
- Match against favorites
- Save selections to JSON

### B. Favorites Manager
- Add/remove channels
- Persist to `favorites.json`
- Used to filter EPG pulls

### C. EPG Viewer
- Pull schedule data for selected channels
- Display in timeline/calendar format
- Export to CSV/TXT

### D. Movie & Show Search
- Search by title, genre, rating, year
- Exclude adult content
- Save results to `watchlist.json`

### E. Data Management
- Save all states:
  - `in_progress.json`
  - `history.json`
  - `epg_data.json`
- Export options:
  - JSON, TXT, CSV

## 3. Data Flow
1. Load user preferences from uploaded files
2. Filter channels using Discovery module
3. Save selected channels to favorites
4. Use favorites to pull EPG data
5. Display and export results

## 4. External Dependencies
- TVMedia.ca API
- Node modules: axios, fs-extra, csv-writer
- Electron for GUI

## 5. Security & Privacy
- API key stored securely
- Local-only data storage
- No cloud sync

## 6. Future Enhancements
- Auto-sync with TVMedia.ca
- Smart recommendations
- Multi-user support
