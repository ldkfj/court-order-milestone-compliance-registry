# Court Order Milestone Compliance Registry

## STAGE 1

- **Objective/users:** Maintain an append-only public signal showing whether one explicit periodic-reporting milestone in a public court order has a same-case public filing. Compliance dashboards consume it; it does not declare contempt or substantive legal compliance.
- **Trust problem / GenLayer:** an order and a later status report use narrative identifiers and dates. A party-controlled index can mis-map a similarly titled filing from another matter. Validators independently connect exact case, order clause, report period, and DOJ-hosted filing.
- **Mechanism/actors/evidence:** owner seals one reporting-clause ID, one reporting period, and two DOJ URLs; assessor returns `case_match`, `order_clause_match`, `report_period_match`, `filing_identity_match`, `filing_date_state`, and `ON_RECORD/MISSING/AMBIGUOUS`. Reader gets `manual_review_required`.
- **Concrete public source set (research, checked 2026-09-21):** the [DOJ Ferguson consent-decree page](https://www.justice.gov/crt/case-document/united-states-v-city-ferguson-consent-decree) binds the decree date, document type, attachment, and related case; the [DOJ decree attachment](https://www.justice.gov/crt/file/883846/dl?inline=) contains paragraph 456, which sets periodic status reporting. The [DOJ first-status-report attachment](https://www.justice.gov/crt/case-document/file/955191/dl) identifies the same federal matter, report period, filing title, and filing date. They support exactly one filing-linkage item. A similarly titled report for another case, a report outside the sealed period, or a source that cannot expose the filing date is the counterexample and returns `AMBIGUOUS`. PDF parsing remains a build-stage feasibility gate.
- **Validator:** independent refetch/extraction with exact-match of full milestone vector; deterministic overdue/manual-review derivation.
- **Closest:** Construction Milestone Entry Gate and Public Records Custody Gap Registry. Inherited: milestone vector and missing-link detection. Material difference: deadline amendments form a precedence chain and output records docket linkage, not construction acceptance or custody sequence. Difference high; new value is a reusable judicial-order tracking receipt.
- **Risks/feasibility:** docket access and legal meaning; restrict to public official entries and procedural linkage, with disclaimer and ambiguity state. One bounded call. Build-stage probing confirmed that the two selected DOJ PDFs are reachable through `web.get()` and that bounded extraction reproduces the sealed anchors; live E2E remains a later gate.
- **Stage 1 acceptance:** clear non-legal scope, public evidence, append-only consequential history, unique mechanism and bounded deployment.

## STAGE 2

- **Model/lifecycle:** `OrderReportLink`, `EvidenceManifest`, `DocketAssessment`; `DRAFT -> SEALED -> ON_RECORD | REVIEW_REQUIRED -> SUPERSEDED`.
- **Invariants/storage:** immutable court/case/order-clause/report-period hashes; exactly one milestone; evidence cannot erase earlier history; `ON_RECORD` requires all five identity/date fields. No amendment precedence and no claim of substantive compliance.
- **API/auth:** `create_report_link`, `seal_manifest`, `assess_filing_link`, `supersede`, `get_filing_status`, `requires_manual_review`. Owner edits/seals; public assessment; strict dates/origins/hashes/enums/replay.
- **Prompt/EP:** fetched text is untrusted; strict schema; validators independently determine controlling deadline and linkage for every item; reasoning not consequential.
- **Failures/retry/appeal:** ambiguity/fetch failure no favorable write; identical replay idempotent; correction or appeal is a new evidence/deadline revision referencing prior ID; timeout preserves state.
- **Tests/E2E:** actual first-report linkage, wrong case/order clause, wrong report period, ambiguous/missing filing date, missing evidence, hostile text, malformed tuple, disagreement, auth, replay, supersession, readback/rollback.
- **CLI/architecture:** future current CLI on Studio Dev with explicit account; one contract/test/README/samples/matrix; SDK only. Exclude docket crawler, legal judgment, penalties, payments, frontend.
- **Acceptance/status:** one-item filing-linkage mechanism and source set are aligned; bounded PDF extraction, pinned local suite, lint/validation, and Studio Dev positive/auth/replay/supersession evidence are recorded. No legal-compliance conclusion is made.
