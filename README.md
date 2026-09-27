# Court Order Milestone Compliance Registry

An append-only GenLayer signal for whether one sealed court-order reporting milestone has a same-case official filing.

## Live Deployment

Studio Dev (chain 61997) deployment: `0x6Dc0D76Cb47093882e2B1d0CB163339F9F40f654` (deployment tx `0x29f62af484e4c6ff10de5d5ad340aa990f5f1e4d62099b2907982e908e9d05d8`). The positive assessment finalized as `ON_RECORD` and the lifecycle was then superseded. This contract does not claim legal compliance or contempt.

Live receipts: create `0x83c1568afdcb4476d952fc7d77a48c4fc1f647e4eb7759d5c6bb5c90656a67aa`; seal `0xa06c4f286134c4eb202775af79d1aed80091d2ad1be728e5b16db9d1e21d773f`; assess `0x5e7f87801e7a3374019614330ad540633ba804585c8d16cf005ca2316a0914c8`; replay `0x10952b40b8868c5ca400487af33e288c52969e7a7d84f43850674f9d27aebadf`; unauthorized `0x3891692bc297f982eca54fe0f757008bac7b64208130dd8c6f2223fc5825976c` (expected execution error); supersede `0xe5faa0d31ae58ea2cca891cfb95f050e2d3f3a88c5cbba2f63ffe4fd754184ac`.

Negative live evidence: wrong-case assessment `0xd3bc3f225c636b1d3151698c51e4469316c9781ea3cfdfacaf38e083760eabaa` returned `REVIEW_REQUIRED`; missing-date assessment `0x4db3121aeced72e487af3cede6d28d991ac7c8690f4540430b99d283f8377227` was non-favorable.

## Purpose

The registry addresses a narrow linkage problem: a court order and a later public status report may use narrative identifiers and dates, while a party-controlled index can point to a similarly titled filing from another matter. The owner seals exact case, clause, period, filing identity, date, and two DOJ URLs. Validators independently refetch the sources and agree on the complete decision vector.

## API

- `create_report_link(...)`: owner-only creation of the one immutable evidence manifest.
- `seal_manifest()`: owner-only transition from `DRAFT` to `SEALED`.
- `assess_filing_link()`: public consensus assessment; writes an append-only assessment and derives `ON_RECORD` or `REVIEW_REQUIRED`.
- `supersede(replacement_reference)`: owner-only append-only replacement marker.
- `get_manifest()`: deterministic oracle view of the sealed linkage tuple and hash.
- `get_filing_status()`: deterministic oracle view for dashboards and downstream contracts.
- `requires_manual_review()`: deterministic boolean oracle view.
- `get_assessment(id)` and `get_history()`: public audit readbacks.

## Consensus Binding Matrix

| Field | Source | Stored? | Downstream effect | Validator check | Binding mode | Differential test |
|---|---|---:|---|---|---|---|
| `case_match` | Sealed case ID + both DOJ texts | Yes | Part of `ON_RECORD` | Re-fetch and exact compare | Full-vector exact | Wrong case number |
| `order_clause_match` | Sealed clause ID/anchor + order/report text | Yes | Part of `ON_RECORD` | Re-fetch and exact compare | Full-vector exact | Mismatched clause ID/anchor |
| `report_period_match` | Sealed period/start/end anchors + filing text | Yes | Part of `ON_RECORD` | Re-fetch and exact compare | Full-vector exact | Wrong period |
| `filing_identity_match` | Sealed filing identity anchor + filing text | Yes | Part of `ON_RECORD` | Re-fetch and exact compare | Full-vector exact | Wrong filing identity |
| `filing_date_state` | Sealed date anchor + filing text count | Yes | `ON_RECORD`, `MISSING`, or `AMBIGUOUS` | Re-fetch and exact compare | Full-vector exact | Missing/duplicate date |
| `outcome` | Deterministic conjunction of the above | Yes | Lifecycle state | Derived from validated fields | Deterministic derivation | Any vector change |
| `manual_review_required` | `outcome != ON_RECORD` | Yes | Dashboard routing | Deterministic derivation | Deterministic derivation | Any non-favorable outcome |

## Security and limitations

Source bytes and extracted text are bounded and treated only as untrusted data. Static DOJ PDFs are fetched with `web.get()` and decoded with a bounded standard-library extractor (500,000 decompressed bytes and 128 PDF streams); malformed, oversized, or unavailable sources produce no favorable evidence. The contract does not parse arbitrary instructions or call an LLM. Official pages can change, disappear, expose incomplete PDF text, or contain ambiguous identifiers; those conditions are intentionally non-favorable and require manual review. The registry is a procedural linkage receipt, not a legal finding.

## Tests

Run with the pinned Studio Next toolchain:

```text
genvm-lint lint contracts/court_order_milestone_compliance_registry.py --json
genvm-lint validate contracts/court_order_milestone_compliance_registry.py --json
pytest tests -q
```

The local Direct Mode suite covers lifecycle, authorization, exact consensus binding, wrong case/period, missing evidence, replay idempotency, and supersession. Studio Dev deployment and live evidence are recorded here after the PRE-DEPLOY gate.

## Consensus Engineering Lessons

- Store only a canonical decision vector; do not store validator-specific explanations.
- Bind the case number and clause/period anchors together so similarly titled filings cannot pass on title alone.
- Treat missing and ambiguous date evidence as non-favorable states.
- Keep all assessments and lifecycle events append-only; make only the proven successful replay idempotent.
- Bounded source text and deterministic extraction make prompt injection inert.

## Reusable integrations

1. A compliance dashboard can read `get_filing_status()` and route `manual_review_required` cases to a human queue.
2. A case-monitoring contract can consume `get_manifest()` and `get_filing_status()` as a procedural evidence oracle.
3. An audit exporter can read `get_history()` and preserve the assessment chain when a new evidence revision supersedes the old one.

## Repository structure

```text
contracts/court_order_milestone_compliance_registry.py
tests/test_court_order_milestone_compliance_registry.py
samples/ferguson_initial_status_report.json
samples/wrong_case_counterexample.json
docs/architecture.md
docs/e2e-matrix.md
README.md
requirements.txt
```

## License

MIT
