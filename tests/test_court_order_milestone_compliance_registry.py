import json
import re
import zlib

import pytest


CONTRACT = "contracts/court_order_milestone_compliance_registry.py"
ORDER_URL = "https://www.justice.gov/crt/file/883846/dl?inline="
FILING_URL = "https://www.justice.gov/crt/case-document/file/955191/dl"

CASE_ID = "4:16-cv-180"
CASE_ANCHOR = "THE CITY OF FERGUSON"
CLAUSE_ANCHOR = "Consent Decree, ¶ 456"
START_ANCHOR = "April 19, 2016"
END_ANCHOR = "October 17, 2016"
IDENTITY_ANCHOR = "CITY OF FERGUSON'S INITIAL STATUS REPORT"
DATE_ANCHOR = "Date: October 17, 2016"

ORDER_BODY = """
UNITED STATES DISTRICT COURT
THE CITY OF FERGUSON
UNITED STATES OF AMERICA v. THE CITY OF FERGUSON
CONSENT DECREE
456. Within 180 days of the Effective Date, FPD will file a status report.
"""

FILING_BODY = """
UNITED STATES DISTRICT COURT
EASTERN DISTRICT OF MISSOURI
UNITED STATES OF AMERICA v. THE CITY OF FERGUSON
Case No: 4:16-cv-180
CITY OF FERGUSON'S INITIAL STATUS REPORT
Consent Decree, ¶ 456 provides periodic reporting.
The effective date was April 19, 2016, and the initial status report was due on October 17, 2016.
The following discussion identifies events within the initial six month period.
Date: October 17, 2016
"""


def create_link(contract):
    contract.create_report_link(
        CASE_ID,
        CASE_ANCHOR,
        "456",
        CLAUSE_ANCHOR,
        "initial six month period",
        START_ANCHOR,
        END_ANCHOR,
        IDENTITY_ANCHOR,
        DATE_ANCHOR,
        ORDER_URL,
        FILING_URL,
    )


def mock_sources(vm, order_body=ORDER_BODY, filing_body=FILING_BODY):
    vm.mock_web(re.escape(ORDER_URL), {"status": 200, "body": order_body})
    vm.mock_web(re.escape(FILING_URL), {"status": 200, "body": filing_body})


def pdf_body(text):
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = ("BT (" + escaped + ") Tj ET").encode("latin-1")
    stream = zlib.compress(content)
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Length "
        + str(len(stream)).encode("ascii")
        + b" /Filter /FlateDecode >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF"
    )


def mock_pdf_sources(vm):
    order_body = pdf_body(
        "CONSENT DECREE 456 UNITED STATES DISTRICT COURT THE CITY OF FERGUSON"
    )
    filing_body = pdf_body(
        "Case No: 4:16-cv-180 THE CITY OF FERGUSON "
        "CITY OF FERGUSON'S INITIAL STATUS REPORT "
        "Consent Decree, \xb6 456 initial six month period "
        "April 19, 2016 October 17, 2016 Date: October 17, 2016"
    )
    mock_sources(vm, order_body=order_body, filing_body=filing_body)


def test_create_seal_and_readback_are_append_only(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    manifest = json.loads(contract.get_manifest())
    assert manifest["order_url"] == ORDER_URL
    assert len(manifest["manifest_hash"]) == 64

    contract.seal_manifest()
    status = json.loads(contract.get_filing_status())
    history = json.loads(contract.get_history())
    assert status["state"] == "SEALED"
    assert status["assessment_count"] == 0
    assert [event["event_type"] for event in history] == [
        "CREATED",
        "REPORT_LINK_CREATED",
        "SEALED",
    ]


def test_consensus_binds_full_decision_vector_and_records_on_record(
    direct_vm, direct_deploy
):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm)

    payload = json.loads(contract.assess_filing_link())
    assert payload == {
        "assessment_id": 1,
        "case_match": True,
        "order_clause_match": True,
        "report_period_match": True,
        "filing_identity_match": True,
        "filing_date_state": "PRESENT",
        "outcome": "ON_RECORD",
        "manual_review_required": False,
        "manifest_hash": json.loads(contract.get_manifest())["manifest_hash"],
    }
    assert contract.requires_manual_review() is False
    assert json.loads(contract.get_filing_status())["state"] == "ON_RECORD"


