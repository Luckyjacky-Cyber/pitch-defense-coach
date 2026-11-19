"""Install optional local analysis without modifying the system Python."""
from pathlib import Path
import argparse,json,subprocess,sys,urllib.request,venv,hashlib

BASE='https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22-rc.20250304/'
VISION={
 'vendor/vision.mjs':BASE+'vision_bundle.mjs',
 **{f'vendor/wasm/{name}':BASE+'wasm/'+name for name in ['vision_wasm_internal.js','vision_wasm_internal.wasm','vision_wasm_nosimd_internal.js','vision_wasm_nosimd_internal.wasm']},
 'models/face.task':'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
 'models/pose.task':'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
 'models/hand.task':'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--app',required=True);p.add_argument('--vision',action='store_true');p.add_argument('--asr',choices=['tiny','small']);p.add_argument('--check',action='store_true');p.add_argument('--discover',action='store_true');p.add_argument('--reuse-from',action='append',default=[]);p.add_argument('--register',action='store_true');p.add_argument('--yes',action='store_true');a=p.parse_args()
 root=Path(a.app).resolve()
 if not (root/'server.py').is_file():p.error('请先用bootstrap创建训练实例')
 sys.path.insert(0,str(root))
 from speech_resources import prepare, candidates, complete_model, configured
 if a.check:
  print(json.dumps({'missingVision':[n for n in VISION if not (root/'public'/n).is_file()],'speechModels':{n:complete_model(root/f'models/whisper-{n}') for n in ['tiny','small']},'configuredSpeech':configured(root),'note':'文件存在不代表可加载；用 --discover 离线验证。'},ensure_ascii=False));return
 if a.discover:
  print(json.dumps(prepare(root,a.reuse_from,register=a.register),ensure_ascii=False));return
 if not a.vision and not a.asr:p.error('请选择 --vision、--asr、--discover 或 --check')
 if a.vision:
  records=[]
  for name,url in VISION.items():
   dest=root/'public'/name;dest.parent.mkdir(parents=True,exist_ok=True)
   if not dest.exists():
    temp=dest.with_suffix(dest.suffix+'.part')
    with urllib.request.urlopen(url,timeout=90) as response,temp.open('wb') as out:
     while chunk:=response.read(1024*1024):out.write(chunk)
    if temp.stat().st_size<1000:raise RuntimeError('下载文件异常：'+name)
    temp.replace(dest)
   records.append({'path':name,'url':url,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()});print(name,flush=True)
  (root/'vision-downloads.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
 if a.asr:
  result=prepare(root,a.reuse_from,register=a.register)
  if result['state']=='ready':
   print(json.dumps({'state':'reused',**result['config'],'note':'已复用本机可用语音环境，无需下载。'},ensure_ascii=False));return
  if not a.yes:
   if not sys.stdin.isatty():
    print(json.dumps({'state':'confirmation_required','model':a.asr,'note':'请在聊天或页面确认安装后使用 --yes；当前未下载任何文件。'},ensure_ascii=False));return
   try:approved=input('未找到可用语音环境。是否联网安装语音依赖与模型？[y/N] ').strip().lower()=='y'
   except EOFError:approved=False
   if not approved:print('已跳过安装，可继续文字训练。');return
  env=root/'.venv';python=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
  if not python.exists():venv.EnvBuilder(with_pip=True).create(env)
  subprocess.run([str(python),'-m','pip','install','faster-whisper==1.2.1','opencc-python-reimplemented==0.1.7'],check=True)
  existing=candidates(root,a.reuse_from)[1][a.asr]
  if not existing:
   code="from huggingface_hub import snapshot_download;import sys;snapshot_download(repo_id='Systran/faster-whisper-'+sys.argv[1],local_dir=sys.argv[2],allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])"
   subprocess.run([str(python),'-c',code,a.asr,str(root/'models'/('whisper-'+a.asr))],check=True)
  result=prepare(root,a.reuse_from,register=a.register)
  if result['state']!='ready':raise RuntimeError('安装后仍未通过本机加载验证，请检查平台兼容性；没有标记为已就绪。')
  choice=root/'data/speech-setup-choice.json'
  if choice.exists():choice.write_text(json.dumps({'choice':a.asr,'status':'completed','note':'已通过模型加载验证，重启页面服务后生效。'},ensure_ascii=False),encoding='utf-8')
  print('请使用该虚拟环境启动，或运行 launch.py：',python)
if __name__=='__main__':main()
