"""Staff-facing one-click Search; operational controls stay in server configuration."""
import json,os
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from services.agency_directory import AGENCIES
from services.discovery import diversified_retrieval_queries,AIRecommendationCache
from services.grants_api import get_grants,get_grant_details
from services.grant_store import LocalGrantStore
from services.search_foundation import discover_project
from services.search_workflow import shortlist_review,rank_results,display_category,opportunity_timing,qualified_records,run_adaptive_research,record_timing
from services.research_engine import (ResearchStore,ResearchBudget,run_research,initial_records,
    request_for_candidate,context_key,protocol_hash,configured_provider)
from modules.search_research import save_research_record


def render_card(record,agency,project,store,scope):
    grant=record['candidate'];oid=record['opportunity_id'];category=display_category(record)
    timing=record_timing(record)
    result=record.get('shared_result');decision=record.get('decision')
    with st.container(border=True):
        st.subheader(grant.get('title') or 'Untitled opportunity')
        st.write('**'+category+'**')
        st.caption(str(grant.get('agencyName') or grant.get('agencyCode') or 'Federal agency not supplied'))
        money=record.get('evidence',{}).get('financials') or record.get('official_summary') or {}
        from services.grants_api import _amount
        floor,ceiling=_amount(money.get('award_floor')),_amount(money.get('award_ceiling'))
        st.caption('Official award range: '+(f'${floor:,.0f}' if isinstance(floor,(float,int)) else 'floor unavailable')+' – '+(f'${ceiling:,.0f}' if isinstance(ceiling,(float,int)) else 'ceiling unavailable'))
        st.caption(f"Opportunity {oid} · {timing['status']} · Listed deadline: {timing['close_date'] or 'Not supplied'}")
        if record.get('funding_note'):st.caption(record['funding_note'])
        if result:
            apply={'needs_review':'Applicant route needs verification','direct_route_excluded':'The reviewed direct route is excluded',
                   'direct_route_supported_subject_to_notice':'Applicant route supported, subject to the current notice'}
            should={'pursue':'Promising for further application preparation','conditional_lead':'Conditional lead — verify the requirements below',
                    'reject':'Not suitable for this project','insufficient_evidence':'Insufficient evidence for an application decision'}
            applicant_assessment=next(d['assessment'] for d in record['analysis']['dimensions'] if d['dimension']=='D')
            apply_text=('Official applicant restrictions conflict with the proposed direct route. An alternate funded role is not confirmed.'
                        if applicant_assessment=='conflicting' else apply[result['can_apply']])
            st.write('**Can we apply?** '+apply_text)
            st.write('**Should we apply?** '+should[result['should_apply']])
            st.write('**Can we act in time?** '+timing['readiness'])
            from services.preparation_time import preparation_estimate
            prep=preparation_estimate(record)
            st.write('**Application Effort:** '+prep['summary'])
            st.caption('Confidence: '+prep['confidence']+' · '+(prep['timing'] if prep['available'] else prep['reason']))
            if prep.get('evidence'):
                st.caption('Evidence-backed requirements: '+', '.join(
                    dict.fromkeys(item.get('key', 'official requirement') for item in prep['evidence'])
                ))
            else:
                st.caption('Missing information: verified full-notice requirements were not sufficient for an effort estimate.')
            if prep['available']:
                st.caption('Assumes dedicated staff, parallel drafting/budget work and timely external responses. Not a guaranteed timeline.')
            score=decision['project_activity_score']
            st.caption('Project relevance: '+(str(score)+'/100' if score is not None else 'Not assessed')+
                       ' · Strategic relevance: '+(str(decision['strategic_score'])+'/100' if decision['strategic_score'] is not None else 'Unavailable'))
            st.write(decision['decision_rationale'].split('. ')[0]+'.')
            concerns=decision.get('material_conditions',[])
            if concerns:st.write('**Key concern:** '+concerns[0])
            if result['next_actions']:st.write('**Next action:** '+result['next_actions'][0])
            st.caption('AI research with source checks; eligibility and claim meaning still require human review. '+
                       ('Previously researched result. ' if record.get('cache_reused') else '')+str(record.get('researched_at','')))
        else:
            st.write('**Can we apply?** '+('Confirmed restriction on the reviewed route.' if record.get('classification')=='CONFIRMED_EXCLUSION' else 'Not yet verified; unknown does not mean ineligible.'))
            st.write('**Should we apply?** Preliminary discovery only; funding-purpose fit has not been fully researched.')
            st.write('**Can we act in time?** '+timing['readiness'])
            if record.get('reason'):st.warning(record['reason'])
            st.write('**Next action:** Check the official notice for applicant routes, allowable activities, match and intermediate deadlines.')
        with st.expander('Official evidence, uncertainties and research details'):
            if result:
                st.write('**Preparation estimate assumptions**')
                for assumption in prep.get('assumptions',[]):st.caption(assumption)
                if prep.get('controlling_deadline'):st.caption('Earliest required deadline used: '+prep['controlling_deadline'])
                for claim in prep.get('evidence',[]):
                    st.text(claim['quote'])
                    source=next((s for s in record['evidence']['sources'] if s['source_id']==claim['source_id']),None)
                    if source:st.link_button('Preparation requirement source',source['url'])
                for condition in result['unresolved_requirements']:st.text(condition)
                sources={s['source_id']:s for s in record.get('source_documents',record['evidence']['sources'])}
                for dimension in record['analysis']['dimensions']:
                    st.write({'A':'Project activities','B':'Verified agency strategy','C':'Funding purpose',
                              'D':'Applicant and partnership route','E':'Timing, match and readiness','F':'Evidence and next steps'}[dimension['dimension']])
                    st.write(dimension['rationale'])
                    for index,claim in enumerate(dimension['claims'],1):
                        st.text(dimension['dimension']+'-'+str(index)+': '+claim['statement'])
                        if claim['source_id']:
                            st.text(claim['quote']);source=sources.get(claim['source_id'])
                            if source and source.get('url'):st.link_button('Official source — '+claim['source_id'],source['url'])
                for index,claim in enumerate(record['analysis']['counterevidence'],1):
                    st.text('COUNTER-'+str(index)+': '+claim['statement'])
                    if claim['source_id']:
                        st.text(claim['quote']);source=sources.get(claim['source_id'])
                        if source and source.get('url'):st.link_button('Counterevidence source — '+claim['source_id'],source['url'])
                for index,claim in enumerate(decision['decision_claims'],1):
                    st.text('Additional decision evidence '+str(index)+': '+claim['statement'])
                    if claim['source_id']:
                        st.text(claim['quote']);source=sources.get(claim['source_id'])
                        if source and source.get('url'):st.link_button('Decision source — '+claim['source_id'],source['url'])
            for gap in record.get('evidence',{}).get('coverage',{}).get('gaps',[]):st.caption(gap)
        if oid.isdecimal():st.link_button('View official opportunity',f'https://www.grants.gov/search-results-detail/{oid}')
        if st.button('Save to My Grants',key='workflow_save_'+scope+'_'+oid,disabled=not oid.isdecimal()):
            save_research_record(store,agency,oid,{'title':grant.get('title'),'close_date':timing['close_date'],
                'official_url':f'https://www.grants.gov/search-results-detail/{oid}','project_description':project,
                'viability_state':record.get('classification','INSUFFICIENT_EVIDENCE'),'research_depth':record.get('research_depth','preliminary'),
                'notes':category+'. Original project: '+project+'. '+('; '.join(result['next_actions']) if result else 'Verify official eligibility, purpose and timing.')})
            st.success('Saved with project context and next actions.')


