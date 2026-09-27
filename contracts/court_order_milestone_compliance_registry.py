# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

import json
import re
import zlib
from dataclasses import dataclass
from hashlib import sha256

import genlayer as gl
from genlayer import *
from genlayer.storage import allow as allow_storage

if hasattr(gl, "contract") and hasattr(gl.contract, "Contract"):
    gl.Contract = gl.contract.Contract


MAX_TEXT = 240
MAX_URL = 256
MAX_SOURCE_TEXT = 400000
MAX_SOURCE_BYTES = 8000000
MAX_SOURCE_DECOMPRESSED = 500000
MAX_PDF_STREAMS = 128


@allow_storage
@dataclass
class EvidenceManifest:
    case_id: str
    case_anchor: str
    order_clause_id: str
    order_clause_anchor: str
    report_period: str
    report_period_start_anchor: str
    report_period_end_anchor: str
    filing_identity_anchor: str
    filing_date_anchor: str
    order_url: str
    filing_url: str
    manifest_hash: str


@allow_storage
@dataclass
class DocketAssessment:
    assessment_id: u32
    case_match: bool
    order_clause_match: bool
    report_period_match: bool
    filing_identity_match: bool
    filing_date_state: str
    outcome: str
    manual_review_required: bool
    manifest_hash: str


@allow_storage
@dataclass
class LifecycleEvent:
    event_id: u32
    event_type: str
    state_after: str
    assessment_id: u32
    outcome: str
    replacement_reference: str


def _require(condition: bool, message: str):
    if not condition:
        raise gl.vm.UserError(message)


def _require_text(value: str, field: str, limit: u32 = MAX_TEXT):
    _require(isinstance(value, str), "INVALID_" + field.upper())
    _require(0 < len(value) <= limit, "INVALID_" + field.upper())
    _require(value.strip() == value, "INVALID_" + field.upper())
    _require("\n" not in value and "\r" not in value, "INVALID_" + field.upper())


def _normalize_clause_id(value):
    # The governed CLI parses bare numeric calldata as an integer. Preserve the
    # same lexical clause identifier expected by the source anchors.
    if isinstance(value, int):
        return str(value)
    return value


def _require_doj_url(value: str, field: str):
    _require_text(value, field, MAX_URL)
    _require(value.startswith("https://www.justice.gov/"), "INVALID_" + field.upper())
    query_count = value.count("?")
    inline_media_url = query_count == 1 and value.endswith("/dl?inline=")
    _require(
        "#" not in value and ("?" not in value or inline_media_url),
        "INVALID_" + field.upper(),
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _contains(source: str, anchor: str) -> bool:
    return _normalize(anchor) in _normalize(source)


def _resolve_lazy(value):
    if isinstance(value, gl.Lazy):
        return value.get()
    return value


def _pdf_literal(value: bytes) -> bytes:
    result = []
    index = 1
    depth = 0
    while index < len(value) - 1:
        byte = value[index]
        if byte == 92:
            index += 1
            if index >= len(value) - 1:
                break
            escaped = value[index]
            replacements = {
                110: 10,
                114: 13,
                116: 9,
                98: 8,
                102: 12,
                40: 40,
                41: 41,
                92: 92,
            }
            if escaped in replacements:
                result.append(replacements[escaped])
            elif 48 <= escaped <= 55:
                octal = [escaped]
                while len(octal) < 3 and index + 1 < len(value) - 1:
                    following = value[index + 1]
                    if not 48 <= following <= 55:
                        break
                    index += 1
                    octal.append(following)
                result.append(int(bytes(octal), 8))
            elif escaped not in (10, 13):
                result.append(escaped)
        elif byte == 40:
            depth += 1
            result.append(byte)
        elif byte == 41 and depth > 0:
            depth -= 1
            result.append(byte)
        else:
            result.append(byte)
        index += 1
    return bytes(result)


def _pdf_hex(value: bytes) -> bytes:
    digits = bytes(value[1:-1]).replace(b" ", b"").replace(b"\t", b"")
    digits = digits.replace(b"\r", b"").replace(b"\n", b"")
    if len(digits) % 2:
        digits += b"0"
    result = []
    for index in range(0, len(digits), 2):
        high = digits[index]
        low = digits[index + 1]
        high_value = int(bytes([high]), 16)
        low_value = int(bytes([low]), 16)
        result.append((high_value << 4) | low_value)
    return bytes(result)


def _pdf_cmap(stream: bytes) -> dict:
    mapping = {}
    text = stream.decode("latin-1", errors="ignore")
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for source, target in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            try:
                key = bytes.fromhex(source)
                raw_target = bytes.fromhex(target)
                mapping[key] = raw_target.decode("utf-16-be", errors="replace")
            except (ValueError, UnicodeError):
                pass
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for source, end, target in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
            block,
        ):
            try:
                start_bytes = bytes.fromhex(source)
                end_bytes = bytes.fromhex(end)
                target_bytes = bytes.fromhex(target)
                start = int.from_bytes(start_bytes, "big")
                finish = int.from_bytes(end_bytes, "big")
                target_start = int.from_bytes(target_bytes, "big")
                width = len(start_bytes)
                target_width = len(target_bytes)
                for offset in range(finish - start + 1):
                    mapping[(start + offset).to_bytes(width, "big")] = (
                        target_start + offset
                    ).to_bytes(target_width, "big").decode(
                        "utf-16-be", errors="replace"
                    )
            except (ValueError, UnicodeError):
                pass
    return mapping


