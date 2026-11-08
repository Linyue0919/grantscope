"""Project-first screening on Dashboard's shared matching/evidence foundation.

Potential Matches are transparent deterministic screening leads, never Sol-verified.
No paid provider is created by retrieval, screening or ranking.
"""
import re
from datetime import date
from services.agency_profiles import get_agency_profile
from services.discovery import diversified_retrieval_queries
from services.match_engine import run_matching,MatchSettings,find_terms,OPEN,parse_date
from services.eligibility_assessment import INELIGIBLE,LIKELY_INELIGIBLE,NOT_CHECKED
from services.research_engine import (request_for_candidate,context_key,ResearchBudget,
                                     run_research,ResearchState,protocol_hash)
from services.search_foundation import build_project_review

# Activity phrases are transparent retrieval/ranking aids, not eligibility rules.
ACTIVITIES={
 'watershed restoration':['watershed restoration','watershed management','stream restoration','river restoration','watershed','stream habitat','river habitat'],
 'riparian/wetland restoration':['riparian','wetland restoration','habitat restoration','wetland conservation','restoration','restore','wetland'],
 'water quality':['water quality','clean water','water pollution'],
 'monitoring':['water monitoring','quality monitoring','monitoring','assessment'],
 'nutrient/runoff reduction':['nutrient','runoff','nonpoint source','stormwater'],
 'flood resilience':['flood mitigation','flood resilience','flood risk','floodplain'],
 'broadband':['broadband','internet access','digital connectivity'],
 'public health':['public health','disease prevention','health preparedness'],
 'cybersecurity':['cybersecurity','cyber security','information security'],
 'education':['teacher training','classroom','student','k-12'],
}


def project_activity_fit(project,title,description):
    requested={k:v for k,v in ACTIVITIES.items() if find_terms(project,v)}
    matches=[];title_hits=[]
    for key,terms in requested.items():
        found=find_terms(title+' '+description,terms)
        if found:matches.append({'activity':key,'terms':found})
        if find_terms(title,terms):title_hits.append(key)
    if not requested:
        stop=set('the and for with from north carolina agency department project government residents communities funding seeks would specific'.split())
        terms=list(dict.fromkeys(w for w in re.findall(r'[a-z]{5,}',project.lower()) if w not in stop))
        found=find_terms(title+' '+description[:2000],terms)
        matches=[{'activity':t,'terms':[t]} for t in found]
        title_hits=find_terms(title,terms)
    # Long generic descriptions require more independent evidence than titles.
    appropriate=bool(description) and (len(matches)>=2 or len(requested)==1 and bool(title_hits) and requested and next(iter(requested)) not in {'riparian/wetland restoration','monitoring'})
    return {'supported_for_screening':appropriate,'matches':matches,'title_matches':title_hits,
            'rank':len(title_hits)*3+len(matches),'basis':'Project activity phrase evidence; not AI suitability or verified allowable activities'}


def project_profile(agency):
    return get_agency_profile(agency)


