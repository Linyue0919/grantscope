"""Explicit evidence-backed gate aggregation; no model calls or inferred grant rules.

Callers must supply independently verified requirement findings. Exact quote matching
alone is NOT claim entailment. These types make that review obligation explicit.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Tuple
from urllib.parse import urlparse


class State(str, Enum):
    PASS = 'PASS'
    CONFIRMED_EXCLUSION = 'CONFIRMED_EXCLUSION'
    CONDITIONAL = 'CONDITIONAL'
    INSUFFICIENT_EVIDENCE = 'INSUFFICIENT_EVIDENCE'


REQUIRED_GATES = ('applicant', 'funding_purpose', 'geography_land', 'match',
                  'sponsorship', 'timing', 'official_documents')


@dataclass(frozen=True)
class Source:
    source_id: str
    url: str
    text: str
    version: str
    retrieved_at: str
    current_and_authoritative: bool = False


@dataclass(frozen=True)
class Citation:
    source_id: str
    quote: str
    location: str


@dataclass(frozen=True)
class Finding:
    gate: str
    state: State
    reason: str
    citations: Tuple[Citation, ...] = ()
    support_reviewed_by: str = ''  # Human or independently tested deterministic rule/version.
    exceptions_reviewed: bool = False
    application_routes_reviewed: bool = False
    unresolved: Tuple[str, ...] = ()
    # An applicant exception only resolves this gate when the alternative route is
    # officially supported AND the project's actual partner/lead commitments verified.
    verified_exception_route: bool = False


@dataclass(frozen=True)
class GateResult:
    phase: str
    state: State
    gates: tuple
    actionable: bool
    unresolved: tuple
    audit: tuple


def _supported(finding, sources):
    if not finding.reason.strip() or not finding.support_reviewed_by.strip() or not finding.citations:
        return False
    for citation in finding.citations:
        source = sources.get(citation.source_id)
        host = urlparse(source.url).hostname if source else ''
        if (not source or not source.current_and_authoritative or not source.version
                or not source.retrieved_at or urlparse(source.url).scheme != 'https'
                or not host or not (host.endswith('.gov') or host.endswith('.mil'))
                or not citation.quote.strip() or citation.quote not in source.text
                or not citation.location.strip()):
            return False
    return True


def evaluate_gates(findings, sources, phase='preliminary'):
    """Aggregate required gates, retaining every submitted finding and its provenance.

    A missing/unsupported claim becomes insufficient evidence, never exclusion.
    PASS requires all material checks resolved, including complete official evidence.
    Only final PASS is actionable; this is viability, not a recommendation to apply.
    No relevance score is accepted by this interface.
    """
    if phase not in {'preliminary', 'final'}:
        raise ValueError('phase must be preliminary or final')
    sources = list(sources)
    if len({s.source_id for s in sources}) != len(sources):
        raise ValueError('Duplicate source identity')
    by_source = {s.source_id: s for s in sources}
    findings = list(findings)
    if any(f.gate not in REQUIRED_GATES or not isinstance(f.state, State) for f in findings):
        raise ValueError('Unknown gate or decision state')
    rows, audit, unresolved = [], [], []
    for gate in REQUIRED_GATES:
        submitted = [f for f in findings if f.gate == gate]
        if len(submitted) != 1:
            state = State.INSUFFICIENT_EVIDENCE
            reason = 'Missing finding' if not submitted else 'Conflicting/duplicate findings require adjudication'
        else:
            finding = submitted[0]
            state, reason = finding.state, finding.reason
            if state in {State.PASS, State.CONFIRMED_EXCLUSION} and not _supported(finding, by_source):
                state, reason = State.INSUFFICIENT_EVIDENCE, 'Official source support/entailment review is missing or invalid'
            elif state == State.CONFIRMED_EXCLUSION:
                if not finding.exceptions_reviewed or not finding.application_routes_reviewed:
                    state, reason = State.CONDITIONAL, 'Restriction requires exception and application-route review'
                elif finding.verified_exception_route:
                    state, reason = State.CONDITIONAL, 'Verified alternative route conflicts with exclusion; adjudicate route readiness'
            if state == State.PASS and (finding.unresolved or not finding.exceptions_reviewed
                                        or not finding.application_routes_reviewed):
                state, reason = State.CONDITIONAL, 'Material conditions or application-route/exception review remain unresolved'
            unresolved.extend(finding.unresolved)
        if state in {State.CONDITIONAL, State.INSUFFICIENT_EVIDENCE}:
            unresolved.append(f'{gate}: {reason}')
        rows.append({'gate': gate, 'state': state.value, 'reason': reason})
        audit.append({'gate': gate, 'submitted_findings': tuple(submitted),
                      'sources': tuple(by_source[c.source_id] for f in submitted for c in f.citations
                                       if c.source_id in by_source), 'effective_state': state.value})
    states = {row['state'] for row in rows}
    overall = next((s for s in (State.CONFIRMED_EXCLUSION, State.INSUFFICIENT_EVIDENCE,
                               State.CONDITIONAL) if s.value in states), State.PASS)
    return GateResult(phase, overall, tuple(rows), overall == State.PASS and phase == 'final',
                      tuple(dict.fromkeys(unresolved)), tuple(audit))


def screen_timing(status, close_date, deadline_kind, as_of, citations=(),
                  current_notice_chain_reviewed=False, readiness_verified=False,
                  unresolved=()):
    """Screen source-reviewed structured timing facts, never model relevance.

    Dates are ISO calendar dates; a hard deadline remains open through its date.
    Target/forecast/unknown dates do not establish expiration. Supersession,
    extensions and late/alternate routes must be reviewed before exclusion.
    Final gate aggregation still requires valid, authoritative source citations.
    """
    from datetime import date
    now = date.fromisoformat(as_of)
    deadline = None
    if close_date:
        try:
            deadline = date.fromisoformat(close_date)
        except (TypeError, ValueError):
            return Finding('timing', State.INSUFFICIENT_EVIDENCE,
                           'Unrecognized official date; verify rather than exclude', tuple(citations))
    status = str(status).strip().upper()
    if status in {'CLOSED', 'ARCHIVED'} or (deadline_kind == 'hard' and deadline and deadline < now):
        return Finding('timing', State.CONFIRMED_EXCLUSION,
                       f'Official status {status}; hard closing date {close_date}; as-of {as_of}',
                       tuple(citations), 'timing-rule-v1', current_notice_chain_reviewed,
                       current_notice_chain_reviewed)
    if (status != 'POSTED' or deadline_kind not in {'hard', 'rolling'}
            or (deadline_kind == 'hard' and not deadline) or not readiness_verified or unresolved):
        return Finding('timing', State.CONDITIONAL,
                       'Opening, deadline interpretation, intermediate deadlines or readiness need verification',
                       tuple(citations), unresolved=tuple(unresolved))
    return Finding('timing', State.PASS, 'Current opening and timing/readiness verified',
                   tuple(citations), 'timing-rule-v1', current_notice_chain_reviewed,
                   current_notice_chain_reviewed)
