import unittest,tempfile,os,json,sys
from pathlib import Path
from unittest.mock import patch
import speech_resources as sr

class SpeechResources(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name).resolve();self.app=self.base/'new-project';self.app.mkdir()
  self.registry=self.base/'registry.json'
  self.env=patch.dict(os.environ,{'PDC_SPEECH_REGISTRY':str(self.registry),'HF_HUB_CACHE':str(self.base/'empty-cache')});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def provider(self,name='old-project'):
  p=self.base/name;p.mkdir();(p/'server.py').touch();(p/'runtime').mkdir();return p
 def model(self,p,name='small'):
  d=p/'models'/('whisper-'+name);d.mkdir(parents=True)
  for n in (*sr.REQUIRED,'vocabulary.json'):(d/n).write_text('{}')
  return d
 def test_reuse_register_and_independent_project(self):
  old=self.provider();model=self.model(old);tiny=self.model(old,'tiny');sentinel=old/'private-answer.txt';sentinel.write_text('private')
  def check(env,path,timeout):return (env['runtime']==str(old/'runtime'),'dependency mismatch')
  result=sr.prepare(self.app,check=check,register=True)
  self.assertEqual(result['state'],'ready');self.assertEqual(result['config']['models'],{'small':str(model),'tiny':str(tiny)})
  self.assertFalse((self.app/'models').exists());self.assertFalse((self.app/'private-answer.txt').exists());self.assertEqual(sentinel.read_text(),'private')
  far=self.base/'separate-agent'/'instance';far.mkdir(parents=True)
  self.assertEqual(sr.prepare(far,check=check)['state'],'ready')
  self.assertEqual(sr.configured(far)['runtime'],str(old/'runtime'))
 def test_broken_cache_and_failed_loading_not_ready(self):
  old=self.provider();d=self.model(old);(d/'tokenizer.json').unlink()
  calls=[]
  def check(*a,**kw):calls.append(a);return False,'incompatible'
  self.assertEqual(sr.prepare(self.app,check=check)['state'],'needs_setup');self.assertEqual(calls,[])
  (d/'tokenizer.json').write_text('{}')
  self.assertEqual(sr.prepare(self.app,check=check)['state'],'needs_setup');self.assertTrue(calls);self.assertFalse((self.app/sr.CONFIG).exists())
 def test_explicit_location_and_stale_registration(self):
  self.registry.write_text(json.dumps({'python':'/missing/python','models':{'small':'/missing/model'}}))
  elsewhere=self.base/'different-platform';elsewhere.mkdir();self.model(elsewhere)
  result=sr.prepare(self.app,extra=[elsewhere],check=lambda *a,**k:(True,''))
  self.assertEqual(result['state'],'ready')
 def test_probe_failure_and_no_network_download(self):
  ok,reason=sr.probe({'python':str(self.base/'nonexistent'),'runtime':None},self.base/'model')
  self.assertFalse(ok);self.assertTrue(reason)
 def test_engine_uses_verified_default_after_larger_model_fails(self):
  from asr_engine import Engine
  self.model(self.app,'small');self.model(self.app,'tiny')
  (self.app/'public').mkdir();(self.app/'public/glossary.json').write_text('{}')
  (self.app/sr.CONFIG).write_text(json.dumps({'defaultModel':'tiny'}))
  engine=Engine(self.app)
  with patch.object(engine,'model') as load:
   engine.load();load.assert_called_once_with('tiny')
  self.assertEqual(engine.status['defaultModel'],'tiny')

if __name__=='__main__':unittest.main()
