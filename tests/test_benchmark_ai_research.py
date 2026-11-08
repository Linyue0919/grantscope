"""Offline benchmark contract tests; no real credentials, Azure or Grants.gov calls."""
import argparse
import copy
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

SPEC = importlib.util.spec_from_file_location('benchmark_ai_research', Path(__file__).resolve().parents[1] / 'scripts/benchmark_ai_research.py')
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


def manifest():
    return json.loads((b.DATA / 'manifest.json').read_text())


def analysis(packet):
    return {'project_activity_understanding': 'Offline fixture only',
            'dimensions': [{'dimension': d, 'assessment': 'unavailable' if d == 'B' and packet['strategic_goal_status'] == 'unavailable' else 'conditional',
                            'rationale': 'Missing requirements need review', 'claims': []} for d in 'ABCDEF'],
            'counterevidence': [], 'missing_documents_or_requirements': ['Full notice']}


def test_offline_plan_and_identical_packets():
    m = manifest()
    report = b.plan(m)
    assert report['case_count'] == 10
    assert report['max_calls'] == 60
    assert report['reference_price_cost_ceiling_usd'] == 38.3
    assert report['human_labels_available'] is False
    for case in m['cases']:
        packet = b.load_packet(case)
        assert packet['evidence_coverage']['full_notice_text_included'] is False
        inputs = []
        for model in b.MODELS:
            p = b.payload_for(model, packet, 1)
            inputs.append(p['messages'])
            assert 'reference_action' not in p['messages'][1]['content']
            assert 'semantic_relevance_score' not in p['messages'][1]['content']
            assert 'sector_for_human_inventory_only' not in p['messages'][1]['content']
            if model != 'gpt4o':
                assert 'temperature' not in p and 'max_tokens' not in p
                assert p['max_completion_tokens'] == 25000
        assert inputs[0] == inputs[1] == inputs[2]


def test_tamper_and_early_score_are_rejected():
    case = manifest()['cases'][0]
    with pytest.raises(ValueError, match='hash mismatch'):
        b.load_packet({**case, 'evidence_sha256': '0' * 64})
    packet = b.load_packet(case)
    result = analysis(packet)
    b.validate_analysis(result, packet)
    with pytest.raises(ValueError, match='extra fields'):
        b.validate_analysis({**result, 'project_score': 95}, packet)


def test_exact_quote_and_strategic_unavailability():
    packet = b.load_packet(manifest()['cases'][2])
    result = analysis(packet)
    claim = {'statement': 'Test claim', 'kind': 'confirmed_fact',
             'source_id': packet['documents'][0]['source_id'], 'quote': 'A fabricated quotation'}
    result['dimensions'][0]['claims'] = [claim]
    with pytest.raises(ValueError, match='Evidence validation'):
        b.validate_analysis(result, packet)
    result['dimensions'][0]['claims'] = []
    result['dimensions'][1]['assessment'] = 'supported'
    result['dimensions'][1]['claims'] = [{**claim, 'quote': packet['documents'][0]['text']}]
    with pytest.raises(ValueError, match='unavailable'):
        b.validate_analysis(result, packet)


def test_high_score_cannot_override_analysis():
    packet = b.load_packet(manifest()['cases'][2])
    result = {'can_apply': 'direct_route_supported_subject_to_notice', 'should_apply': 'pursue',
              'can_act_in_time': 'potentially_in_time', 'decision_rationale': 'Test',
              'material_conditions': [], 'next_actions': ['Read full notice'],
              'relevance_confidence': 'High', 'project_activity_score': 99, 'strategic_score': None}
    with pytest.raises(ValueError, match='Unconditional pursuit'):
        b.validate_decision(result, analysis(packet), packet)


def test_no_paid_mode_without_matching_approval():
    with TemporaryDirectory() as tmp:
        approval = Path(tmp) / 'approval.json'
        approval.write_text(json.dumps({'approved': False}))
        args = argparse.Namespace(approval_file=str(approval), output_dir=str(Path(tmp) / 'out'), az_path='not-used')
        with patch('requests.Session.post') as post, pytest.raises(ValueError, match='approval'):
            b.run(manifest(), args)
        post.assert_not_called()


