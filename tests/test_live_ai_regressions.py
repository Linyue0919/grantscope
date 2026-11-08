"""Regressions demonstrated by live acceptance; fixtures here are synthetic."""
import json
from unittest.mock import Mock
from services.ai_eligibility import validate_eligibility_response
from services.research_engine import AzureSolProvider


def test_complete_short_official_category_is_evidence_but_fragments_are_not():
    details={'applicant_types':[{'description':'State governments'}],'eligibility_text':''}
    raw={'verdict':'likely_eligible','reasoning':'The listed applicant category covers state agencies; verify notice conditions.',
         'quote':"'State governments'",'to_verify':['Check full notice'],'listed_applicant_categories':['State governments']}
    accepted,errors=validate_eligibility_response(json.dumps(raw),details)
    assert not errors and accepted['quote']=='State governments'
    for bad in ['governments','State','', 'County governments']:
        rejected,errors=validate_eligibility_response(json.dumps(dict(raw,quote=bad)),details)
        assert rejected is None and errors


def test_large_decision_packet_uses_recorded_tokens_without_truncation_or_retry():
    packet={'documents':[{'source_id':'synthetic','text':'x'*145000}]}
    analysis={'project_activity_understanding':'y'*30000,'dimensions':[], 'counterevidence':[]}
    session=Mock();response=Mock(status_code=429,text='Rate limited',headers={})
    response.json.return_value={'error':{'code':'RateLimit'}};session.post.return_value=response
    provider=AzureSolProvider({'AZURE_OPENAI_ENDPOINT':'https://example.openai.azure.com','AZURE_OPENAI_API_KEY':'synthetic'},session=session)
    blocked=provider.complete(packet,2,analysis)
    assert 'Input exceeds' in blocked['error']
    session.post.assert_not_called()
    provider.remember_prompt_usage(packet,40000)
    result=provider.complete(packet,2,analysis)
    assert result['request_sent'] and result['http_status']==429 and result['fatal']
    assert result['input_token_upper_bound']<175000
    assert session.post.call_count==1
    sent=json.loads(session.post.call_args.kwargs['json']['messages'][1]['content'])
    assert sent['original_evidence_packet']==packet and sent['own_validated_analysis']==analysis


def test_untrusted_or_other_packet_usage_cannot_relax_guard():
    provider=AzureSolProvider({'AZURE_OPENAI_ENDPOINT':'https://example.openai.azure.com','AZURE_OPENAI_API_KEY':'synthetic'},session=Mock())
    packet={'documents':[{'text':'x'*180000}]}
    for invalid in [None,-1,0,200000,'40000']:
        provider.remember_prompt_usage(packet,invalid)
    provider.remember_prompt_usage({'different':True},40000)
    result=provider.complete(packet,2,{'dimensions':[],'counterevidence':[]})
    assert 'Input exceeds' in result['error']
    provider.session.post.assert_not_called()


def test_others_does_not_override_explicit_mandatory_tribal_applicant():
    from services.eligibility_assessment import assess_eligibility
    types=[{'id':'25','description':'Others (see additional eligibility)'},{'id':'07','description':'Native American tribal governments (Federally recognized)'}]
    notes='To be considered for this program, applicants will meet all the following eligibility requirements:The tribe must be one of the following federally recognized tribes, designated Colorado River Basin tribes: Example Tribe.'
    profile={'applicant_categories':['State governments']}
    excluded=assess_eligibility({'applicant_types':types,'eligibility_text':notes},profile)
    assert excluded['status']=='ineligible' and excluded['certainty']=='confirmed'
    assert excluded['quote'] in notes
    uncertain=assess_eligibility({'applicant_types':types,'eligibility_text':'Tribal communities may benefit; partners may include state agencies.'},profile)
    assert uncertain['status']!='ineligible'


def test_official_applicant_category_order_does_not_change_evidence():
    from services.official_evidence import OfficialEvidenceClient
    session=Mock();response=Mock();response.raise_for_status.return_value=None
    types=[{'id':'00','description':'State governments'},{'id':'01','description':'County governments'}]
    # Mirror the actual fetchOpportunity envelope, without private data.
    response.json.side_effect=[{'data':{'ost':'POSTED','synopsis':{'synopsisDesc':'Synthetic notice','applicantTypes':types}}},
                               {'data':{'ost':'POSTED','synopsis':{'synopsisDesc':'Synthetic notice','applicantTypes':list(reversed(types))}}}]
    session.post.return_value=response
    client=OfficialEvidenceClient(session=session)
    first=client.fetch('910001');second=client.fetch('910001')
    assert first['sources'][0]['text']==second['sources'][0]['text']
    assert 'State governments' in first['sources'][0]['text']


def test_cannot_determine_scope_is_uncertainty_not_a_permission_assertion():
    from research_foundation.citations import citation_checks
    quote='Proposed costs are allowable, allocable, and necessary.'
    packet={'documents':[{'source_id':'official','text':quote}]}
    claim={'statement':'Only allowable, allocable and necessary costs can be funded; the packet cannot determine how much of the broader project would qualify.',
           'kind':'reasoned_inference','source_id':'official','quote':quote}
    value={'dimensions':[],'counterevidence':[claim]}
    assert citation_checks(value,packet)[0]['passed']
    claim['statement']='The agency is eligible; the packet cannot determine its budget.'
    assert citation_checks(value,packet)[0]['category']=='unsupported_material_assertion'
    claim['statement']='These costs are allowable and the project qualifies.'
    assert not citation_checks(value,packet)[0]['passed']
    claim['statement']='The packet cannot determine whether these costs qualify.'
    claim['source_id']='wrong-source'
    assert citation_checks(value,packet)[0]['category']=='unknown_source_id'


def test_validated_zero_ai_fit_stays_reviewable_outside_priority():
    from datetime import date
    from services.match_engine import evaluate_grant,MatchSettings
    from services.agency_profiles import get_agency_profile
    from tests.test_match_engine import details
    profile=get_agency_profile('Department of Environmental Quality')
    hit={'id':'910001','title':'Water quality restoration','oppStatus':'posted','closeDate':'12/01/2027'}
    record=evaluate_grant(hit,profile,details(desc='Water quality restoration and environmental protection.'),
        MatchSettings(min_days_left=None),date(2026,11,7),ai_result={'status':'ok','score':0,'goal_ids':[],'evidence':[]})
    assert record['relevance']['keyword']['score']>0
    assert record['section']=='low_evidence' and record['id']=='910001'


def test_negative_allowability_counterevidence_is_not_an_affirmative_permission():
    from research_foundation.citations import citation_checks
    quote='The opportunities are for lands protected through easements.'
    packet={'documents':[{'source_id':'official','text':quote}]}
    claim={'statement':'The easement-land limitation is material counterevidence against treating the general rural-watershed concept as established allowable work.',
           'kind':'reasoned_inference','source_id':'official','quote':quote}
    value={'dimensions':[],'counterevidence':[claim]}
    assert citation_checks(value,packet)[0]['passed']
    for assertion in ['Equipment purchases are allowable.', 'The applicant qualifies.', 'These activities will be permitted.', 'The agency can apply.']:
        claim['statement']=assertion
        assert not citation_checks(value,packet)[0]['passed']
