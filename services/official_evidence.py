"""Bounded dynamic Grants.gov document intake. No Azure or fixed grant decisions."""
from datetime import datetime,timezone
import hashlib
from io import BytesIO
import json
from html.parser import HTMLParser
from urllib.parse import urlparse,urljoin
import zipfile
import xml.etree.ElementTree as ET
import requests
from services.grants_api import DETAIL_API_URL,plain_official_text


def digest(data):
    return hashlib.sha256(data).hexdigest()


def official_url(url):
    p=urlparse(url);host=p.hostname or ''
    return p.scheme=='https' and (host.endswith('.gov') or host.endswith('.mil')) and not p.username and not p.password


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.extend(v for k,v in attrs if k=='href' and v)


def extract_document(data,mime,name):
    if mime.startswith('application/pdf') or name.lower().endswith('.pdf'):
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(data))
        if len(reader.pages)>250:raise ValueError('PDF page limit exceeded')
        return '\n\n'.join(f'[PDF page {i+1}]\n'+(p.extract_text() or '') for i,p in enumerate(reader.pages)), 'pypdf all pages; no OCR'
    if name.lower().endswith('.docx') or 'wordprocessingml' in mime:
        with zipfile.ZipFile(BytesIO(data)) as z:
            info=z.getinfo('word/document.xml')
            if info.file_size>20_000_000:raise ValueError('DOCX expansion limit exceeded')
            root=ET.fromstring(z.read(info))
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        return '\n'.join(''.join(t.text or '' for t in p.findall('.//'+ns+'t')) for p in root.findall('.//'+ns+'p')),'OOXML body/tables; no image OCR'
    if 'html' in mime or name.lower().endswith(('.htm','.html')):
        return plain_official_text(data.decode('utf-8',errors='replace')),'HTML text; linked policies not implicitly reviewed'
    if mime.startswith('text/plain') or name.endswith('.txt'):return data.decode('utf-8'),'UTF-8 text'
    raise ValueError('Unsupported document format')


