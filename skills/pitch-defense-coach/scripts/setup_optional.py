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
 p=argparse.ArgumentParser();p.add_argument('--app',required=True);p.add_argument('--vision',action='store_true');p.add_argument('--asr',choices=['tiny','small']);p.add_argument('--check',action='store_true');a=p.parse_args()
 root=Path(a.app).resolve()
 if not (root/'server.py').is_file():p.error('请先用bootstrap创建训练实例')
 if a.check:
  print(json.dumps({'missingVision':[n for n in VISION if not (root/'public'/n).is_file()],'speechModels':{n:(root/f'models/whisper-{n}/model.bin').is_file() for n in ['tiny','small']},'note':'文件存在不代表识别效果通过验证；仍需开启工具测试。'},ensure_ascii=False));return
 if not a.vision and not a.asr:p.error('请选择 --vision、--asr 或 --check')
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
  env=root/'.venv';python=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
  if not python.exists():venv.EnvBuilder(with_pip=True).create(env)
  subprocess.run([str(python),'-m','pip','install','faster-whisper==1.2.1','opencc-python-reimplemented==0.1.7'],check=True)
  code="from huggingface_hub import snapshot_download;import sys;snapshot_download(repo_id='Systran/faster-whisper-'+sys.argv[1],local_dir=sys.argv[2],allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])"
  subprocess.run([str(python),'-c',code,a.asr,str(root/'models'/('whisper-'+a.asr))],check=True)
  print('请使用该虚拟环境启动，或运行 launch.py：',python)
if __name__=='__main__':main()
