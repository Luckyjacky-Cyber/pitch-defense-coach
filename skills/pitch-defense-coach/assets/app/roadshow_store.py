from pathlib import Path
import json,time,uuid,threading,math
from competition import resolve_profile

class RoadshowStore:
 def __init__(self,root,clock=time.time):
  self.root=Path(root);self.data=self.root/'data';self.data.mkdir(exist_ok=True);self.path=self.data/'roadshow-current.json';self.clock=clock;self.lock=threading.RLock()
  self.deck=json.loads((self.root/'public/deck.json').read_text(encoding='utf8'));self.current=None
  if self.path.exists():
   try:self.current=json.loads(self.path.read_text(encoding='utf8'))
   except ValueError:pass
 def save(self):
  tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.current,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(self.path)
 def elapsed(self):
  s=self.current
  if s['status']!='running':return s['elapsedMs']
  value=max(0,int(self.clock()*1000-s['startedAt']))
  return min(value,s['limitSeconds']*1000) if s.get('limitSeconds') is not None else value
 def state(self):
  with self.lock:
   if self.current and self.current['status']=='running' and self.current.get('limitSeconds') is not None and self.elapsed()>=self.current['limitSeconds']*1000:self.finish('timeout')
   return {'session':self.current,'deck':self.deck,'serverTime':self.clock()*1000}
 def require(self,sid):
  if not self.current or sid!=self.current['id']:raise ValueError('路演轮次不匹配')
 def start(self,payload):
  with self.lock:
   if self.current and self.current['status']=='running':raise ValueError('请先结束当前路演')
   mode=payload.get('timingMode','timed')
   if mode not in ['timed','untimed']:raise ValueError('计时模式无效')
   page=payload.get('startPage',1) if mode=='untimed' else 1
   if type(page)!=int or not 1<=page<=len(self.deck['slides']):raise ValueError('起始页无效')
   profile=resolve_profile(self.root,payload.get('competitionProfile'))
   road_minutes=payload.get('roadshowMinutes',profile['roadshowMinutes'])
   if type(road_minutes)!=int or not 1<=road_minutes<=30:raise ValueError('路演时长需为1—30分钟')
   minutes=payload.get('defenseMinutes',profile['defenseMinutes'])
   if type(minutes)!=int or not 1<=minutes<=30:raise ValueError('答辩时长需为1—30分钟')
   if type(payload.get('chainDefense',False))!=bool:raise ValueError('串联选项无效')
   if self.current:(self.data/f"roadshow-{self.current['id']}.json").write_text(json.dumps(self.current,ensure_ascii=False,indent=2),encoding='utf8')
   self.current={'id':uuid.uuid4().hex[:12],'source':self.deck['source'],'sourceHash':self.deck['sha256'],'startedAt':self.clock()*1000,'status':'running','timingMode':mode,'practiceGoal':str(payload.get('practiceGoal',''))[:500],'chainDefense':payload.get('chainDefense',False),'defenseMinutes':minutes,'linkedDefenseId':None,'limitSeconds':600 if mode=='timed' else None,'page':page,'visits':[{'page':page,'startMs':0,'endMs':None}],'elapsedMs':0,'transcription':None,'jobId':None,'audioOffsetMs':0,'events':[],'camera':{},'report':None,'capabilities':payload.get('capabilities',{})}
   self.current['limitSeconds']=road_minutes*60 if mode=='timed' else None
   self.current['competition']=profile
   self.save();return self.state()
 def reset(self,sid):
  with self.lock:
   self.require(sid)
   if self.current['status']=='running':raise ValueError('请先结束路演')
   (self.data/f"roadshow-{sid}.json").write_text(json.dumps(self.current,ensure_ascii=False,indent=2),encoding='utf8')
   self.current=None;self.save();return self.state()
 def navigate(self,sid,page,at):
  with self.lock:
   self.require(sid)
   if self.current['status']!='running':return self.state()
   if not isinstance(page,int) or not 1<=page<=len(self.deck['slides']):raise ValueError('页码无效')
   if not isinstance(at,(float,int)) or not math.isfinite(at):raise ValueError('时间无效')
   at=max(self.current['visits'][-1]['startMs'],min(int(at),self.elapsed()))
   if page!=self.current['page']:
    if len(self.current['visits'])>=1000:raise ValueError('翻页记录已达上限，请结束本轮')
    self.current['visits'][-1]['endMs']=at;self.current['visits'].append({'page':page,'startMs':at,'endMs':None});self.current['page']=page
   self.save();return self.state()
 def finish(self,reason='manual'):
  with self.lock:
   s=self.current
   if s and s['status']=='running':
    end=self.elapsed();s['elapsedMs']=end;s['visits'][-1]['endMs']=end;s['status']='ended';s['reason']='timeout' if s.get('limitSeconds') is not None and end>=s['limitSeconds']*1000 else reason;self.save()
   return {'session':s,'deck':self.deck,'serverTime':self.clock()*1000}
 def metadata(self,sid,payload):
  with self.lock:
   self.require(sid)
   events=payload.get('events',[])
   if not isinstance(events,list) or len(events)>1000:raise ValueError('事件格式无效')
   for e in events:
    if not re_page(e.get('questionId'),len(self.deck['slides'])):raise ValueError('事件须绑定有效PPT页码')
    if not all(isinstance(e.get(k),(int,float)) and math.isfinite(e[k]) and e[k]>=0 for k in ['startMs','endMs']):raise ValueError('事件时间无效')
    if e['endMs']<e['startMs']:raise ValueError('事件时间倒置')
   self.current['events']=events;self.current['camera']=payload.get('camera',{});self.save();return self.state()
 def set_job(self,sid,jid,offset=0):
  with self.lock:self.require(sid);self.current['jobId']=jid;self.current['audioOffsetMs']=max(0,min(self.elapsed(),offset));self.save()
 def set_transcript(self,sid,result,error):
  with self.lock:
   if not self.current or self.current['id']!=sid:return
   self.current['transcription']=result;self.current['transcriptionError']=error
   if result:
    segments=result['segments'];offset=self.current.get('audioOffsetMs',0)/1000
    for visit in self.current['visits']:
     begin=visit['startMs']/1000;end=(visit['endMs'] if visit['endMs'] is not None else self.elapsed())/1000
     words=[w for seg in segments for w in seg.get('words',[]) if begin<=((w['start']+w['end'])/2+offset)<end]
     visit['transcript']=''.join(w['word'] for w in words);visit['editedText']=visit['transcript']
   self.save()
 def edit(self,sid,edits):
  with self.lock:
   self.require(sid)
   for e in edits:
    i=e.get('visit');text=e.get('text')
    if not isinstance(i,int) or not 0<=i<len(self.current['visits']) or not isinstance(text,str):raise ValueError('校对记录无效')
    self.current['visits'][i]['editedText']=text[:15000]
   self.save();return self.state()
 def report(self,sid,r):
  with self.lock:
   self.require(sid)
   if len(r.get('priorities',[]))!=3:raise ValueError('报告需要三项可执行改进')
   self.current['report']=r;self.save();return self.state()

def re_page(value,count):
 if not isinstance(value,str) or not value.startswith('P'):return False
 try:return 1<=int(value[1:])<=count
 except ValueError:return False
