#!/usr/bin/env python3
"""Ping dinamico di tutte le 37*36 coppie di router Kathara (richiede un lab avviato)."""
import concurrent.futures, csv, json, subprocess, sys, time
from pathlib import Path

lab=Path(__file__).resolve().parent
data=json.loads((lab/'cost266.json').read_text())
items=sorted(data['nodes'],key=lambda n:n['id'])
def name(s):
 import re,unicodedata
 s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
 return 'r_'+re.sub('[^a-z0-9]+','_',s).strip('_')
pairs=[(a,b) for a in items for b in items if a['id']!=b['id']]
def check(pair):
 a,b=pair
 dest=f'10.200.0.{b["id"]+1}'
 proc=subprocess.run(['kathara','exec',name(a['name']),'--','ping','-c','1','-W','2',dest],capture_output=True,text=True,timeout=25)
 return (a['id'],b['id'],name(a['name']),name(b['name']),dest,proc.returncode==0)
print(f'Verifico {len(pairs)} ping (tempo dipendente dalla macchina).',flush=True)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for index,row in enumerate(pool.map(check,pairs),start=1):
  results.append(row)
  if index%100==0:print(f'{index}/{len(pairs)}',flush=True)
out=lab/'runtime_ping_results.csv'
with out.open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['source_id','dest_id','source','destination','ip','success']);w.writerows(results)
ok=sum(r[-1] for r in results)
print(f'Ping riusciti: {ok}/{len(results)}. File: {out}')
sys.exit(0 if ok==len(results) else 1)
