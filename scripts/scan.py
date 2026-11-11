#!/usr/bin/env python3
"""Refresh tracked 13F filings into GitHub Pages JSON; stdlib only."""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs'/'data'
DATA.mkdir(parents=True,exist_ok=True)
LIMIT=int(os.getenv('MAX_QUARTERS','8'))

def save(path, obj):
    content=json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n'
    if not path.exists() or path.read_text()!=content:
        path.write_text(content)
        print('Updated',path.relative_to(ROOT))

def main():
    if not os.getenv('SEC_USER_AGENT') or 'example.com' in os.getenv('SEC_USER_AGENT',''):
        raise SystemExit('Set SEC_USER_AGENT to your real app name and contact email')
    managers=json.loads((ROOT/'managers.json').read_text())
    save(DATA/'managers.json',managers)
    successes=0
    for m in managers:
        cik=str(m['cik']).zfill(10)
        dest=DATA/(cik+'.json')
        old=json.loads(dest.read_text()) if dest.exists() else {}
        try:
            name,rows=server.filings(cik)
            rows=rows[:LIMIT]
            if not rows: raise ValueError('No 13F-HR filings')
            previous={q['accession']:q for q in old.get('filings',[]) if 'accession' in q}
            collected=[]
            for r in rows:
                acc=r['accessionNumber']
                if acc in previous:
                    item=previous[acc]
                else:
                    holdings,url=server.holding_for(cik,r)
                    item={'accession':acc,'reportDate':r.get('reportDate'),'filingDate':r.get('filingDate'),'form':r.get('form'),'xmlUrl':url,'holdings':holdings}
                    print('Fetched',m['name'],r.get('reportDate'),acc)
                    time.sleep(.2)
                collected.append(item)
            # Store raw holdings, compute changes in browser so all quarters work.
            doc={'name':name or m['name'],'cik':cik,'fetchedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'filings':collected}
            # Avoid a git commit on every scan if filings are unchanged.
            if old.get('filings')==collected and old.get('name')==doc['name']:
                print('No new filings:',m['name'])
            else:save(dest,doc)
            successes+=1
        except Exception as e:
            print('WARNING:',m['name'],str(e),file=sys.stderr)
        time.sleep(.2)
    if not successes:raise SystemExit('All SEC scans failed; preserving prior data')
    print(f'Scanned {successes}/{len(managers)} managers')

if __name__=='__main__':main()
