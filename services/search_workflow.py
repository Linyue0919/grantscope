"""Bounded project workflow and user ranking, independent of Streamlit."""
from datetime import datetime
from zoneinfo import ZoneInfo
from services.search_foundation import build_project_review
from services.research_engine import ResearchState


def opportunity_timing(candidate, evidence=None):
    raw=(evidence or {}).get('status') or candidate.get('oppStatus') or candidate.get('status') or ''
    status=str(raw).upper()
    names={'POSTED':'Posted','FORECASTED':'Forecasted','CLOSED':'Closed','ARCHIVED':'Archived'}
    label=names.get(status,'Status unavailable')
    date=candidate.get('closeDate') or candidate.get('close_date')
    # Prefer refreshed official detail over discovery when provided.
    date=(evidence or {}).get('close_date') or date
    closing=None
    for fmt in ('%m/%d/%Y','%Y-%m-%d','%m-%d-%Y'):
        try:closing=datetime.strptime(str(date)[:10],fmt).date();break
        except ValueError:pass
    past=closing is not None and closing<datetime.now(ZoneInfo('America/New_York')).date()
    readiness=('Not accepting applications' if status in {'CLOSED','ARCHIVED'} or past else
               'Forecast — not currently open' if status=='FORECASTED' else
               'Posted; verify notice and preparation requirements' if status=='POSTED' else 'Current availability needs verification')
    return {'status':label,'close_date':closing.isoformat() if closing else date,'past':past,'readiness':readiness,
            'accepting_possible':status=='POSTED' and not past}


def shortlist_review(grants,agency,project,cached=(),limit=2,profile=None,fetch_details=None):
    from services.discovery import diversified_retrieval_queries
    from services.matching import project_relevance
    queries=diversified_retrieval_queries({},project)
    terms=' '.join(queries[:3])
    # Returned summaries are often title-only. Inspect a bounded topic-led pool
    # before spending on deep research; preserve all uninspected candidates.
    scored=sorted(grants,key=lambda g:-(project_relevance(terms,g)[0] or 0))
    details={}
    if fetch_details:
        for g in scored[:12]:
            oid=str(g.get('id') or g.get('opportunity_id') or '')
            if oid.isdecimal() and oid not in details:
                try:details[oid]=fetch_details(oid)
                except Exception:details[oid]={}
    signals=[]
    cached_by_id={str(r['opportunity_id']):r for r in cached}
    for g in grants:
        oid=str(g.get('id') or g.get('opportunity_id'))
        prior=cached_by_id.get(oid)
        if prior:signals.append(prior)
    enriched=[{**g,**({'description':details[str(g.get('id') or g.get('opportunity_id'))]['description']}
                    if details.get(str(g.get('id') or g.get('opportunity_id')),{}).get('description') else {})} for g in grants]
    initial=build_project_review(enriched,agency,terms,signals,budget=0,agency_profile=profile)
    rows=sorted(initial['queue']['pool'],key=lambda r:(
        not opportunity_timing(r['records'][0])['accepting_possible'],
        -(r['priority_score'] if r['priority_score'] is not None else -1),r['identity']))
    eligible=[r for r in rows if r['identity'][1].isdecimal() and
              r['decision']['state']!='CONFIRMED_EXCLUSION' and
              opportunity_timing(r['records'][0])['status'] not in {'Closed','Archived'} and
              not opportunity_timing(r['records'][0])['past']]
    # Mostly promising candidates; one uncertain/diverse lead when space permits.
    chosen=eligible[:limit]
    if limit>1 and len(eligible)>limit:
        first_agency=chosen[0]['records'][0].get('agencyCode')
        diverse=next((r for r in eligible[1:] if r['records'][0].get('agencyCode')!=first_agency and
                      (r['priority_score'] or 0)>=max(1,(chosen[0]['priority_score'] or 0)*.75)),None)
        if diverse:chosen[-1]=diverse
    ids=[r['identity'][1] for r in chosen]
    review=build_project_review(enriched,agency,project,cached,budget=limit,selected_ids=ids,agency_profile=profile)
    # Never silently fill unused slots with an expired/unidentified candidate.
    review['queue']['selected']=[r for r in review['queue']['pool'] if r['identity'][1] in ids]
    for row in review['queue']['pool']:
        row['selected']=row['identity'][1] in ids
        row['selection_reason']='Project-fit shortlist; applicant/purpose uncertainty requires research' if row['selected'] else None
    review['queue']['selected_count']=len(ids)
    return review


def display_category(record):
    if record.get('classification')=='CONFIRMED_EXCLUSION':return 'Not suitable or confirmed excluded'
    if record.get('state')==ResearchState.RESEARCH_FAILED.value:return 'Research incomplete'
    if record.get('state')!=ResearchState.RESEARCHED_AND_VALIDATED.value:return 'Preliminary match'
    timing=opportunity_timing(record['candidate'],record.get('evidence'))
    if record['decision']['should_apply']=='reject' or timing['past'] or timing['status'] in {'Closed','Archived','Forecasted'}:
        return 'Not suitable or not currently open'
    if record.get('classification')=='ACTIONABLE':return 'Reviewed and promising'
    return 'Conditional — needs verification'


def rank_results(records,review):
    # Queue selection/reasons are deliberately absent from the user ranking key.
    priority={r['identity'][1]:r['priority_score'] or 0 for r in review['queue']['pool']}
    tiers={'Reviewed and promising':0,'Conditional — needs verification':1,'Preliminary match':2,
           'Research incomplete':3,'Not suitable or not currently open':4,'Not suitable or confirmed excluded':5}
    def key(r):
        score=(r.get('decision') or {}).get('project_activity_score')
        findings={d['dimension']:d['assessment'] for d in r.get('analysis',{}).get('dimensions',[])}
        fit={'supported':0,'conditional':1,'unavailable':2,'conflicting':3}
        timing=opportunity_timing(r['candidate'],r.get('evidence'))
        return (tiers[display_category(r)],fit.get(findings.get('C'),2),fit.get(findings.get('D'),2),
                not timing['accepting_possible'],
                -(score if score is not None else priority.get(r['opportunity_id'],0)),r['opportunity_id'])
    return sorted(records.values(),key=key)
