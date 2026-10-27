import {createHash,createHmac,randomBytes,scrypt,timingSafeEqual} from 'node:crypto';
export const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
export const random=()=>randomBytes(32).toString('base64url');
export const mac=(s:string,key:string)=>createHmac('sha256',key).update(s).digest('hex');
export function equal(a:string,b:string){const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y);}
let verifying=false;
export async function verifyPassword(password:string,encoded:string){
 const v=JSON.parse(encoded);if(v.algorithm!=='scrypt'||v.N!==32768||v.r!==8||v.p!==3||Buffer.from(v.salt_b64,'base64').length!==32||Buffer.from(v.key_b64,'base64').length!==32)throw new Error('AUTH_CONFIGURATION');
 if(verifying)throw new Error('AUTH_BUSY');verifying=true;
 try{const key=await new Promise<Buffer>((resolve,reject)=>scrypt(password,Buffer.from(v.salt_b64,'base64'),32,{N:v.N,r:v.r,p:v.p,maxmem:64*1024*1024},(e,k)=>e?reject(e):resolve(k)));return timingSafeEqual(key,Buffer.from(v.key_b64,'base64'));}finally{verifying=false;}
}
export function pathOf(request:Request){const u=new URL(request.url);if(/%(?:2f|5c|2e|25)|\\|\/\//i.test(u.pathname))throw new Error('BAD_PATH');let p:string;try{p=decodeURIComponent(u.pathname);}catch{throw new Error('BAD_PATH');}if(p.split('/').some(x=>x==='..'||x==='.')||/[\x00-\x1f]/.test(p))throw new Error('BAD_PATH');return p;}
export function cookieToken(request:Request){const matches=(request.headers.get('Cookie')||'').split(';').map(x=>x.trim()).filter(x=>x.startsWith('__Host-pubster_session='));if(matches.length!==1)return null;const token=matches[0].slice('__Host-pubster_session='.length);return /^[A-Za-z0-9_-]{43}$/.test(token)?token:null;}
export function fts(query:string){return (query.slice(0,256).match(/[\p{L}\p{N}_]+/gu)||[]).slice(0,12).map(t=>'"'+t+'"').join(' AND ');}
export async function body(request:Request){if(!request.headers.get('Content-Type')?.startsWith('application/json'))throw new Error('JSON_REQUIRED');const reader=request.body?.getReader();if(!reader)throw new Error('BAD_REQUEST');let size=0;const parts:Uint8Array[]=[];while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>16384){await reader.cancel();throw new Error('BODY_TOO_LARGE');}parts.push(value);}const all=new Uint8Array(size);let offset=0;for(const part of parts){all.set(part,offset);offset+=part.byteLength;}return JSON.parse(new TextDecoder().decode(all));}
export function rangeOf(value:string|null,size:number){if(!value)return null;const m=/^bytes=(\d*)-(\d*)$/.exec(value);if(!m||(!m[1]&&!m[2]))throw new Error('BAD_RANGE');let start=m[1]?Number(m[1]):Math.max(0,size-Number(m[2]));let end=m[2]&&m[1]?Number(m[2]):size-1;if(start>=size||start>end||end>=size||!Number.isSafeInteger(start)||!Number.isSafeInteger(end))throw new Error('BAD_RANGE');return {offset:start,length:end-start+1};}
