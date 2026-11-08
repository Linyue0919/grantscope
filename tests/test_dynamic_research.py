"""Multi-agency/multi-opportunity end-to-end tests. All model responses are synthetic.
No benchmark case, live inference, human reference labels or production cache writes.
"""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock,patch
import json
from pathlib import Path
import pytest
from research_foundation.hard_gates import Source,Citation,Finding,State
from services.search_foundation import build_project_review,discover_project
from services.research_engine import (run_research,request_for_candidate,ResearchBudget,ResearchState,ResearchStore,AzureSolProvider,context_key)
from services.official_evidence import OfficialEvidenceClient,extract_document,official_url

GRANTS=[{'id':'910001','title':'Watershed monitoring','agencyCode':'EPA'},
        {'id':'910002','title':'Rural broadband','agencyCode':'NTIA'},
        {'id':'910003','title':'Public health preparedness','agencyCode':'HHS'},
        {'id':'910004','title':'Flood resilience','agencyCode':'FEMA'}]


class Evidence:
    def __init__(self,missing=()):self.missing=set(missing);self.calls=[];self.version='v1'
    def fetch(self,oid):
        self.calls.append(oid)
        text={'910001':'Watershed monitoring. Only research institutes may apply.',
              '910002':'Rural broadband. State agencies may apply with an eligible lead.',
              '910003':'Public health preparedness. Applicant requirements need review.',
              '910004':'Flood resilience. Match is required.'}[oid]
        return {'opportunity_id':oid,'sources':[{'source_id':'notice-'+oid,'url':'https://example.gov/'+oid,
            'text':text,'version':self.version,'retrieved_at':'2026-11-07','kind':'official_document','raw_sha256':self.version+oid}],
            'coverage':{'primary_notice_ingested':oid not in self.missing,'amendments_verified':False,
                        'gaps':['Amendment chain not certified']},'inventory':[],'status':'POSTED'}


class Provider:
    def __init__(self,bad=(),fatal=False):self.bad=set(bad);self.calls=[];self.fatal=fatal
    def complete(self,packet,stage,analysis=None):
        oid=packet['original_request']['opportunity']['opportunity_id'];self.calls.append((oid,stage,deepcopy(packet)))
        if self.fatal:return {'fatal':True,'error':'Synthetic transport failure','request_sent':True}
        assert 'priority_score' not in json.dumps(packet) and 'cached_ai_score' not in json.dumps(packet)
        claim={'statement':'Official program conditions','kind':'confirmed_fact','source_id':'notice-'+oid,'quote':next(d['text'] for d in packet['documents'] if d['source_id']=='notice-'+oid)}
        if oid in self.bad:claim['source_id']='wrong-source'
        if stage==1:
            value={'project_activity_understanding':'Synthetic original activity analysis',
                'dimensions':[{'dimension':d,'assessment':'unavailable' if d=='B' else 'conditional',
                    'rationale':'Requirements remain conditional','claims':[] if d=='B' else [claim]} for d in 'ABCDEF'],
                'counterevidence':[],'missing_documents_or_requirements':['Applicant and partner route need verification']}
        else:
            value={'can_apply':'needs_review','should_apply':'conditional_lead','can_act_in_time':'needs_review',
                'decision_rationale':'Synthetic conditional draft','material_conditions':['Verify lead applicant and match'],
                'next_actions':['Ask official program staff to verify the proposed activities and route'],
                'relevance_confidence':'Medium','project_activity_score':70 if packet['original_request']['mode']=='project_first' else None,
                'strategic_score':None,'application_viability':'CONDITIONAL','decision_claims':[claim]}
        return {'value':value,'request_sent':True,'usage':{'prompt_tokens':100,'completion_tokens':100},'estimated_cost_usd':.001,'elapsed_seconds':.1,'raw_response':json.dumps(value)}


def make_review(agency='NC environment agency',project='Water restoration',count=4):
    return build_project_review(GRANTS[:count],agency,project,[
        {'opportunity_id':'910001','semantic':{'status':'Evaluated','project_relevance_score':99}},
        {'opportunity_id':'910002','semantic':{'status':'Evaluated','project_relevance_score':1}}],budget=count)


