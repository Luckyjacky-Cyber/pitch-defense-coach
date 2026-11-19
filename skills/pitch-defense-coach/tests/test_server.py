import server as s,unittest,threading,tempfile,json,urllib.request,urllib.error,time
from pathlib import Path
class Flow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(dir=s.ROOT/'tmp');s.DATA=Path(cls.tmp.name);s.SESSION=None
  cls.http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);cls.url=f'http://127.0.0.1:{cls.http.server_port}';threading.Thread(target=cls.http.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
 def setUp(self):
  s.SESSION=None;s.ENGINE.jobs.clear()
  s.ROAD=s.RoadshowStore(s.ROOT);s.ROAD.current=None
 def post(self,path,data):
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as r:return json.load(r)
 def test_lifecycle(self):
  st=self.post('/api/start',{'minutes':10,'summary':'测试：充分调研，性能稳定'});sid=st['session']['id'];self.assertEqual(st['session']['status'],'waiting_coach')
  self.assertEqual(st['remaining'],600)
  q={'sessionId':sid,'text':'请举一例说明调研如何影响选题？','dimension':'个人成长','source':'P5','candidateChains':[{'id':'research','gap':'调研记录'},{'id':'pilot','gap':'重复实验条件'}]}
  st=self.post('/api/coach/question',q);self.assertEqual(len(st['session']['candidateChains']),2)
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/coach/question',q)
  self.post('/api/pause',{});rem=s.snapshot()['remaining'];time.sleep(.02);self.assertEqual(s.snapshot()['remaining'],rem)
  self.post('/api/resume',{})
  a={'sessionId':sid,'questionId':'Q01','text':'我们去过很多单位。','events':[{'questionId':'Q02','startMs':1,'endMs':2000}]}
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/answer',a)
  a['events']=[];st=self.post('/api/answer',a);self.assertEqual(st['session']['status'],'waiting_coach')
  q['text']='支持“去过很多单位”这一判断的具体记录是什么？';self.post('/api/coach/question',q)
  a['questionId']='Q02';a['text']='暂时没有带记录，赛前会核对。';a['finish']=True;self.post('/api/answer',a)
  for i in ['Q01','Q02']:self.post('/api/coach/feedback',{'sessionId':sid,'questionId':i,'feedback':{'content':'测试','logic':'测试','evidence':'测试','rewrite':'测试','nonverbal':['未采集']}})
  report={'summary':'测试记录','dimensions':[{'name':n,'level':'弱','basis':'测试'} for n in s.KNOWLEDGE['ruleWeights']],'priorities':[{'action':'a','practice':'b','check':'c','questionIds':['Q01']}]*3}
  st=self.post('/api/coach/report',{'sessionId':sid,'report':report});self.assertEqual(st['session']['status'],'reviewed')
  self.post('/api/reset',{});self.assertFalse((s.DATA/'current.json').exists())
 def test_origin_and_paths(self):
  for path,headers in [('/api/state',{'Origin':'https://other.example'}),('/../server.py',{}),('/%2e%2e/server.py',{})]:
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(self.url+path,headers=headers))
 def test_speech_install_choice_is_explicit_and_does_not_install(self):
  for choice in ['skip','small','tiny']:
   result=self.post('/api/asr/setup-choice',{'choice':choice})
   self.assertEqual(result['status'],'skipped' if choice=='skip' else 'requested')
   self.assertEqual(s.snapshot()['speechSetup']['choice'],choice)
  self.assertFalse((s.ROOT/'.venv').exists())
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/asr/setup-choice',{'choice':'run arbitrary command'})
 def test_untimed_and_independent_clocks(self):
  st=self.post('/api/start',{'minutes':10,'timingMode':'untimed','practiceGoal':'证据范围'});sid=st['session']['id']
  self.assertIsNone(st['remaining'])
  self.post('/api/coach/question',{'sessionId':sid,'text':'对什么工况成立？','dimension':'项目创新'})
  s.SESSION['activeSince']=time.time()-1800
  with s.CHANGED:s.expire()
  self.assertEqual(s.SESSION['status'],'answering');self.assertGreater(s.elapsed(s.SESSION),1799)
  st=self.post('/api/answer',{'sessionId':sid,'questionId':'Q01','text':'仅在已测工况成立。'})
  self.assertEqual(st['session']['status'],'waiting_coach')
  self.post('/api/end',{})
  st=self.post('/api/start',{'minutes':3});sid=st['session']['id'];self.assertEqual(st['remaining'],180)
  self.post('/api/coach/question',{'sessionId':sid,'text':'核心证据是什么？','dimension':'项目创新'})
  s.SESSION['activeSince']=time.time()-181
  with s.CHANGED:s.expire()
  self.assertEqual(s.SESSION['status'],'time_up')
 def test_linked_roadshow_snapshot_and_recovery(self):
  now=[1000.];s.ROAD.clock=lambda:now[0]
  road=self.post('/api/roadshow/start',{'chainDefense':True,'defenseMinutes':5})['session'];sid=road['id']
  hand={'sessionId':sid,'confirmed':True}
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/handoff',hand)
  now[0]+=600
  self.assertEqual(s.ROAD.state()['session']['reason'],'timeout')
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/handoff',hand)
  self.post('/api/roadshow/edit',{'sessionId':sid,'edits':[{'visit':0,'text':'材料性能稳定，已有小试验证。'}]})
  s.ROAD.current['jobId']='test';s.ENGINE.jobs['test']={'status':'running'}
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/handoff',hand)
  s.ENGINE.jobs['test']['status']='done'
  st=self.post('/api/roadshow/handoff',hand);qa=st['session'];self.assertEqual(st['remaining'],300)
  self.assertEqual(qa['sourceRoadshow']['elapsedMs'],600000)
  self.assertEqual(qa['sourceRoadshow']['visits'][0]['editedText'],'材料性能稳定，已有小试验证。')
  self.assertEqual(self.post('/api/roadshow/handoff',hand)['session']['id'],qa['id'])
  s.ROAD.current['linkedDefenseId']=None
  self.assertEqual(self.post('/api/roadshow/handoff',hand)['session']['id'],qa['id'])
  self.post('/api/roadshow/edit',{'sessionId':sid,'edits':[{'visit':0,'text':'后来校对'}]})
  self.assertNotEqual(s.SESSION['sourceRoadshow']['visits'][0]['editedText'],'后来校对')
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/start',{})
 def test_focused_roadshow_exceeds_ten_minutes(self):
  now=[1000.];s.ROAD.clock=lambda:now[0]
  st=self.post('/api/roadshow/start',{'timingMode':'untimed','startPage':2,'practiceGoal':'只练技术解释'})
  sid=st['session']['id'];self.assertEqual(st['session']['page'],2)
  now[0]+=1200;self.assertEqual(s.ROAD.state()['session']['status'],'running')
  self.post('/api/roadshow/navigate',{'sessionId':sid,'page':1,'atMs':1200000})
  now[0]+=10;st=self.post('/api/roadshow/finish',{'sessionId':sid})
  self.assertEqual(st['session']['elapsedMs'],1210000)
  self.assertEqual(st['session']['reason'],'manual')
  recovered=s.RoadshowStore(s.ROOT);self.assertIsNone(recovered.current['limitSeconds'])
  self.assertEqual(recovered.elapsed(),1210000)
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/handoff',{'sessionId':sid,'confirmed':True})
 def test_static_assets_and_identity(self):
  for path in ['/','/roadshow.html','/app.js','/asr-choice.js','/vision.js','/system-prompt.txt','/technical-spec.txt','/deck.json']:
   with urllib.request.urlopen(self.url+path) as r:self.assertEqual(r.status,200)
  with urllib.request.urlopen(self.url+'/api/state') as r:self.assertEqual(json.load(r)['appId'],'pitch-defense-coach-v1')
  with urllib.request.urlopen(self.url+'/api/roadshow') as r:deck=json.load(r)['deck']
  for slide in deck['slides']:
   with urllib.request.urlopen(self.url+'/'+slide['image'].lstrip('/')) as r:self.assertEqual(r.status,200)
 def test_sanchuang_clocks_handoff_and_rubric(self):
  now=[1000.];s.ROAD.clock=lambda:now[0]
  road=self.post('/api/roadshow/start',{'competitionProfile':'sanchuang-regular','chainDefense':True})['session']
  self.assertEqual(road['limitSeconds'],480);self.assertEqual(road['defenseMinutes'],7)
  now[0]+=479;self.assertEqual(s.ROAD.state()['session']['status'],'running')
  now[0]+=1;self.assertEqual(s.ROAD.state()['session']['reason'],'timeout')
  self.post('/api/roadshow/edit',{'sessionId':road['id'],'edits':[{'visit':0,'text':'测试：我们服务商户，收入来自服务费。'}]})
  st=self.post('/api/roadshow/handoff',{'sessionId':road['id'],'confirmed':True});sid=st['session']['id']
  self.assertEqual(st['remaining'],420);self.assertEqual(st['session']['sourceRoadshow']['elapsedMs'],480000)
  self.assertEqual(len(st['session']['ruleWeights']),5)
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/coach/question',{'sessionId':sid,'text':'测试问题','dimension':'个人成长'})
  self.post('/api/coach/question',{'sessionId':sid,'text':'服务费如何计算？','dimension':'创业'})
  self.post('/api/answer',{'sessionId':sid,'questionId':'Q01','text':'需要核对账目。','finish':True})
  self.post('/api/coach/feedback',{'sessionId':sid,'questionId':'Q01','feedback':{'content':'测试','logic':'测试','evidence':'待补账目','rewrite':'不编造','nonverbal':[]}})
  report={'summary':'测试','dimensions':[{'name':n,'level':'缺失','basis':'本轮未覆盖'} for n in st['session']['ruleWeights']],'priorities':[{'action':'核对口径','practice':'重答两次','check':'口径一致','questionIds':['Q01']}]*3}
  duplicate=dict(report,dimensions=report['dimensions']+[report['dimensions'][0]])
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/coach/report',{'sessionId':sid,'report':duplicate})
  self.assertEqual(self.post('/api/coach/report',{'sessionId':sid,'report':report})['session']['status'],'reviewed')
 def test_sanchuang_practical_untimed_and_validation(self):
  st=self.post('/api/start',{'competitionProfile':'sanchuang-practical','timingMode':'untimed'})
  self.assertIsNone(st['remaining']);self.assertEqual(len(st['session']['ruleWeights']),7)
  self.post('/api/coach/question',{'sessionId':st['session']['id'],'text':'运营动作怎样留痕？','dimension':'创业过程'})
  self.post('/api/end',{})
  for invalid in [0,31,8.5,True,'8']:
   with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/start',{'roadshowMinutes':invalid})
  with self.assertRaises(urllib.error.HTTPError):self.post('/api/roadshow/start',{'competitionProfile':'unknown'})
  road=self.post('/api/roadshow/start',{'competitionProfile':'sanchuang-practical','roadshowMinutes':6})['session']
  self.assertEqual(road['limitSeconds'],360);self.assertFalse(road['chainDefense'])
  self.assertEqual(s.RoadshowStore(s.ROOT).current['competition']['id'],'sanchuang-practical')
if __name__=='__main__':unittest.main()
