from copy import deepcopy
from datetime import date
from services.preparation_time import preparation_estimate


def record():
    quotes=['A project proposal must be submitted.','A budget justification is required.',
        'Partner commitment letters are required.','Matching funds are not required.',
        'Signed forms and agency approvals are required.','SAM.gov registration is required.',
        'A draft must be submitted by December 17, 2026.',
        'The application deadline is January 26, 2027.']
    text='\n'.join(quotes)
    claims=[{'kind':'confirmed_fact','statement':'Official application requirement',
             'source_id':'notice','quote':q} for q in quotes]
    return {'state':'RESEARCHED_AND_VALIDATED','candidate':{'id':'1'},
        'evidence':{'status':'POSTED','close_date':'2027-01-26','coverage':{'primary_notice_ingested':True},
                    'sources':[{'source_id':'notice','text':text,'kind':'official_document','url':'https://example.gov/notice'}]},
        'analysis':{'dimensions':[{'dimension':'E','claims':claims}],'counterevidence':[]}}


def test_range_assumptions_and_intermediate_deadline_control_feasibility():
    r=preparation_estimate(record(),date(2026,11,7))
    assert r['available'] and r['range']==[4,8] and r['confidence']=='Low'
    assert r['controlling_deadline']=='2026-12-17' and 'Tight' in r['timing']
    assert r['assumptions'] and r['evidence'] and 'not a guarantee' in r['summary']


def test_description_or_summary_only_cannot_estimate():
    r=record();r['evidence']['sources'][0]['kind']='official_summary'
    assert preparation_estimate(r)['summary']=='Cannot estimate reliably.'
    r=record();r['analysis']['dimensions'][0]['claims']=[]
    assert not preparation_estimate(r)['available']


def test_wrong_source_or_changed_quote_still_fails():
    r=record();r['analysis']['dimensions'][0]['claims'][0]['quote']='All proposals are optional.'
    assert not preparation_estimate(r)['available']
    r=record();r['analysis']['dimensions'][0]['claims'][0]['source_id']='wrong'
    assert not preparation_estimate(r)['available']


def test_missing_requirements_unknown_year_or_final_deadline_cannot_estimate():
    r=record();r['analysis']['dimensions'][0]['claims'].pop(1)
    assert not preparation_estimate(r)['available']
    r=record();q=r['analysis']['dimensions'][0]['claims'][6]
    q['quote']=q['quote'].replace(', 2026','')
    r['evidence']['sources'][0]['text']=r['evidence']['sources'][0]['text'].replace(', 2026','')
    assert not preparation_estimate(r)['available']
    r=record();r['evidence']['close_date']='2027-01-27'
    assert not preparation_estimate(r)['available']


def test_passed_intermediate_deadline_and_closed_status_are_not_in_time():
    assert 'has passed' in preparation_estimate(record(),date(2026,12,18))['timing']
    r=record();r['evidence']['status']='CLOSED'
    assert 'Not currently' in preparation_estimate(r,date(2026,11,7))['timing']


def test_waiver_of_one_requirement_does_not_waive_another():
    r=record();q='A project proposal must be submitted; matching funds are not required.'
    r['analysis']['dimensions'][0]['claims'][0]['quote']=q
    r['evidence']['sources'][0]['text']+='\n'+q
    result=preparation_estimate(r,date(2026,11,7))
    assert result['available'] and result['range'][0]>=3


def test_researched_card_renders_estimate_and_insufficient_evidence(tmp_path):
    from streamlit.testing.v1 import AppTest
    import json
    r=record();r['opportunity_id']='1';r['classification']='CONDITIONAL';r['candidate']['title']='Synthetic notice'
    claims=r['analysis']['dimensions'][0]['claims']
    r['analysis']['dimensions']=[{'dimension':d,'assessment':'conditional','rationale':'Review requirements',
                                 'claims':claims if d=='E' else []} for d in 'ABCDEF']
    r['shared_result']={'can_apply':'needs_review','should_apply':'conditional_lead','can_act_in_time':'needs_review',
                        'next_actions':['Verify readiness'],'unresolved_requirements':[]}
    r['decision']={'should_apply':'conditional_lead','can_act_in_time':'needs_review','project_activity_score':60,'strategic_score':None,'decision_rationale':'Conditional lead.',
                   'material_conditions':['Verify agency readiness'],'decision_claims':[]}
    def render(value):
        return AppTest.from_string('import json\nfrom modules.search_workflow import render_card\nfrom services.grant_store import LocalGrantStore\nr=json.loads('+repr(json.dumps(value))+')\nrender_card(r,"NC agency","Synthetic project",LocalGrantStore('+repr(str(tmp_path/'saved.json'))+'),"prep-test")').run()
    at=render(r)
    assert not at.exception and any('4–8 calendar weeks' in m.value for m in at.markdown)
    assert any('Confidence: Low' in c.value for c in at.caption)
    r['analysis']['dimensions'][4]['claims']=[]
    at=render(r)
    assert not at.exception and any('Cannot estimate reliably.' in m.value for m in at.markdown)