def _inflate(stream: bytes) -> bytes:
    decoder = zlib.decompressobj()
    try:
        return decoder.decompress(stream, MAX_SOURCE_TEXT)
    except zlib.error:
        decoder = zlib.decompressobj(-15)
        try:
            return decoder.decompress(stream, MAX_SOURCE_TEXT)
        except zlib.error:
            return b""


def _pdf_mapped_token(token: bytes, mapping: dict) -> str:
    if not mapping:
        return ""
    widths = sorted({len(key) for key in mapping}, reverse=True)
    for width in widths:
        if len(token) % width:
            continue
        output = []
        complete = True
        for index in range(0, len(token), width):
            key = token[index : index + width]
            value = mapping.get(key)
            if value is None:
                complete = False
                break
            output.append(value)
        if complete:
            return "".join(output)
    return ""


def _pdf_token_text(token: bytes, cmaps: list) -> str:
    candidates = [token.decode("latin-1", errors="replace")]
    for mapping in cmaps:
        mapped = _pdf_mapped_token(token, mapping)
        if mapped:
            candidates.append(mapped)
    return max(
        candidates,
        key=lambda value: sum(
            1 for char in value if char.isalnum() or char in " .,;:'-()"
        ),
    )


def _pdf_text(raw: bytes) -> str:
    if not isinstance(raw, bytes) or not raw.startswith(b"%PDF-"):
        return ""
    if len(raw) > MAX_SOURCE_BYTES:
        return ""

    streams = []
    decompressed_size = 0
    for stream_index, match in enumerate(
        re.finditer(rb"\d+\s+\d+\s+obj\b(.*?)stream\r?\n", raw, re.S)
    ):
        if stream_index >= MAX_PDF_STREAMS:
            break
        end = raw.find(b"endstream", match.end())
        if end < 0:
            continue
        stream = raw[match.end() : end]
        if stream.endswith(b"\r\n"):
            stream = stream[:-2]
        elif stream.endswith(b"\n"):
            stream = stream[:-1]
        dictionary = match.group(1)
        if b"/FlateDecode" in dictionary:
            stream = _inflate(stream)
            if not stream:
                continue
        remaining = MAX_SOURCE_DECOMPRESSED - decompressed_size
        if remaining <= 0:
            break
        stream = stream[:remaining]
        streams.append(stream)
        decompressed_size += len(stream)

    cmaps = [_pdf_cmap(stream) for stream in streams]
    cmaps = [mapping for mapping in cmaps if mapping]
    tokens = []
    token_pattern = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>")
    for stream in streams:
        for token in token_pattern.findall(stream):
            if token.startswith(b"("):
                decoded = _pdf_literal(token)
            else:
                try:
                    decoded = _pdf_hex(token)
                except (ValueError, IndexError):
                    continue
            text = _pdf_token_text(decoded, cmaps)
            if text and any(char.isalnum() for char in text):
                tokens.append(text)
    return "".join(tokens)[:MAX_SOURCE_TEXT]


