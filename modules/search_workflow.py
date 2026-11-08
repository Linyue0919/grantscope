"""Staff-facing one-click Search; operational controls stay in server configuration."""
import json,os
import streamlit as st
from services.agency_directory import AGENCIES
from services.discovery import diversified_retrieval_queries,AIRecommendationCache
from services.grants_api import get_grants,get_grant_details
from services.grant_store import LocalGrantStore
from services.search_foundation import discover_project
from services.search_workflow import shortlist_review,rank_results,display_category,opportunity_timing
from services.research_engine import (ResearchStore,ResearchBudget,run_research,initial_records,
    request_for_candidate,context_key,protocol_hash,configured_provider)
from modules.search_research import save_research_record


def render_card(record,agency,project,store,scope):
    grant=record['candidate'];oid=record['opportunity_id'];category=display_category(record)
    timing=opportunity_timing(grant,record.get('evidence'))
    result=record.get('shared_result');decision=record.get('decision')
    with st.container(border=True):
        st.subheader(grant.get('title') or 'Untitled opportunity')
        st.write('**'+category+'**')
        st.caption(f"Opportunity {oid} · {timing['status']} · Listed deadline: {timing['close_date'] or 'Not supplied'}")
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
            score=decision['project_activity_score']
            st.caption('Project relevance: '+(str(score)+'/100' if score is not None else 'Not assessed')+
                       ' · Strategic relevance: '+(str(decision['strategic_score'])+'/100' if decision['strategic_score'] is not None else 'Unavailable'))
            st.write(decision['decision_rationale'])
            for action in result['next_actions'][:4]:st.write('• '+action)
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
            st.json({'state':record['state'],'coverage':record.get('evidence',{}).get('coverage'),
                     'selection_reason':record.get('selection_reason'),'researched_at':record.get('researched_at'),
                     'reason':record.get('reason')})
        if oid.isdecimal():st.link_button('View official opportunity',f'https://www.grants.gov/search-results-detail/{oid}')
        if st.button('Save to My Grants',key='workflow_save_'+scope+'_'+oid,disabled=not oid.isdecimal()):
            save_research_record(store,agency,oid,{'title':grant.get('title'),'close_date':timing['close_date'],
                'official_url':f'https://www.grants.gov/search-results-detail/{oid}','project_description':project,
                'viability_state':record.get('classification','INSUFFICIENT_EVIDENCE'),'research_depth':record.get('research_depth','preliminary'),
                'notes':category+'. Original project: '+project+'. '+('; '.join(result['next_actions']) if result else 'Verify official eligibility, purpose and timing.')})
            st.success('Saved with project context and next actions.')


