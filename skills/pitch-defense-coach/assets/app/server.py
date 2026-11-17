from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import json,sys,time,uuid,threading,io,mimetypes,argparse,os,math,copy

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'runtime'))
PUBLIC=ROOT/'public'; DATA=ROOT/'data';DATA.mkdir(exist_ok=True)
LOCK=threading.RLock(); CHANGED=threading.Condition(LOCK)
KNOWLEDGE=json.loads((PUBLIC/'knowledge.json').read_text(encoding='utf8'))
from asr_engine import Engine
from roadshow_store import RoadshowStore
ENGINE=Engine(ROOT); ASR=ENGINE.status; ROAD=RoadshowStore(ROOT)
SESSION=None;REV=0; COACH_SEEN=0
if (DATA/'current.json').exists():
 try:
  SESSION=json.loads((DATA/'current.json').read_text(encoding='utf8'))
  if SESSION.get('activeSince'):
   SESSION['activeSince']=None;SESSION['status']='paused'
 except (ValueError,KeyError):SESSION=None

def load_asr():
 ENGINE.load()

def elapsed(s):
 value=s['elapsed']+(max(0,time.time()-s['activeSince']) if s.get('activeSince') else 0)
 return min(s['duration'],value) if s.get('duration') is not None else value

def timed_out(s):
 return s.get('duration') is not None and elapsed(s)>=s['duration']

def freeze(s):
 s['elapsed']=elapsed(s);s['activeSince']=None

def touch():
 global REV
 REV+=1
 if SESSION:
  temp=DATA/'current.tmp'
  temp.write_text(json.dumps(SESSION,ensure_ascii=False,indent=2),encoding='utf8')
  temp.replace(DATA/'current.json')
 elif (DATA/'current.json').exists():(DATA/'current.json').unlink()
 CHANGED.notify_all()

def snapshot():
 return {'appId':'pitch-defense-coach-v1','instanceRoot':str(ROOT),'revision':REV,'session':SESSION,'remaining':max(0,SESSION['duration']-elapsed(SESSION)) if SESSION and SESSION.get('duration') is not None else None,'elapsed':elapsed(SESSION) if SESSION else 0,'asr':ASR,'coachOnline':time.time()-COACH_SEEN<50}

def expire():
 if SESSION and SESSION['status']=='answering' and timed_out(SESSION):
  freeze(SESSION);SESSION['status']='time_up';touch()

def safe_text(v,n=8000):
 if not isinstance(v,str):raise ValueError('需要文字内容')
 return v.strip()[:n]

def new_session(payload,source=None):
 mode=payload.get('timingMode','timed')
 if mode not in ['timed','untimed']:raise ValueError('计时模式无效')
 minutes=payload.get('minutes',10)
 if type(minutes)!=int or not 1<=minutes<=30:raise ValueError('时长需为1—30分钟')
 return {'id':uuid.uuid4().hex[:12],'created':time.time(),'duration':minutes*60 if mode=='timed' else None,'timingMode':mode,'elapsed':0,'activeSince':None,'status':'waiting_coach','summary':safe_text(payload.get('summary',''),6000),'focus':safe_text(payload.get('focus','balanced'),100),'practiceGoal':safe_text(payload.get('practiceGoal',''),500),'questions':[],'report':None,'candidateChains':[],'capabilities':payload.get('capabilities',{}),'sourceRoadshow':source}

