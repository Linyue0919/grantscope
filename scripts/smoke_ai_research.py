#!/usr/bin/env python3
"""Explicitly authorized four-call smoke scope. Default is offline; no production imports."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import benchmark_ai_research as b

AZ = '/tmp/grantscope-azure-cli/bin/az'
GROUP = 'rg-primary-unc-sdis-solveathon-team07'
ACCOUNT = 'grantscope-ai-team07'
ARM_ROOT = f'https://management.azure.com/subscriptions/{b.SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}'
DEPLOYMENT_QUERY = '{name:name,id:id,sku:sku,model:properties.model,state:properties.provisioningState,upgrade:properties.versionUpgradeOption,capacity:properties.currentCapacity,rateLimits:properties.rateLimits,capabilities:properties.capabilities}'


def configure():
    b.MODELS = {k: v for k, v in b.MODELS.items() if k in {'gpt55', 'gpt61sol'}}
    if 'application_viability' not in b.DECISION_SCHEMA['properties']:
        b.ANALYSIS_INSTRUCTION += '''\nUse the fixed dimensions: A project activity fit; B verified agency strategic fit;\nC funding purpose and allowable activities; D applicant eligibility and partnership/exception routes;\nE status, deadlines, match and application readiness; F official evidence, counterevidence and next steps.'''
        b.DECISION_SCHEMA = copy.deepcopy(b.DECISION_SCHEMA)
        b.DECISION_SCHEMA['properties']['application_viability'] = {'type': 'string', 'enum': [
            'ACTIONABLE', 'CONDITIONAL', 'CONFIRMED_EXCLUSION', 'INSUFFICIENT_EVIDENCE']}
        b.DECISION_SCHEMA['required'].append('application_viability')
        b.DECISION_INSTRUCTION += '''\nClassify application_viability separately from relevance. ACTIONABLE requires pursuit
supported by all material requirements. CONDITIONAL means a plausible lead with named unresolved
conditions. CONFIRMED_EXCLUSION requires an explicit source-grounded disqualifying contradiction,
including review of exceptions and alternative application routes; silence or unknown suitability
is not exclusion. INSUFFICIENT_EVIDENCE means the packet cannot support a viability judgment.
These are model findings pending independent human review, not official eligibility certification.'''
        original = b.validate_decision
        def validate(value, analysis, packet):
            original(value, analysis, packet)
            viability = value['application_viability']
            if (viability == 'ACTIONABLE') != (value['should_apply'] == 'pursue'):
                raise ValueError('Actionability and pursuit must be consistent')
            if viability == 'CONFIRMED_EXCLUSION':
                claims = analysis['counterevidence'] + [c for d in analysis['dimensions'] for c in d['claims']]
                if not any(c['kind'] == 'disqualifying_contradiction' and c['source_id'] for c in claims):
                    raise ValueError('Exclusion requires an official cited contradiction')
        b.validate_decision = validate


def smoke_manifest():
    source = b.DATA/'pilot/manifest.json'
    manifest = json.loads(source.read_text())
    manifest['run_kind'] = 'single-case-smoke'
    manifest['cases'] = [c for c in manifest['cases'] if c['opportunity_id'] == '364144']
    manifest['authorization_scope'] = 'four-call-364144-smoke'
    manifest['source_manifest_sha256'] = b.digest(source.read_bytes())
    manifest['smoke_driver_sha256'] = b.digest(Path(__file__).read_bytes())
    return manifest


def deployments():
    return b.cli_json(AZ, ['cognitiveservices', 'account', 'deployment', 'list', '--subscription', b.SUBSCRIPTION,
        '-g', GROUP, '-n', ACCOUNT, '--query', '[].'+DEPLOYMENT_QUERY])


def verify_created(deployment, config):
    if (deployment['model']['name'] != config['model'] or deployment['model']['version'] != config['version']
            or deployment['sku']['name'] != 'GlobalStandard' or deployment['sku']['capacity'] != 200
            or deployment['upgrade'] != 'NoAutoUpgrade' or deployment['state'] != 'Succeeded'):
        raise b.PilotAbort('Authorized deployment identity/capacity/upgrade/provisioning verification failed')
    limits = {r['key']: r['count'] for r in deployment.get('rateLimits') or []}
    if limits.get('token') != 200000:
        raise b.PilotAbort('Allocated TPM differs from the authorized 200k allocation')
    if (deployment.get('capabilities') or {}).get('jsonSchemaResponse') not in {None, 'true'}:
        raise b.PilotAbort('Deployment explicitly reports JSON Schema response unsupported')


def create(manifest, args):
    if args.expected_contract != b.contract_hash(manifest):
        raise b.PilotAbort('Smoke contract mismatch before Azure operations')
    out = Path(args.state_dir)
    out.mkdir(mode=0o700, exist_ok=False)
    before = deployments()
    b.private_write(out/'deployments-before.json', json.dumps(before, indent=2))
    existing = {d['name'] for d in before}
    if any(c['deployment'] in existing for c in b.MODELS.values()):
        raise b.PilotAbort('An authorized deployment already exists; refusing to overwrite')
    models = b.cli_json(AZ, ['cognitiveservices', 'account', 'list-models', '--subscription', b.SUBSCRIPTION,
        '-g', GROUP, '-n', ACCOUNT, '--query', "[?name=='gpt-5.5' || name=='gpt-6.1-sol'].{name:name,version:version,skus:skus}"])
    quotas = b.cli_json(AZ, ['cognitiveservices', 'usage', 'list', '--subscription', b.SUBSCRIPTION,
        '--location', 'eastus', '--query', "[?contains(name.value, 'GlobalStandard.gpt-5.5') || contains(name.value, 'GlobalStandard.gpt-6.1-sol')].{name:name.value,current:currentValue,limit:limit}"])
    for config in b.MODELS.values():
        if not any(m['name'] == config['model'] and m['version'] == config['version']
                   and any(s['name'] == 'GlobalStandard' for s in m['skus']) for m in models):
            raise b.PilotAbort('Exact model/version/SKU is no longer available')
        q = next((q for q in quotas if q['name'] == 'OpenAI.GlobalStandard.'+config['model']), None)
        if not q or q['limit']-q['current'] < 200:
            raise b.PilotAbort('Insufficient current authorized model quota')
    b.private_write(out/'preflight.json', json.dumps({'contract': b.plan(manifest), 'models': models, 'quota': quotas}, indent=2))
    for key, config in b.MODELS.items():
        body = {'sku': {'name': 'GlobalStandard', 'capacity': 200}, 'properties': {
            'model': {'format': 'OpenAI', 'name': config['model'], 'version': config['version']},
            'versionUpgradeOption': 'NoAutoUpgrade'}}
        body_file = out/(key+'-deployment-request.json')
        b.private_write(body_file, json.dumps(body))
        url = ARM_ROOT+'/deployments/'+config['deployment']+'?api-version=2024-10-01'
        created = b.cli_json(AZ, ['rest', '--method', 'put', '--url', url, '--body', '@'+str(body_file), '--query', DEPLOYMENT_QUERY])
        b.private_write(out/(key+'-creation-response.json'), json.dumps(created, indent=2))
        # GET polling is read-only; failed/ambiguous PUT is never retried.
        for _ in range(30):
            observed = next((d for d in deployments() if d['name'] == config['deployment']), None)
            if observed and observed['state'] == 'Succeeded':
                verify_created(observed, config)
                break
            if observed and observed['state'] not in {'Creating', 'Updating', 'Accepted', 'Running'}:
                raise b.PilotAbort('Deployment did not provision successfully')
            print('Waiting for isolated deployment provisioning', flush=True)
            time.sleep(5)
        else:
            raise b.PilotAbort('Provisioning polling expired; stop without another PUT')
        print(json.dumps({'created': config['deployment'], 'state': 'Succeeded', 'TPM': 200000, 'upgrade': 'NoAutoUpgrade'}), flush=True)
    after = deployments()
    old = {d['name']: d for d in before}
    if any(next((d for d in after if d['name'] == name), None) != record for name, record in old.items()):
        raise b.PilotAbort('Existing deployment metadata changed; stop before inference')
    b.private_write(out/'deployments-after.json', json.dumps(after, indent=2))
    print('Both authorized deployments verified; existing deployment metadata unchanged', flush=True)


def execute(manifest, args):
    report = b.plan(manifest)
    if args.expected_contract != report['contract_sha256'] or report['max_calls'] != 4 or report['reference_price_cost_ceiling_usd'] > 15:
        raise b.PilotAbort('Four-call smoke contract/cost check failed')
    state = Path(args.state_dir)
    before = json.loads((state/'deployments-before.json').read_text())
    current = deployments()
    for config in b.MODELS.values():
        verify_created(next(d for d in current if d['name'] == config['deployment']), config)
    for d in before:
        if next((r for r in current if r['name'] == d['name']), None) != d:
            raise b.PilotAbort('Production deployment changed before inference')
    approval = {'approved': True, 'approved_by': 'User explicit November 7 four-call smoke authorization',
        'authorization_scope': 'four-call-364144-smoke', 'contract_sha256': report['contract_sha256'],
        'azure_prices_verified': False, 'public_reference_rates_accepted': True,
        'evidence_scope': manifest['evidence_scope'], 'max_calls': 4, 'max_usd': 15,
        'human_reference_labels_available': False}
    approval_path = state/'smoke-authorization.json'
    b.private_write(approval_path, json.dumps(approval, indent=2))
    args.approval_file = str(approval_path)
    args.az_path = AZ
    b.run(manifest, args)
    after = deployments()
    b.private_write(state/'deployments-post-inference.json', json.dumps(after, indent=2))
    if any(next((r for r in after if r['name'] == d['name']), None) != d for d in before):
        raise b.PilotAbort('Production deployment metadata differs after experiment')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--create-isolated-deployments', action='store_true')
    action.add_argument('--execute-four-calls', action='store_true')
    parser.add_argument('--expected-contract')
    parser.add_argument('--state-dir', default='/tmp/grantscope-smoke-20261107-state')
    parser.add_argument('--output-dir', default='/tmp/grantscope-smoke-20261107-results')
    args = parser.parse_args()
    configure()
    manifest = smoke_manifest()
    if args.create_isolated_deployments:
        create(manifest, args)
    elif args.execute_four_calls:
        execute(manifest, args)
    else:
        print(json.dumps(b.plan(manifest), indent=2))


if __name__ == '__main__':
    main()