def show_one_click_search():
    st.header('Find Federal Funding');st.caption('Find fewer grants. Find the right grants. Act sooner.')
    agency=st.selectbox('NC agency',AGENCIES,key='search_agency',accept_new_options=True)
    project=st.text_area('What project are you trying to fund?',key='search_project',placeholder='Describe the activities, beneficiaries, location and intended outcomes.').strip()
    amount=st.number_input('Funding needed (USD)',min_value=0.,value=None,key='search_funding')
    today=datetime.now(ZoneInfo('America/New_York')).date()
    threshold=st.date_input('Application deadline on or after',value=today,key='search_earliest_date')
    submit=st.button('Find Matching Grants',type='primary',key='search_submit')
    profile={'applicant_identity':agency,'applicant_category':'NC state government agency (user-selected)',
        'geography':['North Carolina'],'funding_needed_usd':amount,
        'earliest_closing_date':threshold.isoformat() if threshold else None}
    if not project:return
    factory=lambda grant:request_for_candidate(agency,project,grant,profile=profile)
    scope=context_key(factory({'id':'scope','title':'scope'}));statekey='workflow_'+scope
    cache=ResearchStore(os.environ.get('GRANTSCOPE_RESEARCH_CACHE','.grantscope/research_v1'))
    if submit:
        import re
        if len(re.findall(r'[A-Za-z]+',project))<8:
            st.info('Please add what activities need funding, who benefits, where the work happens and the outcome you want. A few sentences are enough.');return
        progress=st.empty()
        try:
            progress.info('Discovering opportunities and checking official summaries…')
            queries=diversified_retrieval_queries({},project)
            try:seeds=get_grants(queries[0] if queries else project,100)
            except Exception:seeds=[]
            discovery=discover_project(agency,project,seeds,get_grants)
            st.session_state[statekey]={'grants':discovery['grants'],'errors':discovery['retrieval_errors']}
            try:prior=cache.load(scope)
            except (ValueError,OSError):prior={}
            def persist(records):
                st.session_state[statekey]['records']=records;cache.save(scope,records)
                finished=sum(r.get('state') in {'RESEARCHED_AND_VALIDATED','RESEARCH_FAILED'} for r in records.values())
                progress.info(f'Checking official requirements: {finished} research records finished. Unsuitable or unavailable leads are replaced as coverage continues…')
            provider=configured_provider(st.secrets)
            from services.research_priority import batch_prioritize
            run=run_adaptive_research(discovery['grants'],agency,project,provider,profile=profile,previous=prior,
                fetch_details=get_grant_details,on_update=persist,triage=lambda items:batch_prioritize(provider,items),
                max_candidates=max(4,min(30,int(os.environ.get('GRANTSCOPE_MAX_RESEARCH','12')))),
                max_calls=max(4,min(60,int(os.environ.get('GRANTSCOPE_MAX_CALLS','24')))),
                max_usd=max(5.,min(60.,float(os.environ.get('GRANTSCOPE_MAX_USD','18')))),
                summary_limit=max(12,min(80,int(os.environ.get('GRANTSCOPE_SUMMARY_LIMIT','48')))))
            st.session_state[statekey].update(run)
            if run['aborted']:st.warning('Official research stopped because the provider could not continue safely. Completed findings are retained; no automatic retry was made.')
        except Exception as exc:
            st.session_state.setdefault(statekey,{})['operational_error']=type(exc).__name__
            st.warning('Official research could not finish safely. Completed findings are retained; no automatic retry was made.')
        finally:progress.empty()
    saved=st.session_state.get(statekey)
    if not saved:return
    records=saved.get('records',{});review=saved.get('review')
    if not review:return
    useful=qualified_records(records,review,profile['earliest_closing_date'])
    st.subheader(f'{min(5,len(useful))} qualified opportunities' if useful else 'No suitable opportunities verified yet.')
    coverage=saved.get('coverage',{})
    checked=coverage.get('summaries_checked',0);attempts=len(coverage.get('attempted_ids',[]))
    st.caption(f'Official summaries checked: {checked}. Full-notice research paths reviewed: {attempts}. Discovery is bounded and is not an exhaustive funding inventory.')
    if not useful:
        if saved.get('aborted') or saved.get('operational_error'):st.info('Research was interrupted by an operational problem. This is not a no-match conclusion.')
        elif coverage.get('incomplete') or coverage.get('pending'):st.info('Research coverage is incomplete. Unexamined or unresolved opportunities remain; this is not a confirmed no-match conclusion.')
        else:st.info('The evaluated opportunity pool did not support a suitable current match for this project.')
    store=LocalGrantStore()
    for record in useful[:5]:render_card(record,agency,project,store,scope)
    with st.expander('Research coverage and other leads'):
        st.write('Some leads are preliminary, unsuitable, expired, or could not be fully researched. They are preserved for audit, not presented as recommendations.')
        st.caption(coverage.get('stop_reason','Research did not finish'))
        st.download_button('Download research audit',json.dumps({'records':records,'coverage':coverage},ensure_ascii=False,default=str),file_name='grantscope-research-audit.json',mime='application/json')
        st.dataframe([{'Opportunity':oid,'Title':r['candidate'].get('title'),'Review outcome':display_category(r),
                       'Official closing date':record_timing(r)['close_date'],
                       'Listed status':record_timing(r)['status'],
                       'Timing concern':'Posted listing conflicts with an expired closing date; extension not verified' if record_timing(r)['contradiction'] else ''} for oid,r in records.items()],hide_index=True)