def factory(agency='NC environment agency',project='Water restoration',mode='project_first'):
    return lambda grant:request_for_candidate(agency,project,grant,mode=mode,profile={'mission':'User-provided mission, not verified goals','geography':['NC']})


def test_multi_grant_pipeline_retention_independent_research_and_final_gates(tmp_path):
    review=make_review();client=Evidence();provider=Provider()
    source=Source('review','https://example.gov/review','Only research institutes may apply.','v1','2026-11-07',True)
    exclusion=Finding('applicant',State.CONFIRMED_EXCLUSION,'Synthetic verified exclusive applicant rule',
        (Citation('review',source.text,'Applicant section'),),'synthetic-rule-v1',True,True)
    result=run_research(review,factory(),provider,budget=ResearchBudget(4,8,5),evidence_client=client,
        reviewed_gates={'910001':{'findings':[exclusion],'sources':[source]}})
    assert set(result['records'])=={g['id'] for g in GRANTS}
    assert result['records']['910001']['classification']=='CONFIRMED_EXCLUSION' # cached 99 never overrides it
    assert result['records']['910002']['classification']=='CONDITIONAL' # cached 1 never vetoes it
    assert result['records']['910001']['state']=='PRELIMINARY_SCREENED'
    assert all(result['records'][oid]['state']=='RESEARCHED_AND_VALIDATED' for oid in ['910002','910003','910004'])
    assert len(provider.calls)==6 and len(client.calls)==3
    assert not any(call[0]=='910001' for call in provider.calls)
    assert {c[2]['original_request']['opportunity']['title'] for c in provider.calls}=={g['title'] for g in GRANTS[1:]}
    store=ResearchStore(tmp_path/'research');scope=context_key(factory()(GRANTS[0]));store.save(scope,result['records'])
    assert set(store.load(scope))==set(result['records'])
    before=len(provider.calls)
    reused=run_research(review,factory(),provider,evidence_client=client,previous=result['records'],budget=ResearchBudget(4,8,5))
    assert len(provider.calls)==before+2
    assert all(reused['records'][oid].get('cache_reused') for oid in ['910002','910003','910004'])
    before=len(provider.calls)
    # Changed official evidence invalidates successful cached evaluations.
    client.version='v2'
    run_research(review,factory(),provider,evidence_client=client,previous=result['records'],budget=ResearchBudget(1,2,5))
    assert len(provider.calls)==before+2


def test_other_agencies_projects_and_agency_first_do_not_reuse_project_judgments():
    review=make_review(count=2);provider=Provider();client=Evidence()
    first=run_research(review,factory(),provider,evidence_client=client,budget=ResearchBudget(2,4,5))
    other=make_review('NC technology agency','Rural broadband',2)
    second=run_research(other,factory('NC technology agency','Rural broadband'),provider,evidence_client=client,previous=first['records'],budget=ResearchBudget(2,4,5))
    assert not any(r.get('cache_reused') for r in second['records'].values())
    agency=run_research(other,factory('NC technology agency',None,'agency_first'),provider,evidence_client=client,budget=ResearchBudget(1,2,5))
    record=next(r for r in agency['records'].values() if r['state']=='RESEARCHED_AND_VALIDATED')
    assert record['shared_result']['relevance']['project']['score'] is None
    assert provider.calls[-1][2]['original_request']['project_description'] is None


def test_missing_notice_failed_citations_unknown_routes_and_budget_states():
    review=make_review();provider=Provider(bad=['910002']);client=Evidence(missing=['910001'])
    result=run_research(review,factory(),provider,evidence_client=client,budget=ResearchBudget(4,8,5))
    assert result['records']['910001']['state']=='RESEARCH_FAILED'
    assert not any(c[0]=='910001' for c in provider.calls)
    assert result['records']['910002']['state']=='RESEARCH_FAILED'
    assert not any(c[0]=='910002' and c[1]==2 for c in provider.calls)
    assert result['records']['910003']['classification']=='CONDITIONAL'
    assert result['records']['910003']['shared_result']['can_apply']=='needs_review'
    budgeted=run_research(review,factory(),Provider(),evidence_client=Evidence(),budget=ResearchBudget(4,1,5))
    assert budgeted['budget']['used_calls']==1
    assert all(r['state']=='NOT_YET_RESEARCHED' for r in budgeted['records'].values())
    assert any(r.get('analysis') for r in budgeted['records'].values())


