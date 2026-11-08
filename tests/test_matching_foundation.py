"""Synthetic requirements only; these fixtures assert no facts about real grants."""
from dataclasses import replace
import pytest
from research_foundation.hard_gates import (Citation, Finding, REQUIRED_GATES, Source, State, evaluate_gates)
from research_foundation.research_queue import QueueConfig, build_queue


SOURCE = Source('synthetic-official', 'https://example.gov/notice',
                'Synthetic requirement and verified project condition.', 'fixture-v1',
                '2026-11-07T00:00:00Z', True)
CITE = Citation(SOURCE.source_id, 'Synthetic requirement', 'Synthetic section 1')


def findings():
    return [Finding(g, State.PASS, 'Synthetic satisfied requirement', (CITE,),
                    'synthetic-rule-v1', True, True) for g in REQUIRED_GATES]


def decision(gate, state, **changes):
    rows = [replace(f, state=state, **changes) if f.gate == gate else f for f in findings()]
    return evaluate_gates(rows, [SOURCE], 'final')


@pytest.mark.parametrize('gate', ['applicant', 'timing', 'geography_land', 'funding_purpose'])
def test_confirmed_applicant_expiry_land_and_purpose_exclusions(gate):
    result = decision(gate, State.CONFIRMED_EXCLUSION)
    assert result.state == State.CONFIRMED_EXCLUSION
    assert not result.actionable
    assert any(r['submitted_findings'][0].citations for r in result.audit)


def test_unknown_eligibility_missing_notice_and_unconfirmed_match():
    assert decision('applicant', State.INSUFFICIENT_EVIDENCE).state == State.INSUFFICIENT_EVIDENCE
    assert decision('official_documents', State.INSUFFICIENT_EVIDENCE).state == State.INSUFFICIENT_EVIDENCE
    assert decision('match', State.CONDITIONAL, unresolved=('Match not committed',)).state == State.CONDITIONAL
    # Unsupported purpose is unknown, not a confirmed prohibition.
    assert decision('funding_purpose', State.PASS, support_reviewed_by='').state == State.INSUFFICIENT_EVIDENCE


def test_exception_and_partnership_route_cannot_be_silently_excluded():
    assert decision('applicant', State.CONFIRMED_EXCLUSION, application_routes_reviewed=False).state == State.CONDITIONAL
    assert decision('applicant', State.CONFIRMED_EXCLUSION, verified_exception_route=True).state == State.CONDITIONAL
    # An actual verified alternate route can satisfy applicant gate; other gates still apply.
    assert decision('applicant', State.PASS, verified_exception_route=True).state == State.PASS
    assert decision('applicant', State.PASS, verified_exception_route=True, unresolved=('Lead not committed',)).state == State.CONDITIONAL


def test_pass_is_final_and_complete_not_a_relevance_score():
    assert evaluate_gates(findings(), [SOURCE], 'final').actionable
    assert not evaluate_gates(findings(), [SOURCE], 'preliminary').actionable
    assert evaluate_gates(findings()[:-1], [SOURCE], 'final').state == State.INSUFFICIENT_EVIDENCE
    assert evaluate_gates(findings()+[findings()[0]], [SOURCE], 'final').state == State.INSUFFICIENT_EVIDENCE
    with pytest.raises(TypeError):
        evaluate_gates(findings(), [SOURCE], relevance_score=100)
    assert not decision('applicant', State.CONFIRMED_EXCLUSION).actionable


def test_quotes_currentness_and_support_review_required():
    for change in ({'current_and_authoritative': False}, {'url': 'https://example.com/notice'}):
        assert evaluate_gates(findings(), [replace(SOURCE, **change)], 'final').state == State.INSUFFICIENT_EVIDENCE
    assert decision('applicant', State.CONFIRMED_EXCLUSION, citations=(replace(CITE, quote='invented'),)).state == State.INSUFFICIENT_EVIDENCE
    assert decision('applicant', State.PASS, exceptions_reviewed=False).state == State.CONDITIONAL


def candidates():
    return [{'id': str(i), 'priority_score': 100-i*10, 'agency': 'A' if i < 5 else 'B',
             'program_type': 'monitoring' if i % 2 else 'restoration',
             'gate_state': 'PASS', 'uncertain': i == 4, 'user_selected': i == 8} for i in range(10)]


def test_queue_recall_paths_budget_and_preservation():
    config = QueueConfig(budget=5, user=1, uncertainty=1, diversity=1, recall_audit=1, priority=1)
    result = build_queue(candidates(), config)
    assert len(result['pool']) == 10 and len(result['selected']) == 5
    assert len(result['not_selected']) == 5
    assert {r['selection_reason'] for r in result['selected']} == {'user','uncertainty','diversity','recall_audit','priority'}
    assert any(r['priority_score'] <= 30 for r in result['selected'])
    assert any(r['user_selected'] for r in result['selected'])
    assert all(not r['deep_research_complete'] for r in result['pool'])
    assert all(r['not_selected_reason'] for r in result['not_selected'])


