# Studio Dev E2E Matrix

This matrix is bound to the exact contract revision reviewed before deployment.
Each write is sent once, polled to a terminal receipt, and paired with an
authoritative readback. No scenario is a legal conclusion.

| ID | Scenario | Expected result | Evidence required |
| --- | --- | --- | --- |
| E2E-01 | Deploy empty contract | `FINALIZED`; constructor state `DRAFT`; owner equals deployer | Deployment receipt and `get_history()` |
| E2E-02 | Owner creates the Ferguson manifest | `FINALIZED`; state `DRAFT`; manifest hash is non-empty | Write receipt and `get_manifest()` |
| E2E-03 | Owner seals the manifest | `FINALIZED`; state `SEALED` | Write receipt and `get_filing_status()` |
| E2E-04 | Consensus assessment of the exact filing | `FINALIZED`; `ON_RECORD`; all decision fields true; date `PRESENT` | Assessment receipt, readback, Explorer links |
| E2E-05 | Wrong-case counterexample | `FINALIZED`; `REVIEW_REQUIRED`; `case_match=false`; manual review true | Assessment receipt and readback |
| E2E-06 | Missing filing date | `FINALIZED`; `REVIEW_REQUIRED`; date `MISSING`; manual review true | Assessment receipt and readback |
| E2E-07 | Order source missing sealed clause ID | `FINALIZED`; `REVIEW_REQUIRED`; `order_clause_match=false` | Assessment receipt and readback |
| E2E-08 | Repeated successful assessment | `FINALIZED`; same canonical result; assessment count unchanged | Replay receipt and history readback |
| E2E-09 | Unauthorized write | `FINISHED_WITH_ERROR`; no state change | Revert receipt and before/after readback |
| E2E-10 | Owner supersedes after assessment | `FINALIZED`; `SUPERSEDED`; prior assessment and events preserved | Write receipt and history readback |

The deployed contract must be the exact reviewed source revision. A source
fetch failure, validator disagreement, malformed response, or ambiguous date
must not produce `ON_RECORD`; the transaction may fail or record a review-required
assessment, depending on where the failure occurs.

## Local pre-deploy evidence

- `genvm-lint lint`: PASS (3 checks)
- `genvm-lint validate`: PASS
- Direct Mode suite: 14 passed under `E:\Genlayer-Tools\studio-next-toolchain\.wsl-venv`
- Windows Direct Mode limitation: the current loader fails before assertions
  with the known temporary-file permission error; this is not represented as a
  Windows test pass.

## Studio Dev evidence (chain 61997)

- Contract: `0x6Dc0D76Cb47093882e2B1d0CB163339F9F40f654`; deployment tx `0x29f62af484e4c6ff10de5d5ad340aa990f5f1e4d62099b2907982e908e9d05d8`.
- E2E-01/02/03: deployment, create, and seal accepted; `get_manifest()` and history readbacks match the sealed Ferguson tuple.
- E2E-04: assessment tx `0x5e7f87801e7a3374019614330ad540633ba804585c8d16cf005ca2316a0914c8`; finalized `ON_RECORD`, all five vector fields favorable, date `PRESENT`.
- E2E-08: replay tx `0x10952b40b8868c5ca400487af33e288c52969e7a7d84f43850674f9d27aebadf`; same canonical result and assessment count remained `1`.
- E2E-09: actor8 tx `0x3891692bc297f982eca54fe0f757008bac7b64208130dd8c6f2223fc5825976c`; consensus accepted but execution `FINISHED_WITH_ERROR`, with no state change.
- E2E-10: supersede tx `0xe5faa0d31ae58ea2cca891cfb95f050e2d3f3a88c5cbba2f63ffe4fd754184ac`; status `SUPERSEDED`, replacement reference and prior events preserved.
- E2E-05: separate Studio Dev contract `0xC869672e3b4B39235FE5710A473A9Ce36B14fB3D`; assessment tx `0xd3bc3f225c636b1d3151698c51e4469316c9781ea3cfdfacaf38e083760eabaa`; readback was `REVIEW_REQUIRED`, `case_match=false`, `manual_review_required=true`.
- E2E-06: separate Studio Dev contract `0xa3fCA373D78E48c1f23cE2c9C0a6E257a056dA2B`; assessment tx `0x4db3121aeced72e487af3cede6d28d991ac7c8690f4540430b99d283f8377227`; missing-date manifest produced a non-favorable review result.

E2E-07 remains covered by the 14-test Direct Mode suite; an attempted live manifest with an invalid clause anchor was rejected at creation, so no invalid evidence could be sealed.
