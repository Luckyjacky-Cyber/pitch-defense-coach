import {Calibration,faceFeature,bodyFeature} from './vision-calibration.js';

export const errorText=e=>e?.message||String(e||'未知错误');

// A model failure must not stop a healthy camera stream.
export async function loadVision(video,onStatus,onUnavailable=()=>{},options={}){
 const monitor=new VisionMonitor(video,onStatus,onUnavailable,options);
 try{
  const response=await fetch('/api/state',{signal:AbortSignal.timeout(5000)});
  if(!response.ok)throw Error('服务返回 '+response.status);
 }catch(e){
  onStatus('画面已连接 · 本机服务未连接，暂不分析动作。请重新打开“启动本机训练工具”，再点“重试动作分析”。');
  onUnavailable();return null;
 }
 try{await monitor.init();return monitor;}
 catch(e){monitor.stop();console.error('动作分析加载失败',e);onStatus('画面已连接 · 动作分析未就绪：'+errorText(e)+'。可重试，或仅练内容。');onUnavailable();return null;}
}

export class EventTracker {
 constructor(){this.pending={};this.events=[];this.questionId=null;this.origin=0;this.sway=[];}
 begin(id,now){this.pending={};this.events=[];this.questionId=id;this.origin=now;this.sway=[];}
 update(type,active,now,detail='',confidence='中',minDuration=1500){
  if(!this.questionId)return;
  let p=this.pending[type];
  if(active){
   if(!p)p=this.pending[type]={start:now,last:now,detail,confidence,minDuration};
   p.last=now;
  }else if(p&&now-p.last>300){this.close(type,p.last);}
 }
 close(type,end){
  const p=this.pending[type];if(!p)return;
  if(end-p.start>=p.minDuration)this.events.push({id:crypto.randomUUID(),questionId:this.questionId,type,startMs:Math.round(p.start-this.origin),endMs:Math.round(end-this.origin),durationSeconds:+((end-p.start)/1000).toFixed(1),detail:p.detail,confidence:p.confidence,source:'local-camera',review:'待确认'});
  delete this.pending[type];
 }
 flush(now){for(const type of Object.keys(this.pending))this.close(type,Math.min(now,this.pending[type].last));return [...this.events];}
}

