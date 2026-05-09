# High-Level Design (HLD)

**Version:** 2025-09-21  
**System Name:** IPTV Harmonizer

## Modules
- Source Registry & Fetch Engine
- Normalization Layer
- Alias Resolution & Matching
- Transformation Engine
- Reconciliation & Exception Handling
- Output Generator
- GUI & Automation
- Metadata Enrichment

## Data Flow
1. Fetch M3U/EPG sources
2. Normalize to canonical schema
3. Apply alias resolution
4. Transform using config rules
5. Match M3U to EPG
6. Export final M3U/XMLTV

## Naming Convention
All channels will follow:
- `{country}-{network}-{station} ({location})`
- `{country}-{network} {variant}` for numbered variants

## Output Targets
- Tivimate-compatible M3U
- XMLTV EPG files
- Grouped M3Us by country/category
