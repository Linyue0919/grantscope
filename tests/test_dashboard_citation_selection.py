"""Exact-source selection regressions; no live model calls."""
import json
from services.ai_matching import excerpt_catalog, validate_response, source_selection_input
from services.ai_eligibility import eligibility_quote_options,validate_eligibility_response

SOURCES=[{'id':'D','kind':'grant','label':'Official synopsis','text':'Funds water monitoring and stream restoration projects in eligible communities.'},
 {'id':'goal','kind':'goal','label':'Verified goal','text':'Protect public health by setting and implementing science-based standards and by providing technical assistance to communities.'}]
def reply():
 catalog=excerpt_catalog(SOURCES)
 return {'relevance':75,'goal_ids':['goal'],'evidence':[{'source_id':sid,'excerpt_id':next(k for k,v in catalog.items() if v['source_id']==sid)} for sid in ['D','goal']], 'explanation':'Monitoring supports the verified environmental protection goal.'}

def test_selected_quotes_are_original_source_spans_not_model_rewrites():
 result,errors=validate_response(json.dumps(reply()),SOURCES)
 assert not errors and result['score']==75
 for evidence in result['evidence']:
  source=next(s for s in SOURCES if s['id']==evidence['source_id'])
  assert evidence['quote'] in source['text']


def test_actual_period_insertion_failure_is_still_rejected():
 data=reply();data['evidence']=[{'source_id':'goal','quote':'Protect public health by setting and implementing science-based standards.'},{'source_id':'D','quote':SOURCES[0]['text']}]
 result,errors=validate_response(json.dumps(data),SOURCES)
 assert result is None and any('Quote not found' in e for e in errors)


def test_wrong_source_unknown_excerpt_and_quote_override_fail_closed():
 for change in ['wrong-source','unknown','override']:
  data=reply()
  if change=='wrong-source':data['evidence'][0]['source_id']='goal'
  elif change=='unknown':data['evidence'][0]['excerpt_id']='D:invented'
  else:data['evidence'][0]['quote']='Invented permission to buy equipment.'
  assert validate_response(json.dumps(data),SOURCES)[0] is None


def test_selected_goal_needs_its_own_evidence_and_description_needed():
 data=reply();data['evidence']=data['evidence'][:1]
 assert validate_response(json.dumps(data),SOURCES)[0] is None
 data=reply();data['evidence']=data['evidence'][1:]
 assert validate_response(json.dumps(data),SOURCES)[0] is None


def test_truncated_input_is_disclosed_and_outside_text_cannot_be_selected():
 sources=[dict(SOURCES[0],text='x '*2500),SOURCES[1]]
 payload=json.loads(source_selection_input(sources,8000))
 assert payload['description_truncated'] and payload['sources']==sources
 assert all(e['quote'] in next(s['text'] for s in sources if s['id']==e['source_id']) for e in payload['excerpt_catalog'].values())


def test_eligibility_category_punctuation_is_preserved_and_cannot_be_overridden():
 details={'applicant_types':[{'id':'25','description':'Others (see "Additional Information" for clarification)'},{'id':'00','description':'State governments'}],'eligibility_text':'Additional conditions require program review.'}
 options=eligibility_quote_options(details)
 for key,option in options.items():
  data={'verdict':'uncertain','reasoning':'Confirm the notice requirements before applying.','quote_id':key}
  result,errors=validate_eligibility_response(json.dumps(data),details)
  assert not errors and result['quote']==option['quote']
  data['quote']='Unsupported extra authorization.'
  assert validate_eligibility_response(json.dumps(data),details)[0] is None
 data={'verdict':'uncertain','reasoning':'Unresolved','quote_id':'invented'}
 assert validate_eligibility_response(json.dumps(data),details)[0] is None


def test_paired_contract_cannot_claim_a_goal_without_its_own_excerpt():
 catalog=excerpt_catalog(SOURCES)
 data={'relevance':75,'grant_excerpt_id':next(k for k,v in catalog.items() if v['source_id']=='D'),
       'goals':[{'goal_id':'goal','excerpt_id':next(k for k,v in catalog.items() if v['source_id']=='goal')}], 'explanation':'Strategic alignment supported by the selected activity and goal.'}
 result,errors=validate_response(json.dumps(data),SOURCES)
 assert not errors and result['goal_ids']==['goal']
 data['goals'][0]['excerpt_id']=data['grant_excerpt_id']
 assert validate_response(json.dumps(data),SOURCES)[0] is None


def test_paired_contract_rejects_extra_goal_and_invented_quote_fields():
 data={'relevance':75,'grant_excerpt_id':'D:1','goals':[{'goal_id':'goal','excerpt_id':'goal:1'}], 'explanation':'Supported'}
 data['goal_ids']=['uncited-goal']
 assert validate_response(json.dumps(data),SOURCES)[0] is None
 del data['goal_ids'];data['quote']='Invented quotation'
 assert validate_response(json.dumps(data),SOURCES)[0] is None