def search_potential_matches(agency,project,amount=None,earliest=None,*,search_fn,details_fn,today=None,detail_limit=80):
    today=today or date.today();profile=project_profile(agency);details={}
    queries=diversified_retrieval_queries({},project)[:4]
    result=run_matching(profile,MatchSettings(min_days_left=None,min_award=None,
        include_unknown_deadline=True,detail_limit=detail_limit,max_queries=8),
        search_fn=search_fn,details_fn=details_fn,today=today,extra_keywords=queries,details_cache=details,
        candidate_ranker=lambda h:project_activity_fit(project,h.get('title',''),h.get('description',''))['rank'],
        prefer_official_deadlines=True)
    all_records=result['all_records'];potentials=[]
    threshold=parse_date(earliest) if earliest else today
    for record in all_records:
        oid=record['id'];detail=details.get(oid) or {}
        fit=project_activity_fit(project,record['title'],detail.get('description') or '')
        record['project_fit']=fit;record['potential_match']=False;record['project_screening_reasons']=[]
        reasons=record['project_screening_reasons']
        if record['deadline']['status']!=OPEN:reasons.append('Not verified as currently open with a closing date')
        closing=parse_date(record['deadline']['close_date'])
        if closing and threshold and closing<threshold:reasons.append('Closing date is before the selected threshold')
        if record['eligibility']['status'] in {INELIGIBLE,LIKELY_INELIGIBLE,NOT_CHECKED}:
            reasons.append('Direct applicant route is excluded, unlikely, or not checked; no supported alternative route established')
        if not fit['supported_for_screening']:reasons.append('Insufficient specific project-activity evidence')
        # Regional restrictions are a project-fit hold, not a fabricated legal exclusion.
        restricted_title=re.search(r'\b(?:for (?:indian )?tribes|for indian tribes|tribal (?:governments|organizations)|intertribal consortia|affiliated partner|fellowship|for universities)\b',record['title'],re.I)
        if restricted_title:reasons.append('Special applicant or affiliation route is not established for the selected agency')
        regions=record['eligibility'].get('region_flags',[])
        if any(region not in project.lower() for region in regions):reasons.append('Regional program scope does not support this NC project')
        scope=(detail.get('eligibility_text','')+' '+detail.get('description','')[:2000]).lower()
        if any(x in scope for x in ['western states','western united states','17 western']) and not any(x in project.lower() for x in ['western united states','western states']):
            reasons.append('Western-state program geography requires a supported NC route')
        whitelist=re.search(r'(?:one of the following states or territories|following states or territories|following states)\s*:\s*([^.]*)',detail.get('eligibility_text',''),re.I)
        if whitelist and ('north carolina' in project.lower() or re.search(r'\bNC\b',project)) and 'north carolina' not in whitelist.group(1).lower():
            reasons.append('Official eligible-location list does not include the proposed North Carolina location')
        if re.search(r'research and development|basic and applied research|research proposals',detail.get('description','')[:800],re.I) and not re.search(r'research and development|experimental|prototype|novel|research study',project,re.I):
            reasons.append('Research/development purpose is not established by the proposed implementation project')
        sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',detail.get('description',''))
        record['scope_requirement']=next((text for text in sentences if re.search(r'eligible lands|must be conducted|lands protected through|required|must be sponsored',text,re.I)),None)
        record['funding_preference_note']=None
        floor,ceiling=detail.get('award_floor'),detail.get('award_ceiling')
        if amount and ceiling is not None and amount>ceiling:record['funding_preference_note']='Requested amount exceeds the reported ceiling; partial funding only, if permitted.'
        elif amount and floor is not None and amount<floor:record['funding_preference_note']='Requested amount is below the reported floor; scope/award requirements need review.'
        elif amount and ceiling is None:record['funding_preference_note']='Award ceiling unavailable; funding adequacy is unresolved.'
        record['potential_match']=not reasons
        if not reasons:potentials.append(record)
    potentials.sort(key=lambda r:(-r['project_fit']['rank'],r['eligibility']['status']!='likely_eligible',
                                  bool(r['funding_preference_note']),r['deadline']['close_date'],r['id']))
    return {'potentials':potentials,'all_records':all_records,'details':details,'foundation':result,
            'agency':agency,'project':project,'amount':amount,'earliest':str(earliest) if earliest else None,
            'screening_only':True}


def research_one_candidate(screening,oid,provider,*,cache,evidence_client=None,on_update=None):
    candidate=next((r for r in screening['potentials'] if r['id']==str(oid)),None)
    if not candidate:raise ValueError('Only a screened potential match can be researched from this action')
    profile={'applicant_identity':screening['agency'],'applicant_category':'NC state government agency (user-selected)',
        'geography':['North Carolina'],'funding_needed_usd':screening['amount'],'earliest_closing_date':screening['earliest']}
    factory=lambda g:request_for_candidate(screening['agency'],screening['project'],g,profile=profile)
    hit={'id':oid,'title':candidate['title'],'agencyName':candidate['federal_agency'],
         'oppStatus':'POSTED','closeDate':candidate['deadline']['close_date']}
    scope=context_key(factory(hit));previous=cache.load(scope)
    review=build_project_review([hit],screening['agency'],screening['project'],budget=1,selected_ids=[oid],agency_profile=profile)
    def persist(records):
        cache.save(scope,records)
        if on_update:on_update(records)
    run=run_research(review,factory,provider,budget=ResearchBudget(1,2,2.),previous=previous,
                     evidence_client=evidence_client,on_update=persist)
    return run