export class VisionMonitor {
 constructor(video,onStatus,onUnavailable=()=>{},options={}){
  this.video=video;this.onStatus=onStatus;this.onUnavailable=onUnavailable;this.onReadiness=options.onReadiness||(()=>{});
  this.mode=options.mode||'standing';this.tracker=new EventTracker();this.running=false;this.analyzing=false;this.base=null;
  this.validFrames=0;this.totalFrames=0;this.channelFrames={face:0,body:0};this.lastFrame=-1;this.lastReadiness=0;
 }
 async init(){
  this.onStatus('正在加载本机视觉模型…');
  const {FilesetResolver,FaceLandmarker,PoseLandmarker,HandLandmarker}=await import('./vendor/vision.mjs');
  const fs=await FilesetResolver.forVisionTasks('/vendor/wasm');
  const common={runningMode:'VIDEO'};
  this.face=await FaceLandmarker.createFromOptions(fs,{...common,baseOptions:{modelAssetPath:'/models/face.task',delegate:'CPU'},numFaces:1,outputFaceBlendshapes:true,minFaceDetectionConfidence:.6,minFacePresenceConfidence:.6,minTrackingConfidence:.6});
  this.pose=await PoseLandmarker.createFromOptions(fs,{...common,baseOptions:{modelAssetPath:'/models/pose.task',delegate:'CPU'},numPoses:1,minPoseDetectionConfidence:.6,minPosePresenceConfidence:.6,minTrackingConfidence:.6});
  this.hand=await HandLandmarker.createFromOptions(fs,{...common,baseOptions:{modelAssetPath:'/models/hand.task',delegate:'CPU'},numHands:2,minHandDetectionConfidence:.6,minHandPresenceConfidence:.6,minTrackingConfidence:.6});
  this.running=true;this.onStatus('模型已加载；请先确认画面中是本人，再校准站姿或坐姿。');this.tick();
 }
 setMode(mode){this.mode=mode;this.base=null;this.calibration=null;this.pause();this.onStatus('已切换为'+(mode==='standing'?'站姿':'坐姿')+'，请按新的位置重新校准。');}
 calibrate(){if(!this.running)return;this.base=null;this.calibration=new Calibration(performance.now());this.onStatus('校准中：自然'+(this.mode==='standing'?'站立':'坐稳')+'，保持位置6秒；必要时延长至12秒。');}
 begin(id,origin){this.tracker.begin(id,origin);this.validFrames=0;this.totalFrames=0;this.channelFrames={face:0,body:0};this.analyzing=true;}
 pause(){this.analyzing=false;this.tracker.flush(performance.now());}
 resume(){this.analyzing=true;}
 end(){this.analyzing=false;const pct=n=>this.totalFrames?Math.round(100*n/this.totalFrames):0;return {events:this.tracker.flush(performance.now()),coverage:pct(this.validFrames),calibrated:!!this.base,mode:this.mode,channels:{body:!!this.base?.body,face:!!this.base?.face,faceDetails:!!this.base?.face?.details},coverageByChannel:{body:pct(this.channelFrames.body),face:pct(this.channelFrames.face)}};}
 stop(){this.running=false;this.analyzing=false;clearTimeout(this.timer);for(const key of ['face','pose','hand']){try{this[key]?.close();}catch{}this[key]=null;}}
 readiness(now,ft,bt){
  if(now-this.lastReadiness<700)return;this.lastReadiness=now;
  this.onReadiness('身体：'+(bt?'已识别':'未识别，请让双肩和胯部入镜')+'；脸部：'+(ft?(ft.details?'清晰':'偏小，仅支持头部方向'):'未识别或过小')+'。');
 }
 updateCalibration(now,ft,bt){
  const c=this.calibration;if(!c)return;c.add(now,ft,bt);const ms=now-c.start;if(ms<6000)return;
  const result=c.result();
  if(result){
   this.base=result;this.calibration=null;
   const enabled=[result.body?'身体姿态':null,result.face?'头部方向':null,result.face?.details?'眼神与面部细节':null].filter(Boolean);
   this.onStatus('校准完成 · '+(this.mode==='standing'?'站姿':'坐姿')+' · 可分析：'+enabled.join('、')+(!result.body?'。身体暂未校准，请让双肩和胯部入镜后重校。':'')+(result.face?.details?'。':'。脸部细节暂不分析；如需眼神反馈，请适当靠近。'));
  }else if(ms>=12000){this.calibration=null;this.onStatus(ft||bt?'校准未完成：请保持位置不走动，再试一次。':'没有采集到足够的人体画面。若仍是灰底锁图标，请检查摄像头隐私开关；若已看到本人，请让双肩和胯部入镜。');}
  else this.onStatus('正在补充校准样本（最多12秒）：保持站姿或坐姿，让双肩和胯部入镜。');
 }
 process(now,fr,pr,hr){
  const f=fr.faceLandmarks?.[0],p=pr.landmarks?.[0];
  const ft=faceFeature(f,this.video.videoWidth||640),bt=bodyFeature(p);
  this.readiness(now,ft,bt);this.updateCalibration(now,ft,bt);
  if(!this.analyzing||!this.base)return;
  this.totalFrames++;const face=!!(ft&&this.base.face),body=!!(bt&&this.base.body);
  if(face||body)this.validFrames++;if(face)this.channelFrames.face++;if(body)this.channelFrames.body++;
  const t=(type,available,active,detail,confidence='中')=>{
   if(!available){const pending=this.tracker.pending[type];if(pending)this.tracker.close(type,pending.last);return;}
   this.tracker.update(type,active,now,detail,confidence);
  };
  const fb=this.base.face,bb=this.base.body;
  const details=face&&ft.details&&fb.details;
  t('头部方向偏离',face,face&&(Math.abs(ft.yaw-fb.yaw)>.18||Math.abs(ft.pitch-fb.pitch)>.18),'只根据头部朝向估计；不能等同于眼神，查看PPT也可能触发');
  t('视线方向疑似偏离',details,details&&Math.abs(ft.iris-fb.iris)>.23,'基于清晰脸部的虹膜位置近似估计；不能判定注意力');
  const blend=Object.fromEntries((fr.faceBlendshapes?.[0]?.categories||[]).map(c=>[c.categoryName,c.score]));
  t('眉部持续下压',details,(blend.browDownLeft||0)>.5&&(blend.browDownRight||0)>.5,'仅描述眉部动作，不推断情绪');
  t('唇部持续收紧',details,(blend.mouthPressLeft||0)>.55&&(blend.mouthPressRight||0)>.55,'不能据此确认咬唇，需本人复核','低');
  t('上身侧倾',body,body&&Math.abs(bt.lean-bb.lean)>.25,'肩线相对本人校准姿态倾斜；不作医学判断');
  t('身体明显远离镜头',body,body&&bt.shoulder<bb.shoulder*.78,'肩宽相对本人校准位置缩小；可能是主动移动，不等同于后仰','低');
  const arms=body&&[15,16].every(i=>p[i]&&(p[i].visibility??0)>.65);
  const cross=arms&&p[15].x<p[16].x&&p[15].y>Math.min(p[11].y,p[12].y)&&p[15].y<p[23].y&&p[16].y>Math.min(p[11].y,p[12].y)&&p[16].y<p[24].y;
  t('双臂疑似交叉',arms,cross,'仅记录手腕与躯干位置，不推断心理状态','低');
  const touch=face&&(hr.landmarks||[]).some(h=>[4,8,12,16,20].some(i=>Math.hypot(h[i].x-f[1].x,h[i].y-f[1].y)<ft.faceWidth*.48||Math.hypot(h[i].x-f[152].x,h[i].y-f[152].y)<ft.faceWidth*.45));
  t('手部靠近面部或颈部',face,touch,'二维重叠不能确认触摸，需要本人复核','低');
  if(body){
   this.tracker.sway.push({t:now,x:bt.centerX});this.tracker.sway=this.tracker.sway.filter(v=>now-v.t<5000);
   const xs=this.tracker.sway.map(v=>v.x);let turns=0,last=0;
   for(let i=2;i<xs.length;i+=2){const d=xs[i]-xs[i-2],sg=Math.abs(d)>bb.shoulder*.05?Math.sign(d):0;if(sg&&last&&sg!==last)turns++;if(sg)last=sg;}
   t('身体反复左右移动',true,xs.length>15&&Math.max(...xs)-Math.min(...xs)>bb.shoulder*.45&&turns>=3,'相对本人肩宽计算；主动走位也可能触发，需复核','低');
  }else{this.tracker.sway=[];t('身体反复左右移动',false,false,'');}
 }
 async tick(){
  if(!this.running)return;const now=performance.now();
  try{
   if(this.video.readyState>=2&&this.video.currentTime!==this.lastFrame){
    this.lastFrame=this.video.currentTime;
    const fr=this.face.detectForVideo(this.video,now),pr=this.pose.detectForVideo(this.video,now),hr=this.hand.detectForVideo(this.video,now);
    this.process(now,fr,pr,hr);
   }else if(this.calibration&&now-this.calibration.start>12000){this.calibration=null;this.onStatus('校准未完成：视频没有持续更新，请检查摄像头连接后重试。');}
  }catch(e){this.stop();this.base=null;this.onStatus('画面已连接 · 动作分析已暂停：'+errorText(e)+'。可点“重试动作分析”。');this.onUnavailable();}
  if(this.running)this.timer=setTimeout(()=>this.tick(),150);
 }
}
