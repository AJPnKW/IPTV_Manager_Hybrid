# Cleanup Policy

## Tracked

- Source code under `backend/`, `scripts/`, and future app folders.
- Stable configuration, schemas, source registries, workflow profiles, and mapping definitions.
- Design documentation, operations docs, migration notes, and field dictionaries.
- Small fixtures or examples required for tests and reproducible validation.

## Ignored

- Local notes in `.my_notes/`.
- Copied upstream/source-material repos in `repos/`.
- Cleanup quarantine material in `_cleanup_quarantine/`.
- Active progress bundles and exported report archives.
- Cache, temp, build, virtual environment, logs, and compressed archive artifacts.
- Step-named generated IPTV workflow leftovers.

## Quarantined

Uncertain material is moved to `_cleanup_quarantine/<run_id>/` instead of being deleted. This includes generated typo-folder outputs, duplicate bundles, old workflow artifacts, and material that may need later review before promotion.

## Deleted

Only obvious local bloat is deleted: caches, bytecode, temp files, old active-progress bundles, old generated report zip files, and explicitly ignored runtime artifacts.

## Protected Production Boundary

`C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting` is production-separate. Cleanup in this repo must not rename, move, delete, absorb, refactor, or change behavior in `get_xmltvlisting`.

