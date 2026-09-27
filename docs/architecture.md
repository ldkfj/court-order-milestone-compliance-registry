# Architecture

## Scope

`CourtOrderMilestoneComplianceRegistry` records one sealed linkage between a court-order reporting clause, a bounded reporting period, and one official filing URL. It reports procedural evidence only. It does not determine contempt, substantive legal compliance, penalties, or deadlines beyond the sealed milestone tuple.

## Lifecycle

`DRAFT -> SEALED -> ON_RECORD | REVIEW_REQUIRED -> SUPERSEDED`

- `DRAFT`: only the owner may create the one evidence manifest.
- `SEALED`: the manifest is immutable and public assessment is enabled.
- `ON_RECORD`: the independent source read returned every required identity/date field, including the sealed clause ID in the order PDF and the sealed clause citation in the filing.
- `REVIEW_REQUIRED`: a source mismatch, missing date, ambiguous date, or other non-favorable result was recorded.
- `SUPERSEDED`: the owner records a replacement reference without deleting prior evidence or assessment history.

## Consensus boundary

The contract fetches bounded response bodies from the two sealed DOJ URLs with `web.get()` inside a GenLayer nondeterministic block. PDF bodies are bounded before FlateDecode expansion to 500,000 decompressed bytes and 128 streams, and the extractor returns only a canonical JSON decision vector. Validators independently refetch the same URLs and compare the complete vector exactly. Source bytes are data, not instructions; no text is executed as a prompt.

## State invariants

- The owner is the deployment sender.
- URLs must be distinct HTTPS URLs under `www.justice.gov`.
- The clause anchor must contain the sealed clause ID; the order source must contain that ID and the filing source must contain the sealed citation anchor.
- `ON_RECORD` requires `case_match`, `order_clause_match`, `report_period_match`, `filing_identity_match`, and a uniquely present filing-date anchor.
- Non-favorable outcomes set `manual_review_required` and never become `ON_RECORD`.
- Oversized, malformed, failed, or unextractable PDF bodies become empty evidence and cannot pass the favorable conjunction.
- Assessments and lifecycle events are append-only. A successful `ON_RECORD` replay is idempotent.
- Supersession references the latest assessment and preserves all earlier events.

## Out of scope

No docket crawler, private filing system, legal conclusion, payment, penalty, reputation score, frontend, or dApp is included.
