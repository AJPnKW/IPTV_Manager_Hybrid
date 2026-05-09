# Source Material Review

`repos/` is source material only. It is not part of the canonical application tree and must not be merged wholesale.

Useful files from copied upstream repos may be promoted only by explicit review. A promotion must record:

- original path
- reason for promotion
- destination path
- whether the file is source, schema, fixture, config, documentation, or reference material
- validation performed

Bulk repo contents, generated outputs, temp folders, upstream histories, and quarantine material stay ignored or quarantined until reviewed.

## Batch 3 Repos Bulk Drain

The copied `repos/` source-material bulk was moved out of the active repo root:

- external location: `C:\Users\andrew\PROJECTS\iptv_quarantine\IPTV_Manager_Hybrid_repos_bulk_20260509_111717\repos\`
- reason: preserve source material without forcing Git, GitHub Desktop, or normal repo commands to scan nested copied repositories
- active repo rule: `repos/` must not be recreated as a copied-repo holding area inside `IPTV_Manager_Hybrid`

Future review must promote individual useful assets only. Promote a file by copying it into the appropriate canonical folder, recording the original source path, and validating that it is not generated bloat, provider dump material, or copied upstream history.
