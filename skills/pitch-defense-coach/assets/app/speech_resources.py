"""Offline, bounded discovery of reusable faster-whisper resources. No downloads."""
from pathlib import Path
import json, os, subprocess, sys, time

CONFIG = 'speech-resources.json'
REQUIRED = ('model.bin', 'config.json', 'tokenizer.json')

def read_json(path):
 try:
  value=json.loads(Path(path).read_text(encoding='utf-8'))
  return value if isinstance(value,dict) else {}
 except (OSError,ValueError):return {}

def registry_path():
 return Path(os.environ.get('PDC_SPEECH_REGISTRY',Path.home()/'.cache/pitch-defense-coach/speech-resources.json'))

def complete_model(path):
 path=Path(path)
 try:return all((path/n).is_file() and (path/n).stat().st_size for n in REQUIRED) and any(path.glob('vocabulary.*'))
 except OSError:return False

def candidates(root, extra=()):
 """Inspect known app locations/cache entries; never recursively scan a disk."""
 root=Path(root).resolve();roots=[root,*map(lambda p:Path(p).expanduser().resolve(),extra)]
 try:
  roots.extend([p for p in sorted(root.parent.iterdir()) if p.is_dir() and (p/'server.py').is_file()][:80])
 except OSError:pass
 configs=[read_json(root/CONFIG),read_json(registry_path())]
 configs.extend(read_json(p/CONFIG) for p in roots[1:])
 envs=[];models={'small':[],'tiny':[]}
 def env(py,runtime=None):
  if py and Path(py).is_file():
   v={'python':str(Path(py).resolve()),'runtime':str(Path(runtime).resolve()) if runtime and Path(runtime).is_dir() else None}
   if v not in envs:envs.append(v)
 def model(name,path):
  if name in models and isinstance(path,str) and complete_model(path):
   path=str(Path(path).resolve())
   if path not in models[name]:models[name].append(path)
 for c in configs:
  env(c.get('python'),c.get('runtime'))
  for name,path in c.get('models',{}).items():model(name,path)
 for p in roots:
  env(p/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))
  env(sys.executable,p/'runtime')
  for name in models:model(name,str(p/'models'/('whisper-'+name)))
 env(sys.executable)
 hub=Path(os.environ.get('HF_HUB_CACHE',Path(os.environ.get('HF_HOME',Path.home()/'.cache/huggingface'))/'hub'))
 for name in models:
  snapshots=hub/('models--Systran--faster-whisper-'+name)/'snapshots'
  try:
   for p in sorted(snapshots.iterdir())[:8]:model(name,str(p))
  except OSError:pass
 return envs,models

PROBE = '''import sys,json
if sys.argv[1]:sys.path.insert(0,sys.argv[1])
import av,numpy,opencc
from faster_whisper import WhisperModel
m=WhisperModel(sys.argv[2],device="cpu",compute_type="int8",cpu_threads=2,local_files_only=True)
print(json.dumps({"ok":True}))
'''

def probe(environment, model_path, timeout=12):
 env=os.environ.copy();env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
 try:
  r=subprocess.run([environment['python'],'-I','-X','utf8','-c',PROBE,environment.get('runtime') or '',str(model_path)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,env=env,**options)
  if r.returncode==0 and r.stdout.strip().endswith('{"ok": true}'):return True,''
  return False,(r.stderr or r.stdout)[-400:]
 except (OSError,subprocess.TimeoutExpired) as e:return False,str(e)[:400]

def discover(root, extra=(), check=probe, budget=40):
 envs,models=candidates(root,extra);errors=[];deadline=time.monotonic()+budget;attempts=0
 for name in ('small','tiny'):
  for path in models[name]:
   for env in envs:
    left=deadline-time.monotonic()
    if left<=0 or attempts>=16:break
    attempts+=1;ok,reason=check(env,path,timeout=min(12,left))
    if ok:
     verified={name:path}
     for other in models:
      if other==name:continue
      for other_path in models[other]:
       left=deadline-time.monotonic()
       if left<=0:break
       if check(env,other_path,timeout=min(12,left))[0]:verified[other]=other_path;break
     return {'state':'ready','config':{**env,'models':verified,'defaultModel':name},'availableModels':models}
    errors.append(reason)
   if time.monotonic()>=deadline or attempts>=16:break
  if time.monotonic()>=deadline or attempts>=16:break
 return {'state':'needs_setup','availableModels':models,'detail':'未找到通过加载验证的语音环境；可选择安装/修复或先练文字。','errors':errors[-2:]}

def prepare(root, extra=(), check=probe, register=False):
 root=Path(root);result=discover(root,extra,check=check)
 if result['state']=='ready':
  config=result['config'];(root/CONFIG).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
  if register:
   target=registry_path();target.parent.mkdir(parents=True,exist_ok=True)
   target.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
 return result

def configured(root):
 return read_json(Path(root)/CONFIG)

def model_paths(root):
 config=configured(root)
 return {name:Path(config.get('models',{}).get(name,Path(root)/'models'/('whisper-'+name))) for name in ('small','tiny')}

def activate(root):
 """Called by server.py before imports; re-exec only with a verified local Python."""
 root=Path(root).resolve()
 if os.environ.get('PDC_SPEECH_PREPARED')!=str(root):
  result=prepare(root)
  if result['state']=='ready':
   py=result['config']['python']
   if Path(py).resolve()!=Path(sys.executable).resolve():
    os.environ['PDC_SPEECH_PREPARED']=str(root)
    os.execv(py,[py,str(root/'server.py'),*sys.argv[1:]])
 config=configured(root)
 if config.get('runtime'):sys.path.insert(0,config['runtime'])