class OfficialEvidenceClient:
    def __init__(self,session=None,max_documents=5,max_document_bytes=8_000_000):
        self.session=session or requests.Session();self.max_documents=max_documents;self.max_document_bytes=max_document_bytes

    def _download(self,url):
        for _ in range(4):
            if not official_url(url):raise ValueError('Nonofficial or unsafe document URL')
            r=self.session.get(url,timeout=(10,35),allow_redirects=False,stream=True)
            if r.status_code in {301,302,303,307,308}:
                url=urljoin(url,r.headers['Location']);r.close();continue
            r.raise_for_status();chunks=[];size=0
            for chunk in r.iter_content(65536):
                size+=len(chunk)
                if size>self.max_document_bytes:r.close();raise ValueError('Document byte limit exceeded')
                chunks.append(chunk)
            mime=r.headers.get('Content-Type','').split(';')[0];r.close()
            return b''.join(chunks),mime,url
        raise ValueError('Redirect limit exceeded')

    def fetch(self,opportunity_id):
        oid=str(opportunity_id)
        if not oid.isdecimal():raise ValueError('Numeric Grants.gov identity required')
        response=self.session.post(DETAIL_API_URL,json={'opportunityId':int(oid)},timeout=(10,35),allow_redirects=False)
        response.raise_for_status();envelope=response.json()
        if str(envelope.get('errorcode','0'))!='0' or not isinstance(envelope.get('data'),dict):
            raise ValueError('Official detail API failure')
        data=envelope['data'];fields=data.get('synopsis') or data.get('forecast') or {}
        now=datetime.now(timezone.utc).isoformat();url='https://www.grants.gov/search-results-detail/'+oid
        selected={k:fields.get(k) for k in ['synopsisDesc','forecastDesc','applicantEligibilityDesc','applicantTypes',
            'fundingActivityCategoryDesc','responseDateStr','responseDateDesc','estApplicationResponseDateStr',
            'awardFloor','awardCeiling','costSharing','costSharingOrMatchingRequirement'] if fields.get(k) is not None}
        sources=[{'source_id':'grantsgov-'+oid,'url':url,'text':json.dumps({'status':data.get('ost','Unknown'),**{k:plain_official_text(v) if isinstance(v,str) else v for k,v in selected.items()}},ensure_ascii=False),
                  'retrieved_at':now,'version':now,'kind':'official_summary'}]
        candidates=[]
        # Published API related-document folders, not envelope session/contact data.
        def collect(node):
            if isinstance(node,dict):
                if node.get('fileName') and node.get('id') is not None:
                    name=str(node['fileName']);aid=str(node['id'])
                    if aid.isdecimal():candidates.append({'url':'https://apply07.grants.gov/grantsws/rest/opportunity/att/download/'+aid,
                        'name':name,'mime':str(node.get('mimeType') or ''),'id':aid})
                for k,v in node.items():
                    if k not in {'synopsis','forecast','contact','agencyDetails'}:collect(v)
            elif isinstance(node,list):
                for v in node:collect(v)
        collect(data)
        links=Links();links.feed(str(fields.get('synopsisDesc') or fields.get('forecastDesc') or ''))
        for link in links.links:
            if official_url(link):candidates.append({'url':link,'name':urlparse(link).path.rsplit('/',1)[-1] or 'linked-document','mime':'','id':digest(link.encode())[:12]})
        # Primary notices and amendments first; no document is silently declared read.
        def priority(item):
            text=item['name'].lower()
            return (0 if any(t in text for t in ['nofo','notice','solicitation','foa','amend','funding']) else 1,item['name'])
        seen=set();inventory=[];gaps=[];full_notice=False;attempted_documents=0
        for item in sorted(candidates,key=priority):
            if item['url'] in seen:continue
            seen.add(item['url']);record={**item,'ingested':False}
            if attempted_documents>=self.max_documents:
                record['error']='Document-count limit';gaps.append('Not ingested: '+item['name']);inventory.append(record);continue
            attempted_documents+=1
            try:
                raw,mime,final_url=self._download(item['url'])
                text,method=extract_document(raw,mime or item['mime'],item['name'])
                if not text.strip():raise ValueError('No extractable text; OCR required')
                source={'source_id':'attachment-'+oid+'-'+item['id'],'url':final_url,'text':text,'retrieved_at':now,
                    'version':digest(raw),'raw_sha256':digest(raw),'text_sha256':digest(text.encode()),
                    'extraction_method':method,'kind':'official_document','name':item['name']}
                sources.append(source);record.update(ingested=True,raw_sha256=digest(raw))
                heading=' '.join(text[:6000].lower().split())
                notice_heading=any(t in heading for t in ['notice of funding opportunity','funding opportunity announcement','program solicitation','notice of funding availability'])
                if ((priority(item)[0]==0 or notice_heading) and not any(t in item['name'].lower() for t in ['amend','budget','fact sheet'])):full_notice=True
            except Exception:
                record['error']='Unavailable, unreadable or unsupported document';gaps.append('Could not ingest: '+item['name'])
            inventory.append(record)
        if not full_notice:gaps.append('Primary full notice not identified and ingested; summary is insufficient for deep recommendation')
        gaps.append('Amendment chain and referenced policies not independently certified complete')
        return {'opportunity_id':oid,'sources':sources,'inventory':inventory,'coverage':{'primary_notice_ingested':full_notice,
            'amendments_verified':False,'gaps':gaps},'fetched_at':now,'status':data.get('ost','Unknown'),
                'close_date':fields.get('responseDateStr') or fields.get('estApplicationResponseDateStr'),
                'financials':{'award_floor':fields.get('awardFloor'),'award_ceiling':fields.get('awardCeiling'),
                              'cost_sharing':fields.get('costSharing') or fields.get('costSharingOrMatchingRequirement')}}
