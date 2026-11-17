import assert from 'node:assert/strict';
import {loadVision,VisionMonitor,errorText} from '../assets/app/public/vision.js';
const originalFetch=globalThis.fetch, originalInit=VisionMonitor.prototype.init;
let stopped=0,unavailable=0,status='';
const video={srcObject:{getTracks:()=>[{stop(){stopped++},readyState:'live'}]}};
try{
 globalThis.fetch=async()=>{throw new TypeError('Failed to fetch')};
 assert.equal(await loadVision(video,t=>status=t,()=>unavailable++),null);
 assert.match(status,/本机服务未连接/);assert.equal(stopped,0);assert.equal(unavailable,1);
 globalThis.fetch=async()=>({ok:true});
 VisionMonitor.prototype.init=async function(){throw '模型读取失败'};
 assert.equal(await loadVision(video,t=>status=t,()=>unavailable++),null);
 assert.match(status,/模型读取失败/);assert.equal(stopped,0);assert.equal(unavailable,2);
 assert.equal(errorText(undefined),'未知错误');
 VisionMonitor.prototype.init=async function(){this.running=true};
 const m=await loadVision(video,t=>status=t);assert.equal(m.running,true);m.stop();m.stop();
 console.log('PASS: 服务断开保留画面、模型失败保留画面、错误可读、恢复重试、重复清理');
}finally{globalThis.fetch=originalFetch;VisionMonitor.prototype.init=originalInit;}