def test_queue_determinism_diversity_dedup_and_no_veto():
    rows = candidates()
    config = QueueConfig(budget=6, user=0, uncertainty=0, diversity=6, recall_audit=0, priority=0)
    first = build_queue(rows, config)
    second = build_queue(list(reversed(rows)), config)
    assert [r['identity'] for r in first['selected']] == [r['identity'] for r in second['selected']]
    assert len({tuple(g) for r in first['selected'] for g in r['groups']}) == 4
    rows += [{'id': '009', 'priority_score': 0, 'gate_state': 'CONFIRMED_EXCLUSION'}]
    result = build_queue(rows, QueueConfig(budget=0))
    assert len(result['pool']) == 10 and not result['selected']
    record = next(r for r in result['pool'] if r['identity'][1] == '9')
    assert len(record['records']) == 2 and record['uncertain']
    assert len(build_queue(rows, QueueConfig(budget=100, priority=100))['selected']) == 10


@pytest.mark.parametrize('config', [QueueConfig(budget=-1), QueueConfig(budget=True), QueueConfig(low_rank_fraction=0)])
def test_invalid_queue_configuration(config):
    with pytest.raises(ValueError):
        build_queue(candidates(), config)


def test_deep_packet_cannot_take_prioritizer_outputs_and_agency_scope_is_separate():
    import json
    from research_foundation.contract import Agency, Opportunity, ResearchInput, deep_research_packet
    request = ResearchInput('project_first', Agency('test', 'Synthetic agency', 'NC', 'Synthetic mission'),
        (), 'Synthetic project', ('Synthetic activity',), 'Synthetic applicant', 'state', ('NC',),
        ('Budget unspecified',), Opportunity('fixture', 'Synthetic opportunity', 'Synthetic funder', 'test'),
        (SOURCE,), ('Amendments not verified',), '2026-11-07')
    packet = deep_research_packet(request)
    assert packet['strategic_evidence_status'] == 'unavailable'
    assert 'priority_score' not in json.dumps(packet)
    assert 'recommendation_label' not in json.dumps(packet)
    with pytest.raises(TypeError):
        replace(request, priority_score=95)
    with pytest.raises(ValueError, match='Agency-only'):
        deep_research_packet(replace(request, mode='agency_first'))
    agency_packet = deep_research_packet(replace(request, mode='agency_first', project_description=None, proposed_activities=()))
    assert agency_packet['project_description'] is None


def test_actual_date_screening_distinguishes_expiry_target_and_unknown():
    from research_foundation.hard_gates import screen_timing
    def aggregate(timing):
        return evaluate_gates([f for f in findings() if f.gate != 'timing']+[timing], [SOURCE], 'final')
    expired = screen_timing('POSTED', '2026-11-06', 'hard', '2026-11-07', (CITE,), True)
    assert aggregate(expired).state == State.CONFIRMED_EXCLUSION
    unreviewed_extension = replace(expired, exceptions_reviewed=False)
    assert aggregate(unreviewed_extension).state == State.CONDITIONAL
    target = screen_timing('POSTED', '2026-11-06', 'target', '2026-11-07', (CITE,), True)
    assert aggregate(target).state == State.CONDITIONAL
    today = screen_timing('POSTED', '2026-11-07', 'hard', '2026-11-07', (CITE,), True, True)
    assert aggregate(today).state == State.PASS
    assert aggregate(screen_timing('FORECASTED', None, 'unknown', '2026-11-07')).state == State.CONDITIONAL
    assert aggregate(screen_timing('POSTED', 'unknown', 'hard', '2026-11-07')).state == State.INSUFFICIENT_EVIDENCE


def test_shared_result_relevance_cannot_override_hard_gate():
    from research_foundation.contract import CONTRACT_VERSION, SharedResult, validate_shared_result
    result = SharedResult(CONTRACT_VERSION, 'synthetic', 'synthetic-fingerprint', 'deep',
        {'full_notice': True, 'amendments_verified': False},
        {'project': {'score': 100}, 'strategic': {'status': 'unavailable', 'score': None}},
        decision('applicant', State.CONFIRMED_EXCLUSION), (), (), (), 'excluded', 'pursue',
        'needs_review', ('Verify alternate route',), {'status': 'synthetic only'})
    with pytest.raises(ValueError, match='Relevance cannot override'):
        validate_shared_result(result)
    validate_shared_result(replace(result, should_apply='reject'))


def test_nested_model_metadata_is_not_accepted_as_an_agency_profile():
    from research_foundation.contract import Opportunity, ResearchInput, deep_research_packet
    request = ResearchInput('agency_first', {'name': 'test', 'gpt4o_score': 99}, (), None, (),
        'Applicant', 'state', (), (), Opportunity('test', 'Test', 'Test', 'Test'), (), (), '2026-11-07')
    with pytest.raises(ValueError, match='original-context'):
        deep_research_packet(request)


def test_multiple_explicit_user_choices_reserve_the_whole_small_budget():
    rows=[{'id':str(i),'priority_score':100-i,'user_selected':i in {8,9},'gate_state':'INSUFFICIENT_EVIDENCE'} for i in range(10)]
    result=build_queue(rows,QueueConfig(budget=2,user=2,uncertainty=2,diversity=2,recall_audit=2,priority=2))
    assert {r['identity'][1] for r in result['selected']}=={'8','9'}
    assert all(r['selection_reason']=='user' for r in result['selected'])
    assert len(result['pool'])==10