def test_transport_aborts_all_remaining_paths_and_no_automatic_retry():
    review=make_review();provider=Provider(fatal=True)
    result=run_research(review,factory(),provider,evidence_client=Evidence(),budget=ResearchBudget(4,8,5))
    assert result['aborted'] and len(provider.calls)==1
    assert len(result['records'])==4


def test_dynamic_intake_uses_current_opportunity_and_amendments_not_fixtures():
    session=Mock();response=Mock()
    response.json.return_value={'errorcode':0,'data':{'ost':'POSTED','synopsis':{'synopsisDesc':'Official summary'},
        'documents':[{'id':11,'fileName':'Funding-NOFO.html','mimeType':'text/html'},
                     {'id':12,'fileName':'Amendment.html','mimeType':'text/html'}]}}
    session.post.return_value=response
    def get(url,**kwargs):
        r=Mock(status_code=200,headers={'Content-Type':'text/html'})
        r.iter_content.return_value=[b'<h1>Notice of Funding Opportunity</h1><p>State agencies eligible. Match and activities require review.</p>']
        return r
    session.get.side_effect=get
    result=OfficialEvidenceClient(session=session).fetch('910099')
    assert result['coverage']['primary_notice_ingested'] and len(result['sources'])==3
    assert not result['coverage']['amendments_verified']
    assert all(s['source_id'].startswith(('grantsgov-910099','attachment-910099')) for s in result['sources'])
    assert session.post.call_args.kwargs['json']['opportunityId']==910099
    assert session.get.call_count==2
    assert not official_url('http://localhost/private') and not official_url('https://example.com/fake.pdf')


def test_partnership_exception_retained_and_no_false_confirmed_exclusion():
    from services.search_foundation import candidate_decision
    source=Source('s','https://example.gov/notice','Institutes may lead with government partners.','v1','2026-11-07',True)
    restriction=Finding('applicant',State.CONFIRMED_EXCLUSION,'Only a qualified institute may lead',
        (Citation('s',source.text,'Section 1'),),'synthetic-rule',True,False)
    assert candidate_decision([restriction],[source])['state']!='CONFIRMED_EXCLUSION'


def test_user_can_research_a_low_gpt4o_priority_with_small_budget():
    cached=[{'opportunity_id':'910002','semantic':{'status':'Evaluated','project_relevance_score':1}}]
    review=build_project_review(GRANTS,'NC technology agency','Broadband',cached,budget=1,selected_ids=('910002',))
    provider=Provider()
    result=run_research(review,factory('NC technology agency','Broadband'),provider,evidence_client=Evidence(),budget=ResearchBudget(1,2,2))
    assert [(oid,stage) for oid,stage,_ in provider.calls]==[('910002',1),('910002',2)]
    assert result['records']['910002']['state']=='RESEARCHED_AND_VALIDATED'
    assert len(result['records'])==4


def test_streamlit_multi_grant_dynamic_research_and_save_without_a_live_call(tmp_path):
    from streamlit.testing.v1 import AppTest
    from services.grant_store import LocalGrantStore
    provider=Provider();store=LocalGrantStore(tmp_path/'saved.json');cache=Mock();cache.get.return_value={'records':[]}
    research_store=ResearchStore(tmp_path/'research')
    with patch('modules.search.get_grants',return_value=GRANTS),patch('modules.search.AIRecommendationCache',return_value=cache),\
         patch('modules.search.LocalGrantStore',return_value=store),patch('modules.search_research.ResearchStore',return_value=research_store),\
         patch('modules.search_research.AzureSolProvider',return_value=provider),patch('services.research_engine.OfficialEvidenceClient',return_value=Evidence()),\
         patch('modules.search.prepare_ai_recommendations') as legacy_paid:
        at=AppTest.from_string('from modules.search import show_search\nshow_search()').run()
        assert not at.session_state.filtered_state.get('search_show_example')
        at.selectbox(key='search_agency').select('Other NC agency / enter profile').run()
        at.text_input(key='search_custom_agency').input('Synthetic NC technology office').run()
        at.text_area[0].input('Rural broadband buildout')
        at.text_area(key='search_agency_mission').input('Support rural connectivity')
        at.button(key='search_submit').click().run()
        assert not at.exception
        run_button=next(b for b in at.button if b.key and b.key.startswith('dynamic_research_run_'))
        assert run_button.disabled
        consent=next(c for c in at.checkbox if c.key and c.key.startswith('dynamic_research_consent_'))
        at.checkbox(key=consent.key).check().run()
        at.button(key=run_button.key).click().run()
        assert not at.exception
        assert len(provider.calls)==6
        assert all(c[2]['original_request']['agency']['name']=='Synthetic NC technology office' for c in provider.calls)
        assert len({c[0] for c in provider.calls})==3
        assert sum('RESEARCHED_AND_VALIDATED' in e.value for e in at.markdown)>=3
        save=next(b for b in at.button if b.key and b.key.startswith('dynamic_save_'))
        oid=save.key.rsplit('_',1)[1]
        at.button(key=save.key).click().run()
        assert 'experimental researched result' in store.get('Synthetic NC technology office',oid)['notes']
        assert len(provider.calls)==6 # Save/rerun does not repeat provider calls
        legacy_paid.assert_not_called();cache.save.assert_not_called()


