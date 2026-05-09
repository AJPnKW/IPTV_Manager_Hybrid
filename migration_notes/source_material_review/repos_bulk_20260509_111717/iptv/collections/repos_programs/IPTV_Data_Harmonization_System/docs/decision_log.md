# Decision Log

**Version:** 2025-09-21  
**Maintainer:** Andrew Pearen

## 2025-09-21 — Channel Naming Convention Finalized
**Decision:** Use format `{country}-{network}-{station} ({location})` or `{country}-{network} {variant}`  
**Rationale:** Ensures sortability, clarity, and disambiguation across countries  
**Examples:**  
- US-ABC-WXYZ (Detroit)  
- CA-CTV-CBLT (Toronto)  
- US-HBO 1  
- UK-HBO 1

## 2025-09-21 — Config-Driven Architecture Adopted
**Decision:** All transformations, mappings, and source definitions will be YAML/JSON-based  
**Rationale:** Enables reproducibility, auditability, and GUI integration

## 2025-09-21 — Binder Documentation Structure Established
**Decision:** All project documentation will be stored in `/docs` with standardized `.md` files  
**Rationale:** Supports traceability, version control, and collaborative clarity
