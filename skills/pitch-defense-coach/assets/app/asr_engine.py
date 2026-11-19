import io,threading,time,uuid,re,json
from pathlib import Path
from speech_resources import model_paths, complete_model, configured


class Engine:
 def __init__(self,root):
  self.root=Path(root);self.models={};self.lock=threading.Lock();self.jobs={};self.jobs_lock=threading.Lock()
  self.paths=model_paths(root)
  config=json.loads((self.root/'public/glossary.json').read_text(encoding='utf-8'))
  self.terms=config.get('terms',[]);self.suggestions=config.get('suggestions',{})
  self.status={'state':'loading','detail':'本机中文模型正在加载','defaultModel':'small','terms':self.terms}
 def load(self):
  try:
   name=configured(self.root).get('defaultModel') or ('small' if complete_model(self.paths['small']) else 'tiny')
   self.model(name);self.status.update(state='ready',defaultModel=name,detail='准确优先模型已就绪 · 支持专业词提示' if name=='small' else '快速模型已就绪 · 准确优先模型尚未安装')
  except Exception as e:self.status.update(state='unavailable',needsSetup=True,detail='语音环境尚未就绪，可选择安装/修复或继续文字训练。',diagnostic=str(e)[:160])
 def model(self,name):
  if name not in ['small','tiny']:raise ValueError('请选择准确优先或快速转写')
  if name not in self.models:
   from faster_whisper import WhisperModel
   path=self.paths[name]
   if not (path/'model.bin').exists():raise ValueError('该本机模型尚未安装')
   self.models[name]=WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
  return self.models[name]
 def transcribe(self,body,model='small',terms='',limit=190,progress=None):
  import av,numpy as np
  from opencc import OpenCC
  convert=OpenCC('t2s').convert
  glossary=list(dict.fromkeys(self.terms+[x.strip() for x in re.split(r'[,，;；\n]',terms[:1000]) if x.strip()]))[:60]
  with self.lock:
   if progress:progress(0,'正在解码录音')
   resampler=av.audio.resampler.AudioResampler(format='s16',layout='mono',rate=16000);arrays=[];samples=0
   with av.open(io.BytesIO(body),mode='r') as container:
    for frame in container.decode(audio=0):
     for f in resampler.resample(frame):
      a=f.to_ndarray().flatten();arrays.append(a);samples+=len(a)
      if samples>(limit+20)*16000:raise ValueError('录音超出本轮允许时长')
    for f in resampler.resample(None):arrays.append(f.to_ndarray().flatten())
   if not arrays:raise ValueError('没有可解码的音频')
   waveform=np.concatenate(arrays).astype(np.float32)/32768.0
   waveform=waveform[:limit*16000]
   m=self.model(model)
   segs,info=m.transcribe(waveform,language='zh',task='transcribe',beam_size=5,temperature=0,word_timestamps=True,vad_filter=True,vad_parameters={'min_silence_duration_ms':650,'speech_pad_ms':300},condition_on_previous_text=False,initial_prompt='简体中文科研路演逐字记录，保留口语。专业词汇：'+ '、'.join(glossary),hotwords=' '.join(glossary),hallucination_silence_threshold=2)
   result=[]
   for s in segs:
    if s.no_speech_prob>.8 and s.avg_logprob<-.8:continue
    words=[{'word':convert(w.word),'start':w.start,'end':w.end,'probability':w.probability} for w in s.words or []]
    result.append({'start':s.start,'end':s.end,'text':convert(s.text),'rawText':s.text,'words':words,'needsReview':s.avg_logprob<-.65 or any(w['probability']<.45 for w in words)})
    if progress:progress(min(99,int(s.end/max(info.duration,.1)*100)),'正在识别录音')
   raw=''.join(s['rawText'] for s in result);text=''.join(s['text'] for s in result)
   suggestions=[{'heard':a,'suggested':b,'reason':'常见同音误识别，请回听确认后采纳'} for a,b in self.suggestions.items() if a in text]
   return {'text':text,'rawText':raw,'segments':result,'duration':info.duration,'mode':'local-whisper-'+model,'model':model,'suggestions':suggestions,'reviewSegments':[{'start':s['start'],'end':s['end'],'text':s['text']} for s in result if s['needsReview']],'note':'只做简繁规范化；未自动改专业词、数字或倍数。口音与术语仍需回听校对。'}
 def start_job(self,body,model,terms,limit,on_done=None):
  with self.jobs_lock:
   self.jobs={k:v for k,v in self.jobs.items() if time.time()-v['created']<3600}
   if sum(j['status'] in ['queued','running'] for j in self.jobs.values())>=2:raise ValueError('已有转写任务，请等待完成')
   jid=uuid.uuid4().hex;self.jobs[jid]={'id':jid,'status':'queued','progress':0,'detail':'等待本机转写','created':time.time()}
  def progress(p,d):
   with self.jobs_lock:self.jobs[jid].update(status='running',progress=p,detail=d)
  def work():
   try:
    result=self.transcribe(body,model,terms,limit,progress)
    with self.jobs_lock:self.jobs[jid].update(status='done',progress=100,result=result,detail='转写完成，请校对')
    if on_done:on_done(result,None)
   except Exception as e:
    with self.jobs_lock:self.jobs[jid].update(status='error',error=str(e)[:240],detail='转写失败，时间记录仍然保留')
    if on_done:on_done(None,str(e)[:240])
  threading.Thread(target=work,daemon=True).start();return self.jobs[jid].copy()