def test_usage_and_raw_output_survive_validator_rejection():
    m = manifest()
    with TemporaryDirectory() as tmp:
        labels = {'cases': [{'case_id': c['case_id'], 'reviewer_1': 'synthetic-test-reviewer-1',
                            'reviewer_2': 'synthetic-test-reviewer-2', 'reference_action': 'insufficient_evidence',
                            'reference_dimension_findings': {d: 'Synthetic test only' for d in 'ABCDEF'},
                            'source_locations': ['Synthetic fixture'], 'adjudication_rationale': 'Synthetic fixture'} for c in m['cases']]}
        label_file = Path(tmp) / 'synthetic-test-labels.json'
        label_file.write_text(json.dumps(labels))
        approval = Path(tmp) / 'synthetic-approval.json'
        approval.write_text(json.dumps({'approved': True, 'approved_by': 'offline test only',
            'contract_sha256': b.contract_hash(m), 'azure_prices_verified': True,
            'evidence_scope': 'summary-only', 'max_calls': 60, 'max_usd': 40,
            'reference_labels_path': str(label_file), 'reference_labels_sha256': b.digest(label_file.read_bytes())}))
        args = argparse.Namespace(approval_file=str(approval), output_dir=str(Path(tmp) / 'run'), az_path='not-used')
        def cli(_, arguments):
            if arguments[0] == 'account':
                return {'accessToken': 'synthetic-token-never-log'}
            name = arguments[arguments.index('--deployment-name') + 1]
            config = next(v for v in b.MODELS.values() if v['deployment'] == name)
            return {'model': {'name': config['model'], 'version': config['version']}, 'state': 'Succeeded'}
        response = Mock(status_code=200, headers={'x-request-id': 'offline-test-request'})
        response.json.return_value = {'model': 'synthetic', 'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30},
            'choices': [{'finish_reason': 'stop', 'message': {'content': '{"schema":"invalid"}'}}]}
        with patch.object(b, 'PACING_SECONDS', 0), patch.object(b, 'cli_json', side_effect=cli), patch('requests.Session.post', return_value=response) as post, patch('sys.stdout', new=io.StringIO()):
            b.run(m, args)
        assert post.call_count == 30  # failed phase 1 never proceeds to phase 2; no retries
        raw = (Path(args.output_dir) / 'events.jsonl').read_text()
        assert 'synthetic-token-never-log' not in raw
        events = [json.loads(line) for line in raw.splitlines()]
        failures = [e for e in events if e['status'] == 'failed']
        assert len(failures) == 30
        assert all(e['usage']['total_tokens'] == 30 and e['raw_content'] and e['elapsed_seconds'] >= 0 for e in failures)
        assert all(e['http_status'] == 200 for e in failures)


def pilot_manifest():
    return json.loads((b.DATA / 'pilot/manifest.json').read_text())


