#!/usr/bin/env python3
"""13F Intelligence: stdlib-only SEC EDGAR proxy and holdings comparison."""
import json, os, re, time, urllib.request, urllib.error, xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

ROOT=Path(__file__).parent
UA=os.environ.get('SEC_USER_AGENT','13F Intelligence research-app contact research@example.com')
CACHE={}
MANAGERS=[{'name':'Atreides Management, LP','manager':'Gavin Baker','cik':'0001777813'}, {'name':'Pershing Square Capital Management','manager':'Bill Ackman','cik':'0001336528'}, {'name':'Duquesne Family Office','manager':'Stanley Druckenmiller','cik':'0001536411'}, {'name':'Appaloosa Management','manager':'David Tepper','cik':'0001656456'}, {'name':'Berkshire Hathaway','manager':'Warren Buffett','cik':'0001067983'}, {'name':'Scion Asset Management','manager':'Michael Burry','cik':'0001649339'}]
def fetch(url, ttl=3600):
    now=time.time()
    if url in CACHE and now-CACHE[url][0]<ttl:return CACHE[url][1]
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Encoding':'identity','Accept':'application/json, application/xml, text/xml, */*'})
    with urllib.request.urlopen(req,timeout=22) as r: data=r.read(12_000_000)
    CACHE[url]=(now,data)
    return data

def local(tag):return tag.rsplit('}',1)[-1].lower()
def field(node,name):
    for x in node.iter():
        if local(x.tag)==name.lower():return (x.text or '').strip()
    return ''
def parse_table(raw):
    root=ET.fromstring(raw)
    out=[]
    for node in root.iter():
        if local(node.tag)!='infotable':continue
        issuer=field(node,'nameOfIssuer'); cusip=field(node,'cusip')
        if not issuer or not cusip:continue
        try:value=float(field(node,'value').replace(',',''))
        except ValueError:value=0
        # SEC 13F XML value is expressed in thousands of dollars.
        try:shares=float(field(node,'sshPrnamt').replace(',',''))
        except ValueError:shares=0
        out.append({'issuer':issuer,'class':field(node,'titleOfClass'),'cusip':cusip,'value':value*1000,'shares':shares,'shareType':field(node,'sshPrnamtType'),'option':field(node,'putCall').upper(),'discretion':field(node,'investmentDiscretion')})
    return out

def submission_rows(data):
    recent=data.get('filings',{}).get('recent',{})
    rows=[dict(zip(recent.keys(),vals)) for vals in zip(*recent.values())] if recent else []
    for old in data.get('filings',{}).get('files',[]):
        try:
            extra=json.loads(fetch('https://data.sec.gov/submissions/'+old['name'],ttl=86400))
            rows.extend(dict(zip(extra.keys(),vals)) for vals in zip(*extra.values()))
        except Exception:pass
    return rows

def filings(cik):
    data=json.loads(fetch('https://data.sec.gov/submissions/CIK'+cik+'.json',ttl=900))
    rows=[r for r in submission_rows(data) if r.get('form') in ('13F-HR','13F-HR/A')]
    rows.sort(key=lambda x:(x.get('reportDate',''),x.get('filingDate',''),x.get('acceptanceDateTime','')),reverse=True)
    # Avoid double-counting amendment as separate quarter. Latest amendment supersedes original for restatements.
    unique={}
    for r in rows:
        quarter=r.get('reportDate')
        if quarter and quarter not in unique:unique[quarter]=r
    return data.get('name',''),list(unique.values())

def holding_for(cik,row):
    accession=row['accessionNumber'].replace('-','')
    base=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/'
    index=json.loads(fetch(base+'index.json',ttl=86400))
    items=index.get('directory',{}).get('item',[])
    candidates=[x['name'] for x in items if x['name'].lower().endswith('.xml') and not x['name'].lower().startswith(('primary_doc','filing','form13f'))]
    errors=[]
    for filename in candidates:
        try:
            parsed=parse_table(fetch(base+filename,ttl=86400))
            if parsed:return parsed,base+filename
        except Exception as e:errors.append(str(e))
    # Some filings use a primary XML that contains the information table.
    for x in items:
        filename=x['name']
        if filename.lower().endswith('.xml') and filename not in candidates:
            try:
                parsed=parse_table(fetch(base+filename,ttl=86400))
                if parsed:return parsed,base+filename
            except Exception:pass
    raise ValueError('No XML information table found in this filing. It may be a legacy/nonstandard submission.')

def compare(curr,prev):
    # Option direction + class + CUSIP prevents conflating calls, puts, and shares.
    key=lambda h:(h['cusip'],h['class'].upper(),h['option'])
    previous={key(x):x for x in prev}
    current={key(x):x for x in curr}
    result=[]
    for h in curr:
        old=previous.get(key(h)); delta=h['shares']-(old['shares'] if old else 0)
        status='New' if old is None else 'Increased' if delta>0 else 'Reduced' if delta<0 else 'Unchanged'
        result.append({**h,'status':status,'shareDelta':delta,'priorShares':old['shares'] if old else 0})
    for h in prev:
        if key(h) not in current:result.append({**h,'value':0,'shares':0,'status':'Exited','shareDelta':-h['shares'],'priorShares':h['shares']})
    return result

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'static'),**kwargs)
    def jsonout(self,data,status=200):
        payload=json.dumps(data).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        parsed=urlparse(self.path)
        if not parsed.path.startswith('/api/'):return super().do_GET()
        q=parse_qs(parsed.query)
        try:
            if parsed.path=='/api/managers':return self.jsonout(MANAGERS)
            if parsed.path=='/api/search':
                term=q.get('q',[''])[0].lower().strip()
                if len(term)<2:return self.jsonout(MANAGERS)
                # SEC official company-ticker list helps locate managers by company name; curated names cover individuals.
                found=[m for m in MANAGERS if term in (m['name']+' '+m['manager']+' '+m['cik']).lower()]
                try:
                    data=json.loads(fetch('https://www.sec.gov/files/company_tickers.json',ttl=86400))
                    for v in data.values():
                        if term in v['title'].lower() and len(found)<20:
                            cik=str(v['cik_str']).zfill(10)
                            if not any(m['cik']==cik for m in found):found.append({'name':v['title'],'manager':'','cik':cik})
                except Exception:pass
                return self.jsonout(found[:20])
            if parsed.path=='/api/holdings':
                cik=q.get('cik',['0001777813'])[0]
                if not re.fullmatch(r'\d{1,10}',cik):raise ValueError('CIK must be numeric')
                cik=cik.zfill(10)
                name,rows=filings(cik)
                if not rows:return self.jsonout({'error':'No 13F-HR filings found for this CIK.'},404)
                idx=int(q.get('quarter',['0'])[0]);idx=max(0,min(idx,len(rows)-1))
                current=rows[idx]; holdings,xmlurl=holding_for(cik,current)
                prev=[]
                if idx+1<len(rows):
                    try:prev,_=holding_for(cik,rows[idx+1])
                    except Exception:pass
                changes=compare(holdings,prev) if prev else [{**h,'status':'Unknown','shareDelta':0,'priorShares':0} for h in holdings]
                total=sum(x['value'] for x in holdings)
                for h in changes:h['weight']=100*h['value']/total if total else 0
                changes.sort(key=lambda h:h['value'],reverse=True)
                acc=current['accessionNumber'].replace('-','')
                return self.jsonout({'name':name,'cik':cik,'quarters':[{'reportDate':r.get('reportDate'),'filingDate':r.get('filingDate'),'form':r.get('form')} for r in rows],'selected':idx,'reportDate':current.get('reportDate'),'filingDate':current.get('filingDate'),'form':current.get('form'),'filingUrl':f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{current["accessionNumber"]}-index.htm','xmlUrl':xmlurl,'holdings':changes,'totalValue':total,'positionCount':len(holdings),'previousAvailable':bool(prev),'fetchedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
            self.jsonout({'error':'Unknown endpoint'},404)
        except (urllib.error.HTTPError,urllib.error.URLError) as e:self.jsonout({'error':'SEC request failed. Check SEC_USER_AGENT, network access, or SEC rate limits.','details':str(e)},502)
        except Exception as e:self.jsonout({'error':str(e)},400)

if __name__=='__main__':
    port=int(os.environ.get('PORT','8765'))
    print(f'13F Intelligence at http://localhost:{port} | Set SEC_USER_AGENT to YourApp your-email@example.com')
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