def test_real_recorded_opportunities_remain_reviewable_when_notices_unavailable():
    root=Path(__file__).resolve().parents[1]/'docs/ai-research-benchmark/evidence'
    seeds=[];frozen={}
    for oid in ['362755','362843']:
        data=json.loads((root/(oid+'.json')).read_text());frozen[oid]=data
        seeds.append({'id':oid,'title':data['title']})
    session=Mock()
    def post(url,**kwargs):
        oid=str(kwargs['json']['opportunityId']);d=frozen[oid];r=Mock()
        r.json.return_value={'errorcode':0,'data':{'ost':d['status'],'synopsis':d['official_fields'],'documents':d['attachment_metadata']}}
        return r
    session.post.side_effect=post
    import requests
    session.get.side_effect=requests.ConnectionError('Synthetic offline attachment outage')
    provider=Provider();review=build_project_review(seeds,'NC water agency','watershed restoration',budget=2)
    result=run_research(review,factory('NC water agency','watershed restoration'),provider,
        evidence_client=OfficialEvidenceClient(session=session,max_documents=2),budget=ResearchBudget(2,4,5))
    assert set(result['records'])=={'362755','362843'} and not provider.calls
    assert all(r['state']=='RESEARCH_FAILED' and r['evidence']['sources'] for r in result['records'].values())
    assert all('grantsgov-'+oid==r['evidence']['sources'][0]['source_id'] for oid,r in result['records'].items())
    assert session.get.call_count<=4


def test_partial_analysis_resumes_without_repeating_a_paid_stage():
    review=build_project_review(GRANTS[:1],'NC water agency','water',budget=1)
    provider=Provider();evidence=Evidence();req=factory('NC water agency','water')
    first=run_research(review,req,provider,evidence_client=evidence,budget=ResearchBudget(1,1,5))
    assert first['records']['910001']['state']=='NOT_YET_RESEARCHED'
    second=run_research(review,req,provider,evidence_client=evidence,previous=first['records'],budget=ResearchBudget(1,1,5))
    assert second['records']['910001']['state']=='RESEARCHED_AND_VALIDATED'
    assert [(oid,stage) for oid,stage,_ in provider.calls]==[('910001',1),('910001',2)]


def test_gpt4o_prioritization_never_excludes_low_priority_opportunities():
    from services.research_priority import prioritize_pool
    review=make_review(count=2);provider=Mock()
    provider.prioritize.side_effect=lambda req,details:{'opportunity_id':req.opportunity.opportunity_id,
        'priority_score':1 if req.opportunity.opportunity_id=='910002' else 99,'uncertain':True,'reason':'Synthetic triage only'}
    output=prioritize_pool(review,factory(),provider,max_candidates=2,max_usd=.34,fetch_details=lambda oid:{'description':'Official summary'})
    assert output['candidate_count']==2 and output['calls']==2
    assert output['priorities']['910002']['priority_score']==1
    assert not any('eligibility' in p or 'classification' in p for p in output['priorities'].values())
    cached=[{'opportunity_id':oid,'semantic':{'status':'Prioritized','project_relevance_score':r['priority_score']}} for oid,r in output['priorities'].items()]
    rebuilt=build_project_review(GRANTS[:2],'NC environment agency','Water restoration',cached,budget=2)
    assert rebuilt['candidate_count']==2
    assert all(row['decision']['state']=='INSUFFICIENT_EVIDENCE' for row in rebuilt['queue']['pool'])