def test_pilot_frozen_full_documents_and_no_label_leakage():
    m = pilot_manifest()
    report = b.plan(m)
    assert report['max_calls'] == 18
    assert report['reference_price_cost_ceiling_usd'] == 11.49
    for case in m['cases']:
        packet = b.load_packet(case)
        assert packet['evidence_coverage']['full_notice_text_included']
        assert not packet['evidence_coverage']['amendment_chain_verified']
        assert packet['evidence_coverage']['missing_documents_or_requirements']
        messages = [b.payload_for(model, packet, 1)['messages'] for model in b.MODELS]
        assert messages[0] == messages[1] == messages[2]
        assert 'reference_dimension_findings' not in json.dumps(messages)
        assert any(d['source_id'].startswith('official-') for d in packet['documents'])
    case = copy.deepcopy(m['cases'][0])
    case['official_documents'][0]['text_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='document hash mismatch'):
        b.load_packet(case)
    with pytest.raises(ValueError, match='exactly the three'):
        b.plan({**m, 'cases': m['cases'][:2]})


def test_pilot_mocked_two_stage_pipeline(tmp_path):
    m = pilot_manifest()
    labels = {'cases': [{'case_id': c['case_id'], 'reviewer_1': 'synthetic-1', 'reviewer_2': 'synthetic-2',
        'reference_action': 'conditional_lead', 'reference_dimension_findings': {d: 'Synthetic only' for d in 'ABCDEF'},
        'source_locations': ['Synthetic only'], 'adjudication_rationale': 'Synthetic only'} for c in m['cases']]}
    label_path = tmp_path / 'labels.json'
    label_path.write_text(json.dumps(labels))
    approval = tmp_path / 'approval.json'
    approval.write_text(json.dumps({'approved': True, 'approved_by': 'offline test only',
        'contract_sha256': b.contract_hash(m), 'azure_prices_verified': True,
        'evidence_scope': m['evidence_scope'], 'max_calls': 18, 'max_usd': 15,
        'reference_labels_path': str(label_path), 'reference_labels_sha256': b.digest(label_path.read_bytes())}))
    args = argparse.Namespace(approval_file=str(approval), output_dir=str(tmp_path/'run'), az_path='not-used')
    def cli(_, arguments):
        if arguments[0] == 'account':
            return {'accessToken': 'synthetic-do-not-log'}
        name = arguments[arguments.index('--deployment-name') + 1]
        config = next(v for v in b.MODELS.values() if v['deployment'] == name)
        return {'model': {'name': config['model'], 'version': config['version']}, 'state': 'Succeeded'}
    def post(*_, **kwargs):
        packet = json.loads(kwargs['json']['messages'][1]['content'])['frozen_packet']
        if kwargs['json']['response_format']['json_schema']['schema'] == b.ANALYSIS_SCHEMA:
            result = analysis(packet)
        else:
            result = {'can_apply': 'needs_review', 'should_apply': 'conditional_lead',
                'can_act_in_time': 'needs_review', 'decision_rationale': 'Synthetic offline result',
                'material_conditions': ['Review missing requirements'], 'next_actions': ['Consult official program office'],
                'relevance_confidence': 'Low', 'project_activity_score': 50, 'strategic_score': None}
        response = Mock(status_code=200, headers={})
        response.json.return_value = {'usage': {'prompt_tokens': 10, 'completion_tokens': 20,
            'completion_tokens_details': {'reasoning_tokens': 5}},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}
        return response
    with patch.object(b, 'PACING_SECONDS', 0), patch.object(b, 'cli_json', side_effect=cli), patch('requests.Session.post', side_effect=post) as request, patch('sys.stdout', new=io.StringIO()):
        b.run(m, args)
    assert request.call_count == 18
    text = (Path(args.output_dir)/'events.jsonl').read_text()
    assert 'synthetic-do-not-log' not in text
    completed = [json.loads(line) for line in text.splitlines() if json.loads(line)['status'] == 'validated']
    assert len(completed) == 18
    assert sum(e['stage'] == 2 for e in completed) == 9
    assert all(e['usage']['completion_tokens_details']['reasoning_tokens'] == 5 for e in completed)


def synthetic_pilot_run_args(tmp_path):
    m = pilot_manifest()
    labels = {'cases': [{'case_id': c['case_id'], 'reviewer_1': 'synthetic-1', 'reviewer_2': 'synthetic-2',
        'reference_action': 'conditional_lead', 'reference_dimension_findings': {d: 'Synthetic' for d in 'ABCDEF'},
        'source_locations': ['Synthetic'], 'adjudication_rationale': 'Synthetic'} for c in m['cases']]}
    label_file = tmp_path/'labels.json'
    label_file.write_text(json.dumps(labels))
    approval = tmp_path/'approval.json'
    approval.write_text(json.dumps({'approved': True, 'approved_by': 'offline fixture only',
        'contract_sha256': b.contract_hash(m), 'azure_prices_verified': True,
        'evidence_scope': m['evidence_scope'], 'max_calls': 18, 'max_usd': 15,
        'reference_labels_path': str(label_file), 'reference_labels_sha256': b.digest(label_file.read_bytes())}))
    return m, argparse.Namespace(approval_file=str(approval), output_dir=str(tmp_path/'run'), az_path='not-used')


def synthetic_cli(_, arguments):
    if arguments[0] == 'account':
        return {'accessToken': 'SYNTHETIC_SECRET_NEVER_SAVE'}
    name = arguments[arguments.index('--deployment-name')+1]
    config = next(v for v in b.MODELS.values() if v['deployment'] == name)
    return {'model': {'name': config['model'], 'version': config['version']}, 'state': 'Succeeded'}


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500, 503])
def test_provider_errors_stop_entire_run_and_preserve_private_diagnostics(tmp_path, status):
    import stat
    m, args = synthetic_pilot_run_args(tmp_path)
    response = Mock(status_code=status, headers={'x-request-id': 'synthetic-request'},
                    text='Synthetic provider body SYNTHETIC_SECRET_NEVER_SAVE')
    response.json.return_value = {'error': {'code': 'SyntheticProviderError'},
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}
    with patch.object(b, 'cli_json', side_effect=synthetic_cli), patch('requests.Session.post', return_value=response) as post, pytest.raises(b.PilotAbort):
        b.run(m, args)
    assert post.call_count == 1
    out = Path(args.output_dir)
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.iterdir())
    text = (out/'events.jsonl').read_text()
    assert 'SYNTHETIC_SECRET_NEVER_SAVE' not in text and '[REDACTED]' in text
    failed = json.loads(text.splitlines()[-1])
    assert failed['abort_run'] and failed['http_status'] == status
    assert failed['usage']['completion_tokens'] == 5
    assert failed['elapsed_seconds'] >= 0 and failed['raw_response_body']