def show_one_click_search():
    st.header('Find Federal Funding');st.caption('Find fewer grants. Find the right grants. Act sooner.')
    agency=st.selectbox('NC agency',AGENCIES+['Other NC agency'],key='search_agency')
    if agency=='Other NC agency':agency=st.text_input('Agency name',key='search_custom_agency').strip()
    project=st.text_area('What project are you trying to fund?',key='search_project',placeholder='Describe the work, people served and intended outcomes.').strip()
    with st.expander('Applicant and geography (optional)'):
        applicant=st.text_input('Applicant / lead organization',key='search_applicant_identity')
        geography=st.text_input('Project geography',value='North Carolina',key='search_geography')
    profile={'applicant_identity':applicant or agency,'geography':[geography] if geography else []}
    submit=st.button('Find Matching Grants',type='primary',key='search_submit')
    if not agency or not project:
        if submit:st.warning('Select an agency and describe the project.')
        return
    factory=lambda grant:request_for_candidate(agency,project,grant,profile=profile)
    scope=context_key(factory({'id':'scope','title':'scope'}));statekey='workflow_'+scope
    cache=ResearchStore(os.environ.get('GRANTSCOPE_RESEARCH_CACHE','.grantscope/research_v1'))
    if submit:
        progress=st.empty()
        try:
            progress.info('Finding opportunities across several project search terms…')
            queries=diversified_retrieval_queries({},project)
            seeds=get_grants(queries[0] if queries else project,100)
            discovery=discover_project(agency,project,seeds,get_grants)
            grants=discovery['grants']
            # Snapshot the exact original request. Changing a widget never authorizes another call.
            st.session_state[statekey]={'grants':grants,'errors':discovery['retrieval_errors']}
            st.session_state['workflow_last_scope']=scope
            try:prior=cache.load(scope)
            except (ValueError,OSError):prior={}
            limit=max(1,min(3,int(os.environ.get('GRANTSCOPE_INITIAL_SHORTLIST','2'))))
            try:old=AIRecommendationCache().get(agency,project) or {}
            except Exception:old={}
            review=shortlist_review(grants,agency,project,old.get('records',()),limit,profile,fetch_details=get_grant_details)
            records=initial_records(review)
            for oid,old_record in prior.items():
                if oid in records and old_record.get('context_key')==scope and old_record.get('protocol_hash')==protocol_hash():
                    records[oid]={**old_record,'cache_reused':True}
            st.session_state[statekey].update(review=review,records=records)
            def persist(value):
                st.session_state[statekey]['records']=value
                cache.save(scope,value)
                selected_ids={r['identity'][1] for r in review['queue']['selected']}
                complete=sum(r.get('state') in {'RESEARCHED_AND_VALIDATED','RESEARCH_FAILED'} for oid,r in value.items() if oid in selected_ids)
                progress.info(f'Reading official documents and checking funding requirements: {complete} of {len(review["queue"]["selected"])} shortlist records finished. Other candidates are retained.')
            progress.info('Researching the initial shortlist from official documents…')
            provider=configured_provider(st.secrets)
            run=run_research(review,factory,provider,budget=ResearchBudget(limit,limit*2,min(4.,limit*1.21)),previous=prior,on_update=persist)
            st.session_state[statekey].update(records=run['records'],run=run)
            if run['aborted']:st.warning('Research stopped safely: '+run['aborted']+'. No automatic retry was made.')
        except Exception as exc:
            # Never render exception bodies that might contain request headers/config.
            if statekey in st.session_state:st.session_state[statekey]['operational_error']=type(exc).__name__
            st.warning('Research could not finish safely. Available candidates and partial results remain below. No automatic retry was made.')
        finally:progress.empty()
    saved=st.session_state.get(statekey)
    if not saved:
        st.caption('Click Find Matching Grants to discover and research a bounded initial shortlist.');return
    if not saved.get('review'):return
    for error in saved.get('errors',[]):st.warning(error)
    review=saved['review'];records=saved.get('records') or initial_records(review)
    ranked=rank_results(records,review)
    completed=sum(r.get('state')=='RESEARCHED_AND_VALIDATED' for r in ranked)
    st.write(f'**{len(ranked)} opportunities found · {completed} researched with validated sources**')
    failed=sum(r.get('state')=='RESEARCH_FAILED' for r in ranked)
    if failed:st.caption(f'{failed} research records are incomplete or failed; the remaining opportunities are still preliminary, not negative eligibility findings.')
    st.caption('Search covers up to eight diversified API queries, 25 results each, plus up to 100 seed results. It is not an exhaustive federal funding inventory. Strategic fit is unavailable without verified agency goals.')
    store=LocalGrantStore()
    visible=ranked[:5]
    for record in visible:render_card(record,agency,project,store,scope)
    with st.expander('All Opportunities — including preliminary, incomplete and unsuitable leads'):
        st.download_button('Download research audit',json.dumps(records,ensure_ascii=False,default=str),file_name='grantscope-research-audit.json',mime='application/json')
        pages=max(1,(max(0,len(ranked)-5)+9)//10)
        page=int(st.number_input('More opportunities page',min_value=1,max_value=pages,value=1,key='workflow_page_'+scope))
        for record in ranked[5+(page-1)*10:5+page*10]:render_card(record,agency,project,store,scope)