def handoff(payload):
 global SESSION
 with CHANGED, ROAD.lock:
  ROAD.require(payload.get('sessionId')); road=ROAD.current
  if road['status']=='running':raise ValueError('请先结束路演')
  if not road.get('chainDefense'):raise ValueError('本轮未开启路演后接答辩')
  if payload.get('confirmed') is not True:raise ValueError('请先校对并确认讲述文字')
  linked=road.get('linkedDefenseId')
  # Recover a saved handoff if the server stopped between the two atomic writes.
  if SESSION and (SESSION.get('sourceRoadshow') or {}).get('id')==road['id']:
   road['linkedDefenseId']=SESSION['id'];ROAD.save();return snapshot()
  if linked:raise ValueError('本轮已串联答辩，请查看历史记录或开始新路演')
  if SESSION and SESSION['status'] not in ['ended','reviewed']:raise ValueError('请先结束当前答辩')
  if ENGINE.jobs.get(road.get('jobId'),{}).get('status') in ['running','queued']:raise ValueError('请等待转写结束并校对')
  if not any(v.get('editedText','').strip() for v in road['visits']):raise ValueError('请先填写或转写至少一页实际讲述内容')
  source=copy.deepcopy(road);source['confirmedAt']=time.time()
  session=new_session({'minutes':road.get('defenseMinutes',5),'focus':'roadshow','summary':'基于本轮已校对路演追问；以最新PPT核验事实。','practiceGoal':road.get('practiceGoal','')},source)
  if SESSION:(DATA/f"session-{SESSION['id']}.json").write_text(json.dumps(SESSION,ensure_ascii=False,indent=2),encoding='utf8')
  SESSION=session;touch();road['linkedDefenseId']=SESSION['id'];ROAD.save();return snapshot()

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def guard(self):
  host=self.headers.get('Host','')
  if host not in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']:return False
  origin=self.headers.get('Origin')
  if origin and origin not in [f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}']:return False
  return self.headers.get('Sec-Fetch-Site','none') not in ['cross-site']
 def reply(self,obj,code=200):
  raw=json.dumps(obj,ensure_ascii=False).encode('utf8')
  self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  global COACH_SEEN
  if not self.guard():return self.reply({'error':'仅允许本机同源访问'},403)
  route=self.path.split('?')[0]
  if route=='/api/roadshow':return self.reply(ROAD.state())
  if route=='/api/asr-job':
   from urllib.parse import parse_qs,urlsplit
   jid=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
   job=ENGINE.jobs.get(jid)
   return self.reply(job if job else {'error':'转写任务未找到，请回听录音后重新提交'},200 if job else 404)
  if route=='/api/state':
   with LOCK:expire();self.reply(snapshot())
   return
  if route=='/api/coach/poll':
   from urllib.parse import parse_qs,urlsplit
   query=parse_qs(urlsplit(self.path).query)
   after=int(query.get('after',['-1'])[0]); wait=min(30,max(0,int(query.get('wait',['25'])[0])))
   with CHANGED:
    COACH_SEEN=time.time();deadline=time.time()+wait
    while REV<=after and time.time()<deadline:CHANGED.wait(timeout=min(1,deadline-time.time()));expire()
    COACH_SEEN=time.time();self.reply(snapshot())
   return
  if route=='/api/export':
   with LOCK:self.reply(snapshot())
   return
  from urllib.parse import unquote
  p=(PUBLIC/unquote(route.lstrip('/') or 'index.html')).resolve()
  if not p.is_relative_to(PUBLIC) or not p.is_file():return self.reply({'error':'not found'},404)
  mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
  if p.suffix=='.mjs':mime='text/javascript'
  raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8' if mime.startswith('text/') else mime)
  self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
  self.send_header('Cache-Control','no-cache');self.send_header('Permissions-Policy','camera=(self), microphone=(self)');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_POST(self):
  global SESSION,COACH_SEEN
  if not self.guard():return self.reply({'error':'仅允许本机同源访问'},403)
  length=int(self.headers.get('Content-Length','0'))
  if length<=0 or length>15_000_000:return self.reply({'error':'请求大小超限'},413)
  body=self.rfile.read(length)
  if self.path in ['/api/transcribe','/api/transcribe/start']:
   if ASR['state']!='ready':return self.reply({'error':ASR['detail']},503)
   if not self.headers.get('Content-Type','').startswith('audio/'):return self.reply({'error':'需要音频'},415)
   try:
    from urllib.parse import unquote
    model=self.headers.get('X-ASR-Model',ASR['defaultModel']);terms=unquote(self.headers.get('X-Glossary',''))
    sid=self.headers.get('X-Roadshow-Id');limit=190;callback=None
    if sid:
     ROAD.require(sid)
     if ROAD.current['status']=='running':raise ValueError('请先结束路演，再转写录音')
     limit=max(1,math.ceil(ROAD.current['elapsedMs']/1000)+5);offset=float(self.headers.get('X-Audio-Offset-Ms','0'))
     if not math.isfinite(offset):raise ValueError('音频时间无效')
     ROAD.set_job(sid,None,offset)
     callback=lambda result,error:ROAD.set_transcript(sid,result,error)
    if self.path.endswith('/start'):
     job=ENGINE.start_job(body,model,terms,limit,callback)
     if sid:ROAD.set_job(sid,job['id'],offset)
     return self.reply(job,202)
    return self.reply(ENGINE.transcribe(body,model,terms,limit))
   except Exception as e:return self.reply({'error':'转写失败，可回听录音或键入回答。'+str(e)[:180]},400)
  if not self.headers.get('Content-Type','').startswith('application/json'):return self.reply({'error':'JSON required'},415)
  try:
   payload=json.loads(body)
   if self.path.startswith('/api/roadshow/'):
    action=self.path.rsplit('/',1)[-1];sid=payload.get('sessionId')
    if action=='handoff':return self.reply(handoff(payload))
    if action=='start':
     if SESSION and SESSION['status'] not in ['ended','reviewed']:raise ValueError('请先结束当前答辩模拟')
     if ROAD.current and ROAD.current.get('jobId') and ENGINE.jobs.get(ROAD.current['jobId'],{}).get('status') in ['running','queued']:raise ValueError('请等待上一轮转写完成')
     return self.reply(ROAD.start(payload))
    ROAD.require(sid)
    if action=='reset':
     if ROAD.current.get('jobId') and ENGINE.jobs.get(ROAD.current['jobId'],{}).get('status') in ['running','queued']:raise ValueError('请等待转写完成')
     return self.reply(ROAD.reset(sid))
    if action=='navigate':return self.reply(ROAD.navigate(sid,payload.get('page'),payload.get('atMs')))
    if action=='finish':return self.reply(ROAD.finish())
    if action=='metadata':return self.reply(ROAD.metadata(sid,payload))
    if action=='edit':return self.reply(ROAD.edit(sid,payload.get('edits',[])))
    if action=='report':return self.reply(ROAD.report(sid,payload.get('report',{})))
    return self.reply({'error':'not found'},404)
   with CHANGED:
    route=self.path
    if route=='/api/start':
     if ROAD.state()['session'] and ROAD.current['status']=='running':raise ValueError('请先结束当前路演模拟')
     if SESSION and SESSION['status'] not in ['ended','reviewed']:raise ValueError('当前轮次尚未结束')
     if SESSION:(DATA/f"session-{SESSION['id']}.json").write_text(json.dumps(SESSION,ensure_ascii=False,indent=2),encoding='utf8')
     SESSION=new_session(payload)
    elif route=='/api/coach/question':
     COACH_SEEN=time.time()
     if not SESSION or payload.get('sessionId')!=SESSION['id']:raise ValueError('轮次不匹配')
     if SESSION['status']!='waiting_coach':raise ValueError('只能在等待教练时出题')
     q=safe_text(payload['text'],800)
     if q.count('？')+q.count('?')>1:raise ValueError('每次只问一个问题')
     dim=payload['dimension']
     if dim not in KNOWLEDGE['ruleWeights']:raise ValueError('维度不匹配')
     if timed_out(SESSION):raise ValueError('本轮时间已结束')
     SESSION['questions'].append({'id':f"Q{len(SESSION['questions'])+1:02}",'text':q,'dimension':dim,'chainId':payload.get('chainId',''),'source':payload.get('source',''),'issuedAt':time.time(),'answer':None,'feedback':None})
     SESSION['candidateChains']=payload.get('candidateChains',SESSION['candidateChains'])
     SESSION['status']='answering';SESSION['activeSince']=time.time()
    elif route=='/api/answer':
     if not SESSION or payload.get('sessionId')!=SESSION['id']:raise ValueError('轮次不匹配')
     if SESSION['status'] not in ['answering','paused','time_up']:raise ValueError('当前不能提交')
     q=SESSION['questions'][-1]
     if payload.get('questionId')!=q['id'] or q['answer']:raise ValueError('题号错误或已提交')
     text=safe_text(payload.get('text',''),8000)
     if not text:raise ValueError('请先输入或转写回答')
     ev=payload.get('events',[])
     if not isinstance(ev,list) or len(ev)>500:raise ValueError('事件数量异常')
     for event in ev:
      if event.get('questionId')!=q['id']:raise ValueError('事件必须绑定当前问题')
      if not all(isinstance(event.get(k), (int,float)) and math.isfinite(event[k]) for k in ['startMs','endMs']):raise ValueError('事件时间无效')
      if event['endMs']<event['startMs']:raise ValueError('事件时间倒置')
     freeze(SESSION)
     q['answer']={'text':text,'originalTranscript':safe_text(payload.get('originalTranscript',''),8000),'events':ev,'submittedAt':time.time(),'durationSeconds':max(0,min(900,float(payload.get('durationSeconds',0)))),'audio':payload.get('audio',{}),'camera':payload.get('camera',{})}
     SESSION['status']='ended' if timed_out(SESSION) or payload.get('finish') else 'waiting_coach'
    elif route=='/api/coach/feedback':
     COACH_SEEN=time.time()
     if not SESSION or payload.get('sessionId')!=SESSION['id']:raise ValueError('轮次不匹配')
     q=next((q for q in SESSION['questions'] if q['id']==payload.get('questionId')),None)
     if not q or not q['answer']:raise ValueError('未找到已答问题')
     q['feedback']=payload.get('feedback')
    elif route=='/api/pause':
     if SESSION and SESSION['status']=='answering':freeze(SESSION);SESSION['status']='paused'
    elif route=='/api/resume':
     if SESSION and SESSION['status']=='paused':SESSION['status']='answering';SESSION['activeSince']=time.time()
    elif route=='/api/end':
     if SESSION:freeze(SESSION);SESSION['status']='ended'
    elif route=='/api/coach/report':
     COACH_SEEN=time.time()
     if not SESSION or payload.get('sessionId')!=SESSION['id']:raise ValueError('轮次不匹配')
     report=payload['report']
     if len(report.get('priorities',[]))!=3:raise ValueError('需要三项具体改进')
     levels=report.get('dimensions',[])
     if {v.get('name') for v in levels}!=set(KNOWLEDGE['ruleWeights']):raise ValueError('需要四维度证据等级')
     if any(v.get('level') not in ['强','中','弱','缺失'] for v in levels):raise ValueError('等级无效')
     SESSION['report']=report;freeze(SESSION);SESSION['status']='reviewed'
    elif route=='/api/reset':
     if SESSION:(DATA/f"session-{SESSION['id']}.json").write_text(json.dumps(SESSION,ensure_ascii=False,indent=2),encoding='utf8')
     SESSION=None
    else:return self.reply({'error':'not found'},404)
    touch();self.reply(snapshot())
  except (ValueError,KeyError,TypeError,IndexError) as e:self.reply({'error':str(e)},400)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8769);args=p.parse_args()
 threading.Thread(target=load_asr,daemon=True).start()
 server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
 print(f'Defense coach ready http://127.0.0.1:{args.port}',flush=True)
 server.serve_forever()
