import {loadVision,errorText} from './vision.js';
import {createAsrChoice} from './asr-choice.js';
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let deck,knowledge,state,session,qid,stream,mic,vision,recorder,audioCtx,analyser,recording=false,processing=false,chunks=[],originalTranscript='',audioSegments=[],events=[],cameraResult={},answerStart=0,recordStart=0,lastQuiet=null,speechSeen=false,stopPromise=null,finishPending=false,cameraEnabled=false,silenceMonitor=null;
let replayUrl=null;
const updateAsrChoice=createAsrChoice($('#asrModel'));
let activeTiming=false,localRemaining=600,lastSync=performance.now(),renderRevision=-1;
const api=async(path,data)=>{const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const v=await r.json();if(!r.ok)throw new Error(v.error||'请求失败');return v;};
const notice=s=>$('#notice').textContent=s;
const save=(filename,text,type='text/plain;charset=utf-8')=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
const labelTime=ms=>(ms/1000).toFixed(1)+'秒';
function show(which){for(const id of ['setup','training','review'])$('#'+id).hidden=id!==which;}
function currentQuestion(){return session?.questions?.at(-1);}
function ensureAnswer(){if(answerStart)return;answerStart=performance.now();if(vision?.base)vision.begin(qid,answerStart);}
let cameraBusy=false;
function cameraButtons(){
 $('#postureMode').disabled=cameraBusy;$('#cameraBtn').disabled=cameraBusy;$('#retryVision').disabled=cameraBusy;
 $('#retryVision').hidden=!cameraEnabled||!!vision?.running;
 $('#calibrateBtn').disabled=cameraBusy||!vision?.running;
}
async function retryVision(){
 if(cameraBusy||!cameraEnabled)return;
 cameraBusy=true;cameraButtons();vision?.stop();vision=null;
 try{vision=await loadVision($('#video'),t=>{$('#visionStatus').textContent=t;if(vision?.base&&answerStart&&session?.status==='answering'&&!vision.analyzing)vision.begin(qid,answerStart);},cameraButtons,{mode:$('#postureMode').value,onReadiness:t=>$('#visionReadiness').textContent=t});}
 finally{cameraBusy=false;cameraButtons();}
}
async function enableCamera(){
 if(cameraBusy)return;
 if(cameraEnabled){
  vision?.stop();vision=null;stream?.getTracks().forEach(t=>t.stop());stream=null;cameraEnabled=false;
  $('#video').srcObject=null;$('#cameraPlaceholder').hidden=false;$('#cameraBtn').textContent='开启摄像头';
  $('#visionStatus').textContent='摄像头已关闭，不生成视觉反馈';$('#visionReadiness').textContent='等待开启摄像头。';cameraButtons();return;
 }
 cameraBusy=true;cameraButtons();$('#visionStatus').textContent='正在连接摄像头…';
 try{
  stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},frameRate:{ideal:15,max:24}},audio:false});
  $('#video').srcObject=stream;await $('#video').play();
  cameraEnabled=true;$('#cameraPlaceholder').hidden=true;$('#cameraBtn').textContent='关闭摄像头';
  stream.getVideoTracks()[0].addEventListener('ended',()=>{
   vision?.stop();vision=null;cameraEnabled=false;$('#video').srcObject=null;$('#cameraPlaceholder').hidden=false;
   $('#cameraBtn').textContent='开启摄像头';$('#visionStatus').textContent='摄像头连接已被系统中断，请检查设备连接或权限后重新开启。';cameraButtons();
  },{once:true});
 }catch(e){
  stream?.getTracks().forEach(t=>t.stop());stream=null;$('#video').srcObject=null;
  $('#visionStatus').textContent='摄像头未能开启：'+errorText(e)+'。仍可练习内容。';
 }finally{cameraBusy=false;cameraButtons();}
 if(cameraEnabled)await retryVision();
}
async function enableMic(){
 try{if(!mic||!mic.getAudioTracks().some(t=>t.readyState==='live'))mic=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});$('#micBtn').textContent='麦克风已启用';$('#audioStatus').textContent=state?.asr?.state==='ready'?'本机中文转写已就绪 · 音频不上传外网':'麦克风可用，转写模型尚未就绪';return true;}catch(e){$('#audioStatus').textContent='未能开启麦克风，可直接输入回答';return false;}
}
function addAudioEvent(type,start,end,detail){if(end-start<3000)return;events.push({id:crypto.randomUUID(),questionId:qid,type,startMs:Math.round(start-answerStart),endMs:Math.round(end-answerStart),durationSeconds:+((end-start)/1000).toFixed(1),source:'local-microphone',confidence:'中',detail,review:'待确认'});}
function monitorSilence(){
 if(!recording)return;const now=performance.now(),buf=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(buf);const rms=Math.sqrt(buf.reduce((s,v)=>s+v*v,0)/buf.length);
 if(rms>.018){if(lastQuiet&&speechSeen)addAudioEvent('回答中停顿',lastQuiet,now,'音量低于阈值超过3秒；可能含思考或环境影响');lastQuiet=null;speechSeen=true;}
 else if(speechSeen&&!lastQuiet)lastQuiet=now;
 $('#recordStatus').textContent=`正在录音 ${Math.floor((now-recordStart)/1000)}秒 · 停止后在本机转写`;
 if(now-recordStart>180000){stopRecord();return;}silenceMonitor=setTimeout(monitorSilence,100);
}
async function startRecord(){
 if(processing||!qid||session?.status!=='answering')return;
 if(!(await enableMic()))return;
 ensureAnswer();audioCtx=audioCtx||new AudioContext();await audioCtx.resume();analyser=audioCtx.createAnalyser();analyser.fftSize=1024;audioCtx.createMediaStreamSource(mic).connect(analyser);
 const type=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
 recorder=new MediaRecorder(mic,type?{mimeType:type}:{});chunks=[];recordStart=performance.now();lastQuiet=null;speechSeen=false;
 recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
 stopPromise=new Promise(resolve=>recorder.onstop=async()=>{
  processing=true;$('#recordBtn').disabled=true;$('#submitBtn').disabled=true;$('#recordStatus').textContent='本机转写中，请稍候…';
  const startedAt=recordStart, mime=recorder.mimeType||'audio/webm';let pausedByAsr=false;
  try{
   vision?.pause();if(session?.status==='answering'){render(await api('pause',{}));pausedByAsr=true;}
   const blob=new Blob(chunks,{type:mime});chunks=[];
   if(replayUrl)URL.revokeObjectURL(replayUrl);replayUrl=URL.createObjectURL(blob);$('#replay').src=replayUrl;$('#asrReview').hidden=false;
   const res=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':mime,'X-ASR-Model':$('#asrModel').value,'X-Glossary':encodeURIComponent($('#glossary').value)},body:blob});const t=await res.json();if(!res.ok)throw new Error(t.error);
   const prefix=$('#answer').value.trim();$('#answer').value=prefix+(prefix?'\n':'')+t.text;originalTranscript+=(originalTranscript?'\n':'')+(t.rawText||t.text);
   $('#rawAsr').textContent=t.rawText||t.text;$('#asrHints').textContent=(t.reviewSegments?.length?`有${t.reviewSegments.length}处识别不确定，请回听确认。`:'')+(t.suggestions||[]).map(x=>`“${x.heard}”可能是“${x.suggested}”，请自行确认。`).join(' ')+' 数字、单位和倍数不会自动改成PPT数值。';
   audioSegments.push(...t.segments.map(s=>({...s,offsetMs:startedAt-answerStart})));
   $('#recordStatus').textContent=t.text?'转写完成，请检查数字和专业名词':'未识别到清晰语音，可重录或输入';
  }catch(e){$('#recordStatus').textContent=e.message;}finally{
   processing=false;recorder=null;if(pausedByAsr&&!finishPending){try{render(await api('resume',{}));vision?.resume();}catch{}}
   $('#recordBtn').disabled=false;$('#recordBtn').textContent='继续录音';$('#recordBtn').classList.remove('recording');$('#submitBtn').disabled=false;renderEvents();resolve();
  }
 });
 recorder.start();recording=true;$('#recordBtn').textContent='停止并转写';$('#recordBtn').classList.add('recording');monitorSilence();
}
async function stopRecord(){if(!recording)return stopPromise;recording=false;processing=true;clearTimeout(silenceMonitor);if(lastQuiet)addAudioEvent('回答中停顿',lastQuiet,performance.now(),'音量低于阈值超过3秒；尾部停顿可忽略');lastQuiet=null;recorder.stop();return stopPromise;}
function speechStats(){
 events=events.filter(e=>e.type!=='语速阶段性加快');
 const words=audioSegments.flatMap(s=>(s.words||[]).map(w=>({...w,startMs:s.offsetMs+w.start*1000,endMs:s.offsetMs+w.end*1000})));
 const fillers=[];for(const s of audioSegments){for(const m of s.text.matchAll(/嗯+|呃+|啊+|然后|就是/g)){fillers.push({word:m[0],startMs:s.offsetMs+s.start*1000,endMs:s.offsetMs+s.end*1000});}}
 const windows=[];const end=Math.max(0,...words.map(w=>w.endMs));
 for(let start=0;start+15000<=end;start+=15000){const ws=words.filter(w=>w.startMs>=start&&w.startMs<start+15000);const n=ws.reduce((sum,w)=>sum+(w.word.match(/[\u3400-\u9fffA-Za-z0-9]/g)||[]).length,0);windows.push({startMs:start,endMs:start+15000,cpm:n*4});}
 if(windows.length>=3){const baseline=(windows[0].cpm+windows[1].cpm)/2;for(const w of windows.slice(2))if(baseline>60&&w.cpm>baseline*1.35)events.push({id:crypto.randomUUID(),questionId:qid,type:'语速阶段性加快',...w,durationSeconds:15,source:'local-asr',confidence:'低',detail:`15秒窗口约${w.cpm}字/分钟，高于本人前30秒基线；需核对转写时间戳`,review:'待确认'});}
 return {mode:words.length?'local-whisper':'text-only',fillers,windows,segments:audioSegments,limitation:'填充词来自自动转写，只是可复核下限；然后、就是也可能具有正常语义。'};
}
function renderEvents(){const all=[...events,...(vision?.tracker.events||[])];const box=$('#eventReview');box.hidden=all.length===0;box.innerHTML='<b>可复核的观测事件</b><p>取消勾选误检或查阅资料引起的动作；教练不会把这些动作等同于紧张。</p>'+all.map(e=>`<label><input type="checkbox" data-eid="${esc(e.id)}" checked>${esc(e.type)} · ${labelTime(e.startMs)}—${labelTime(e.endMs)}（${esc(e.confidence)}可信度）</label>`).join('');}
async function submitAnswer(finish=false){
 if(processing)return notice('请等待本机转写完成');
 if(recording)await stopRecord();
 const text=$('#answer').value.trim();if(!text)return notice('请先录音转写或输入回答');
 ensureAnswer();const stats=speechStats();cameraResult=vision?.end()||{events:[],coverage:0,calibrated:false};
 const unchecked=new Set([...document.querySelectorAll('[data-eid]:not(:checked)')].map(e=>e.dataset.eid));
 const all=[...events,...cameraResult.events].map(e=>({...e,review:unchecked.has(e.id)?'本人标记误检':'待确认'}));
 $('#submitBtn').disabled=true;notice('正在提交给教练…');
 try{state=await api('answer',{sessionId:session.id,questionId:qid,text,originalTranscript,events:all,audio:stats,camera:{enabled:cameraEnabled,coverage:cameraResult.coverage,calibrated:cameraResult.calibrated,mode:cameraResult.mode,channels:cameraResult.channels,coverageByChannel:cameraResult.coverageByChannel},durationSeconds:(performance.now()-answerStart)/1000,finish});notice('已提交。教练会根据这次回答决定下一问。');render(state);}catch(e){notice(e.message);$('#submitBtn').disabled=false;}
}
function resetAnswer(q){if(replayUrl)URL.revokeObjectURL(replayUrl);replayUrl=null;$('#replay').removeAttribute('src');$('#asrReview').hidden=true;qid=q.id;answerStart=0;originalTranscript='';audioSegments=[];events=[];cameraResult={};$('#answer').value='';$('#eventReview').hidden=true;$('#recordStatus').textContent='可录音后检查转写，也可直接输入';$('#recordBtn').textContent='开始录音';notice('');}
function render(s){
 updateAsrChoice(s.asr);
 const previousId=session?.id;state=s;session=s.session;if(previousId!==session?.id)qid=null;localRemaining=s.remaining??600;lastSync=performance.now();activeTiming=session?.status==='answering';
 $('#audioStatus').textContent=s.asr.detail;$('#coachStatus').textContent=s.coachOnline?'教练已连接':'等待当前聊天接入';
 if(!session){show('setup');return;}
 if(['ended','reviewed'].includes(session.status)){show('review');$('#reviewStatus').textContent=session.report?'逐题证据与动作反馈已完成。以下等级仅作训练参考。':'本轮已结束。请让当前聊天中的教练生成报告；已答内容仍可下载。';$('#reviewStatus').textContent+=' '+phaseSummary();renderReport();return;}
 $('#stageSummary').textContent=session.sourceRoadshow?`已接入路演 ${session.sourceRoadshow.source}（${Math.round(session.sourceRoadshow.elapsedMs/1000)}秒）· 答辩独立计时，等待教练和转写不计时。请在聊天发送“开始串联答辩”。`:session.practiceGoal?`本轮目标：${session.practiceGoal}`:'';
 show('training');if(!$('#cameraSlot').children.length)$('#cameraSlot').append($('.preflight'));
 const q=currentQuestion();if(q&&q.id!==qid)resetAnswer(q);
 const enabled=['answering','paused','time_up'].includes(session.status)&&q&&!q.answer;
 $('#answer').disabled=!enabled;$('#recordBtn').disabled=!enabled||processing||session.status!=='answering'||s.asr.state!=='ready';$('#submitBtn').disabled=!enabled||processing;$('#pauseBtn').disabled=!['answering','paused'].includes(session.status);$('#pauseBtn').textContent=session.status==='paused'?'继续':'暂停';
 if(q){$('#question').textContent=q.text;$('#qid').textContent=q.id;$('#dimension').textContent=q.dimension;$('#sourceLabel').textContent=q.source||'基于你的材料与本轮回答';const m=(q.source||'').match(/P(\d+)/);const slide=m?deck.slides[Number(m[1])-1]:null;if(slide){$('#slidePreview').src=slide.image;$('#slidePreview').hidden=false;}else $('#slidePreview').hidden=true;}
 $('#timerState').textContent=({answering:'回答中',paused:'已暂停',waiting_coach:'等待教练 · 暂停计时',time_up:'时间到 · 提交后复盘'})[session.status]||'';
 if(session.status==='waiting_coach')notice(q?'回答已提交，等待教练继续追问。':'请回到当前聊天发送“开始模拟”，我会接入。');
 if(session.status==='time_up'){notice('本轮时间已到，请提交当前回答或结束复盘。');if(recording)stopRecord();}
 if(renderRevision!==s.revision){$('#history').innerHTML=session.questions.filter(q=>q.answer).map(q=>`<details><summary>${esc(q.id)} · ${esc(q.text)}</summary><p>${esc(q.answer.text)}</p></details>`).join('');renderRevision=s.revision;}
}
function phaseSummary(){const road=session?.sourceRoadshow;return (road?`路演实际用时：${(road.elapsedMs/1000).toFixed(1)}秒；`:'')+`答辩有效用时：${(session?.elapsed||0).toFixed(1)}秒${session?.duration===null?'（不计时专项）':'（独立计时）'}。`;}
function reportText(){if(!session)return '';let lines=['项目模拟答辩反馈','训练参考，不代表官方评分。',phaseSummary()];
 if(session.report){const r=session.report;lines.push(r.summary||'','本轮赛事各维度证据充分度',...r.dimensions.map(x=>`${x.name}：${x.level}。${x.basis}`),'下一轮优先修正的3件事',...r.priorities.map((p,i)=>`${i+1}. ${p.action}\n练法：${p.practice}\n验收：${p.check}\n关联：${p.questionIds?.join('、')||''}`));}
 for(const q of session.questions){lines.push('\n'+q.id+' '+q.text,'回答：'+(q.answer?.text||'未回答'));if(q.feedback){lines.push('内容：'+(q.feedback.content||''),'逻辑：'+(q.feedback.logic||''),'证据：'+(q.feedback.evidence||''),'改法：'+(q.feedback.rewrite||''));for(const n of q.feedback.nonverbal||[])lines.push('动作关联：'+n);}else lines.push('教练反馈待完成');if(q.answer?.events?.length)lines.push('观测事件：'+q.answer.events.map(e=>`${e.type} ${labelTime(e.startMs)}—${labelTime(e.endMs)} ${e.review}`).join('；'));}
 return lines.join('\n');}
