# IPTV Manager Hybrid Target Structure

This structure is the local go-forward shape while `IPTV_Manager_Hybrid` remains the leading canonical candidate pending evidence.

```text
backend/                         application/backend source
config/                          configuration, source registries, workflow profiles
data/                            canonical data, mappings, decisions, curated references
docs/                            architecture, operations, migration, field dictionaries
input/                           curated source examples, fixtures, review queues
outputs/                         generated runtime outputs, generally ignored unless fixtures
reports/                         stable current/history reports; active_progress ignored
scripts/                         cleanup, git, validation, census, and workflow scripts
schemas/                         JSON/schema definitions
tests/                           fixtures and validation tests
migration_notes/                 source-material review notes and promotion records
production_links/                external production contracts, especially get_xmltvlisting
repos/                           ignored source-material stash; no wholesale staging
_cleanup_quarantine/             ignored quarantine for uncertain generated/bulk material
```

Top-level generated report bundles and copied upstream repos are not source of truth. They must stay ignored unless a specific asset is promoted into a reviewed destination.

