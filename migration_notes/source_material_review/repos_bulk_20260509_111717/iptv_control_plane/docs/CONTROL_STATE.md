# IPTV Control State

Last updated: 2026-04-22

## Current Repo State

- Local branch: `main`
- Local HEAD: `713ead89caa4b7a3c944b0966ef4fd06f86b3218`
- Working tree: dirty, with substantial untracked local work under `config/`, `docs/`, `logs/`, `manifests/`, `reports/`, and many `scripts/*.ps1`
- Remote comparison baseline: `origin/main` was reported as `8ad15eee4823da18e2153444ae7ae6fd1180168d`, with local `main` behind by 10 at the time this control pass started
- This pass did not fetch, pull, rebase, reset, or otherwise change Git state

## What Exists Now

- Tracked control-plane docs already cover committed inventory and quarantine state:
  - `docs/index.html`
  - `docs/architecture/current_state.html`
  - `docs/architecture/system_registry.json`
  - `docs/inventory/quarantine_review.html`
  - `docs/inventory/quarantine_move_plan.html`
  - `reports/source_inventory_summary.txt`
  - `reports/quarantine_review_summary.txt`
  - `reports/quarantine_move_plan_summary.txt`
  - `reports/second_tier_move_plan_summary.txt`
- Untracked local work extends the control plane beyond the committed baseline:
  - promotion candidate analysis
  - promotion move planning
  - promotion parity checks
  - canonical input overlap review
  - legacy load-files dedupe review
  - deploy and pipeline pack outputs

## Status Split

### In Progress

- Inventory and cleanup planning are active and already have generated outputs.
- High-confidence quarantine planning exists for `iptv` temp/archive areas and Tivimate legacy staging.
- Second-tier review planning exists for duplicated `epg` trees and staged provider-processing outputs.
- Promotion planning exists locally for curated movement into `iptv/inputs/*` but is not committed yet.

### Future

- Local persistence concepts for control-plane decisions, manifests, and resumable execution state
- Hosting and local-network delivery model for serving curated outputs inside the home network
- Saved/downloaded playback copy strategy, including what belongs in runtime versus preserved source inputs
- Watch-party and service-integration concepts
- Source-link architecture that cleanly distinguishes URL-backed sources from local-file-backed sources
- Cross-thread/process controls so future ideas and repo decisions do not disappear into chat history

### Blocked

- Any sync work against `origin/main`
- Any cleanup that assumes the dirty local tree is already curated
- Any commit/push decision that bundles unrelated untracked work without review
- Any attempt to treat runtime folders or legacy staging folders as canonical source-of-truth

## Do Not Do Until Sync Issues Are Resolved

- Do not pull, fetch for implementation, rebase, merge, or reset this repo.
- Do not delete or bulk-move untracked local work just to make the tree clean.
- Do not promote local generated docs, manifests, or scripts blindly; review and curate them first.
- Do not rely on parity reports alone where the source side currently reads as zero files; re-validate against the actual source roots before execution.
- Do not move beyond planning/execution manifests if the move would mix committed control artifacts with unreviewed local batches.

## Backlog

### Ready Later

- Curate the untracked promotion pipeline artifacts into a minimal committed set:
  - candidate manifest
  - move plan
  - execution/report summary
- Convert the current generated-state story into one durable control-plane status page that links, rather than repeats, HTML report output.
- Formalize canonical input target folders inside the umbrella `iptv` workspace:
  - `inputs/m3u_sources`
  - `inputs/free_epg`
  - `inputs/review_from_legacy_load_files`
- Capture operator runbooks for non-destructive quarantine, promotion, and verification passes.

### Blocked By Sync/State

- Reconcile this dirty local tree with the 10-commit remote gap before any safe integration or publish workflow.
- Decide which untracked local docs in `docs/deploy/`, `docs/pipeline/`, and `docs/inventory/` are durable control artifacts versus disposable generated output.
- Decide which untracked PowerShell scripts are part of the supported toolchain versus one-off local batch helpers.
- Review the existing untracked manifests and reports before any commit boundary is chosen.

### Needs Design

- Local persistence model for job state, review state, and resumable control-plane runs
- Hosting model for local-network delivery of manifests, curated source bundles, and generated outputs
- Saved/downloaded playback copy model:
  - where copies live
  - naming and retention rules
  - what metadata links them back to source manifests
- Watch-party and external service integration model:
  - identity boundary
  - session coordination
  - source entitlement boundary
- Source-link architecture for `url` versus `local_path` provenance, validation, and publish rules
- Decision log/process control model so repo-level choices stay visible across tabs, threads, and adjacent repos

### Future Enhancement

- Consistent repo-local dashboards for current batch state, last successful run, and pending review queues
- Drift detection between committed control docs and local generated reports
- Structured backlog capture that turns dropped ideas into tagged roadmap entries instead of chat-only notes
- Hygiene rules for generated artifacts:
  - what stays local
  - what gets committed
  - what must be regenerated

## Current Signals Worth Tracking

- `reports/quarantine_review_summary.txt`: 80,388 high-confidence quarantine candidates totaling 4.58 GB
- `reports/second_tier_move_plan_summary.txt`: 8,092 second-tier candidates totaling 648.65 MB
- `reports/promotion_candidates_summary.txt` and related untracked reports: 837 promotion candidates identified locally
- `reports/promotion_move_plan_summary.txt`: 651 candidate files mapped into target input areas with zero target conflicts reported
- `reports/promotion_parity_summary.txt`: target-side files exist, but source-side counts read as zero in the current report; treat that as a validation warning, not execution clearance
- `reports/legacy_load_files_dedupe_summary.txt`: no duplicate groups found in the current legacy review target

## Control-Thread Guidance

- Use this file as the single place to capture newly surfaced future ideas unless they immediately become executable work.
- When a new concept is raised, place it in exactly one backlog section and link to the supporting artifact if one exists.
- Keep generated HTML reports as evidence, but keep this file concise and decision-oriented.
