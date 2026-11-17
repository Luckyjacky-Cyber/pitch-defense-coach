"""Local bridge for the current conversation coach. No cloud model or credentials."""
import argparse,json,sys,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action',choices=['poll','question','feedback','report','end','reset']);p.add_argument('--after',type=int,default=-1);p.add_argument('--wait',type=int,default=25);p.add_argument('--file');p.add_argument('--port',type=int,default=8769);a=p.parse_args()
base=f'http://127.0.0.1:{a.port}'
if a.action=='poll':
 r=urllib.request.urlopen(f'{base}/api/coach/poll?after={a.after}&wait={a.wait}',timeout=a.wait+10)
else:
 data=json.loads(Path(a.file).read_text(encoding='utf8')) if a.file else {}
 route='/api/'+('coach/'+a.action if a.action in ['question','feedback','report'] else a.action)
 r=urllib.request.urlopen(urllib.request.Request(base+route,data=json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'}),timeout=30)
print(r.read().decode('utf8'))
