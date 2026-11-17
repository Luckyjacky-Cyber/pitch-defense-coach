// Independent face/body baselines: distant speakers can calibrate their body alone.
export function bodyFeature(p){
 if(!p||![11,12,23,24].every(i=>p[i]&&(p[i].visibility??0)>=.55&&p[i].x>0&&p[i].x<1&&p[i].y>0&&p[i].y<1))return null;
 const width=Math.abs(p[11].x-p[12].x),height=Math.abs((p[23].y+p[24].y-p[11].y-p[12].y)/2);
 if(width<.055||height<.08)return null;
 return {shoulder:width,centerX:(p[11].x+p[12].x)/2,lean:(p[11].y-p[12].y)/width};
}
export function faceFeature(f,pixels=640){
 if(!f||f.length<455)return null;
 const width=Math.abs(f[454].x-f[234].x);
 if(width*pixels<70)return null;
 const eye=(f[33].y+f[263].y)/2,chin=f[152].y;
 const iris=f.length>473?((f[468].x-(f[33].x+f[133].x)/2)/(Math.abs(f[33].x-f[133].x)||.01)+(f[473].x-(f[362].x+f[263].x)/2)/(Math.abs(f[362].x-f[263].x)||.01))/2:null;
 return {yaw:(f[1].x-(f[234].x+f[454].x)/2)/width,pitch:(f[1].y-eye)/(chin-eye||.1),iris,faceWidth:width,details:width*pixels>=120&&iris!==null};
}
const avg=(xs,key)=>xs.reduce((n,s)=>n+s.value[key],0)/xs.length;
export function baseline(samples,keys,stabilityKeys){
 if(samples.length<10||samples.at(-1).at-samples[0].at<2500)return null;
 const result=Object.fromEntries(keys.map(k=>[k,avg(samples,k)]));
 for(const [key,tolerance] of stabilityKeys){const values=samples.map(s=>s.value[key]).sort((a,b)=>a-b);if(values[Math.floor(values.length*.9)]-values[Math.floor(values.length*.1)]>tolerance)return null;}
 return result;
}
export class Calibration {
 constructor(now){this.start=now;this.face=[];this.body=[];}
 add(now,face,body){for(const [key,value] of [['face',face],['body',body]]){if(value)this[key].push({at:now,value});this[key]=this[key].filter(s=>now-s.at<=5000);}}
 result(){
 const face=baseline(this.face,['yaw','pitch','iris','faceWidth'],[['yaw',.15],['pitch',.15]]);
 if(face)face.details=this.face.filter(s=>s.value.details).length/this.face.length>=.8;
 const body=baseline(this.body,['shoulder','centerX','lean'],[['centerX',.06],['lean',.15]]);
 return face||body?{face,body}:null;
 }
}
