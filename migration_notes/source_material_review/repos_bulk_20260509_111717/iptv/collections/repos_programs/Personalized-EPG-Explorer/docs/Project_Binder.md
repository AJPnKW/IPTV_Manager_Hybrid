# Project Binder: Personalized EPG Explorer (TVMedia.ca)

## Project Name
Personalized EPG Explorer

## Owner
Andrew

## Purpose
To build a GUI-based application that integrates with TVMedia.ca’s API to help users discover, filter, and manage TV channels and EPG data across CA, US, UK, and AU — tailored to personal preferences.

## Core Features
- Channel Discovery & Filtering
- EPG Data Viewer
- Movie & Show Search (no actor/cast data)
- Favorites Manager (channels only)
- JSON/TXT/CSV data export
- History & Progress Tracking

## File Handling
- Input: JSON (user preferences), TXT (raw listings), CSV (bulk data)
- Output: JSON (final selections), TXT (summaries), CSV (EPG exports)
- Persistent storage for:
  - Favorites
  - In-progress selections
  - History logs
  - Extracted EPG data

## Inspirations
- [AJ-Program-Guide](https://github.com/Overplay/AJ-Program-Guide)
- [node-tv-listings](https://github.com/mdpauley/node-tv-listings)
- [tv-media-tv-listings](https://github.com/mc7721/tv-media-tv-listings)

## API Reference
- TVMedia.ca API
  - Endpoints: ChannelListings, Lineup, SeriesSearch, MovieSearch, StationSearch
  - Format: JSON
  - Authentication: API key

## Next Steps
- Build Channel Discovery prototype
- Implement Favorites Manager
- Create API wrapper for TVMedia.ca
- Design GUI layout