def test_actual_pdf_extractor_reads_bounded_document_text():
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    content=DecodedStreamObject();content.set_data(b'BT /F1 12 Tf 40 700 Td (Notice of Funding Opportunity - synthetic requirement) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(content)
    stream=BytesIO();writer.write(stream)
    text,method=extract_document(stream.getvalue(),'application/pdf','notice.pdf')
    assert 'synthetic requirement' in text and '[PDF page 1]' in text and 'pypdf' in method


@pytest.mark.parametrize('error',['http','timeout','malformed'])
def test_live_provider_adapter_fails_closed_without_retry_or_secret_logging(error):
    import requests
    session=Mock();r=Mock(status_code=429 if error=='http' else 200,text='Synthetic SYNTHETIC_KEY response')
    r.json.return_value={'error':{'code':'Synthetic'}}
    if error=='malformed':r.json.side_effect=ValueError('Invalid envelope')
    session.post.side_effect=requests.Timeout('SYNTHETIC_KEY') if error=='timeout' else None
    session.post.return_value=r
    provider=AzureSolProvider({'AZURE_OPENAI_ENDPOINT':'https://unit.openai.azure.com','AZURE_OPENAI_API_KEY':'SYNTHETIC_KEY'},session=session)
    result=provider.complete({'documents':[]},1)
    assert result['fatal'] and session.post.call_count==1
    assert 'SYNTHETIC_KEY' not in json.dumps(result)
    assert session.post.call_args.kwargs['allow_redirects'] is False


def test_funding_purpose_rejection_is_not_recast_as_an_application_lead():
    class NotSuitable(Provider):
        def complete(self,packet,stage,analysis=None):
            response=super().complete(packet,stage,analysis)
            if stage==2:
                response['value']['should_apply']='reject'
                response['value']['decision_rationale']='Synthetic program purpose does not support the proposed activity; eligibility remains unknown'
            return response
    review=make_review(count=1)
    result=run_research(review,factory(),NotSuitable(),evidence_client=Evidence(),budget=ResearchBudget(1,2,5))
    row=result['records']['910001']
    assert row['shared_result']['should_apply']=='reject'
    assert row['classification']!='ACTIONABLE' and row['classification']!='CONFIRMED_EXCLUSION'
    assert row['shared_result']['can_apply']=='needs_review'


def test_actionability_requires_reviewed_gates_and_complete_evidence():
    from research_foundation.hard_gates import REQUIRED_GATES
    class Supported(Provider):
        def complete(self,packet,stage,analysis=None):
            response=super().complete(packet,stage,analysis)
            if stage==1:
                for d in response['value']['dimensions']:
                    if d['dimension']!='B':d['assessment']='supported'
                response['value']['missing_documents_or_requirements']=[]
            else:
                response['value'].update(can_apply='direct_route_supported_subject_to_notice',should_apply='pursue',
                    application_viability='ACTIONABLE',can_act_in_time='potentially_in_time',material_conditions=[],
                    next_actions=['Submit the reviewed compliant application'])
            return response
    review=build_project_review(GRANTS[1:2],'NC tech agency','Broadband',budget=1)
    source=Source('reviewed','https://example.gov/reviewed','All synthetic fixture requirements have been verified for this applicant and project.','fixture-v1','2026-11-07',True)
    findings=[Finding(g,State.PASS,'Synthetic rule verified condition',(Citation('reviewed',source.text,'Synthetic verified conditions'),),
        'synthetic-rule-v1',True,True) for g in REQUIRED_GATES]
    checked={'910002':{'findings':findings,'sources':[source],
        'coverage':{'primary_notice_ingested':True,'amendments_verified':True,'gaps':[]}}}
    result=run_research(review,factory('NC tech agency','Broadband'),Supported(),evidence_client=Evidence(),
        budget=ResearchBudget(1,2,5),reviewed_gates=checked)
    assert result['records']['910002']['classification']=='ACTIONABLE'
    unreviewed=run_research(review,factory('NC tech agency','Broadband'),Supported(),evidence_client=Evidence(),budget=ResearchBudget(1,2,5))
    assert unreviewed['records']['910002']['state']=='RESEARCH_FAILED'


def test_user_context_is_citable_but_cannot_prove_official_eligibility():
    from services.research_engine import make_packet
    from research_foundation import protocol
    request=factory()(GRANTS[0]);packet=make_packet(request,Evidence().fetch('910001'))
    analysis=Provider().complete(packet,1)['value']
    claim={'statement':'The user proposes water restoration','kind':'confirmed_fact','source_id':'user-project-context','quote':request.project_description}
    analysis['dimensions'][0]['claims']=[claim]
    protocol.validate_analysis(analysis,packet)
    analysis['dimensions'][3]['claims']=[claim]
    with pytest.raises(ValueError,match='source evidence'):
        protocol.validate_analysis(analysis,packet)


def test_research_cache_preserves_old_candidates_and_version_audit(tmp_path):
    store=ResearchStore(tmp_path/'research');scope='a'*64
    store.save(scope,{'one':{'input_key':'v1','protocol_hash':'p','state':'RESEARCHED_AND_VALIDATED','candidate':{'id':'one'}},
                      'two':{'input_key':'other','protocol_hash':'p','state':'RESEARCH_FAILED','candidate':{'id':'two'}}})
    store.save(scope,{'one':{'input_key':'v2','protocol_hash':'p','state':'RESEARCHED_AND_VALIDATED','candidate':{'id':'one'}}})
    cached=store.load(scope)
    assert set(cached)=={'one','two'}
    assert cached['one']['prior_versions'][0]['input_key']=='v1'


def test_missing_official_identity_is_retained_instead_of_silently_discarded():
    review=build_project_review([{'title':'Unresolved official listing','number':'SYNTHETIC-NOTICE'}],
                              'NC local agency','Public health',budget=1)
    assert review['candidate_count']==1
    row=review['queue']['pool'][0]
    assert row['identity'][1].startswith('unresolved-')
    assert row['records'][0]['original_record']['number']=='SYNTHETIC-NOTICE'
    assert row['decision']['state']=='INSUFFICIENT_EVIDENCE'


def test_verified_agency_goals_cannot_be_substituted_with_grant_topic_quotes():
    from services.research_engine import make_packet
    from research_foundation.contract import VerifiedGoal
    from research_foundation import protocol
    goal_source=Source('agency-plan','https://example.gov/plan','Improve rural water quality.','fixture-v1','2026-11-07',True)
    goal=VerifiedGoal('g','Improve rural water quality.','agency-plan',goal_source.text,'p1','synthetic-reviewed-source')
    req=request_for_candidate('NC water agency','Water restoration',GRANTS[0],profile={'verified_goals':[goal],'goal_sources':[goal_source]})
    packet=make_packet(req,Evidence().fetch('910001'));value=Provider().complete(packet,1)['value']
    value['dimensions'][1].update(assessment='supported',claims=[value['dimensions'][2]['claims'][0]])
    with pytest.raises(ValueError,match='agency goal source'):protocol.validate_analysis(value,packet)
    value['dimensions'][1]['claims']=[{'statement':'Agency has a water-quality goal','kind':'confirmed_fact','source_id':'agency-plan','quote':goal_source.text}]
    protocol.validate_analysis(value,packet)


def test_interrupted_request_is_persisted_and_not_silently_repeated(tmp_path):
    class SimulatedCrash(BaseException):pass
    class CrashingProvider:
        def complete(self,*args):raise SimulatedCrash()
    review=build_project_review(GRANTS[:1],'NC water agency','water',budget=1);req=factory('NC water agency','water')
    store=ResearchStore(tmp_path/'research');scope=context_key(req(GRANTS[0]))
    with pytest.raises(SimulatedCrash):
        run_research(review,req,CrashingProvider(),evidence_client=Evidence(),budget=ResearchBudget(1,2,5),
                     on_update=lambda records:store.save(scope,records))
    prior=store.load(scope)
    assert prior['910001']['inflight_stage']==1
    provider=Provider()
    next_run=run_research(review,req,provider,evidence_client=Evidence(),previous=prior,budget=ResearchBudget(1,2,5))
    assert next_run['aborted'] and not provider.calls