function renderReport(){
 const r=session.report;$('#report').innerHTML=r?`<p>${esc(r.summary)}</p><div class="levels">${r.dimensions.map(d=>`<div class="level">${esc(d.name)} · ${esc((session.ruleWeights||knowledge.ruleWeights)[d.name]||'训练参考')}<strong>${esc(d.level)}</strong><p>${esc(d.basis)}</p></div>`).join('')}</div><section class="report-section"><h2>下一轮优先修正的3件事</h2>${r.priorities.map((p,i)=>`<div class="priority"><b>${i+1}. ${esc(p.action)}</b><p>练法：${esc(p.practice)}<br>验收：${esc(p.check)}<br>对应问题：${esc((p.questionIds||[]).join('、'))}</p></div>`).join('')}</section>`:'';
 $('#reviewQuestions').innerHTML=session.questions.map(q=>{const f=q.feedback;return `<section class="report-section"><span class="tag">${esc(q.dimension)}</span><span>${esc(q.id)}</span><h3>${esc(q.text)}</h3><details><summary>查看我的回答</summary><p>${esc(q.answer?.text||'未回答')}</p></details>${f?`<p><b>内容：</b>${esc(f.content)}</p><p><b>逻辑：</b>${esc(f.logic)}</p><p><b>证据：</b>${esc(f.evidence)}</p><p><b>建议表达：</b>${esc(f.rewrite)}</p>${(f.nonverbal||[]).map(n=>`<p><b>本题动作关联：</b>${esc(n)}</p>`).join('')}`:'<p>等待教练逐题反馈，不以关键词命中代替内容判断。</p>'}</section>`;}).join('');
}
$('#postureMode').onchange=()=>{vision?.setMode($('#postureMode').value);$('#postureGuide').textContent=$('#postureMode').value==='standing'?'站姿：让双肩、手臂和胯部完整入镜，不必强求全身。脸部过小时仍可分析身体姿态。':'坐姿：让头部、双肩和腰胯入镜，保持自然坐姿；如需眼神反馈，请靠近到脸部清晰。';};
$('#cameraBtn').onclick=enableCamera;$('#retryVision').onclick=retryVision;$('#calibrateBtn').onclick=()=>vision?.calibrate();$('#micBtn').onclick=enableMic;$('#helpBtn').onclick=()=>$('#help').showModal();$('#closeHelp').onclick=()=>$('#help').close();
$('#startBtn').onclick=async()=>{if(!$('#consent').checked){$('#consent').focus();return alert('请先确认允许教练读取提交的文字与事件摘要。');}try{render(await api('start',{competitionProfile:$('#competitionProfile').value,minutes:Number($('#minutes').value),timingMode:$('#timingMode').value,practiceGoal:$('#practiceGoal').value,focus:$('#focus').value,summary:$('#summary').value,capabilities:{camera:cameraEnabled,calibrated:!!vision?.base,audio:!!mic}}));}catch(e){alert(e.message);}};
$('#recordBtn').onclick=()=>recording?stopRecord():startRecord();$('#answer').addEventListener('input',ensureAnswer);$('#submitBtn').onclick=()=>submitAnswer(false);
$('#pauseBtn').onclick=async()=>{if(recording)await stopRecord();if(session.status==='paused'){vision?.resume();render(await api('resume',{}));}else{vision?.pause();render(await api('pause',{}));}};
$('#endBtn').onclick=async()=>{finishPending=true;$('#endBtn').disabled=true;try{if(recording)await stopRecord();else if(processing)await stopPromise;if($('#answer').value.trim()&&currentQuestion()&&!currentQuestion().answer){await submitAnswer(true);}else render(await api('end',{}));vision?.stop();mic?.getTracks().forEach(t=>t.stop());stream?.getTracks().forEach(t=>t.stop());}catch(e){notice(e.message);}finally{finishPending=false;$('#endBtn').disabled=false;}};
$('#speakBtn').onclick=()=>{if(!currentQuestion())return;const u=new SpeechSynthesisUtterance(currentQuestion().text);u.lang='zh-CN';const voice=speechSynthesis.getVoices().find(v=>v.localService&&v.lang.startsWith('zh'));if(!voice)return notice('此浏览器没有可用的本机中文朗读音色，请直接阅读问题。');u.voice=voice;speechSynthesis.cancel();speechSynthesis.speak(u);};
$('#exportBtn').onclick=()=>save('项目_本轮答辩记录.json',JSON.stringify(session,null,2),'application/json');$('#reportBtn').onclick=()=>save('项目_本轮反馈.txt',reportText());
$('#againBtn').onclick=async()=>{if(!confirm('已保存本轮记录。现在开始新一轮吗？'))return;await api('reset',{});location.reload();};
$('#competitionProfile').onchange=()=>{$('#minutes').value=$('#competitionProfile').value==='project'?'10':'7';};
$('#timingMode').onchange=()=>{$('#minutesLabel').hidden=$('#timingMode').value==='untimed';};
setInterval(()=>{if(session?.duration===null){$('#clock').textContent='不计时';$('.timer-wrap').classList.remove('warn');$('#activeNote').textContent='专项训练不设截止时间；练会当前目标后主动结束。';return;}const rem=Math.max(0,localRemaining-(activeTiming?(performance.now()-lastSync)/1000:0));$('#clock').textContent=`${String(Math.floor(rem/60)).padStart(2,'0')}:${String(Math.floor(rem%60)).padStart(2,'0')}`;$('.timer-wrap').classList.toggle('warn',rem<=60);if(rem<=60&&activeTiming)$('#activeNote').textContent='剩余不足1分钟：优先把当前问题的结论、证据和边界说完。';},200);
async function poll(){try{render(await api('state'));}catch(e){$('#audioStatus').textContent='本机服务未连接：请重新打开“启动本机训练工具”。';if(!$('#training').hidden)notice('本机服务暂未连接，请重新启动工具；未提交文字保留在输入框。');}setTimeout(poll,1000);}
$('#glossary').value=localStorage.getItem('coachGlossary')||'';$('#glossary').oninput=()=>localStorage.setItem('coachGlossary',$('#glossary').value);
deck=await(await fetch('deck.json')).json();knowledge=await(await fetch('knowledge.json')).json();$('#competitionProfile').value=knowledge.competitionProfile||'project';$('#competitionProfile').onchange();$('#facts').innerHTML=knowledge.facts.map(f=>`<div class="fact"><strong>${esc(f.id)} · ${f.pages.map(p=>'P'+p).join('/')} · ${esc(f.status)}</strong><p>${esc(f.claim)}</p><p class="gap">证据缺口：${esc(f.gap)}</p></div>`).join('');poll();
window.addEventListener('beforeunload',()=>{stream?.getTracks().forEach(t=>t.stop());mic?.getTracks().forEach(t=>t.stop());});
