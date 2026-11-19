"""Standard-library tests use isolated temporary instances, never real practice data."""
from pathlib import Path
import subprocess,sys,tempfile,json,base64,importlib.util,unittest,shutil,hashlib

SKILL=Path(__file__).resolve().parents[1]
def run(script,*args,ok=True):
 r=subprocess.run([sys.executable,'-X','utf8',str(SKILL/'scripts'/script),*map(str,args)],input='',capture_output=True,text=True,encoding='utf-8')
 if ok and r.returncode:raise RuntimeError(r.stderr)
 return r
def main():
 with tempfile.TemporaryDirectory(prefix='coach-skill-test-') as tmp:
  base=Path(tmp);app=base/'instance'
  run('bootstrap.py','--target',app)
  before=(app/'public/knowledge.json').read_bytes()
  assert run('bootstrap.py','--target',app,ok=False).returncode!=0
  assert (app/'public/knowledge.json').read_bytes()==before
  check=json.loads(run('setup_optional.py','--app',app,'--check').stdout)
  assert len(check['missingVision'])==8
  images=base/'images';images.mkdir()
  png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0msAAAAASUVORK5CYII=')
  for n in ['2.png','1.png']:(images/n).write_bytes(png)
  run('import_slides.py','--app',app,'--images',images)
  deck=json.loads((app/'public/deck.json').read_text(encoding='utf-8'))
  assert [x['originalFilename'] for x in deck['slides']]==['1.png','2.png']
  assert all((app/'public'/x['image']).read_bytes()==png for x in deck['slides'])
  assert run('import_slides.py','--app',app,'--images',images,ok=False).returncode!=0
  order=base/'order.json';order.write_text(json.dumps(['2.png','1.png']),encoding='utf-8')
  run('import_slides.py','--app',app,'--images',images,'--order',order,'--replace')
  assert len(list((app/'deck-history').glob('*.json')))==1
  sys.path.insert(0,str(app));(app/'tmp').mkdir()
  from roadshow_store import RoadshowStore
  now=[1000.0];store=RoadshowStore(app,clock=lambda:now[0]);sid=store.start({})['session']['id']
  now[0]+=20;store.navigate(sid,2,20000);now[0]+=580
  session=store.state()['session'];assert session['reason']=='timeout'
  assert sum(v['endMs']-v['startMs'] for v in session['visits'])==600000
  assert RoadshowStore(app).current['id']==sid
  from asr_engine import Engine
  engine=Engine(app);engine.load();assert engine.status['state']=='unavailable'
  spec=importlib.util.spec_from_file_location('flow_tests',SKILL/'tests/test_server.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(mod))
  if not result.wasSuccessful():raise RuntimeError('API tests failed')
  spec=importlib.util.spec_from_file_location('speech_tests',SKILL/'tests/test_speech_resources.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(mod))
  if not result.wasSuccessful():raise RuntimeError('Speech resource tests failed')
  confirmation=run('setup_optional.py','--app',app,'--asr','tiny')
  assert json.loads(confirmation.stdout)['state']=='confirmation_required'
  assert not (app/'.venv').exists()
  for path in SKILL.rglob('*.py'):compile(path.read_text(encoding='utf-8'),str(path),'exec')
  print('PASS: isolated bootstrap, overwrite protection, optional setup check, ordered slide import/archive, 600s deadline, session recovery, missing-ASR fallback, API lifecycle and origin guards')
if __name__=='__main__':main()
