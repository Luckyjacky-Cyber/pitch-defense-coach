"""Launch this app only, with optional speech venv and hidden Windows process."""
from pathlib import Path
import argparse,json,subprocess,sys,time,urllib.request,webbrowser
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8769);p.add_argument('--roadshow',action='store_true');p.add_argument('--no-browser',action='store_true');a=p.parse_args()
 root=Path(__file__).resolve().parent;base=f'http://127.0.0.1:{a.port}'
 def alive():
  try:
   with urllib.request.urlopen(base+'/api/state',timeout=2) as r:data=json.load(r)
  except Exception:return False
  if data.get('appId')!='pitch-defense-coach-v1' or Path(data.get('instanceRoot','')).resolve()!=root:
   raise RuntimeError('该端口已由其他工具/项目占用，请使用 --port 选择其他端口。')
  return True
 if not alive():
  py=root/'.venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
  options={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {'start_new_session':True}
  with (root/'server.log').open('a',encoding='utf-8') as log:
   subprocess.Popen([str(py) if py.exists() else sys.executable,str(root/'server.py'),'--port',str(a.port)],cwd=root,stdout=log,stderr=log,**options)
  for i in range(50):
   if alive():break
   time.sleep(.2)
  else:raise RuntimeError('启动失败。查看server.log，或在终端运行 python server.py。')
 url=base+('/roadshow.html' if a.roadshow else '/')
 if not a.no_browser:webbrowser.open(url)
 print(url)
if __name__=='__main__':main()
