"""Four-call authorization scope exercised offline only."""
import argparse
import pytest
import importlib
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    s = importlib.import_module('smoke_ai_research')
    s.configure()
    return s


def test_smoke_scope_and_four_mock_calls_without_invented_labels(tmp_path, monkeypatch):
    if not (Path(__file__).resolve().parents[1]/"docs/ai-research-benchmark/pilot/manifest.json").exists():
        pytest.skip("Optional private pilot evidence is not distributed")
    s = load(monkeypatch); b = s.b; manifest = s.smoke_manifest()
    report = b.plan(manifest)
    assert report['max_calls'] == 4 and report['reference_price_cost_ceiling_usd'] == 3.12
    assert not report['human_labels_available']
    packet = b.load_packet(manifest['cases'][0])
    assert b.payload_for('gpt55', packet, 1)['messages'] == b.payload_for('gpt61sol', packet, 1)['messages']
    assert 'reference_action' not in json.dumps(packet)
    approval = tmp_path/'approval.json'
    approval.write_text(json.dumps({'approved': True, 'approved_by': 'synthetic offline fixture',
        'authorization_scope': 'four-call-364144-smoke', 'public_reference_rates_accepted': True,
        'contract_sha256': report['contract_sha256'], 'evidence_scope': manifest['evidence_scope'],
        'azure_prices_verified': False, 'max_calls': 4, 'max_usd': 15}))
    args = argparse.Namespace(approval_file=str(approval), output_dir=str(tmp_path/'run'), az_path='not-used')
    def cli(_, arguments):
        if arguments[0] == 'account':return {'accessToken': 'SYNTHETIC_NEVER_LOG'}
        name = arguments[arguments.index('--deployment-name')+1]
        config = next(c for c in b.MODELS.values() if c['deployment'] == name)
        return {'model': {'name': config['model'], 'version': config['version']}, 'state': 'Succeeded'}
    def post(*_, **kwargs):
        stage1 = kwargs['json']['response_format']['json_schema']['schema'] == b.ANALYSIS_SCHEMA
        value = {'project_activity_understanding': 'Synthetic offline fixture', 'dimensions': [
            {'dimension': d, 'assessment': 'conditional', 'rationale': 'Synthetic unknown', 'claims': []} for d in 'ABCDEF'],
            'counterevidence': [], 'missing_documents_or_requirements': ['Synthetic unknown']} if stage1 else {
            'can_apply': 'needs_review', 'should_apply': 'conditional_lead', 'can_act_in_time': 'needs_review',
            'decision_rationale': 'Synthetic only', 'material_conditions': ['Unknown'], 'next_actions': ['Review source'],
            'relevance_confidence': 'Low', 'project_activity_score': 50, 'strategic_score': None,
            'application_viability': 'CONDITIONAL'}
        response = Mock(status_code=200, headers={}, text='Synthetic response')
        response.json.return_value = {'usage': {'prompt_tokens': 10, 'completion_tokens': 10},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}
        return response
    with patch.object(b, 'cli_json', side_effect=cli), patch.object(b, 'PACING_SECONDS', 0), patch('requests.Session.post', side_effect=post) as request, patch('sys.stdout', new=io.StringIO()):
        b.run(manifest, args)
    assert request.call_count == 4
    events = [json.loads(line) for line in (Path(args.output_dir)/'events.jsonl').read_text().splitlines()]
    done = [e for e in events if e['status'] == 'validated']
    assert len(done) == 4 and all(e['end_at'] and e['model_version'] for e in done)
    assert {e['deployment'] for e in done} == {c['deployment'] for c in b.MODELS.values()}


def test_missing_capability_flag_is_not_a_provider_incompatibility(monkeypatch):
    import pytest
    s = load(monkeypatch);config = s.b.MODELS['gpt55']
    deployment = {'model': {'name': config['model'], 'version': config['version']},
        'sku': {'name': 'GlobalStandard', 'capacity': 200}, 'upgrade': 'NoAutoUpgrade',
        'state': 'Succeeded', 'rateLimits': [{'key': 'token', 'count': 200000}],
        'capabilities': {'chatCompletion': 'true'}}
    s.verify_created(deployment, config)
    deployment['capabilities']['jsonSchemaResponse'] = 'false'
    with pytest.raises(s.b.PilotAbort, match='explicitly'):
        s.verify_created(deployment, config)