def _bounded_text(response) -> str:
    response = _resolve_lazy(response)
    if isinstance(response, bytes):
        if response.startswith(b"%PDF-"):
            return _pdf_text(response)
        return response.decode("utf-8", errors="replace")[:MAX_SOURCE_TEXT]
    if isinstance(response, str):
        return response[:MAX_SOURCE_TEXT]
    body = getattr(response, "body", None)
    status = getattr(response, "status", 200)
    if status < 200 or status >= 300 or not isinstance(body, bytes):
        return ""
    if body.startswith(b"%PDF-"):
        return _pdf_text(body)
    return body.decode("utf-8", errors="replace")[:MAX_SOURCE_TEXT]


def _manifest_digest(
    case_id: str,
    case_anchor: str,
    order_clause_id: str,
    order_clause_anchor: str,
    report_period: str,
    report_period_start_anchor: str,
    report_period_end_anchor: str,
    filing_identity_anchor: str,
    filing_date_anchor: str,
    order_url: str,
    filing_url: str,
) -> str:
    canonical = "|".join(
        [
            case_id,
            case_anchor,
            order_clause_id,
            order_clause_anchor,
            report_period,
            report_period_start_anchor,
            report_period_end_anchor,
            filing_identity_anchor,
            filing_date_anchor,
            order_url,
            filing_url,
        ]
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _source_assessment(
    order_text: str,
    filing_text: str,
    case_id: str,
    case_anchor: str,
    order_clause_id: str,
    order_clause_anchor: str,
    report_period: str,
    report_period_start_anchor: str,
    report_period_end_anchor: str,
    filing_identity_anchor: str,
    filing_date_anchor: str,
) -> str:
    order_match = _contains(order_text, "Consent Decree")
    case_match = (
        _contains(order_text, case_anchor)
        and _contains(filing_text, "Case No: " + case_id)
        and _contains(filing_text, "CITY OF FERGUSON")
    )
    order_clause_match = (
        order_match
        and _contains(order_text, order_clause_id)
        and _contains(filing_text, order_clause_anchor)
    )
    report_period_match = (
        _contains(filing_text, report_period)
        and
        _contains(filing_text, report_period_start_anchor)
        and _contains(filing_text, report_period_end_anchor)
    )
    filing_identity_match = _contains(filing_text, filing_identity_anchor)
    filing_date_occurrences = _normalize(filing_text).count(_normalize(filing_date_anchor))
    if filing_date_occurrences == 1:
        filing_date_state = "PRESENT"
    elif filing_date_occurrences == 0:
        filing_date_state = "MISSING"
    else:
        filing_date_state = "AMBIGUOUS"

    all_identity_fields_match = (
        case_match
        and order_clause_match
        and report_period_match
        and filing_identity_match
    )
    if all_identity_fields_match and filing_date_state == "PRESENT":
        outcome = "ON_RECORD"
    elif all_identity_fields_match and filing_date_state == "MISSING":
        outcome = "MISSING"
    else:
        outcome = "AMBIGUOUS"

    return json.dumps(
        {
            "case_match": case_match,
            "order_clause_match": order_clause_match,
            "report_period_match": report_period_match,
            "filing_identity_match": filing_identity_match,
            "filing_date_state": filing_date_state,
            "outcome": outcome,
            "manual_review_required": outcome != "ON_RECORD",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _assessment_payload(assessment: DocketAssessment) -> str:
    return json.dumps(
        {
            "assessment_id": int(assessment.assessment_id),
            "case_match": assessment.case_match,
            "order_clause_match": assessment.order_clause_match,
            "report_period_match": assessment.report_period_match,
            "filing_identity_match": assessment.filing_identity_match,
            "filing_date_state": assessment.filing_date_state,
            "outcome": assessment.outcome,
            "manual_review_required": assessment.manual_review_required,
            "manifest_hash": assessment.manifest_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class CourtOrderMilestoneComplianceRegistry(gl.Contract):
    owner: Address
    state: str
    manifest: EvidenceManifest
    assessments: gl.storage.DynArray[DocketAssessment]
    events: gl.storage.DynArray[LifecycleEvent]
    next_assessment_id: u32
    next_event_id: u32

    def __init__(self):
        self.owner = gl.message.sender_address
        self.state = "DRAFT"
        self.manifest = EvidenceManifest(
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )
        self.next_assessment_id = u32(1)
        self.next_event_id = u32(1)
        self._append_event("CREATED", "DRAFT", u32(0), "", "")

    def _only_owner(self):
        _require(gl.message.sender_address == self.owner, "ONLY_OWNER")

    def _append_event(
        self,
        event_type: str,
        state_after: str,
        assessment_id: u32,
        outcome: str,
        replacement_reference: str,
    ):
        self.events.append(
            LifecycleEvent(
                self.next_event_id,
                event_type,
                state_after,
                assessment_id,
                outcome,
                replacement_reference,
            )
        )
        self.next_event_id = self.next_event_id + u32(1)

    @gl.public.write
    def create_report_link(
        self,
        case_id: str,
        case_anchor: str,
        order_clause_id: str,
        order_clause_anchor: str,
        report_period: str,
        report_period_start_anchor: str,
        report_period_end_anchor: str,
        filing_identity_anchor: str,
        filing_date_anchor: str,
        order_url: str,
        filing_url: str,
    ):
        self._only_owner()
        _require(self.state == "DRAFT", "INVALID_STATE")
        _require(self.manifest.manifest_hash == "", "ALREADY_CREATED")

        _require_text(case_id, "case_id")
        _require_text(case_anchor, "case_anchor")
        order_clause_id = _normalize_clause_id(order_clause_id)
        _require_text(order_clause_id, "order_clause_id")
        _require_text(order_clause_anchor, "order_clause_anchor")
        _require_text(report_period, "report_period")
        _require_text(report_period_start_anchor, "report_period_start_anchor")
        _require_text(report_period_end_anchor, "report_period_end_anchor")
        _require_text(filing_identity_anchor, "filing_identity_anchor")
        _require_text(filing_date_anchor, "filing_date_anchor")
        _require_doj_url(order_url, "order_url")
        _require_doj_url(filing_url, "filing_url")
        _require(order_url != filing_url, "DUPLICATE_SOURCE_URL")
        _require(_contains(order_clause_anchor, order_clause_id), "MISMATCHED_ORDER_CLAUSE")

        manifest_hash = _manifest_digest(
            case_id,
            case_anchor,
            order_clause_id,
            order_clause_anchor,
            report_period,
            report_period_start_anchor,
            report_period_end_anchor,
            filing_identity_anchor,
            filing_date_anchor,
            order_url,
            filing_url,
        )
        self.manifest = EvidenceManifest(
            case_id,
            case_anchor,
            order_clause_id,
            order_clause_anchor,
            report_period,
            report_period_start_anchor,
            report_period_end_anchor,
            filing_identity_anchor,
            filing_date_anchor,
            order_url,
            filing_url,
            manifest_hash,
        )
        self._append_event("REPORT_LINK_CREATED", "DRAFT", u32(0), "", "")

    @gl.public.write
    def seal_manifest(self):
        self._only_owner()
        _require(self.state == "DRAFT", "INVALID_STATE")
        _require(self.manifest.manifest_hash != "", "MANIFEST_NOT_CREATED")
        self.state = "SEALED"
        self._append_event("SEALED", "SEALED", u32(0), "", "")

    @gl.public.write
    def assess_filing_link(self) -> str:
        _require(
            self.state in ["SEALED", "ON_RECORD", "REVIEW_REQUIRED"],
            "INVALID_STATE",
        )

        case_id = self.manifest.case_id
        case_anchor = self.manifest.case_anchor
        order_clause_id = self.manifest.order_clause_id
        order_clause_anchor = self.manifest.order_clause_anchor
        report_period = self.manifest.report_period
        report_period_start_anchor = self.manifest.report_period_start_anchor
        report_period_end_anchor = self.manifest.report_period_end_anchor
        filing_identity_anchor = self.manifest.filing_identity_anchor
        filing_date_anchor = self.manifest.filing_date_anchor
        order_url = self.manifest.order_url
        filing_url = self.manifest.filing_url
        manifest_hash = self.manifest.manifest_hash

        def read_sources() -> str:
            order_text = _bounded_text(
                gl.nondet.web.get(order_url)
            )
            filing_text = _bounded_text(
                gl.nondet.web.get(filing_url)
            )
            return _source_assessment(
                order_text,
                filing_text,
                case_id,
                case_anchor,
                order_clause_id,
                order_clause_anchor,
                report_period,
                report_period_start_anchor,
                report_period_end_anchor,
                filing_identity_anchor,
                filing_date_anchor,
            )

        def validate_result(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            validator_result = read_sources()
            return leader_result.calldata == validator_result

        if self.state == "ON_RECORD" and len(self.assessments) > 0:
            return _assessment_payload(self.assessments[len(self.assessments) - 1])

        result = json.loads(gl.vm.run_nondet(read_sources, validate_result))
        outcome = result["outcome"]
        assessment = DocketAssessment(
            self.next_assessment_id,
            result["case_match"],
            result["order_clause_match"],
            result["report_period_match"],
            result["filing_identity_match"],
            result["filing_date_state"],
            outcome,
            result["manual_review_required"],
            manifest_hash,
        )
        self.assessments.append(assessment)
        self.next_assessment_id = self.next_assessment_id + u32(1)
        self.state = "ON_RECORD" if outcome == "ON_RECORD" else "REVIEW_REQUIRED"
        self._append_event(
            "ASSESSED",
            self.state,
            assessment.assessment_id,
            outcome,
            "",
        )
        return _assessment_payload(assessment)

    @gl.public.write
    def supersede(self, replacement_reference: str):
        self._only_owner()
        _require(self.state in ["SEALED", "ON_RECORD", "REVIEW_REQUIRED"], "INVALID_STATE")
        _require_text(replacement_reference, "replacement_reference")
        self.state = "SUPERSEDED"
        assessment_id = u32(0)
        outcome = ""
        if len(self.assessments) > 0:
            latest = self.assessments[len(self.assessments) - 1]
            assessment_id = latest.assessment_id
            outcome = latest.outcome
        self._append_event(
            "SUPERSEDED",
            "SUPERSEDED",
            assessment_id,
            outcome,
            replacement_reference,
        )

    @gl.public.view
    def get_manifest(self) -> str:
        return json.dumps(
            {
                "case_id": self.manifest.case_id,
                "case_anchor": self.manifest.case_anchor,
                "order_clause_id": self.manifest.order_clause_id,
                "order_clause_anchor": self.manifest.order_clause_anchor,
                "report_period": self.manifest.report_period,
                "report_period_start_anchor": self.manifest.report_period_start_anchor,
                "report_period_end_anchor": self.manifest.report_period_end_anchor,
                "filing_identity_anchor": self.manifest.filing_identity_anchor,
                "filing_date_anchor": self.manifest.filing_date_anchor,
                "order_url": self.manifest.order_url,
                "filing_url": self.manifest.filing_url,
                "manifest_hash": self.manifest.manifest_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @gl.public.view
    def get_filing_status(self) -> str:
        if len(self.assessments) == 0:
            return json.dumps(
                {
                    "assessment_count": 0,
                    "outcome": "UNASSESSED",
                    "assessment_id": 0,
                    "manual_review_required": self.state != "ON_RECORD",
                    "manifest_hash": self.manifest.manifest_hash,
                    "state": self.state,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        latest = self.assessments[len(self.assessments) - 1]
        payload = json.loads(_assessment_payload(latest))
        payload["assessment_count"] = len(self.assessments)
        payload["state"] = self.state
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @gl.public.view
    def requires_manual_review(self) -> bool:
        return self.state != "ON_RECORD"

    @gl.public.view
    def get_assessment(self, assessment_id: u32) -> str:
        _require(assessment_id > u32(0), "INVALID_ASSESSMENT_ID")
        index = int(assessment_id) - 1
        _require(index < len(self.assessments), "ASSESSMENT_NOT_FOUND")
        return _assessment_payload(self.assessments[index])

    @gl.public.view
    def get_history(self) -> str:
        history = []
        for event in self.events:
            history.append(
                {
                    "event_id": int(event.event_id),
                    "event_type": event.event_type,
                    "state_after": event.state_after,
                    "assessment_id": int(event.assessment_id),
                    "outcome": event.outcome,
                    "replacement_reference": event.replacement_reference,
                }
            )
        return json.dumps(history, sort_keys=True, separators=(",", ":"))