def test_static_pdf_get_path_extracts_bounded_text(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_pdf_sources(direct_vm)

    payload = json.loads(contract.assess_filing_link())
    assert payload["outcome"] == "ON_RECORD"
    assert payload["case_match"] is True
    assert payload["order_clause_match"] is True
    assert payload["filing_date_state"] == "PRESENT"


def test_validator_rejects_different_decision_vector(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm)
    contract.assess_filing_link()

    direct_vm.clear_mocks()
    mock_sources(direct_vm, filing_body=FILING_BODY.replace(CASE_ID, "2:99-cv-999"))
    assert direct_vm.run_validator() is False


def test_missing_or_wrong_source_is_manual_review(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm, filing_body=FILING_BODY.replace(DATE_ANCHOR, "Filed without a date"))

    payload = json.loads(contract.assess_filing_link())
    assert payload["outcome"] == "MISSING"
    assert payload["manual_review_required"] is True
    assert contract.requires_manual_review() is True


def test_order_source_missing_clause_fails_closed(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm, order_body=ORDER_BODY.replace("456.", "457."))

    payload = json.loads(contract.assess_filing_link())
    assert payload["order_clause_match"] is False
    assert payload["outcome"] == "AMBIGUOUS"
    assert payload["manual_review_required"] is True


def test_numeric_clause_id_is_normalized_for_cli_calldata(direct_deploy):
    contract = direct_deploy(CONTRACT)
    contract.create_report_link(
        CASE_ID,
        CASE_ANCHOR,
        456,
        CLAUSE_ANCHOR,
        "initial six month period",
        START_ANCHOR,
        END_ANCHOR,
        IDENTITY_ANCHOR,
        DATE_ANCHOR,
        ORDER_URL,
        FILING_URL,
    )

    manifest = json.loads(contract.get_manifest())
    assert manifest["order_clause_id"] == "456"


def test_wrong_report_period_and_clause_fail_closed(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    with direct_vm.expect_revert("MISMATCHED_ORDER_CLAUSE"):
        contract.create_report_link(
            CASE_ID,
            CASE_ANCHOR,
            "457",
            CLAUSE_ANCHOR,
            "initial six month period",
            START_ANCHOR,
            END_ANCHOR,
            IDENTITY_ANCHOR,
            DATE_ANCHOR,
            ORDER_URL,
            FILING_URL,
        )

    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm, filing_body=FILING_BODY.replace("initial six month period", "different period"))
    payload = json.loads(contract.assess_filing_link())
    assert payload["report_period_match"] is False
    assert payload["outcome"] == "AMBIGUOUS"


def test_successful_assessment_replay_is_idempotent(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm)

    first = contract.assess_filing_link()
    second = contract.assess_filing_link()
    status = json.loads(contract.get_filing_status())
    history = json.loads(contract.get_history())
    assert first == second
    assert status["assessment_count"] == 1
    assert [event["event_type"] for event in history].count("ASSESSED") == 1


def test_only_owner_can_create_seal_and_supersede(
    direct_vm, direct_deploy, direct_alice
):
    contract = direct_deploy(CONTRACT)
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("ONLY_OWNER"):
        create_link(contract)

    create_link(contract)
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("ONLY_OWNER"):
        contract.seal_manifest()

    contract.seal_manifest()
    with direct_vm.prank(direct_alice), direct_vm.expect_revert("ONLY_OWNER"):
        contract.supersede("replacement-1")


def test_invalid_input_and_replay_are_rejected(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    with direct_vm.expect_revert("INVALID_ORDER_URL"):
        contract.create_report_link(
            CASE_ID,
            CASE_ANCHOR,
            "456",
            CLAUSE_ANCHOR,
            "period",
            START_ANCHOR,
            END_ANCHOR,
            IDENTITY_ANCHOR,
            DATE_ANCHOR,
            "https://example.com/order",
            FILING_URL,
        )

    create_link(contract)
    with direct_vm.expect_revert("ALREADY_CREATED"):
        create_link(contract)


def test_inline_doj_query_shape_is_accepted(direct_deploy):
    contract = direct_deploy(CONTRACT)
    contract.create_report_link(
        CASE_ID,
        CASE_ANCHOR,
        "456",
        CLAUSE_ANCHOR,
        "period",
        START_ANCHOR,
        END_ANCHOR,
        IDENTITY_ANCHOR,
        DATE_ANCHOR,
        ORDER_URL,
        FILING_URL,
    )
    assert json.loads(contract.get_manifest())["filing_url"] == FILING_URL


def test_doj_query_prefix_is_rejected(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    with direct_vm.expect_revert("INVALID_FILING_URL"):
        contract.create_report_link(
            CASE_ID,
            CASE_ANCHOR,
            "456",
            CLAUSE_ANCHOR,
            "period",
            START_ANCHOR,
            END_ANCHOR,
            IDENTITY_ANCHOR,
            DATE_ANCHOR,
            ORDER_URL,
            "https://www.justice.gov/evil?x=1/dl?inline=",
        )


def test_supersession_preserves_prior_assessment_and_history(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    create_link(contract)
    contract.seal_manifest()
    mock_sources(direct_vm)
    contract.assess_filing_link()
    contract.supersede("replacement-manifest-2")

    status = json.loads(contract.get_filing_status())
    history = json.loads(contract.get_history())
    assert status["state"] == "SUPERSEDED"
    assert status["assessment_count"] == 1
    assert history[-1]["event_type"] == "SUPERSEDED"
    assert history[-1]["replacement_reference"] == "replacement-manifest-2"