@pytest.mark.parametrize('failure', ['timeout', 'connection', 'malformed_envelope'])
def test_ambiguous_paid_requests_stop_without_retry(tmp_path, failure):
    import requests
    m, args = synthetic_pilot_run_args(tmp_path)
    response = Mock(status_code=200, headers={}, text='Malformed synthetic envelope')
    response.json.side_effect = ValueError('Synthetic malformed envelope')
    kwargs = {'return_value': response} if failure == 'malformed_envelope' else {
        'side_effect': requests.Timeout('SYNTHETIC_SECRET_NEVER_SAVE') if failure == 'timeout'
        else requests.ConnectionError('SYNTHETIC_SECRET_NEVER_SAVE')}
    with patch.object(b, 'cli_json', side_effect=synthetic_cli), patch('requests.Session.post', **kwargs) as post, pytest.raises(b.PilotAbort):
        b.run(m, args)
    assert post.call_count == 1
    text = (Path(args.output_dir)/'events.jsonl').read_text()
    assert 'SYNTHETIC_SECRET_NEVER_SAVE' not in text
    failure = json.loads(text.splitlines()[-1])
    assert failure['abort_run'] and not failure['billing_usage_known']


def test_private_output_refuses_overwrite_or_unsafe_ledger(tmp_path):
    import os
    path = tmp_path/'record.json'
    b.private_write(path, 'first')
    with pytest.raises(FileExistsError):
        b.private_write(path, 'second')
    os.chmod(path, 0o644)
    with pytest.raises(b.PilotAbort, match='Unsafe'):
        b.event(path, {'test': True})
    assert path.read_text() == 'first'


def test_cache_write_cost_replaces_input_rate_and_bounds_are_conservative():
    usage={'prompt_tokens':16440,'completion_tokens':3500,'prompt_tokens_details':{'cache_write_tokens':16437,'cached_tokens':0}}
    assert b.estimate_token_cost('gpt61sol',usage) == pytest.approx(.0760985)
    assert b.reserve_token_cost('gpt61sol',1) == pytest.approx(.55)
    with pytest.raises(b.PilotAbort):
        b.estimate_token_cost('gpt61sol',{'prompt_tokens':10,'completion_tokens':1,'prompt_tokens_details':{'cache_write_tokens':11}})
