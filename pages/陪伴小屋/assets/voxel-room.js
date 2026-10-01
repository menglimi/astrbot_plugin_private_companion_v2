(()=>{var Zi={LEFT:0,MIDDLE:1,RIGHT:2,ROTATE:0,DOLLY:1,PAN:2},Ji={ROTATE:0,PAN:1,DOLLY_PAN:2,DOLLY_ROTATE:3},Cd=0,Jc=1,Rd=2;var Sa=1,bl=2,ps=3,fs=0,Tn=1,En=2,mi=0,Ta=1,Kc=2,$c=3,Qc=4,Pd=5;var ms=100,Id=101,Ld=102,Dd=103,Ud=104,Nd=200,Od=201,Fd=202,Bd=203,zd=204,kd=205,Vd=206,Gd=207,Hd=208,Wd=209,jd=210,Xd=211,qd=212,Yd=213,Zd=214,eh=0,th=1,nh=2,Sl=3,ih=4,rh=5,sh=6,ah=7,Jd=0,Kd=1,$d=2,si=0,oh=1,lh=2,ch=3,Ea=4,hh=5,uh=6,dh=7;var ph=300,gs=301,fr=302,Tl=303,El=304,wa=306,hr=1e3,Wi=1001,Co=1002,Yn=1003,Qd=1004;var Aa=1005;var Xt=1006,wl=1007;var mr=1008;var zn=1009,fh=1010,mh=1011,_s=1012,Al=1013,Li=1014,Kn=1015,gi=1016,Cl=1017,Rl=1018,vs=1020,gh=35902,_h=35899,ep=1021,tp=1022,ai=1023,Ki=1026,gr=1027,Pl=1028,Il=1029,ys=1030,vh=1031;var yh=1033,Ll=33776,Dl=33777,Ul=33778,Nl=33779,xh=35840,Mh=35841,bh=35842,Sh=35843,Th=36196,Eh=37492,wh=37496,Ah=37488,Ch=37489,Rh=37490,Ph=37491,Ih=37808,Lh=37809,Dh=37810,Uh=37811,Nh=37812,Oh=37813,Fh=37814,Bh=37815,zh=37816,kh=37817,Vh=37818,Gh=37819,Hh=37820,Wh=37821,jh=36492,Xh=36494,qh=36495,Yh=36283,Zh=36284,Jh=36285,Kh=36286;var qs=2300,Ro=2301,wo=2302,Fc=2303,Bc=2400,zc=2401,kc=2402;var np=0,ip=1,_r="",Ut="srgb",ur="srgb-linear",Ys="linear",gt="srgb";var cr=7680;var rp=512,sp=513,ap=514,Ol=515,op=516,lp=517,Fl=518,cp=519,Vc=35044,$h=35048;var Qh="300 es",Ri=2e3,Zr=2001;function Sf(r){return ArrayBuffer.isView(r)&&!(r instanceof DataView)}function Jr(r){return document.createElementNS("http://www.w3.org/1999/xhtml",r)}function hp(){let r=Jr("canvas");return r.style.display="block",r}var qu={},Kr=null;function eu(...r){let e="THREE."+r.shift();Kr?Kr("log",e,...r):console.log(e,...r)}function up(r){let e=r[0];if(typeof e=="string"&&e.startsWith("TSL:")){let t=r[1];t&&t.isStackTrace?r[0]+=" "+t.getLocation():r[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return r}function Ye(...r){let e="THREE."+(r=up(r)).shift();if(Kr)Kr("warn",e,...r);else{let t=r[0];t&&t.isStackTrace?console.warn(t.getError(e)):console.warn(e,...r)}}function Je(...r){let e="THREE."+(r=up(r)).shift();if(Kr)Kr("error",e,...r);else{let t=r[0];t&&t.isStackTrace?console.error(t.getError(e)):console.error(e,...r)}}function Zs(...r){let e=r.join(" ");e in qu||(qu[e]=!0,Ye(...r))}function dp(r,e,t){return new Promise(function(n,i){setTimeout(function s(){switch(r.clientWaitSync(e,r.SYNC_FLUSH_COMMANDS_BIT,0)){case r.WAIT_FAILED:i();break;case r.TIMEOUT_EXPIRED:setTimeout(s,t);break;default:n()}},t)})}var pp={[eh]:1,[nh]:6,[ih]:7,[Sl]:5,[th]:0,[sh]:2,[ah]:4,[rh]:3},pi=class{addEventListener(e,t){this._listeners===void 0&&(this._listeners={});let n=this._listeners;n[e]===void 0&&(n[e]=[]),n[e].indexOf(t)===-1&&n[e].push(t)}hasEventListener(e,t){let n=this._listeners;return n!==void 0&&n[e]!==void 0&&n[e].indexOf(t)!==-1}removeEventListener(e,t){let n=this._listeners;if(n===void 0)return;let i=n[e];if(i!==void 0){let s=i.indexOf(t);s!==-1&&i.splice(s,1)}}dispatchEvent(e){let t=this._listeners;if(t===void 0)return;let n=t[e.type];if(n!==void 0){e.target=this;let i=n.slice(0);for(let s=0,a=i.length;s<a;s++)i[s].call(this,e);e.target=null}}},rn=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"],Yu=1234567,qr=Math.PI/180,$r=180/Math.PI;function vr(){let r=4294967295*Math.random()|0,e=4294967295*Math.random()|0,t=4294967295*Math.random()|0,n=4294967295*Math.random()|0;return(rn[255&r]+rn[r>>8&255]+rn[r>>16&255]+rn[r>>24&255]+"-"+rn[255&e]+rn[e>>8&255]+"-"+rn[e>>16&15|64]+rn[e>>24&255]+"-"+rn[63&t|128]+rn[t>>8&255]+"-"+rn[t>>16&255]+rn[t>>24&255]+rn[255&n]+rn[n>>8&255]+rn[n>>16&255]+rn[n>>24&255]).toLowerCase()}function nt(r,e,t){return Math.max(e,Math.min(t,r))}function Gc(r,e){return(r%e+e)%e}function Ws(r,e,t){return(1-t)*r+t*e}function Xr(r,e){switch(e.constructor){case Float32Array:return r;case Uint32Array:return r/4294967295;case Uint16Array:return r/65535;case Uint8Array:return r/255;case Int32Array:return Math.max(r/2147483647,-1);case Int16Array:return Math.max(r/32767,-1);case Int8Array:return Math.max(r/127,-1);default:throw new Error("Invalid component type.")}}function gn(r,e){switch(e.constructor){case Float32Array:return r;case Uint32Array:return Math.round(4294967295*r);case Uint16Array:return Math.round(65535*r);case Uint8Array:return Math.round(255*r);case Int32Array:return Math.round(2147483647*r);case Int16Array:return Math.round(32767*r);case Int8Array:return Math.round(127*r);default:throw new Error("Invalid component type.")}}var pt={DEG2RAD:qr,RAD2DEG:$r,generateUUID:vr,clamp:nt,euclideanModulo:Gc,mapLinear:function(r,e,t,n,i){return n+(r-e)*(i-n)/(t-e)},inverseLerp:function(r,e,t){return r!==e?(t-r)/(e-r):0},lerp:Ws,damp:function(r,e,t,n){return Ws(r,e,1-Math.exp(-t*n))},pingpong:function(r,e=1){return e-Math.abs(Gc(r,2*e)-e)},smoothstep:function(r,e,t){return r<=e?0:r>=t?1:(r=(r-e)/(t-e))*r*(3-2*r)},smootherstep:function(r,e,t){return r<=e?0:r>=t?1:(r=(r-e)/(t-e))*r*r*(r*(6*r-15)+10)},randInt:function(r,e){return r+Math.floor(Math.random()*(e-r+1))},randFloat:function(r,e){return r+Math.random()*(e-r)},randFloatSpread:function(r){return r*(.5-Math.random())},seededRandom:function(r){r!==void 0&&(Yu=r);let e=Yu+=1831565813;return e=Math.imul(e^e>>>15,1|e),e^=e+Math.imul(e^e>>>7,61|e),((e^e>>>14)>>>0)/4294967296},degToRad:function(r){return r*qr},radToDeg:function(r){return r*$r},isPowerOfTwo:function(r){return!(r&r-1)&&r!==0},ceilPowerOfTwo:function(r){return Math.pow(2,Math.ceil(Math.log(r)/Math.LN2))},floorPowerOfTwo:function(r){return Math.pow(2,Math.floor(Math.log(r)/Math.LN2))},setQuaternionFromProperEuler:function(r,e,t,n,i){let s=Math.cos,a=Math.sin,o=s(t/2),c=a(t/2),l=s((e+n)/2),h=a((e+n)/2),p=s((e-n)/2),f=a((e-n)/2),m=s((n-e)/2),u=a((n-e)/2);switch(i){case"XYX":r.set(o*h,c*p,c*f,o*l);break;case"YZY":r.set(c*f,o*h,c*p,o*l);break;case"ZXZ":r.set(c*p,c*f,o*h,o*l);break;case"XZX":r.set(o*h,c*u,c*m,o*l);break;case"YXY":r.set(c*m,o*h,c*u,o*l);break;case"ZYZ":r.set(c*u,c*m,o*h,o*l);break;default:Ye("MathUtils: .setQuaternionFromProperEuler() encountered an unknown order: "+i)}},normalize:gn,denormalize:Xr},_e=class r{constructor(e=0,t=0){r.prototype.isVector2=!0,this.x=e,this.y=t}get width(){return this.x}set width(e){this.x=e}get height(){return this.y}set height(e){this.y=e}set(e,t){return this.x=e,this.y=t,this}setScalar(e){return this.x=e,this.y=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;default:throw new Error("index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;default:throw new Error("index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y)}copy(e){return this.x=e.x,this.y=e.y,this}add(e){return this.x+=e.x,this.y+=e.y,this}addScalar(e){return this.x+=e,this.y+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this}subScalar(e){return this.x-=e,this.y-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this}multiply(e){return this.x*=e.x,this.y*=e.y,this}multiplyScalar(e){return this.x*=e,this.y*=e,this}divide(e){return this.x/=e.x,this.y/=e.y,this}divideScalar(e){return this.multiplyScalar(1/e)}applyMatrix3(e){let t=this.x,n=this.y,i=e.elements;return this.x=i[0]*t+i[3]*n+i[6],this.y=i[1]*t+i[4]*n+i[7],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this}clamp(e,t){return this.x=nt(this.x,e.x,t.x),this.y=nt(this.y,e.y,t.y),this}clampScalar(e,t){return this.x=nt(this.x,e,t),this.y=nt(this.y,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(nt(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(e){return this.x*e.x+this.y*e.y}cross(e){return this.x*e.y-this.y*e.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(e){let t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;let n=this.dot(e)/t;return Math.acos(nt(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){let t=this.x-e.x,n=this.y-e.y;return t*t+n*n}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this}equals(e){return e.x===this.x&&e.y===this.y}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this}rotateAround(e,t){let n=Math.cos(t),i=Math.sin(t),s=this.x-e.x,a=this.y-e.y;return this.x=s*n-a*i+e.x,this.y=s*i+a*n+e.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},kt=class{constructor(e=0,t=0,n=0,i=1){this.isQuaternion=!0,this._x=e,this._y=t,this._z=n,this._w=i}static slerpFlat(e,t,n,i,s,a,o){let c=n[i+0],l=n[i+1],h=n[i+2],p=n[i+3],f=s[a+0],m=s[a+1],u=s[a+2],g=s[a+3];if(p!==g||c!==f||l!==m||h!==u){let x=c*f+l*m+h*u+p*g;x<0&&(f=-f,m=-m,u=-u,g=-g,x=-x);let _=1-o;if(x<.9995){let v=Math.acos(x),S=Math.sin(v);_=Math.sin(_*v)/S,c=c*_+f*(o=Math.sin(o*v)/S),l=l*_+m*o,h=h*_+u*o,p=p*_+g*o}else{c=c*_+f*o,l=l*_+m*o,h=h*_+u*o,p=p*_+g*o;let v=1/Math.sqrt(c*c+l*l+h*h+p*p);c*=v,l*=v,h*=v,p*=v}}e[t]=c,e[t+1]=l,e[t+2]=h,e[t+3]=p}static multiplyQuaternionsFlat(e,t,n,i,s,a){let o=n[i],c=n[i+1],l=n[i+2],h=n[i+3],p=s[a],f=s[a+1],m=s[a+2],u=s[a+3];return e[t]=o*u+h*p+c*m-l*f,e[t+1]=c*u+h*f+l*p-o*m,e[t+2]=l*u+h*m+o*f-c*p,e[t+3]=h*u-o*p-c*f-l*m,e}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get w(){return this._w}set w(e){this._w=e,this._onChangeCallback()}set(e,t,n,i){return this._x=e,this._y=t,this._z=n,this._w=i,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(e){return this._x=e.x,this._y=e.y,this._z=e.z,this._w=e.w,this._onChangeCallback(),this}setFromEuler(e,t=!0){let n=e._x,i=e._y,s=e._z,a=e._order,o=Math.cos,c=Math.sin,l=o(n/2),h=o(i/2),p=o(s/2),f=c(n/2),m=c(i/2),u=c(s/2);switch(a){case"XYZ":this._x=f*h*p+l*m*u,this._y=l*m*p-f*h*u,this._z=l*h*u+f*m*p,this._w=l*h*p-f*m*u;break;case"YXZ":this._x=f*h*p+l*m*u,this._y=l*m*p-f*h*u,this._z=l*h*u-f*m*p,this._w=l*h*p+f*m*u;break;case"ZXY":this._x=f*h*p-l*m*u,this._y=l*m*p+f*h*u,this._z=l*h*u+f*m*p,this._w=l*h*p-f*m*u;break;case"ZYX":this._x=f*h*p-l*m*u,this._y=l*m*p+f*h*u,this._z=l*h*u-f*m*p,this._w=l*h*p+f*m*u;break;case"YZX":this._x=f*h*p+l*m*u,this._y=l*m*p+f*h*u,this._z=l*h*u-f*m*p,this._w=l*h*p-f*m*u;break;case"XZY":this._x=f*h*p-l*m*u,this._y=l*m*p-f*h*u,this._z=l*h*u+f*m*p,this._w=l*h*p+f*m*u;break;default:Ye("Quaternion: .setFromEuler() encountered an unknown order: "+a)}return t===!0&&this._onChangeCallback(),this}setFromAxisAngle(e,t){let n=t/2,i=Math.sin(n);return this._x=e.x*i,this._y=e.y*i,this._z=e.z*i,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(e){let t=e.elements,n=t[0],i=t[4],s=t[8],a=t[1],o=t[5],c=t[9],l=t[2],h=t[6],p=t[10],f=n+o+p;if(f>0){let m=.5/Math.sqrt(f+1);this._w=.25/m,this._x=(h-c)*m,this._y=(s-l)*m,this._z=(a-i)*m}else if(n>o&&n>p){let m=2*Math.sqrt(1+n-o-p);this._w=(h-c)/m,this._x=.25*m,this._y=(i+a)/m,this._z=(s+l)/m}else if(o>p){let m=2*Math.sqrt(1+o-n-p);this._w=(s-l)/m,this._x=(i+a)/m,this._y=.25*m,this._z=(c+h)/m}else{let m=2*Math.sqrt(1+p-n-o);this._w=(a-i)/m,this._x=(s+l)/m,this._y=(c+h)/m,this._z=.25*m}return this._onChangeCallback(),this}setFromUnitVectors(e,t){let n=e.dot(t)+1;return n<1e-8?(n=0,Math.abs(e.x)>Math.abs(e.z)?(this._x=-e.y,this._y=e.x,this._z=0,this._w=n):(this._x=0,this._y=-e.z,this._z=e.y,this._w=n)):(this._x=e.y*t.z-e.z*t.y,this._y=e.z*t.x-e.x*t.z,this._z=e.x*t.y-e.y*t.x,this._w=n),this.normalize()}angleTo(e){return 2*Math.acos(Math.abs(nt(this.dot(e),-1,1)))}rotateTowards(e,t){let n=this.angleTo(e);if(n===0)return this;let i=Math.min(1,t/n);return this.slerp(e,i),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(e){return this._x*e._x+this._y*e._y+this._z*e._z+this._w*e._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let e=this.length();return e===0?(this._x=0,this._y=0,this._z=0,this._w=1):(e=1/e,this._x=this._x*e,this._y=this._y*e,this._z=this._z*e,this._w=this._w*e),this._onChangeCallback(),this}multiply(e){return this.multiplyQuaternions(this,e)}premultiply(e){return this.multiplyQuaternions(e,this)}multiplyQuaternions(e,t){let n=e._x,i=e._y,s=e._z,a=e._w,o=t._x,c=t._y,l=t._z,h=t._w;return this._x=n*h+a*o+i*l-s*c,this._y=i*h+a*c+s*o-n*l,this._z=s*h+a*l+n*c-i*o,this._w=a*h-n*o-i*c-s*l,this._onChangeCallback(),this}slerp(e,t){let n=e._x,i=e._y,s=e._z,a=e._w,o=this.dot(e);o<0&&(n=-n,i=-i,s=-s,a=-a,o=-o);let c=1-t;if(o<.9995){let l=Math.acos(o),h=Math.sin(l);c=Math.sin(c*l)/h,t=Math.sin(t*l)/h,this._x=this._x*c+n*t,this._y=this._y*c+i*t,this._z=this._z*c+s*t,this._w=this._w*c+a*t,this._onChangeCallback()}else this._x=this._x*c+n*t,this._y=this._y*c+i*t,this._z=this._z*c+s*t,this._w=this._w*c+a*t,this.normalize();return this}slerpQuaternions(e,t,n){return this.copy(e).slerp(t,n)}random(){let e=2*Math.PI*Math.random(),t=2*Math.PI*Math.random(),n=Math.random(),i=Math.sqrt(1-n),s=Math.sqrt(n);return this.set(i*Math.sin(e),i*Math.cos(e),s*Math.sin(t),s*Math.cos(t))}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._w===this._w}fromArray(e,t=0){return this._x=e[t],this._y=e[t+1],this._z=e[t+2],this._w=e[t+3],this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._w,e}fromBufferAttribute(e,t){return this._x=e.getX(t),this._y=e.getY(t),this._z=e.getZ(t),this._w=e.getW(t),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},D=class r{constructor(e=0,t=0,n=0){r.prototype.isVector3=!0,this.x=e,this.y=t,this.z=n}set(e,t,n){return n===void 0&&(n=this.z),this.x=e,this.y=t,this.z=n,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;default:throw new Error("index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this}multiplyVectors(e,t){return this.x=e.x*t.x,this.y=e.y*t.y,this.z=e.z*t.z,this}applyEuler(e){return this.applyQuaternion(Zu.setFromEuler(e))}applyAxisAngle(e,t){return this.applyQuaternion(Zu.setFromAxisAngle(e,t))}applyMatrix3(e){let t=this.x,n=this.y,i=this.z,s=e.elements;return this.x=s[0]*t+s[3]*n+s[6]*i,this.y=s[1]*t+s[4]*n+s[7]*i,this.z=s[2]*t+s[5]*n+s[8]*i,this}applyNormalMatrix(e){return this.applyMatrix3(e).normalize()}applyMatrix4(e){let t=this.x,n=this.y,i=this.z,s=e.elements,a=1/(s[3]*t+s[7]*n+s[11]*i+s[15]);return this.x=(s[0]*t+s[4]*n+s[8]*i+s[12])*a,this.y=(s[1]*t+s[5]*n+s[9]*i+s[13])*a,this.z=(s[2]*t+s[6]*n+s[10]*i+s[14])*a,this}applyQuaternion(e){let t=this.x,n=this.y,i=this.z,s=e.x,a=e.y,o=e.z,c=e.w,l=2*(a*i-o*n),h=2*(o*t-s*i),p=2*(s*n-a*t);return this.x=t+c*l+a*p-o*h,this.y=n+c*h+o*l-s*p,this.z=i+c*p+s*h-a*l,this}project(e){return this.applyMatrix4(e.matrixWorldInverse).applyMatrix4(e.projectionMatrix)}unproject(e){return this.applyMatrix4(e.projectionMatrixInverse).applyMatrix4(e.matrixWorld)}transformDirection(e){let t=this.x,n=this.y,i=this.z,s=e.elements;return this.x=s[0]*t+s[4]*n+s[8]*i,this.y=s[1]*t+s[5]*n+s[9]*i,this.z=s[2]*t+s[6]*n+s[10]*i,this.normalize()}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this}divideScalar(e){return this.multiplyScalar(1/e)}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this}clamp(e,t){return this.x=nt(this.x,e.x,t.x),this.y=nt(this.y,e.y,t.y),this.z=nt(this.z,e.z,t.z),this}clampScalar(e,t){return this.x=nt(this.x,e,t),this.y=nt(this.y,e,t),this.z=nt(this.z,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(nt(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this}cross(e){return this.crossVectors(this,e)}crossVectors(e,t){let n=e.x,i=e.y,s=e.z,a=t.x,o=t.y,c=t.z;return this.x=i*c-s*o,this.y=s*a-n*c,this.z=n*o-i*a,this}projectOnVector(e){let t=e.lengthSq();if(t===0)return this.set(0,0,0);let n=e.dot(this)/t;return this.copy(e).multiplyScalar(n)}projectOnPlane(e){return cc.copy(this).projectOnVector(e),this.sub(cc)}reflect(e){return this.sub(cc.copy(e).multiplyScalar(2*this.dot(e)))}angleTo(e){let t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;let n=this.dot(e)/t;return Math.acos(nt(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){let t=this.x-e.x,n=this.y-e.y,i=this.z-e.z;return t*t+n*n+i*i}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)+Math.abs(this.z-e.z)}setFromSpherical(e){return this.setFromSphericalCoords(e.radius,e.phi,e.theta)}setFromSphericalCoords(e,t,n){let i=Math.sin(t)*e;return this.x=i*Math.sin(n),this.y=Math.cos(t)*e,this.z=i*Math.cos(n),this}setFromCylindrical(e){return this.setFromCylindricalCoords(e.radius,e.theta,e.y)}setFromCylindricalCoords(e,t,n){return this.x=e*Math.sin(t),this.y=n,this.z=e*Math.cos(t),this}setFromMatrixPosition(e){let t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this}setFromMatrixScale(e){let t=this.setFromMatrixColumn(e,0).length(),n=this.setFromMatrixColumn(e,1).length(),i=this.setFromMatrixColumn(e,2).length();return this.x=t,this.y=n,this.z=i,this}setFromMatrixColumn(e,t){return this.fromArray(e.elements,4*t)}setFromMatrix3Column(e,t){return this.fromArray(e.elements,3*t)}setFromEuler(e){return this.x=e._x,this.y=e._y,this.z=e._z,this}setFromColor(e){return this.x=e.r,this.y=e.g,this.z=e.b,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let e=Math.random()*Math.PI*2,t=2*Math.random()-1,n=Math.sqrt(1-t*t);return this.x=n*Math.cos(e),this.y=t,this.z=n*Math.sin(e),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},cc=new D,Zu=new kt,et=class r{constructor(e,t,n,i,s,a,o,c,l){r.prototype.isMatrix3=!0,this.elements=[1,0,0,0,1,0,0,0,1],e!==void 0&&this.set(e,t,n,i,s,a,o,c,l)}set(e,t,n,i,s,a,o,c,l){let h=this.elements;return h[0]=e,h[1]=i,h[2]=o,h[3]=t,h[4]=s,h[5]=c,h[6]=n,h[7]=a,h[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(e){let t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],this}extractBasis(e,t,n){return e.setFromMatrix3Column(this,0),t.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(e){let t=e.elements;return this.set(t[0],t[4],t[8],t[1],t[5],t[9],t[2],t[6],t[10]),this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){let n=e.elements,i=t.elements,s=this.elements,a=n[0],o=n[3],c=n[6],l=n[1],h=n[4],p=n[7],f=n[2],m=n[5],u=n[8],g=i[0],x=i[3],_=i[6],v=i[1],S=i[4],E=i[7],w=i[2],R=i[5],z=i[8];return s[0]=a*g+o*v+c*w,s[3]=a*x+o*S+c*R,s[6]=a*_+o*E+c*z,s[1]=l*g+h*v+p*w,s[4]=l*x+h*S+p*R,s[7]=l*_+h*E+p*z,s[2]=f*g+m*v+u*w,s[5]=f*x+m*S+u*R,s[8]=f*_+m*E+u*z,this}multiplyScalar(e){let t=this.elements;return t[0]*=e,t[3]*=e,t[6]*=e,t[1]*=e,t[4]*=e,t[7]*=e,t[2]*=e,t[5]*=e,t[8]*=e,this}determinant(){let e=this.elements,t=e[0],n=e[1],i=e[2],s=e[3],a=e[4],o=e[5],c=e[6],l=e[7],h=e[8];return t*a*h-t*o*l-n*s*h+n*o*c+i*s*l-i*a*c}invert(){let e=this.elements,t=e[0],n=e[1],i=e[2],s=e[3],a=e[4],o=e[5],c=e[6],l=e[7],h=e[8],p=h*a-o*l,f=o*c-h*s,m=l*s-a*c,u=t*p+n*f+i*m;if(u===0)return this.set(0,0,0,0,0,0,0,0,0);let g=1/u;return e[0]=p*g,e[1]=(i*l-h*n)*g,e[2]=(o*n-i*a)*g,e[3]=f*g,e[4]=(h*t-i*c)*g,e[5]=(i*s-o*t)*g,e[6]=m*g,e[7]=(n*c-l*t)*g,e[8]=(a*t-n*s)*g,this}transpose(){let e,t=this.elements;return e=t[1],t[1]=t[3],t[3]=e,e=t[2],t[2]=t[6],t[6]=e,e=t[5],t[5]=t[7],t[7]=e,this}getNormalMatrix(e){return this.setFromMatrix4(e).invert().transpose()}transposeIntoArray(e){let t=this.elements;return e[0]=t[0],e[1]=t[3],e[2]=t[6],e[3]=t[1],e[4]=t[4],e[5]=t[7],e[6]=t[2],e[7]=t[5],e[8]=t[8],this}setUvTransform(e,t,n,i,s,a,o){let c=Math.cos(s),l=Math.sin(s);return this.set(n*c,n*l,-n*(c*a+l*o)+a+e,-i*l,i*c,-i*(-l*a+c*o)+o+t,0,0,1),this}scale(e,t){return this.premultiply(hc.makeScale(e,t)),this}rotate(e){return this.premultiply(hc.makeRotation(-e)),this}translate(e,t){return this.premultiply(hc.makeTranslation(e,t)),this}makeTranslation(e,t){return e.isVector2?this.set(1,0,e.x,0,1,e.y,0,0,1):this.set(1,0,e,0,1,t,0,0,1),this}makeRotation(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,n,t,0,0,0,1),this}makeScale(e,t){return this.set(e,0,0,0,t,0,0,0,1),this}equals(e){let t=this.elements,n=e.elements;for(let i=0;i<9;i++)if(t[i]!==n[i])return!1;return!0}fromArray(e,t=0){for(let n=0;n<9;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){let n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e}clone(){return new this.constructor().fromArray(this.elements)}},hc=new et,Ju=new et().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Ku=new et().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function Tf(){let r={enabled:!0,workingColorSpace:ur,spaces:{},convert:function(i,s,a){return this.enabled!==!1&&s!==a&&s&&a&&(this.spaces[s].transfer===gt&&(i.r=Ci(i.r),i.g=Ci(i.g),i.b=Ci(i.b)),this.spaces[s].primaries!==this.spaces[a].primaries&&(i.applyMatrix3(this.spaces[s].toXYZ),i.applyMatrix3(this.spaces[a].fromXYZ)),this.spaces[a].transfer===gt&&(i.r=Yr(i.r),i.g=Yr(i.g),i.b=Yr(i.b))),i},workingToColorSpace:function(i,s){return this.convert(i,this.workingColorSpace,s)},colorSpaceToWorking:function(i,s){return this.convert(i,s,this.workingColorSpace)},getPrimaries:function(i){return this.spaces[i].primaries},getTransfer:function(i){return i===""?Ys:this.spaces[i].transfer},getToneMappingMode:function(i){return this.spaces[i].outputColorSpaceConfig.toneMappingMode||"standard"},getLuminanceCoefficients:function(i,s=this.workingColorSpace){return i.fromArray(this.spaces[s].luminanceCoefficients)},define:function(i){Object.assign(this.spaces,i)},_getMatrix:function(i,s,a){return i.copy(this.spaces[s].toXYZ).multiply(this.spaces[a].fromXYZ)},_getDrawingBufferColorSpace:function(i){return this.spaces[i].outputColorSpaceConfig.drawingBufferColorSpace},_getUnpackColorSpace:function(i=this.workingColorSpace){return this.spaces[i].workingColorSpaceConfig.unpackColorSpace},fromWorkingColorSpace:function(i,s){return Zs("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),r.workingToColorSpace(i,s)},toWorkingColorSpace:function(i,s){return Zs("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),r.colorSpaceToWorking(i,s)}},e=[.64,.33,.3,.6,.15,.06],t=[.2126,.7152,.0722],n=[.3127,.329];return r.define({[ur]:{primaries:e,whitePoint:n,transfer:Ys,toXYZ:Ju,fromXYZ:Ku,luminanceCoefficients:t,workingColorSpaceConfig:{unpackColorSpace:Ut},outputColorSpaceConfig:{drawingBufferColorSpace:Ut}},[Ut]:{primaries:e,whitePoint:n,transfer:gt,toXYZ:Ju,fromXYZ:Ku,luminanceCoefficients:t,outputColorSpaceConfig:{drawingBufferColorSpace:Ut}}}),r}var ut=Tf();function Ci(r){return r<.04045?.0773993808*r:Math.pow(.9478672986*r+.0521327014,2.4)}function Yr(r){return r<.0031308?12.92*r:1.055*Math.pow(r,.41666)-.055}var Dr,Po=class{static getDataURL(e,t="image/png"){if(/^data:/i.test(e.src)||typeof HTMLCanvasElement>"u")return e.src;let n;if(e instanceof HTMLCanvasElement)n=e;else{Dr===void 0&&(Dr=Jr("canvas")),Dr.width=e.width,Dr.height=e.height;let i=Dr.getContext("2d");e instanceof ImageData?i.putImageData(e,0,0):i.drawImage(e,0,0,e.width,e.height),n=Dr}return n.toDataURL(t)}static sRGBToLinear(e){if(typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&e instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&e instanceof ImageBitmap){let t=Jr("canvas");t.width=e.width,t.height=e.height;let n=t.getContext("2d");n.drawImage(e,0,0,e.width,e.height);let i=n.getImageData(0,0,e.width,e.height),s=i.data;for(let a=0;a<s.length;a++)s[a]=255*Ci(s[a]/255);return n.putImageData(i,0,0),t}if(e.data){let t=e.data.slice(0);for(let n=0;n<t.length;n++)t instanceof Uint8Array||t instanceof Uint8ClampedArray?t[n]=Math.floor(255*Ci(t[n]/255)):t[n]=Ci(t[n]);return{data:t,width:e.width,height:e.height}}return Ye("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),e}},Ef=0,Qr=class{constructor(e=null){this.isSource=!0,Object.defineProperty(this,"id",{value:Ef++}),this.uuid=vr(),this.data=e,this.dataReady=!0,this.version=0}getSize(e){let t=this.data;return typeof HTMLVideoElement<"u"&&t instanceof HTMLVideoElement?e.set(t.videoWidth,t.videoHeight,0):typeof VideoFrame<"u"&&t instanceof VideoFrame?e.set(t.displayHeight,t.displayWidth,0):t!==null?e.set(t.width,t.height,t.depth||0):e.set(0,0,0),e}set needsUpdate(e){e===!0&&this.version++}toJSON(e){let t=e===void 0||typeof e=="string";if(!t&&e.images[this.uuid]!==void 0)return e.images[this.uuid];let n={uuid:this.uuid,url:""},i=this.data;if(i!==null){let s;if(Array.isArray(i)){s=[];for(let a=0,o=i.length;a<o;a++)i[a].isDataTexture?s.push(uc(i[a].image)):s.push(uc(i[a]))}else s=uc(i);n.url=s}return t||(e.images[this.uuid]=n),n}};function uc(r){return typeof HTMLImageElement<"u"&&r instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&r instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&r instanceof ImageBitmap?Po.getDataURL(r):r.data?{data:Array.from(r.data),width:r.width,height:r.height,type:r.data.constructor.name}:(Ye("Texture: Unable to serialize Texture."),{})}var wf=0,dc=new D,an=class r extends pi{constructor(e=r.DEFAULT_IMAGE,t=r.DEFAULT_MAPPING,n=1001,i=1001,s=1006,a=1008,o=1023,c=1009,l=r.DEFAULT_ANISOTROPY,h=""){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:wf++}),this.uuid=vr(),this.name="",this.source=new Qr(e),this.mipmaps=[],this.mapping=t,this.channel=0,this.wrapS=n,this.wrapT=i,this.magFilter=s,this.minFilter=a,this.anisotropy=l,this.format=o,this.internalFormat=null,this.type=c,this.offset=new _e(0,0),this.repeat=new _e(1,1),this.center=new _e(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new et,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=h,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(e&&e.depth&&e.depth>1),this.pmremVersion=0}get width(){return this.source.getSize(dc).x}get height(){return this.source.getSize(dc).y}get depth(){return this.source.getSize(dc).z}get image(){return this.source.data}set image(e=null){this.source.data=e}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(e){return this.name=e.name,this.source=e.source,this.mipmaps=e.mipmaps.slice(0),this.mapping=e.mapping,this.channel=e.channel,this.wrapS=e.wrapS,this.wrapT=e.wrapT,this.magFilter=e.magFilter,this.minFilter=e.minFilter,this.anisotropy=e.anisotropy,this.format=e.format,this.internalFormat=e.internalFormat,this.type=e.type,this.offset.copy(e.offset),this.repeat.copy(e.repeat),this.center.copy(e.center),this.rotation=e.rotation,this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrix.copy(e.matrix),this.generateMipmaps=e.generateMipmaps,this.premultiplyAlpha=e.premultiplyAlpha,this.flipY=e.flipY,this.unpackAlignment=e.unpackAlignment,this.colorSpace=e.colorSpace,this.renderTarget=e.renderTarget,this.isRenderTargetTexture=e.isRenderTargetTexture,this.isArrayTexture=e.isArrayTexture,this.userData=JSON.parse(JSON.stringify(e.userData)),this.needsUpdate=!0,this}setValues(e){for(let t in e){let n=e[t];if(n===void 0){Ye(`Texture.setValues(): parameter '${t}' has value of undefined.`);continue}let i=this[t];i!==void 0?i&&n&&i.isVector2&&n.isVector2||i&&n&&i.isVector3&&n.isVector3||i&&n&&i.isMatrix3&&n.isMatrix3?i.copy(n):this[t]=n:Ye(`Texture.setValues(): property '${t}' does not exist.`)}}toJSON(e){let t=e===void 0||typeof e=="string";if(!t&&e.textures[this.uuid]!==void 0)return e.textures[this.uuid];let n={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(e).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),t||(e.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(e){if(this.mapping!==ph)return e;if(e.applyMatrix3(this.matrix),e.x<0||e.x>1)switch(this.wrapS){case hr:e.x=e.x-Math.floor(e.x);break;case Wi:e.x=e.x<0?0:1;break;case Co:Math.abs(Math.floor(e.x)%2)===1?e.x=Math.ceil(e.x)-e.x:e.x=e.x-Math.floor(e.x)}if(e.y<0||e.y>1)switch(this.wrapT){case hr:e.y=e.y-Math.floor(e.y);break;case Wi:e.y=e.y<0?0:1;break;case Co:Math.abs(Math.floor(e.y)%2)===1?e.y=Math.ceil(e.y)-e.y:e.y=e.y-Math.floor(e.y)}return this.flipY&&(e.y=1-e.y),e}set needsUpdate(e){e===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(e){e===!0&&this.pmremVersion++}};an.DEFAULT_IMAGE=null,an.DEFAULT_MAPPING=ph,an.DEFAULT_ANISOTROPY=1;var wt=class r{constructor(e=0,t=0,n=0,i=1){r.prototype.isVector4=!0,this.x=e,this.y=t,this.z=n,this.w=i}get width(){return this.z}set width(e){this.z=e}get height(){return this.w}set height(e){this.w=e}set(e,t,n,i){return this.x=e,this.y=t,this.z=n,this.w=i,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this.w=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setW(e){return this.w=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;case 3:this.w=t;break;default:throw new Error("index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this.w=e.w!==void 0?e.w:1,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this.w+=e.w,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this.w+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this.w=e.w+t.w,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this.w+=e.w*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this.w-=e.w,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this.w-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this.w=e.w-t.w,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this.w*=e.w,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this.w*=e,this}applyMatrix4(e){let t=this.x,n=this.y,i=this.z,s=this.w,a=e.elements;return this.x=a[0]*t+a[4]*n+a[8]*i+a[12]*s,this.y=a[1]*t+a[5]*n+a[9]*i+a[13]*s,this.z=a[2]*t+a[6]*n+a[10]*i+a[14]*s,this.w=a[3]*t+a[7]*n+a[11]*i+a[15]*s,this}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this.w/=e.w,this}divideScalar(e){return this.multiplyScalar(1/e)}setAxisAngleFromQuaternion(e){this.w=2*Math.acos(e.w);let t=Math.sqrt(1-e.w*e.w);return t<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=e.x/t,this.y=e.y/t,this.z=e.z/t),this}setAxisAngleFromRotationMatrix(e){let t,n,i,s,c=e.elements,l=c[0],h=c[4],p=c[8],f=c[1],m=c[5],u=c[9],g=c[2],x=c[6],_=c[10];if(Math.abs(h-f)<.01&&Math.abs(p-g)<.01&&Math.abs(u-x)<.01){if(Math.abs(h+f)<.1&&Math.abs(p+g)<.1&&Math.abs(u+x)<.1&&Math.abs(l+m+_-3)<.1)return this.set(1,0,0,0),this;t=Math.PI;let S=(l+1)/2,E=(m+1)/2,w=(_+1)/2,R=(h+f)/4,z=(p+g)/4,j=(u+x)/4;return S>E&&S>w?S<.01?(n=0,i=.707106781,s=.707106781):(n=Math.sqrt(S),i=R/n,s=z/n):E>w?E<.01?(n=.707106781,i=0,s=.707106781):(i=Math.sqrt(E),n=R/i,s=j/i):w<.01?(n=.707106781,i=.707106781,s=0):(s=Math.sqrt(w),n=z/s,i=j/s),this.set(n,i,s,t),this}let v=Math.sqrt((x-u)*(x-u)+(p-g)*(p-g)+(f-h)*(f-h));return Math.abs(v)<.001&&(v=1),this.x=(x-u)/v,this.y=(p-g)/v,this.z=(f-h)/v,this.w=Math.acos((l+m+_-1)/2),this}setFromMatrixPosition(e){let t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this.w=t[15],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this.w=Math.min(this.w,e.w),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this.w=Math.max(this.w,e.w),this}clamp(e,t){return this.x=nt(this.x,e.x,t.x),this.y=nt(this.y,e.y,t.y),this.z=nt(this.z,e.z,t.z),this.w=nt(this.w,e.w,t.w),this}clampScalar(e,t){return this.x=nt(this.x,e,t),this.y=nt(this.y,e,t),this.z=nt(this.z,e,t),this.w=nt(this.w,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(nt(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z+this.w*e.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this.w+=(e.w-this.w)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this.w=e.w+(t.w-e.w)*n,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z&&e.w===this.w}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this.w=e[t+3],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e[t+3]=this.w,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this.w=e.getW(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}},Io=class extends pi{constructor(e=1,t=1,n={}){super(),n=Object.assign({generateMipmaps:!1,internalFormat:null,minFilter:Xt,depthBuffer:!0,stencilBuffer:!1,resolveDepthBuffer:!0,resolveStencilBuffer:!0,depthTexture:null,samples:0,count:1,depth:1,multiview:!1},n),this.isRenderTarget=!0,this.width=e,this.height=t,this.depth=n.depth,this.scissor=new wt(0,0,e,t),this.scissorTest=!1,this.viewport=new wt(0,0,e,t),this.textures=[];let i={width:e,height:t,depth:n.depth},s=new an(i),a=n.count;for(let o=0;o<a;o++)this.textures[o]=s.clone(),this.textures[o].isRenderTargetTexture=!0,this.textures[o].renderTarget=this;this._setTextureOptions(n),this.depthBuffer=n.depthBuffer,this.stencilBuffer=n.stencilBuffer,this.resolveDepthBuffer=n.resolveDepthBuffer,this.resolveStencilBuffer=n.resolveStencilBuffer,this._depthTexture=null,this.depthTexture=n.depthTexture,this.samples=n.samples,this.multiview=n.multiview}_setTextureOptions(e={}){let t={minFilter:Xt,generateMipmaps:!1,flipY:!1,internalFormat:null};e.mapping!==void 0&&(t.mapping=e.mapping),e.wrapS!==void 0&&(t.wrapS=e.wrapS),e.wrapT!==void 0&&(t.wrapT=e.wrapT),e.wrapR!==void 0&&(t.wrapR=e.wrapR),e.magFilter!==void 0&&(t.magFilter=e.magFilter),e.minFilter!==void 0&&(t.minFilter=e.minFilter),e.format!==void 0&&(t.format=e.format),e.type!==void 0&&(t.type=e.type),e.anisotropy!==void 0&&(t.anisotropy=e.anisotropy),e.colorSpace!==void 0&&(t.colorSpace=e.colorSpace),e.flipY!==void 0&&(t.flipY=e.flipY),e.generateMipmaps!==void 0&&(t.generateMipmaps=e.generateMipmaps),e.internalFormat!==void 0&&(t.internalFormat=e.internalFormat);for(let n=0;n<this.textures.length;n++)this.textures[n].setValues(t)}get texture(){return this.textures[0]}set texture(e){this.textures[0]=e}set depthTexture(e){this._depthTexture!==null&&(this._depthTexture.renderTarget=null),e!==null&&(e.renderTarget=this),this._depthTexture=e}get depthTexture(){return this._depthTexture}setSize(e,t,n=1){if(this.width!==e||this.height!==t||this.depth!==n){this.width=e,this.height=t,this.depth=n;for(let i=0,s=this.textures.length;i<s;i++)this.textures[i].image.width=e,this.textures[i].image.height=t,this.textures[i].image.depth=n,this.textures[i].isData3DTexture!==!0&&(this.textures[i].isArrayTexture=this.textures[i].image.depth>1);this.dispose()}this.viewport.set(0,0,e,t),this.scissor.set(0,0,e,t)}clone(){return new this.constructor().copy(this)}copy(e){this.width=e.width,this.height=e.height,this.depth=e.depth,this.scissor.copy(e.scissor),this.scissorTest=e.scissorTest,this.viewport.copy(e.viewport),this.textures.length=0;for(let t=0,n=e.textures.length;t<n;t++){this.textures[t]=e.textures[t].clone(),this.textures[t].isRenderTargetTexture=!0,this.textures[t].renderTarget=this;let i=Object.assign({},e.textures[t].image);this.textures[t].source=new Qr(i)}return this.depthBuffer=e.depthBuffer,this.stencilBuffer=e.stencilBuffer,this.resolveDepthBuffer=e.resolveDepthBuffer,this.resolveStencilBuffer=e.resolveStencilBuffer,e.depthTexture!==null&&(this.depthTexture=e.depthTexture.clone()),this.samples=e.samples,this}dispose(){this.dispatchEvent({type:"dispose"})}},Dn=class extends Io{constructor(e=1,t=1,n={}){super(e,t,n),this.isWebGLRenderTarget=!0}},Js=class extends an{constructor(e=null,t=1,n=1,i=1){super(null),this.isDataArrayTexture=!0,this.image={data:e,width:t,height:n,depth:i},this.magFilter=Yn,this.minFilter=Yn,this.wrapR=Wi,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1,this.layerUpdates=new Set}addLayerUpdate(e){this.layerUpdates.add(e)}clearLayerUpdates(){this.layerUpdates.clear()}};var Lo=class extends an{constructor(e=null,t=1,n=1,i=1){super(null),this.isData3DTexture=!0,this.image={data:e,width:t,height:n,depth:i},this.magFilter=Yn,this.minFilter=Yn,this.wrapR=Wi,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}};var Ke=class r{constructor(e,t,n,i,s,a,o,c,l,h,p,f,m,u,g,x){r.prototype.isMatrix4=!0,this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],e!==void 0&&this.set(e,t,n,i,s,a,o,c,l,h,p,f,m,u,g,x)}set(e,t,n,i,s,a,o,c,l,h,p,f,m,u,g,x){let _=this.elements;return _[0]=e,_[4]=t,_[8]=n,_[12]=i,_[1]=s,_[5]=a,_[9]=o,_[13]=c,_[2]=l,_[6]=h,_[10]=p,_[14]=f,_[3]=m,_[7]=u,_[11]=g,_[15]=x,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new r().fromArray(this.elements)}copy(e){let t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],t[9]=n[9],t[10]=n[10],t[11]=n[11],t[12]=n[12],t[13]=n[13],t[14]=n[14],t[15]=n[15],this}copyPosition(e){let t=this.elements,n=e.elements;return t[12]=n[12],t[13]=n[13],t[14]=n[14],this}setFromMatrix3(e){let t=e.elements;return this.set(t[0],t[3],t[6],0,t[1],t[4],t[7],0,t[2],t[5],t[8],0,0,0,0,1),this}extractBasis(e,t,n){return this.determinant()===0?(e.set(1,0,0),t.set(0,1,0),n.set(0,0,1),this):(e.setFromMatrixColumn(this,0),t.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this)}makeBasis(e,t,n){return this.set(e.x,t.x,n.x,0,e.y,t.y,n.y,0,e.z,t.z,n.z,0,0,0,0,1),this}extractRotation(e){if(e.determinant()===0)return this.identity();let t=this.elements,n=e.elements,i=1/Ur.setFromMatrixColumn(e,0).length(),s=1/Ur.setFromMatrixColumn(e,1).length(),a=1/Ur.setFromMatrixColumn(e,2).length();return t[0]=n[0]*i,t[1]=n[1]*i,t[2]=n[2]*i,t[3]=0,t[4]=n[4]*s,t[5]=n[5]*s,t[6]=n[6]*s,t[7]=0,t[8]=n[8]*a,t[9]=n[9]*a,t[10]=n[10]*a,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromEuler(e){let t=this.elements,n=e.x,i=e.y,s=e.z,a=Math.cos(n),o=Math.sin(n),c=Math.cos(i),l=Math.sin(i),h=Math.cos(s),p=Math.sin(s);if(e.order==="XYZ"){let f=a*h,m=a*p,u=o*h,g=o*p;t[0]=c*h,t[4]=-c*p,t[8]=l,t[1]=m+u*l,t[5]=f-g*l,t[9]=-o*c,t[2]=g-f*l,t[6]=u+m*l,t[10]=a*c}else if(e.order==="YXZ"){let f=c*h,m=c*p,u=l*h,g=l*p;t[0]=f+g*o,t[4]=u*o-m,t[8]=a*l,t[1]=a*p,t[5]=a*h,t[9]=-o,t[2]=m*o-u,t[6]=g+f*o,t[10]=a*c}else if(e.order==="ZXY"){let f=c*h,m=c*p,u=l*h,g=l*p;t[0]=f-g*o,t[4]=-a*p,t[8]=u+m*o,t[1]=m+u*o,t[5]=a*h,t[9]=g-f*o,t[2]=-a*l,t[6]=o,t[10]=a*c}else if(e.order==="ZYX"){let f=a*h,m=a*p,u=o*h,g=o*p;t[0]=c*h,t[4]=u*l-m,t[8]=f*l+g,t[1]=c*p,t[5]=g*l+f,t[9]=m*l-u,t[2]=-l,t[6]=o*c,t[10]=a*c}else if(e.order==="YZX"){let f=a*c,m=a*l,u=o*c,g=o*l;t[0]=c*h,t[4]=g-f*p,t[8]=u*p+m,t[1]=p,t[5]=a*h,t[9]=-o*h,t[2]=-l*h,t[6]=m*p+u,t[10]=f-g*p}else if(e.order==="XZY"){let f=a*c,m=a*l,u=o*c,g=o*l;t[0]=c*h,t[4]=-p,t[8]=l*h,t[1]=f*p+g,t[5]=a*h,t[9]=m*p-u,t[2]=u*p-m,t[6]=o*h,t[10]=g*p+f}return t[3]=0,t[7]=0,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromQuaternion(e){return this.compose(Af,e,Cf)}lookAt(e,t,n){let i=this.elements;return Pn.subVectors(e,t),Pn.lengthSq()===0&&(Pn.z=1),Pn.normalize(),Oi.crossVectors(n,Pn),Oi.lengthSq()===0&&(Math.abs(n.z)===1?Pn.x+=1e-4:Pn.z+=1e-4,Pn.normalize(),Oi.crossVectors(n,Pn)),Oi.normalize(),Ja.crossVectors(Pn,Oi),i[0]=Oi.x,i[4]=Ja.x,i[8]=Pn.x,i[1]=Oi.y,i[5]=Ja.y,i[9]=Pn.y,i[2]=Oi.z,i[6]=Ja.z,i[10]=Pn.z,this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){let n=e.elements,i=t.elements,s=this.elements,a=n[0],o=n[4],c=n[8],l=n[12],h=n[1],p=n[5],f=n[9],m=n[13],u=n[2],g=n[6],x=n[10],_=n[14],v=n[3],S=n[7],E=n[11],w=n[15],R=i[0],z=i[4],j=i[8],O=i[12],Q=i[1],Y=i[5],k=i[9],X=i[13],K=i[2],te=i[6],oe=i[10],ee=i[14],xe=i[3],be=i[7],we=i[11],Se=i[15];return s[0]=a*R+o*Q+c*K+l*xe,s[4]=a*z+o*Y+c*te+l*be,s[8]=a*j+o*k+c*oe+l*we,s[12]=a*O+o*X+c*ee+l*Se,s[1]=h*R+p*Q+f*K+m*xe,s[5]=h*z+p*Y+f*te+m*be,s[9]=h*j+p*k+f*oe+m*we,s[13]=h*O+p*X+f*ee+m*Se,s[2]=u*R+g*Q+x*K+_*xe,s[6]=u*z+g*Y+x*te+_*be,s[10]=u*j+g*k+x*oe+_*we,s[14]=u*O+g*X+x*ee+_*Se,s[3]=v*R+S*Q+E*K+w*xe,s[7]=v*z+S*Y+E*te+w*be,s[11]=v*j+S*k+E*oe+w*we,s[15]=v*O+S*X+E*ee+w*Se,this}multiplyScalar(e){let t=this.elements;return t[0]*=e,t[4]*=e,t[8]*=e,t[12]*=e,t[1]*=e,t[5]*=e,t[9]*=e,t[13]*=e,t[2]*=e,t[6]*=e,t[10]*=e,t[14]*=e,t[3]*=e,t[7]*=e,t[11]*=e,t[15]*=e,this}determinant(){let e=this.elements,t=e[0],n=e[4],i=e[8],s=e[12],a=e[1],o=e[5],c=e[9],l=e[13],h=e[2],p=e[6],f=e[10],m=e[14],u=e[3],g=e[7],x=e[11],_=e[15],v=c*m-l*f,S=o*m-l*p,E=o*f-c*p,w=a*m-l*h,R=a*f-c*h,z=a*p-o*h;return t*(g*v-x*S+_*E)-n*(u*v-x*w+_*R)+i*(u*S-g*w+_*z)-s*(u*E-g*R+x*z)}transpose(){let e=this.elements,t;return t=e[1],e[1]=e[4],e[4]=t,t=e[2],e[2]=e[8],e[8]=t,t=e[6],e[6]=e[9],e[9]=t,t=e[3],e[3]=e[12],e[12]=t,t=e[7],e[7]=e[13],e[13]=t,t=e[11],e[11]=e[14],e[14]=t,this}setPosition(e,t,n){let i=this.elements;return e.isVector3?(i[12]=e.x,i[13]=e.y,i[14]=e.z):(i[12]=e,i[13]=t,i[14]=n),this}invert(){let e=this.elements,t=e[0],n=e[1],i=e[2],s=e[3],a=e[4],o=e[5],c=e[6],l=e[7],h=e[8],p=e[9],f=e[10],m=e[11],u=e[12],g=e[13],x=e[14],_=e[15],v=t*o-n*a,S=t*c-i*a,E=t*l-s*a,w=n*c-i*o,R=n*l-s*o,z=i*l-s*c,j=h*g-p*u,O=h*x-f*u,Q=h*_-m*u,Y=p*x-f*g,k=p*_-m*g,X=f*_-m*x,K=v*X-S*k+E*Y+w*Q-R*O+z*j;if(K===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let te=1/K;return e[0]=(o*X-c*k+l*Y)*te,e[1]=(i*k-n*X-s*Y)*te,e[2]=(g*z-x*R+_*w)*te,e[3]=(f*R-p*z-m*w)*te,e[4]=(c*Q-a*X-l*O)*te,e[5]=(t*X-i*Q+s*O)*te,e[6]=(x*E-u*z-_*S)*te,e[7]=(h*z-f*E+m*S)*te,e[8]=(a*k-o*Q+l*j)*te,e[9]=(n*Q-t*k-s*j)*te,e[10]=(u*R-g*E+_*v)*te,e[11]=(p*E-h*R-m*v)*te,e[12]=(o*O-a*Y-c*j)*te,e[13]=(t*Y-n*O+i*j)*te,e[14]=(g*S-u*w-x*v)*te,e[15]=(h*w-p*S+f*v)*te,this}scale(e){let t=this.elements,n=e.x,i=e.y,s=e.z;return t[0]*=n,t[4]*=i,t[8]*=s,t[1]*=n,t[5]*=i,t[9]*=s,t[2]*=n,t[6]*=i,t[10]*=s,t[3]*=n,t[7]*=i,t[11]*=s,this}getMaxScaleOnAxis(){let e=this.elements,t=e[0]*e[0]+e[1]*e[1]+e[2]*e[2],n=e[4]*e[4]+e[5]*e[5]+e[6]*e[6],i=e[8]*e[8]+e[9]*e[9]+e[10]*e[10];return Math.sqrt(Math.max(t,n,i))}makeTranslation(e,t,n){return e.isVector3?this.set(1,0,0,e.x,0,1,0,e.y,0,0,1,e.z,0,0,0,1):this.set(1,0,0,e,0,1,0,t,0,0,1,n,0,0,0,1),this}makeRotationX(e){let t=Math.cos(e),n=Math.sin(e);return this.set(1,0,0,0,0,t,-n,0,0,n,t,0,0,0,0,1),this}makeRotationY(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,0,n,0,0,1,0,0,-n,0,t,0,0,0,0,1),this}makeRotationZ(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,0,n,t,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(e,t){let n=Math.cos(t),i=Math.sin(t),s=1-n,a=e.x,o=e.y,c=e.z,l=s*a,h=s*o;return this.set(l*a+n,l*o-i*c,l*c+i*o,0,l*o+i*c,h*o+n,h*c-i*a,0,l*c-i*o,h*c+i*a,s*c*c+n,0,0,0,0,1),this}makeScale(e,t,n){return this.set(e,0,0,0,0,t,0,0,0,0,n,0,0,0,0,1),this}makeShear(e,t,n,i,s,a){return this.set(1,n,s,0,e,1,a,0,t,i,1,0,0,0,0,1),this}compose(e,t,n){let i=this.elements,s=t._x,a=t._y,o=t._z,c=t._w,l=s+s,h=a+a,p=o+o,f=s*l,m=s*h,u=s*p,g=a*h,x=a*p,_=o*p,v=c*l,S=c*h,E=c*p,w=n.x,R=n.y,z=n.z;return i[0]=(1-(g+_))*w,i[1]=(m+E)*w,i[2]=(u-S)*w,i[3]=0,i[4]=(m-E)*R,i[5]=(1-(f+_))*R,i[6]=(x+v)*R,i[7]=0,i[8]=(u+S)*z,i[9]=(x-v)*z,i[10]=(1-(f+g))*z,i[11]=0,i[12]=e.x,i[13]=e.y,i[14]=e.z,i[15]=1,this}decompose(e,t,n){let i=this.elements;e.x=i[12],e.y=i[13],e.z=i[14];let s=this.determinant();if(s===0)return n.set(1,1,1),t.identity(),this;let a=Ur.set(i[0],i[1],i[2]).length(),o=Ur.set(i[4],i[5],i[6]).length(),c=Ur.set(i[8],i[9],i[10]).length();s<0&&(a=-a),ti.copy(this);let l=1/a,h=1/o,p=1/c;return ti.elements[0]*=l,ti.elements[1]*=l,ti.elements[2]*=l,ti.elements[4]*=h,ti.elements[5]*=h,ti.elements[6]*=h,ti.elements[8]*=p,ti.elements[9]*=p,ti.elements[10]*=p,t.setFromRotationMatrix(ti),n.x=a,n.y=o,n.z=c,this}makePerspective(e,t,n,i,s,a,o=2e3,c=!1){let l=this.elements,h=2*s/(t-e),p=2*s/(n-i),f=(t+e)/(t-e),m=(n+i)/(n-i),u,g;if(c)u=s/(a-s),g=a*s/(a-s);else if(o===Ri)u=-(a+s)/(a-s),g=-2*a*s/(a-s);else{if(o!==Zr)throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+o);u=-a/(a-s),g=-a*s/(a-s)}return l[0]=h,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=p,l[9]=m,l[13]=0,l[2]=0,l[6]=0,l[10]=u,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(e,t,n,i,s,a,o=2e3,c=!1){let l=this.elements,h=2/(t-e),p=2/(n-i),f=-(t+e)/(t-e),m=-(n+i)/(n-i),u,g;if(c)u=1/(a-s),g=a/(a-s);else if(o===Ri)u=-2/(a-s),g=-(a+s)/(a-s);else{if(o!==Zr)throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+o);u=-1/(a-s),g=-s/(a-s)}return l[0]=h,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=p,l[9]=0,l[13]=m,l[2]=0,l[6]=0,l[10]=u,l[14]=g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(e){let t=this.elements,n=e.elements;for(let i=0;i<16;i++)if(t[i]!==n[i])return!1;return!0}fromArray(e,t=0){for(let n=0;n<16;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){let n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e[t+9]=n[9],e[t+10]=n[10],e[t+11]=n[11],e[t+12]=n[12],e[t+13]=n[13],e[t+14]=n[14],e[t+15]=n[15],e}},Ur=new D,ti=new Ke,Af=new D(0,0,0),Cf=new D(1,1,1),Oi=new D,Ja=new D,Pn=new D,$u=new Ke,Qu=new kt,Un=class r{constructor(e=0,t=0,n=0,i=r.DEFAULT_ORDER){this.isEuler=!0,this._x=e,this._y=t,this._z=n,this._order=i}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get order(){return this._order}set order(e){this._order=e,this._onChangeCallback()}set(e,t,n,i=this._order){return this._x=e,this._y=t,this._z=n,this._order=i,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(e){return this._x=e._x,this._y=e._y,this._z=e._z,this._order=e._order,this._onChangeCallback(),this}setFromRotationMatrix(e,t=this._order,n=!0){let i=e.elements,s=i[0],a=i[4],o=i[8],c=i[1],l=i[5],h=i[9],p=i[2],f=i[6],m=i[10];switch(t){case"XYZ":this._y=Math.asin(nt(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(-h,m),this._z=Math.atan2(-a,s)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-nt(h,-1,1)),Math.abs(h)<.9999999?(this._y=Math.atan2(o,m),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-p,s),this._z=0);break;case"ZXY":this._x=Math.asin(nt(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-p,m),this._z=Math.atan2(-a,l)):(this._y=0,this._z=Math.atan2(c,s));break;case"ZYX":this._y=Math.asin(-nt(p,-1,1)),Math.abs(p)<.9999999?(this._x=Math.atan2(f,m),this._z=Math.atan2(c,s)):(this._x=0,this._z=Math.atan2(-a,l));break;case"YZX":this._z=Math.asin(nt(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-h,l),this._y=Math.atan2(-p,s)):(this._x=0,this._y=Math.atan2(o,m));break;case"XZY":this._z=Math.asin(-nt(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(o,s)):(this._x=Math.atan2(-h,m),this._y=0);break;default:Ye("Euler: .setFromRotationMatrix() encountered an unknown order: "+t)}return this._order=t,n===!0&&this._onChangeCallback(),this}setFromQuaternion(e,t,n){return $u.makeRotationFromQuaternion(e),this.setFromRotationMatrix($u,t,n)}setFromVector3(e,t=this._order){return this.set(e.x,e.y,e.z,t)}reorder(e){return Qu.setFromEuler(this),this.setFromQuaternion(Qu,e)}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._order===this._order}fromArray(e){return this._x=e[0],this._y=e[1],this._z=e[2],e[3]!==void 0&&(this._order=e[3]),this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._order,e}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};Un.DEFAULT_ORDER="XYZ";var es=class{constructor(){this.mask=1}set(e){this.mask=1<<e>>>0}enable(e){this.mask|=1<<e}enableAll(){this.mask=-1}toggle(e){this.mask^=1<<e}disable(e){this.mask&=~(1<<e)}disableAll(){this.mask=0}test(e){return(this.mask&e.mask)!==0}isEnabled(e){return!!(this.mask&1<<e)}},Rf=0,ed=new D,Nr=new kt,bi=new Ke,Ka=new D,Os=new D,Pf=new D,If=new kt,td=new D(1,0,0),nd=new D(0,1,0),id=new D(0,0,1),rd={type:"added"},Lf={type:"removed"},Or={type:"childadded",child:null},pc={type:"childremoved",child:null},Ft=class r extends pi{constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:Rf++}),this.uuid=vr(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=r.DEFAULT_UP.clone();let e=new D,t=new Un,n=new kt,i=new D(1,1,1);t._onChange(function(){n.setFromEuler(t,!1)}),n._onChange(function(){t.setFromQuaternion(n,void 0,!1)}),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:e},rotation:{configurable:!0,enumerable:!0,value:t},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:i},modelViewMatrix:{value:new Ke},normalMatrix:{value:new et}}),this.matrix=new Ke,this.matrixWorld=new Ke,this.matrixAutoUpdate=r.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=r.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new es,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(e){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(e),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(e){return this.quaternion.premultiply(e),this}setRotationFromAxisAngle(e,t){this.quaternion.setFromAxisAngle(e,t)}setRotationFromEuler(e){this.quaternion.setFromEuler(e,!0)}setRotationFromMatrix(e){this.quaternion.setFromRotationMatrix(e)}setRotationFromQuaternion(e){this.quaternion.copy(e)}rotateOnAxis(e,t){return Nr.setFromAxisAngle(e,t),this.quaternion.multiply(Nr),this}rotateOnWorldAxis(e,t){return Nr.setFromAxisAngle(e,t),this.quaternion.premultiply(Nr),this}rotateX(e){return this.rotateOnAxis(td,e)}rotateY(e){return this.rotateOnAxis(nd,e)}rotateZ(e){return this.rotateOnAxis(id,e)}translateOnAxis(e,t){return ed.copy(e).applyQuaternion(this.quaternion),this.position.add(ed.multiplyScalar(t)),this}translateX(e){return this.translateOnAxis(td,e)}translateY(e){return this.translateOnAxis(nd,e)}translateZ(e){return this.translateOnAxis(id,e)}localToWorld(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(this.matrixWorld)}worldToLocal(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(bi.copy(this.matrixWorld).invert())}lookAt(e,t,n){e.isVector3?Ka.copy(e):Ka.set(e,t,n);let i=this.parent;this.updateWorldMatrix(!0,!1),Os.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?bi.lookAt(Os,Ka,this.up):bi.lookAt(Ka,Os,this.up),this.quaternion.setFromRotationMatrix(bi),i&&(bi.extractRotation(i.matrixWorld),Nr.setFromRotationMatrix(bi),this.quaternion.premultiply(Nr.invert()))}add(e){if(arguments.length>1){for(let t=0;t<arguments.length;t++)this.add(arguments[t]);return this}return e===this?(Je("Object3D.add: object can't be added as a child of itself.",e),this):(e&&e.isObject3D?(e.removeFromParent(),e.parent=this,this.children.push(e),e.dispatchEvent(rd),Or.child=e,this.dispatchEvent(Or),Or.child=null):Je("Object3D.add: object not an instance of THREE.Object3D.",e),this)}remove(e){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}let t=this.children.indexOf(e);return t!==-1&&(e.parent=null,this.children.splice(t,1),e.dispatchEvent(Lf),pc.child=e,this.dispatchEvent(pc),pc.child=null),this}removeFromParent(){let e=this.parent;return e!==null&&e.remove(this),this}clear(){return this.remove(...this.children)}attach(e){return this.updateWorldMatrix(!0,!1),bi.copy(this.matrixWorld).invert(),e.parent!==null&&(e.parent.updateWorldMatrix(!0,!1),bi.multiply(e.parent.matrixWorld)),e.applyMatrix4(bi),e.removeFromParent(),e.parent=this,this.children.push(e),e.updateWorldMatrix(!1,!0),e.dispatchEvent(rd),Or.child=e,this.dispatchEvent(Or),Or.child=null,this}getObjectById(e){return this.getObjectByProperty("id",e)}getObjectByName(e){return this.getObjectByProperty("name",e)}getObjectByProperty(e,t){if(this[e]===t)return this;for(let n=0,i=this.children.length;n<i;n++){let s=this.children[n].getObjectByProperty(e,t);if(s!==void 0)return s}}getObjectsByProperty(e,t,n=[]){this[e]===t&&n.push(this);let i=this.children;for(let s=0,a=i.length;s<a;s++)i[s].getObjectsByProperty(e,t,n);return n}getWorldPosition(e){return this.updateWorldMatrix(!0,!1),e.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(Os,e,Pf),e}getWorldScale(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(Os,If,e),e}getWorldDirection(e){this.updateWorldMatrix(!0,!1);let t=this.matrixWorld.elements;return e.set(t[8],t[9],t[10]).normalize()}raycast(){}traverse(e){e(this);let t=this.children;for(let n=0,i=t.length;n<i;n++)t[n].traverse(e)}traverseVisible(e){if(this.visible===!1)return;e(this);let t=this.children;for(let n=0,i=t.length;n<i;n++)t[n].traverseVisible(e)}traverseAncestors(e){let t=this.parent;t!==null&&(e(t),t.traverseAncestors(e))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let e=this.pivot;if(e!==null){let t=e.x,n=e.y,i=e.z,s=this.matrix.elements;s[12]+=t-s[0]*t-s[4]*n-s[8]*i,s[13]+=n-s[1]*t-s[5]*n-s[9]*i,s[14]+=i-s[2]*t-s[6]*n-s[10]*i}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(e){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||e)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,e=!0);let t=this.children;for(let n=0,i=t.length;n<i;n++)t[n].updateMatrixWorld(e)}updateWorldMatrix(e,t){let n=this.parent;if(e===!0&&n!==null&&n.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),t===!0){let i=this.children;for(let s=0,a=i.length;s<a;s++)i[s].updateWorldMatrix(!1,!0)}}toJSON(e){let t=e===void 0||typeof e=="string",n={};t&&(e={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let i={};function s(o,c){return o[c.uuid]===void 0&&(o[c.uuid]=c.toJSON(e)),c.uuid}if(i.uuid=this.uuid,i.type=this.type,this.name!==""&&(i.name=this.name),this.castShadow===!0&&(i.castShadow=!0),this.receiveShadow===!0&&(i.receiveShadow=!0),this.visible===!1&&(i.visible=!1),this.frustumCulled===!1&&(i.frustumCulled=!1),this.renderOrder!==0&&(i.renderOrder=this.renderOrder),this.static!==!1&&(i.static=this.static),Object.keys(this.userData).length>0&&(i.userData=this.userData),i.layers=this.layers.mask,i.matrix=this.matrix.toArray(),i.up=this.up.toArray(),this.pivot!==null&&(i.pivot=this.pivot.toArray()),this.matrixAutoUpdate===!1&&(i.matrixAutoUpdate=!1),this.morphTargetDictionary!==void 0&&(i.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(i.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(i.type="InstancedMesh",i.count=this.count,i.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(i.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(i.type="BatchedMesh",i.perObjectFrustumCulled=this.perObjectFrustumCulled,i.sortObjects=this.sortObjects,i.drawRanges=this._drawRanges,i.reservedRanges=this._reservedRanges,i.geometryInfo=this._geometryInfo.map(o=>({...o,boundingBox:o.boundingBox?o.boundingBox.toJSON():void 0,boundingSphere:o.boundingSphere?o.boundingSphere.toJSON():void 0})),i.instanceInfo=this._instanceInfo.map(o=>({...o})),i.availableInstanceIds=this._availableInstanceIds.slice(),i.availableGeometryIds=this._availableGeometryIds.slice(),i.nextIndexStart=this._nextIndexStart,i.nextVertexStart=this._nextVertexStart,i.geometryCount=this._geometryCount,i.maxInstanceCount=this._maxInstanceCount,i.maxVertexCount=this._maxVertexCount,i.maxIndexCount=this._maxIndexCount,i.geometryInitialized=this._geometryInitialized,i.matricesTexture=this._matricesTexture.toJSON(e),i.indirectTexture=this._indirectTexture.toJSON(e),this._colorsTexture!==null&&(i.colorsTexture=this._colorsTexture.toJSON(e)),this.boundingSphere!==null&&(i.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(i.boundingBox=this.boundingBox.toJSON())),this.isScene)this.background&&(this.background.isColor?i.background=this.background.toJSON():this.background.isTexture&&(i.background=this.background.toJSON(e).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(i.environment=this.environment.toJSON(e).uuid);else if(this.isMesh||this.isLine||this.isPoints){i.geometry=s(e.geometries,this.geometry);let o=this.geometry.parameters;if(o!==void 0&&o.shapes!==void 0){let c=o.shapes;if(Array.isArray(c))for(let l=0,h=c.length;l<h;l++){let p=c[l];s(e.shapes,p)}else s(e.shapes,c)}}if(this.isSkinnedMesh&&(i.bindMode=this.bindMode,i.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(s(e.skeletons,this.skeleton),i.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let o=[];for(let c=0,l=this.material.length;c<l;c++)o.push(s(e.materials,this.material[c]));i.material=o}else i.material=s(e.materials,this.material);if(this.children.length>0){i.children=[];for(let o=0;o<this.children.length;o++)i.children.push(this.children[o].toJSON(e).object)}if(this.animations.length>0){i.animations=[];for(let o=0;o<this.animations.length;o++){let c=this.animations[o];i.animations.push(s(e.animations,c))}}if(t){let o=a(e.geometries),c=a(e.materials),l=a(e.textures),h=a(e.images),p=a(e.shapes),f=a(e.skeletons),m=a(e.animations),u=a(e.nodes);o.length>0&&(n.geometries=o),c.length>0&&(n.materials=c),l.length>0&&(n.textures=l),h.length>0&&(n.images=h),p.length>0&&(n.shapes=p),f.length>0&&(n.skeletons=f),m.length>0&&(n.animations=m),u.length>0&&(n.nodes=u)}return n.object=i,n;function a(o){let c=[];for(let l in o){let h=o[l];delete h.metadata,c.push(h)}return c}}clone(e){return new this.constructor().copy(this,e)}copy(e,t=!0){if(this.name=e.name,this.up.copy(e.up),this.position.copy(e.position),this.rotation.order=e.rotation.order,this.quaternion.copy(e.quaternion),this.scale.copy(e.scale),e.pivot!==null&&(this.pivot=e.pivot.clone()),this.matrix.copy(e.matrix),this.matrixWorld.copy(e.matrixWorld),this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrixWorldAutoUpdate=e.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=e.matrixWorldNeedsUpdate,this.layers.mask=e.layers.mask,this.visible=e.visible,this.castShadow=e.castShadow,this.receiveShadow=e.receiveShadow,this.frustumCulled=e.frustumCulled,this.renderOrder=e.renderOrder,this.static=e.static,this.animations=e.animations.slice(),this.userData=JSON.parse(JSON.stringify(e.userData)),t===!0)for(let n=0;n<e.children.length;n++){let i=e.children[n];this.add(i.clone())}return this}};Ft.DEFAULT_UP=new D(0,1,0),Ft.DEFAULT_MATRIX_AUTO_UPDATE=!0,Ft.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var Kt=class extends Ft{constructor(){super(),this.isGroup=!0,this.type="Group"}},Df={type:"move"},ts=class{constructor(){this._targetRay=null,this._grip=null,this._hand=null}getHandSpace(){return this._hand===null&&(this._hand=new Kt,this._hand.matrixAutoUpdate=!1,this._hand.visible=!1,this._hand.joints={},this._hand.inputState={pinching:!1}),this._hand}getTargetRaySpace(){return this._targetRay===null&&(this._targetRay=new Kt,this._targetRay.matrixAutoUpdate=!1,this._targetRay.visible=!1,this._targetRay.hasLinearVelocity=!1,this._targetRay.linearVelocity=new D,this._targetRay.hasAngularVelocity=!1,this._targetRay.angularVelocity=new D),this._targetRay}getGripSpace(){return this._grip===null&&(this._grip=new Kt,this._grip.matrixAutoUpdate=!1,this._grip.visible=!1,this._grip.hasLinearVelocity=!1,this._grip.linearVelocity=new D,this._grip.hasAngularVelocity=!1,this._grip.angularVelocity=new D),this._grip}dispatchEvent(e){return this._targetRay!==null&&this._targetRay.dispatchEvent(e),this._grip!==null&&this._grip.dispatchEvent(e),this._hand!==null&&this._hand.dispatchEvent(e),this}connect(e){if(e&&e.hand){let t=this._hand;if(t)for(let n of e.hand.values())this._getHandJoint(t,n)}return this.dispatchEvent({type:"connected",data:e}),this}disconnect(e){return this.dispatchEvent({type:"disconnected",data:e}),this._targetRay!==null&&(this._targetRay.visible=!1),this._grip!==null&&(this._grip.visible=!1),this._hand!==null&&(this._hand.visible=!1),this}update(e,t,n){let i=null,s=null,a=null,o=this._targetRay,c=this._grip,l=this._hand;if(e&&t.session.visibilityState!=="visible-blurred"){if(l&&e.hand){a=!0;for(let g of e.hand.values()){let x=t.getJointPose(g,n),_=this._getHandJoint(l,g);x!==null&&(_.matrix.fromArray(x.transform.matrix),_.matrix.decompose(_.position,_.rotation,_.scale),_.matrixWorldNeedsUpdate=!0,_.jointRadius=x.radius),_.visible=x!==null}let h=l.joints["index-finger-tip"],p=l.joints["thumb-tip"],f=h.position.distanceTo(p.position),m=.02,u=.005;l.inputState.pinching&&f>m+u?(l.inputState.pinching=!1,this.dispatchEvent({type:"pinchend",handedness:e.handedness,target:this})):!l.inputState.pinching&&f<=m-u&&(l.inputState.pinching=!0,this.dispatchEvent({type:"pinchstart",handedness:e.handedness,target:this}))}else c!==null&&e.gripSpace&&(s=t.getPose(e.gripSpace,n),s!==null&&(c.matrix.fromArray(s.transform.matrix),c.matrix.decompose(c.position,c.rotation,c.scale),c.matrixWorldNeedsUpdate=!0,s.linearVelocity?(c.hasLinearVelocity=!0,c.linearVelocity.copy(s.linearVelocity)):c.hasLinearVelocity=!1,s.angularVelocity?(c.hasAngularVelocity=!0,c.angularVelocity.copy(s.angularVelocity)):c.hasAngularVelocity=!1));o!==null&&(i=t.getPose(e.targetRaySpace,n),i===null&&s!==null&&(i=s),i!==null&&(o.matrix.fromArray(i.transform.matrix),o.matrix.decompose(o.position,o.rotation,o.scale),o.matrixWorldNeedsUpdate=!0,i.linearVelocity?(o.hasLinearVelocity=!0,o.linearVelocity.copy(i.linearVelocity)):o.hasLinearVelocity=!1,i.angularVelocity?(o.hasAngularVelocity=!0,o.angularVelocity.copy(i.angularVelocity)):o.hasAngularVelocity=!1,this.dispatchEvent(Df)))}return o!==null&&(o.visible=i!==null),c!==null&&(c.visible=s!==null),l!==null&&(l.visible=a!==null),this}_getHandJoint(e,t){if(e.joints[t.jointName]===void 0){let n=new Kt;n.matrixAutoUpdate=!1,n.visible=!1,e.joints[t.jointName]=n,e.add(n)}return e.joints[t.jointName]}},fp={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},Fi={h:0,s:0,l:0},$a={h:0,s:0,l:0};function fc(r,e,t){return t<0&&(t+=1),t>1&&(t-=1),t<1/6?r+6*(e-r)*t:t<.5?e:t<2/3?r+6*(e-r)*(2/3-t):r}var He=class{constructor(e,t,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(e,t,n)}set(e,t,n){if(t===void 0&&n===void 0){let i=e;i&&i.isColor?this.copy(i):typeof i=="number"?this.setHex(i):typeof i=="string"&&this.setStyle(i)}else this.setRGB(e,t,n);return this}setScalar(e){return this.r=e,this.g=e,this.b=e,this}setHex(e,t=Ut){return e=Math.floor(e),this.r=(e>>16&255)/255,this.g=(e>>8&255)/255,this.b=(255&e)/255,ut.colorSpaceToWorking(this,t),this}setRGB(e,t,n,i=ut.workingColorSpace){return this.r=e,this.g=t,this.b=n,ut.colorSpaceToWorking(this,i),this}setHSL(e,t,n,i=ut.workingColorSpace){if(e=Gc(e,1),t=nt(t,0,1),n=nt(n,0,1),t===0)this.r=this.g=this.b=n;else{let s=n<=.5?n*(1+t):n+t-n*t,a=2*n-s;this.r=fc(a,s,e+1/3),this.g=fc(a,s,e),this.b=fc(a,s,e-1/3)}return ut.colorSpaceToWorking(this,i),this}setStyle(e,t=Ut){function n(s){s!==void 0&&parseFloat(s)<1&&Ye("Color: Alpha component of "+e+" will be ignored.")}let i;if(i=/^(\w+)\(([^\)]*)\)/.exec(e)){let s,a=i[1],o=i[2];switch(a){case"rgb":case"rgba":if(s=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(s[4]),this.setRGB(Math.min(255,parseInt(s[1],10))/255,Math.min(255,parseInt(s[2],10))/255,Math.min(255,parseInt(s[3],10))/255,t);if(s=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(s[4]),this.setRGB(Math.min(100,parseInt(s[1],10))/100,Math.min(100,parseInt(s[2],10))/100,Math.min(100,parseInt(s[3],10))/100,t);break;case"hsl":case"hsla":if(s=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(s[4]),this.setHSL(parseFloat(s[1])/360,parseFloat(s[2])/100,parseFloat(s[3])/100,t);break;default:Ye("Color: Unknown color model "+e)}}else if(i=/^\#([A-Fa-f\d]+)$/.exec(e)){let s=i[1],a=s.length;if(a===3)return this.setRGB(parseInt(s.charAt(0),16)/15,parseInt(s.charAt(1),16)/15,parseInt(s.charAt(2),16)/15,t);if(a===6)return this.setHex(parseInt(s,16),t);Ye("Color: Invalid hex color "+e)}else if(e&&e.length>0)return this.setColorName(e,t);return this}setColorName(e,t=Ut){let n=fp[e.toLowerCase()];return n!==void 0?this.setHex(n,t):Ye("Color: Unknown color "+e),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(e){return this.r=e.r,this.g=e.g,this.b=e.b,this}copySRGBToLinear(e){return this.r=Ci(e.r),this.g=Ci(e.g),this.b=Ci(e.b),this}copyLinearToSRGB(e){return this.r=Yr(e.r),this.g=Yr(e.g),this.b=Yr(e.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(e=Ut){return ut.workingToColorSpace(sn.copy(this),e),65536*Math.round(nt(255*sn.r,0,255))+256*Math.round(nt(255*sn.g,0,255))+Math.round(nt(255*sn.b,0,255))}getHexString(e=Ut){return("000000"+this.getHex(e).toString(16)).slice(-6)}getHSL(e,t=ut.workingColorSpace){ut.workingToColorSpace(sn.copy(this),t);let n=sn.r,i=sn.g,s=sn.b,a=Math.max(n,i,s),o=Math.min(n,i,s),c,l,h=(o+a)/2;if(o===a)c=0,l=0;else{let p=a-o;switch(l=h<=.5?p/(a+o):p/(2-a-o),a){case n:c=(i-s)/p+(i<s?6:0);break;case i:c=(s-n)/p+2;break;case s:c=(n-i)/p+4}c/=6}return e.h=c,e.s=l,e.l=h,e}getRGB(e,t=ut.workingColorSpace){return ut.workingToColorSpace(sn.copy(this),t),e.r=sn.r,e.g=sn.g,e.b=sn.b,e}getStyle(e=Ut){ut.workingToColorSpace(sn.copy(this),e);let t=sn.r,n=sn.g,i=sn.b;return e!==Ut?`color(${e} ${t.toFixed(3)} ${n.toFixed(3)} ${i.toFixed(3)})`:`rgb(${Math.round(255*t)},${Math.round(255*n)},${Math.round(255*i)})`}offsetHSL(e,t,n){return this.getHSL(Fi),this.setHSL(Fi.h+e,Fi.s+t,Fi.l+n)}add(e){return this.r+=e.r,this.g+=e.g,this.b+=e.b,this}addColors(e,t){return this.r=e.r+t.r,this.g=e.g+t.g,this.b=e.b+t.b,this}addScalar(e){return this.r+=e,this.g+=e,this.b+=e,this}sub(e){return this.r=Math.max(0,this.r-e.r),this.g=Math.max(0,this.g-e.g),this.b=Math.max(0,this.b-e.b),this}multiply(e){return this.r*=e.r,this.g*=e.g,this.b*=e.b,this}multiplyScalar(e){return this.r*=e,this.g*=e,this.b*=e,this}lerp(e,t){return this.r+=(e.r-this.r)*t,this.g+=(e.g-this.g)*t,this.b+=(e.b-this.b)*t,this}lerpColors(e,t,n){return this.r=e.r+(t.r-e.r)*n,this.g=e.g+(t.g-e.g)*n,this.b=e.b+(t.b-e.b)*n,this}lerpHSL(e,t){this.getHSL(Fi),e.getHSL($a);let n=Ws(Fi.h,$a.h,t),i=Ws(Fi.s,$a.s,t),s=Ws(Fi.l,$a.l,t);return this.setHSL(n,i,s),this}setFromVector3(e){return this.r=e.x,this.g=e.y,this.b=e.z,this}applyMatrix3(e){let t=this.r,n=this.g,i=this.b,s=e.elements;return this.r=s[0]*t+s[3]*n+s[6]*i,this.g=s[1]*t+s[4]*n+s[7]*i,this.b=s[2]*t+s[5]*n+s[8]*i,this}equals(e){return e.r===this.r&&e.g===this.g&&e.b===this.b}fromArray(e,t=0){return this.r=e[t],this.g=e[t+1],this.b=e[t+2],this}toArray(e=[],t=0){return e[t]=this.r,e[t+1]=this.g,e[t+2]=this.b,e}fromBufferAttribute(e,t){return this.r=e.getX(t),this.g=e.getY(t),this.b=e.getZ(t),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},sn=new He;He.NAMES=fp;var Ks=class r{constructor(e,t=1,n=1e3){this.isFog=!0,this.name="",this.color=new He(e),this.near=t,this.far=n}clone(){return new r(this.color,this.near,this.far)}toJSON(){return{type:"Fog",name:this.name,color:this.color.getHex(),near:this.near,far:this.far}}},$s=class extends Ft{constructor(){super(),this.isScene=!0,this.type="Scene",this.background=null,this.environment=null,this.fog=null,this.backgroundBlurriness=0,this.backgroundIntensity=1,this.backgroundRotation=new Un,this.environmentIntensity=1,this.environmentRotation=new Un,this.overrideMaterial=null,typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}copy(e,t){return super.copy(e,t),e.background!==null&&(this.background=e.background.clone()),e.environment!==null&&(this.environment=e.environment.clone()),e.fog!==null&&(this.fog=e.fog.clone()),this.backgroundBlurriness=e.backgroundBlurriness,this.backgroundIntensity=e.backgroundIntensity,this.backgroundRotation.copy(e.backgroundRotation),this.environmentIntensity=e.environmentIntensity,this.environmentRotation.copy(e.environmentRotation),e.overrideMaterial!==null&&(this.overrideMaterial=e.overrideMaterial.clone()),this.matrixAutoUpdate=e.matrixAutoUpdate,this}toJSON(e){let t=super.toJSON(e);return this.fog!==null&&(t.object.fog=this.fog.toJSON()),this.backgroundBlurriness>0&&(t.object.backgroundBlurriness=this.backgroundBlurriness),this.backgroundIntensity!==1&&(t.object.backgroundIntensity=this.backgroundIntensity),t.object.backgroundRotation=this.backgroundRotation.toArray(),this.environmentIntensity!==1&&(t.object.environmentIntensity=this.environmentIntensity),t.object.environmentRotation=this.environmentRotation.toArray(),t}},ni=new D,Si=new D,mc=new D,Ti=new D,Fr=new D,Br=new D,sd=new D,gc=new D,_c=new D,vc=new D,yc=new wt,xc=new wt,Mc=new wt,Ai=class r{constructor(e=new D,t=new D,n=new D){this.a=e,this.b=t,this.c=n}static getNormal(e,t,n,i){i.subVectors(n,t),ni.subVectors(e,t),i.cross(ni);let s=i.lengthSq();return s>0?i.multiplyScalar(1/Math.sqrt(s)):i.set(0,0,0)}static getBarycoord(e,t,n,i,s){ni.subVectors(i,t),Si.subVectors(n,t),mc.subVectors(e,t);let a=ni.dot(ni),o=ni.dot(Si),c=ni.dot(mc),l=Si.dot(Si),h=Si.dot(mc),p=a*l-o*o;if(p===0)return s.set(0,0,0),null;let f=1/p,m=(l*c-o*h)*f,u=(a*h-o*c)*f;return s.set(1-m-u,u,m)}static containsPoint(e,t,n,i){return this.getBarycoord(e,t,n,i,Ti)!==null&&Ti.x>=0&&Ti.y>=0&&Ti.x+Ti.y<=1}static getInterpolation(e,t,n,i,s,a,o,c){return this.getBarycoord(e,t,n,i,Ti)===null?(c.x=0,c.y=0,"z"in c&&(c.z=0),"w"in c&&(c.w=0),null):(c.setScalar(0),c.addScaledVector(s,Ti.x),c.addScaledVector(a,Ti.y),c.addScaledVector(o,Ti.z),c)}static getInterpolatedAttribute(e,t,n,i,s,a){return yc.setScalar(0),xc.setScalar(0),Mc.setScalar(0),yc.fromBufferAttribute(e,t),xc.fromBufferAttribute(e,n),Mc.fromBufferAttribute(e,i),a.setScalar(0),a.addScaledVector(yc,s.x),a.addScaledVector(xc,s.y),a.addScaledVector(Mc,s.z),a}static isFrontFacing(e,t,n,i){return ni.subVectors(n,t),Si.subVectors(e,t),ni.cross(Si).dot(i)<0}set(e,t,n){return this.a.copy(e),this.b.copy(t),this.c.copy(n),this}setFromPointsAndIndices(e,t,n,i){return this.a.copy(e[t]),this.b.copy(e[n]),this.c.copy(e[i]),this}setFromAttributeAndIndices(e,t,n,i){return this.a.fromBufferAttribute(e,t),this.b.fromBufferAttribute(e,n),this.c.fromBufferAttribute(e,i),this}clone(){return new this.constructor().copy(this)}copy(e){return this.a.copy(e.a),this.b.copy(e.b),this.c.copy(e.c),this}getArea(){return ni.subVectors(this.c,this.b),Si.subVectors(this.a,this.b),.5*ni.cross(Si).length()}getMidpoint(e){return e.addVectors(this.a,this.b).add(this.c).multiplyScalar(1/3)}getNormal(e){return r.getNormal(this.a,this.b,this.c,e)}getPlane(e){return e.setFromCoplanarPoints(this.a,this.b,this.c)}getBarycoord(e,t){return r.getBarycoord(e,this.a,this.b,this.c,t)}getInterpolation(e,t,n,i,s){return r.getInterpolation(e,this.a,this.b,this.c,t,n,i,s)}containsPoint(e){return r.containsPoint(e,this.a,this.b,this.c)}isFrontFacing(e){return r.isFrontFacing(this.a,this.b,this.c,e)}intersectsBox(e){return e.intersectsTriangle(this)}closestPointToPoint(e,t){let n=this.a,i=this.b,s=this.c,a,o;Fr.subVectors(i,n),Br.subVectors(s,n),gc.subVectors(e,n);let c=Fr.dot(gc),l=Br.dot(gc);if(c<=0&&l<=0)return t.copy(n);_c.subVectors(e,i);let h=Fr.dot(_c),p=Br.dot(_c);if(h>=0&&p<=h)return t.copy(i);let f=c*p-h*l;if(f<=0&&c>=0&&h<=0)return a=c/(c-h),t.copy(n).addScaledVector(Fr,a);vc.subVectors(e,s);let m=Fr.dot(vc),u=Br.dot(vc);if(u>=0&&m<=u)return t.copy(s);let g=m*l-c*u;if(g<=0&&l>=0&&u<=0)return o=l/(l-u),t.copy(n).addScaledVector(Br,o);let x=h*u-m*p;if(x<=0&&p-h>=0&&m-u>=0)return sd.subVectors(s,i),o=(p-h)/(p-h+(m-u)),t.copy(i).addScaledVector(sd,o);let _=1/(x+g+f);return a=g*_,o=f*_,t.copy(n).addScaledVector(Fr,a).addScaledVector(Br,o)}equals(e){return e.a.equals(this.a)&&e.b.equals(this.b)&&e.c.equals(this.c)}},$t=class{constructor(e=new D(1/0,1/0,1/0),t=new D(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=e,this.max=t}set(e,t){return this.min.copy(e),this.max.copy(t),this}setFromArray(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t+=3)this.expandByPoint(ii.fromArray(e,t));return this}setFromBufferAttribute(e){this.makeEmpty();for(let t=0,n=e.count;t<n;t++)this.expandByPoint(ii.fromBufferAttribute(e,t));return this}setFromPoints(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t++)this.expandByPoint(e[t]);return this}setFromCenterAndSize(e,t){let n=ii.copy(t).multiplyScalar(.5);return this.min.copy(e).sub(n),this.max.copy(e).add(n),this}setFromObject(e,t=!1){return this.makeEmpty(),this.expandByObject(e,t)}clone(){return new this.constructor().copy(this)}copy(e){return this.min.copy(e.min),this.max.copy(e.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(e){return this.isEmpty()?e.set(0,0,0):e.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(e){return this.isEmpty()?e.set(0,0,0):e.subVectors(this.max,this.min)}expandByPoint(e){return this.min.min(e),this.max.max(e),this}expandByVector(e){return this.min.sub(e),this.max.add(e),this}expandByScalar(e){return this.min.addScalar(-e),this.max.addScalar(e),this}expandByObject(e,t=!1){e.updateWorldMatrix(!1,!1);let n=e.geometry;if(n!==void 0){let s=n.getAttribute("position");if(t===!0&&s!==void 0&&e.isInstancedMesh!==!0)for(let a=0,o=s.count;a<o;a++)e.isMesh===!0?e.getVertexPosition(a,ii):ii.fromBufferAttribute(s,a),ii.applyMatrix4(e.matrixWorld),this.expandByPoint(ii);else e.boundingBox!==void 0?(e.boundingBox===null&&e.computeBoundingBox(),Qa.copy(e.boundingBox)):(n.boundingBox===null&&n.computeBoundingBox(),Qa.copy(n.boundingBox)),Qa.applyMatrix4(e.matrixWorld),this.union(Qa)}let i=e.children;for(let s=0,a=i.length;s<a;s++)this.expandByObject(i[s],t);return this}containsPoint(e){return e.x>=this.min.x&&e.x<=this.max.x&&e.y>=this.min.y&&e.y<=this.max.y&&e.z>=this.min.z&&e.z<=this.max.z}containsBox(e){return this.min.x<=e.min.x&&e.max.x<=this.max.x&&this.min.y<=e.min.y&&e.max.y<=this.max.y&&this.min.z<=e.min.z&&e.max.z<=this.max.z}getParameter(e,t){return t.set((e.x-this.min.x)/(this.max.x-this.min.x),(e.y-this.min.y)/(this.max.y-this.min.y),(e.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(e){return e.max.x>=this.min.x&&e.min.x<=this.max.x&&e.max.y>=this.min.y&&e.min.y<=this.max.y&&e.max.z>=this.min.z&&e.min.z<=this.max.z}intersectsSphere(e){return this.clampPoint(e.center,ii),ii.distanceToSquared(e.center)<=e.radius*e.radius}intersectsPlane(e){let t,n;return e.normal.x>0?(t=e.normal.x*this.min.x,n=e.normal.x*this.max.x):(t=e.normal.x*this.max.x,n=e.normal.x*this.min.x),e.normal.y>0?(t+=e.normal.y*this.min.y,n+=e.normal.y*this.max.y):(t+=e.normal.y*this.max.y,n+=e.normal.y*this.min.y),e.normal.z>0?(t+=e.normal.z*this.min.z,n+=e.normal.z*this.max.z):(t+=e.normal.z*this.max.z,n+=e.normal.z*this.min.z),t<=-e.constant&&n>=-e.constant}intersectsTriangle(e){if(this.isEmpty())return!1;this.getCenter(Fs),eo.subVectors(this.max,Fs),zr.subVectors(e.a,Fs),kr.subVectors(e.b,Fs),Vr.subVectors(e.c,Fs),Bi.subVectors(kr,zr),zi.subVectors(Vr,kr),sr.subVectors(zr,Vr);let t=[0,-Bi.z,Bi.y,0,-zi.z,zi.y,0,-sr.z,sr.y,Bi.z,0,-Bi.x,zi.z,0,-zi.x,sr.z,0,-sr.x,-Bi.y,Bi.x,0,-zi.y,zi.x,0,-sr.y,sr.x,0];return!!bc(t,zr,kr,Vr,eo)&&(t=[1,0,0,0,1,0,0,0,1],!!bc(t,zr,kr,Vr,eo)&&(to.crossVectors(Bi,zi),t=[to.x,to.y,to.z],bc(t,zr,kr,Vr,eo)))}clampPoint(e,t){return t.copy(e).clamp(this.min,this.max)}distanceToPoint(e){return this.clampPoint(e,ii).distanceTo(e)}getBoundingSphere(e){return this.isEmpty()?e.makeEmpty():(this.getCenter(e.center),e.radius=.5*this.getSize(ii).length()),e}intersect(e){return this.min.max(e.min),this.max.min(e.max),this.isEmpty()&&this.makeEmpty(),this}union(e){return this.min.min(e.min),this.max.max(e.max),this}applyMatrix4(e){return this.isEmpty()||(Ei[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(e),Ei[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(e),Ei[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(e),Ei[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(e),Ei[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(e),Ei[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(e),Ei[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(e),Ei[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(e),this.setFromPoints(Ei)),this}translate(e){return this.min.add(e),this.max.add(e),this}equals(e){return e.min.equals(this.min)&&e.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(e){return this.min.fromArray(e.min),this.max.fromArray(e.max),this}},Ei=[new D,new D,new D,new D,new D,new D,new D,new D],ii=new D,Qa=new $t,zr=new D,kr=new D,Vr=new D,Bi=new D,zi=new D,sr=new D,Fs=new D,eo=new D,to=new D,ar=new D;function bc(r,e,t,n,i){for(let s=0,a=r.length-3;s<=a;s+=3){ar.fromArray(r,s);let o=i.x*Math.abs(ar.x)+i.y*Math.abs(ar.y)+i.z*Math.abs(ar.z),c=e.dot(ar),l=t.dot(ar),h=n.dot(ar);if(Math.max(-Math.max(c,l,h),Math.min(c,l,h))>o)return!1}return!0}var t0=Uf();function Uf(){let r=new ArrayBuffer(4),e=new Float32Array(r),t=new Uint32Array(r),n=new Uint32Array(512),i=new Uint32Array(512);for(let c=0;c<256;++c){let l=c-127;l<-27?(n[c]=0,n[256|c]=32768,i[c]=24,i[256|c]=24):l<-14?(n[c]=1024>>-l-14,n[256|c]=1024>>-l-14|32768,i[c]=-l-1,i[256|c]=-l-1):l<=15?(n[c]=l+15<<10,n[256|c]=l+15<<10|32768,i[c]=13,i[256|c]=13):l<128?(n[c]=31744,n[256|c]=64512,i[c]=24,i[256|c]=24):(n[c]=31744,n[256|c]=64512,i[c]=13,i[256|c]=13)}let s=new Uint32Array(2048),a=new Uint32Array(64),o=new Uint32Array(64);for(let c=1;c<1024;++c){let l=c<<13,h=0;for(;!(8388608&l);)l<<=1,h-=8388608;l&=-8388609,h+=947912704,s[c]=l|h}for(let c=1024;c<2048;++c)s[c]=939524096+(c-1024<<13);for(let c=1;c<31;++c)a[c]=c<<23;a[31]=1199570944,a[32]=2147483648;for(let c=33;c<63;++c)a[c]=2147483648+(c-32<<23);a[63]=3347054592;for(let c=1;c<64;++c)c!==32&&(o[c]=1024);return{floatView:e,uint32View:t,baseTable:n,shiftTable:i,mantissaTable:s,exponentTable:a,offsetTable:o}}var Ot=new D,no=new _e,Nf=0,_n=class{constructor(e,t,n=!1){if(Array.isArray(e))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:Nf++}),this.name="",this.array=e,this.itemSize=t,this.count=e!==void 0?e.length/t:0,this.normalized=n,this.usage=Vc,this.updateRanges=[],this.gpuType=Kn,this.version=0}onUploadCallback(){}set needsUpdate(e){e===!0&&this.version++}setUsage(e){return this.usage=e,this}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}copy(e){return this.name=e.name,this.array=new e.array.constructor(e.array),this.itemSize=e.itemSize,this.count=e.count,this.normalized=e.normalized,this.usage=e.usage,this.gpuType=e.gpuType,this}copyAt(e,t,n){e*=this.itemSize,n*=t.itemSize;for(let i=0,s=this.itemSize;i<s;i++)this.array[e+i]=t.array[n+i];return this}copyArray(e){return this.array.set(e),this}applyMatrix3(e){if(this.itemSize===2)for(let t=0,n=this.count;t<n;t++)no.fromBufferAttribute(this,t),no.applyMatrix3(e),this.setXY(t,no.x,no.y);else if(this.itemSize===3)for(let t=0,n=this.count;t<n;t++)Ot.fromBufferAttribute(this,t),Ot.applyMatrix3(e),this.setXYZ(t,Ot.x,Ot.y,Ot.z);return this}applyMatrix4(e){for(let t=0,n=this.count;t<n;t++)Ot.fromBufferAttribute(this,t),Ot.applyMatrix4(e),this.setXYZ(t,Ot.x,Ot.y,Ot.z);return this}applyNormalMatrix(e){for(let t=0,n=this.count;t<n;t++)Ot.fromBufferAttribute(this,t),Ot.applyNormalMatrix(e),this.setXYZ(t,Ot.x,Ot.y,Ot.z);return this}transformDirection(e){for(let t=0,n=this.count;t<n;t++)Ot.fromBufferAttribute(this,t),Ot.transformDirection(e),this.setXYZ(t,Ot.x,Ot.y,Ot.z);return this}set(e,t=0){return this.array.set(e,t),this}getComponent(e,t){let n=this.array[e*this.itemSize+t];return this.normalized&&(n=Xr(n,this.array)),n}setComponent(e,t,n){return this.normalized&&(n=gn(n,this.array)),this.array[e*this.itemSize+t]=n,this}getX(e){let t=this.array[e*this.itemSize];return this.normalized&&(t=Xr(t,this.array)),t}setX(e,t){return this.normalized&&(t=gn(t,this.array)),this.array[e*this.itemSize]=t,this}getY(e){let t=this.array[e*this.itemSize+1];return this.normalized&&(t=Xr(t,this.array)),t}setY(e,t){return this.normalized&&(t=gn(t,this.array)),this.array[e*this.itemSize+1]=t,this}getZ(e){let t=this.array[e*this.itemSize+2];return this.normalized&&(t=Xr(t,this.array)),t}setZ(e,t){return this.normalized&&(t=gn(t,this.array)),this.array[e*this.itemSize+2]=t,this}getW(e){let t=this.array[e*this.itemSize+3];return this.normalized&&(t=Xr(t,this.array)),t}setW(e,t){return this.normalized&&(t=gn(t,this.array)),this.array[e*this.itemSize+3]=t,this}setXY(e,t,n){return e*=this.itemSize,this.normalized&&(t=gn(t,this.array),n=gn(n,this.array)),this.array[e+0]=t,this.array[e+1]=n,this}setXYZ(e,t,n,i){return e*=this.itemSize,this.normalized&&(t=gn(t,this.array),n=gn(n,this.array),i=gn(i,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=i,this}setXYZW(e,t,n,i,s){return e*=this.itemSize,this.normalized&&(t=gn(t,this.array),n=gn(n,this.array),i=gn(i,this.array),s=gn(s,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=i,this.array[e+3]=s,this}onUpload(e){return this.onUploadCallback=e,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let e={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(e.name=this.name),this.usage!==Vc&&(e.usage=this.usage),e}};var Qs=class extends _n{constructor(e,t,n){super(new Uint16Array(e),t,n)}};var ea=class extends _n{constructor(e,t,n){super(new Uint32Array(e),t,n)}};var Xe=class extends _n{constructor(e,t,n){super(new Float32Array(e),t,n)}},Of=new $t,Bs=new D,Sc=new D,Zn=class{constructor(e=new D,t=-1){this.isSphere=!0,this.center=e,this.radius=t}set(e,t){return this.center.copy(e),this.radius=t,this}setFromPoints(e,t){let n=this.center;t!==void 0?n.copy(t):Of.setFromPoints(e).getCenter(n);let i=0;for(let s=0,a=e.length;s<a;s++)i=Math.max(i,n.distanceToSquared(e[s]));return this.radius=Math.sqrt(i),this}copy(e){return this.center.copy(e.center),this.radius=e.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(e){return e.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(e){return e.distanceTo(this.center)-this.radius}intersectsSphere(e){let t=this.radius+e.radius;return e.center.distanceToSquared(this.center)<=t*t}intersectsBox(e){return e.intersectsSphere(this)}intersectsPlane(e){return Math.abs(e.distanceToPoint(this.center))<=this.radius}clampPoint(e,t){let n=this.center.distanceToSquared(e);return t.copy(e),n>this.radius*this.radius&&(t.sub(this.center).normalize(),t.multiplyScalar(this.radius).add(this.center)),t}getBoundingBox(e){return this.isEmpty()?(e.makeEmpty(),e):(e.set(this.center,this.center),e.expandByScalar(this.radius),e)}applyMatrix4(e){return this.center.applyMatrix4(e),this.radius=this.radius*e.getMaxScaleOnAxis(),this}translate(e){return this.center.add(e),this}expandByPoint(e){if(this.isEmpty())return this.center.copy(e),this.radius=0,this;Bs.subVectors(e,this.center);let t=Bs.lengthSq();if(t>this.radius*this.radius){let n=Math.sqrt(t),i=.5*(n-this.radius);this.center.addScaledVector(Bs,i/n),this.radius+=i}return this}union(e){return e.isEmpty()?this:this.isEmpty()?(this.copy(e),this):(this.center.equals(e.center)===!0?this.radius=Math.max(this.radius,e.radius):(Sc.subVectors(e.center,this.center).setLength(e.radius),this.expandByPoint(Bs.copy(e.center).add(Sc)),this.expandByPoint(Bs.copy(e.center).sub(Sc))),this)}equals(e){return e.center.equals(this.center)&&e.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(e){return this.radius=e.radius,this.center.fromArray(e.center),this}},Ff=0,qn=new Ke,Tc=new Ft,Gr=new D,In=new $t,zs=new $t,jt=new D,bt=class r extends pi{constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:Ff++}),this.uuid=vr(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={}}getIndex(){return this.index}setIndex(e){return Array.isArray(e)?this.index=new((function(t){for(let n=t.length-1;n>=0;--n)if(t[n]>=65535)return!0;return!1})(e)?ea:Qs)(e,1):this.index=e,this}setIndirect(e,t=0){return this.indirect=e,this.indirectOffset=t,this}getIndirect(){return this.indirect}getAttribute(e){return this.attributes[e]}setAttribute(e,t){return this.attributes[e]=t,this}deleteAttribute(e){return delete this.attributes[e],this}hasAttribute(e){return this.attributes[e]!==void 0}addGroup(e,t,n=0){this.groups.push({start:e,count:t,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(e,t){this.drawRange.start=e,this.drawRange.count=t}applyMatrix4(e){let t=this.attributes.position;t!==void 0&&(t.applyMatrix4(e),t.needsUpdate=!0);let n=this.attributes.normal;if(n!==void 0){let s=new et().getNormalMatrix(e);n.applyNormalMatrix(s),n.needsUpdate=!0}let i=this.attributes.tangent;return i!==void 0&&(i.transformDirection(e),i.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}applyQuaternion(e){return qn.makeRotationFromQuaternion(e),this.applyMatrix4(qn),this}rotateX(e){return qn.makeRotationX(e),this.applyMatrix4(qn),this}rotateY(e){return qn.makeRotationY(e),this.applyMatrix4(qn),this}rotateZ(e){return qn.makeRotationZ(e),this.applyMatrix4(qn),this}translate(e,t,n){return qn.makeTranslation(e,t,n),this.applyMatrix4(qn),this}scale(e,t,n){return qn.makeScale(e,t,n),this.applyMatrix4(qn),this}lookAt(e){return Tc.lookAt(e),Tc.updateMatrix(),this.applyMatrix4(Tc.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(Gr).negate(),this.translate(Gr.x,Gr.y,Gr.z),this}setFromPoints(e){let t=this.getAttribute("position");if(t===void 0){let n=[];for(let i=0,s=e.length;i<s;i++){let a=e[i];n.push(a.x,a.y,a.z||0)}this.setAttribute("position",new Xe(n,3))}else{let n=Math.min(e.length,t.count);for(let i=0;i<n;i++){let s=e[i];t.setXYZ(i,s.x,s.y,s.z||0)}e.length>t.count&&Ye("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),t.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new $t);let e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute)return Je("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),void this.boundingBox.set(new D(-1/0,-1/0,-1/0),new D(1/0,1/0,1/0));if(e!==void 0){if(this.boundingBox.setFromBufferAttribute(e),t)for(let n=0,i=t.length;n<i;n++){let s=t[n];In.setFromBufferAttribute(s),this.morphTargetsRelative?(jt.addVectors(this.boundingBox.min,In.min),this.boundingBox.expandByPoint(jt),jt.addVectors(this.boundingBox.max,In.max),this.boundingBox.expandByPoint(jt)):(this.boundingBox.expandByPoint(In.min),this.boundingBox.expandByPoint(In.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&Je('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Zn);let e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute)return Je("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),void this.boundingSphere.set(new D,1/0);if(e){let n=this.boundingSphere.center;if(In.setFromBufferAttribute(e),t)for(let s=0,a=t.length;s<a;s++){let o=t[s];zs.setFromBufferAttribute(o),this.morphTargetsRelative?(jt.addVectors(In.min,zs.min),In.expandByPoint(jt),jt.addVectors(In.max,zs.max),In.expandByPoint(jt)):(In.expandByPoint(zs.min),In.expandByPoint(zs.max))}In.getCenter(n);let i=0;for(let s=0,a=e.count;s<a;s++)jt.fromBufferAttribute(e,s),i=Math.max(i,n.distanceToSquared(jt));if(t)for(let s=0,a=t.length;s<a;s++){let o=t[s],c=this.morphTargetsRelative;for(let l=0,h=o.count;l<h;l++)jt.fromBufferAttribute(o,l),c&&(Gr.fromBufferAttribute(e,l),jt.add(Gr)),i=Math.max(i,n.distanceToSquared(jt))}this.boundingSphere.radius=Math.sqrt(i),isNaN(this.boundingSphere.radius)&&Je('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let e=this.index,t=this.attributes;if(e===null||t.position===void 0||t.normal===void 0||t.uv===void 0)return void Je("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");let n=t.position,i=t.normal,s=t.uv;this.hasAttribute("tangent")===!1&&this.setAttribute("tangent",new _n(new Float32Array(4*n.count),4));let a=this.getAttribute("tangent"),o=[],c=[];for(let j=0;j<n.count;j++)o[j]=new D,c[j]=new D;let l=new D,h=new D,p=new D,f=new _e,m=new _e,u=new _e,g=new D,x=new D;function _(j,O,Q){l.fromBufferAttribute(n,j),h.fromBufferAttribute(n,O),p.fromBufferAttribute(n,Q),f.fromBufferAttribute(s,j),m.fromBufferAttribute(s,O),u.fromBufferAttribute(s,Q),h.sub(l),p.sub(l),m.sub(f),u.sub(f);let Y=1/(m.x*u.y-u.x*m.y);isFinite(Y)&&(g.copy(h).multiplyScalar(u.y).addScaledVector(p,-m.y).multiplyScalar(Y),x.copy(p).multiplyScalar(m.x).addScaledVector(h,-u.x).multiplyScalar(Y),o[j].add(g),o[O].add(g),o[Q].add(g),c[j].add(x),c[O].add(x),c[Q].add(x))}let v=this.groups;v.length===0&&(v=[{start:0,count:e.count}]);for(let j=0,O=v.length;j<O;++j){let Q=v[j],Y=Q.start;for(let k=Y,X=Y+Q.count;k<X;k+=3)_(e.getX(k+0),e.getX(k+1),e.getX(k+2))}let S=new D,E=new D,w=new D,R=new D;function z(j){w.fromBufferAttribute(i,j),R.copy(w);let O=o[j];S.copy(O),S.sub(w.multiplyScalar(w.dot(O))).normalize(),E.crossVectors(R,O);let Q=E.dot(c[j])<0?-1:1;a.setXYZW(j,S.x,S.y,S.z,Q)}for(let j=0,O=v.length;j<O;++j){let Q=v[j],Y=Q.start;for(let k=Y,X=Y+Q.count;k<X;k+=3)z(e.getX(k+0)),z(e.getX(k+1)),z(e.getX(k+2))}}computeVertexNormals(){let e=this.index,t=this.getAttribute("position");if(t!==void 0){let n=this.getAttribute("normal");if(n===void 0)n=new _n(new Float32Array(3*t.count),3),this.setAttribute("normal",n);else for(let f=0,m=n.count;f<m;f++)n.setXYZ(f,0,0,0);let i=new D,s=new D,a=new D,o=new D,c=new D,l=new D,h=new D,p=new D;if(e)for(let f=0,m=e.count;f<m;f+=3){let u=e.getX(f+0),g=e.getX(f+1),x=e.getX(f+2);i.fromBufferAttribute(t,u),s.fromBufferAttribute(t,g),a.fromBufferAttribute(t,x),h.subVectors(a,s),p.subVectors(i,s),h.cross(p),o.fromBufferAttribute(n,u),c.fromBufferAttribute(n,g),l.fromBufferAttribute(n,x),o.add(h),c.add(h),l.add(h),n.setXYZ(u,o.x,o.y,o.z),n.setXYZ(g,c.x,c.y,c.z),n.setXYZ(x,l.x,l.y,l.z)}else for(let f=0,m=t.count;f<m;f+=3)i.fromBufferAttribute(t,f+0),s.fromBufferAttribute(t,f+1),a.fromBufferAttribute(t,f+2),h.subVectors(a,s),p.subVectors(i,s),h.cross(p),n.setXYZ(f+0,h.x,h.y,h.z),n.setXYZ(f+1,h.x,h.y,h.z),n.setXYZ(f+2,h.x,h.y,h.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){let e=this.attributes.normal;for(let t=0,n=e.count;t<n;t++)jt.fromBufferAttribute(e,t),jt.normalize(),e.setXYZ(t,jt.x,jt.y,jt.z)}toNonIndexed(){function e(o,c){let l=o.array,h=o.itemSize,p=o.normalized,f=new l.constructor(c.length*h),m=0,u=0;for(let g=0,x=c.length;g<x;g++){m=o.isInterleavedBufferAttribute?c[g]*o.data.stride+o.offset:c[g]*h;for(let _=0;_<h;_++)f[u++]=l[m++]}return new _n(f,h,p)}if(this.index===null)return Ye("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let t=new r,n=this.index.array,i=this.attributes;for(let o in i){let c=e(i[o],n);t.setAttribute(o,c)}let s=this.morphAttributes;for(let o in s){let c=[],l=s[o];for(let h=0,p=l.length;h<p;h++){let f=e(l[h],n);c.push(f)}t.morphAttributes[o]=c}t.morphTargetsRelative=this.morphTargetsRelative;let a=this.groups;for(let o=0,c=a.length;o<c;o++){let l=a[o];t.addGroup(l.start,l.count,l.materialIndex)}return t}toJSON(){let e={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(e.uuid=this.uuid,e.type=this.type,this.name!==""&&(e.name=this.name),Object.keys(this.userData).length>0&&(e.userData=this.userData),this.parameters!==void 0){let c=this.parameters;for(let l in c)c[l]!==void 0&&(e[l]=c[l]);return e}e.data={attributes:{}};let t=this.index;t!==null&&(e.data.index={type:t.array.constructor.name,array:Array.prototype.slice.call(t.array)});let n=this.attributes;for(let c in n){let l=n[c];e.data.attributes[c]=l.toJSON(e.data)}let i={},s=!1;for(let c in this.morphAttributes){let l=this.morphAttributes[c],h=[];for(let p=0,f=l.length;p<f;p++){let m=l[p];h.push(m.toJSON(e.data))}h.length>0&&(i[c]=h,s=!0)}s&&(e.data.morphAttributes=i,e.data.morphTargetsRelative=this.morphTargetsRelative);let a=this.groups;a.length>0&&(e.data.groups=JSON.parse(JSON.stringify(a)));let o=this.boundingSphere;return o!==null&&(e.data.boundingSphere=o.toJSON()),e}clone(){return new this.constructor().copy(this)}copy(e){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let t={};this.name=e.name;let n=e.index;n!==null&&this.setIndex(n.clone());let i=e.attributes;for(let l in i){let h=i[l];this.setAttribute(l,h.clone(t))}let s=e.morphAttributes;for(let l in s){let h=[],p=s[l];for(let f=0,m=p.length;f<m;f++)h.push(p[f].clone(t));this.morphAttributes[l]=h}this.morphTargetsRelative=e.morphTargetsRelative;let a=e.groups;for(let l=0,h=a.length;l<h;l++){let p=a[l];this.addGroup(p.start,p.count,p.materialIndex)}let o=e.boundingBox;o!==null&&(this.boundingBox=o.clone());let c=e.boundingSphere;return c!==null&&(this.boundingSphere=c.clone()),this.drawRange.start=e.drawRange.start,this.drawRange.count=e.drawRange.count,this.userData=e.userData,this}dispose(){this.dispatchEvent({type:"dispose"})}};var n0=new D;var Bf=0,Pi=class extends pi{constructor(){super(),this.isMaterial=!0,Object.defineProperty(this,"id",{value:Bf++}),this.uuid=vr(),this.name="",this.type="Material",this.blending=1,this.side=0,this.vertexColors=!1,this.opacity=1,this.transparent=!1,this.alphaHash=!1,this.blendSrc=204,this.blendDst=205,this.blendEquation=100,this.blendSrcAlpha=null,this.blendDstAlpha=null,this.blendEquationAlpha=null,this.blendColor=new He(0,0,0),this.blendAlpha=0,this.depthFunc=3,this.depthTest=!0,this.depthWrite=!0,this.stencilWriteMask=255,this.stencilFunc=519,this.stencilRef=0,this.stencilFuncMask=255,this.stencilFail=cr,this.stencilZFail=cr,this.stencilZPass=cr,this.stencilWrite=!1,this.clippingPlanes=null,this.clipIntersection=!1,this.clipShadows=!1,this.shadowSide=null,this.colorWrite=!0,this.precision=null,this.polygonOffset=!1,this.polygonOffsetFactor=0,this.polygonOffsetUnits=0,this.dithering=!1,this.alphaToCoverage=!1,this.premultipliedAlpha=!1,this.forceSinglePass=!1,this.allowOverride=!0,this.visible=!0,this.toneMapped=!0,this.userData={},this.version=0,this._alphaTest=0}get alphaTest(){return this._alphaTest}set alphaTest(e){this._alphaTest>0!=e>0&&this.version++,this._alphaTest=e}onBeforeRender(){}onBeforeCompile(){}customProgramCacheKey(){return this.onBeforeCompile.toString()}setValues(e){if(e!==void 0)for(let t in e){let n=e[t];if(n===void 0){Ye(`Material: parameter '${t}' has value of undefined.`);continue}let i=this[t];i!==void 0?i&&i.isColor?i.set(n):i&&i.isVector3&&n&&n.isVector3?i.copy(n):this[t]=n:Ye(`Material: '${t}' is not a property of THREE.${this.type}.`)}}toJSON(e){let t=e===void 0||typeof e=="string";t&&(e={textures:{},images:{}});let n={metadata:{version:4.7,type:"Material",generator:"Material.toJSON"}};function i(s){let a=[];for(let o in s){let c=s[o];delete c.metadata,a.push(c)}return a}if(n.uuid=this.uuid,n.type=this.type,this.name!==""&&(n.name=this.name),this.color&&this.color.isColor&&(n.color=this.color.getHex()),this.roughness!==void 0&&(n.roughness=this.roughness),this.metalness!==void 0&&(n.metalness=this.metalness),this.sheen!==void 0&&(n.sheen=this.sheen),this.sheenColor&&this.sheenColor.isColor&&(n.sheenColor=this.sheenColor.getHex()),this.sheenRoughness!==void 0&&(n.sheenRoughness=this.sheenRoughness),this.emissive&&this.emissive.isColor&&(n.emissive=this.emissive.getHex()),this.emissiveIntensity!==void 0&&this.emissiveIntensity!==1&&(n.emissiveIntensity=this.emissiveIntensity),this.specular&&this.specular.isColor&&(n.specular=this.specular.getHex()),this.specularIntensity!==void 0&&(n.specularIntensity=this.specularIntensity),this.specularColor&&this.specularColor.isColor&&(n.specularColor=this.specularColor.getHex()),this.shininess!==void 0&&(n.shininess=this.shininess),this.clearcoat!==void 0&&(n.clearcoat=this.clearcoat),this.clearcoatRoughness!==void 0&&(n.clearcoatRoughness=this.clearcoatRoughness),this.clearcoatMap&&this.clearcoatMap.isTexture&&(n.clearcoatMap=this.clearcoatMap.toJSON(e).uuid),this.clearcoatRoughnessMap&&this.clearcoatRoughnessMap.isTexture&&(n.clearcoatRoughnessMap=this.clearcoatRoughnessMap.toJSON(e).uuid),this.clearcoatNormalMap&&this.clearcoatNormalMap.isTexture&&(n.clearcoatNormalMap=this.clearcoatNormalMap.toJSON(e).uuid,n.clearcoatNormalScale=this.clearcoatNormalScale.toArray()),this.sheenColorMap&&this.sheenColorMap.isTexture&&(n.sheenColorMap=this.sheenColorMap.toJSON(e).uuid),this.sheenRoughnessMap&&this.sheenRoughnessMap.isTexture&&(n.sheenRoughnessMap=this.sheenRoughnessMap.toJSON(e).uuid),this.dispersion!==void 0&&(n.dispersion=this.dispersion),this.iridescence!==void 0&&(n.iridescence=this.iridescence),this.iridescenceIOR!==void 0&&(n.iridescenceIOR=this.iridescenceIOR),this.iridescenceThicknessRange!==void 0&&(n.iridescenceThicknessRange=this.iridescenceThicknessRange),this.iridescenceMap&&this.iridescenceMap.isTexture&&(n.iridescenceMap=this.iridescenceMap.toJSON(e).uuid),this.iridescenceThicknessMap&&this.iridescenceThicknessMap.isTexture&&(n.iridescenceThicknessMap=this.iridescenceThicknessMap.toJSON(e).uuid),this.anisotropy!==void 0&&(n.anisotropy=this.anisotropy),this.anisotropyRotation!==void 0&&(n.anisotropyRotation=this.anisotropyRotation),this.anisotropyMap&&this.anisotropyMap.isTexture&&(n.anisotropyMap=this.anisotropyMap.toJSON(e).uuid),this.map&&this.map.isTexture&&(n.map=this.map.toJSON(e).uuid),this.matcap&&this.matcap.isTexture&&(n.matcap=this.matcap.toJSON(e).uuid),this.alphaMap&&this.alphaMap.isTexture&&(n.alphaMap=this.alphaMap.toJSON(e).uuid),this.lightMap&&this.lightMap.isTexture&&(n.lightMap=this.lightMap.toJSON(e).uuid,n.lightMapIntensity=this.lightMapIntensity),this.aoMap&&this.aoMap.isTexture&&(n.aoMap=this.aoMap.toJSON(e).uuid,n.aoMapIntensity=this.aoMapIntensity),this.bumpMap&&this.bumpMap.isTexture&&(n.bumpMap=this.bumpMap.toJSON(e).uuid,n.bumpScale=this.bumpScale),this.normalMap&&this.normalMap.isTexture&&(n.normalMap=this.normalMap.toJSON(e).uuid,n.normalMapType=this.normalMapType,n.normalScale=this.normalScale.toArray()),this.displacementMap&&this.displacementMap.isTexture&&(n.displacementMap=this.displacementMap.toJSON(e).uuid,n.displacementScale=this.displacementScale,n.displacementBias=this.displacementBias),this.roughnessMap&&this.roughnessMap.isTexture&&(n.roughnessMap=this.roughnessMap.toJSON(e).uuid),this.metalnessMap&&this.metalnessMap.isTexture&&(n.metalnessMap=this.metalnessMap.toJSON(e).uuid),this.emissiveMap&&this.emissiveMap.isTexture&&(n.emissiveMap=this.emissiveMap.toJSON(e).uuid),this.specularMap&&this.specularMap.isTexture&&(n.specularMap=this.specularMap.toJSON(e).uuid),this.specularIntensityMap&&this.specularIntensityMap.isTexture&&(n.specularIntensityMap=this.specularIntensityMap.toJSON(e).uuid),this.specularColorMap&&this.specularColorMap.isTexture&&(n.specularColorMap=this.specularColorMap.toJSON(e).uuid),this.envMap&&this.envMap.isTexture&&(n.envMap=this.envMap.toJSON(e).uuid,this.combine!==void 0&&(n.combine=this.combine)),this.envMapRotation!==void 0&&(n.envMapRotation=this.envMapRotation.toArray()),this.envMapIntensity!==void 0&&(n.envMapIntensity=this.envMapIntensity),this.reflectivity!==void 0&&(n.reflectivity=this.reflectivity),this.refractionRatio!==void 0&&(n.refractionRatio=this.refractionRatio),this.gradientMap&&this.gradientMap.isTexture&&(n.gradientMap=this.gradientMap.toJSON(e).uuid),this.transmission!==void 0&&(n.transmission=this.transmission),this.transmissionMap&&this.transmissionMap.isTexture&&(n.transmissionMap=this.transmissionMap.toJSON(e).uuid),this.thickness!==void 0&&(n.thickness=this.thickness),this.thicknessMap&&this.thicknessMap.isTexture&&(n.thicknessMap=this.thicknessMap.toJSON(e).uuid),this.attenuationDistance!==void 0&&this.attenuationDistance!==1/0&&(n.attenuationDistance=this.attenuationDistance),this.attenuationColor!==void 0&&(n.attenuationColor=this.attenuationColor.getHex()),this.size!==void 0&&(n.size=this.size),this.shadowSide!==null&&(n.shadowSide=this.shadowSide),this.sizeAttenuation!==void 0&&(n.sizeAttenuation=this.sizeAttenuation),this.blending!==1&&(n.blending=this.blending),this.side!==0&&(n.side=this.side),this.vertexColors===!0&&(n.vertexColors=!0),this.opacity<1&&(n.opacity=this.opacity),this.transparent===!0&&(n.transparent=!0),this.blendSrc!==204&&(n.blendSrc=this.blendSrc),this.blendDst!==205&&(n.blendDst=this.blendDst),this.blendEquation!==100&&(n.blendEquation=this.blendEquation),this.blendSrcAlpha!==null&&(n.blendSrcAlpha=this.blendSrcAlpha),this.blendDstAlpha!==null&&(n.blendDstAlpha=this.blendDstAlpha),this.blendEquationAlpha!==null&&(n.blendEquationAlpha=this.blendEquationAlpha),this.blendColor&&this.blendColor.isColor&&(n.blendColor=this.blendColor.getHex()),this.blendAlpha!==0&&(n.blendAlpha=this.blendAlpha),this.depthFunc!==3&&(n.depthFunc=this.depthFunc),this.depthTest===!1&&(n.depthTest=this.depthTest),this.depthWrite===!1&&(n.depthWrite=this.depthWrite),this.colorWrite===!1&&(n.colorWrite=this.colorWrite),this.stencilWriteMask!==255&&(n.stencilWriteMask=this.stencilWriteMask),this.stencilFunc!==519&&(n.stencilFunc=this.stencilFunc),this.stencilRef!==0&&(n.stencilRef=this.stencilRef),this.stencilFuncMask!==255&&(n.stencilFuncMask=this.stencilFuncMask),this.stencilFail!==cr&&(n.stencilFail=this.stencilFail),this.stencilZFail!==cr&&(n.stencilZFail=this.stencilZFail),this.stencilZPass!==cr&&(n.stencilZPass=this.stencilZPass),this.stencilWrite===!0&&(n.stencilWrite=this.stencilWrite),this.rotation!==void 0&&this.rotation!==0&&(n.rotation=this.rotation),this.polygonOffset===!0&&(n.polygonOffset=!0),this.polygonOffsetFactor!==0&&(n.polygonOffsetFactor=this.polygonOffsetFactor),this.polygonOffsetUnits!==0&&(n.polygonOffsetUnits=this.polygonOffsetUnits),this.linewidth!==void 0&&this.linewidth!==1&&(n.linewidth=this.linewidth),this.dashSize!==void 0&&(n.dashSize=this.dashSize),this.gapSize!==void 0&&(n.gapSize=this.gapSize),this.scale!==void 0&&(n.scale=this.scale),this.dithering===!0&&(n.dithering=!0),this.alphaTest>0&&(n.alphaTest=this.alphaTest),this.alphaHash===!0&&(n.alphaHash=!0),this.alphaToCoverage===!0&&(n.alphaToCoverage=!0),this.premultipliedAlpha===!0&&(n.premultipliedAlpha=!0),this.forceSinglePass===!0&&(n.forceSinglePass=!0),this.allowOverride===!1&&(n.allowOverride=!1),this.wireframe===!0&&(n.wireframe=!0),this.wireframeLinewidth>1&&(n.wireframeLinewidth=this.wireframeLinewidth),this.wireframeLinecap!=="round"&&(n.wireframeLinecap=this.wireframeLinecap),this.wireframeLinejoin!=="round"&&(n.wireframeLinejoin=this.wireframeLinejoin),this.flatShading===!0&&(n.flatShading=!0),this.visible===!1&&(n.visible=!1),this.toneMapped===!1&&(n.toneMapped=!1),this.fog===!1&&(n.fog=!1),Object.keys(this.userData).length>0&&(n.userData=this.userData),t){let s=i(e.textures),a=i(e.images);s.length>0&&(n.textures=s),a.length>0&&(n.images=a)}return n}clone(){return new this.constructor().copy(this)}copy(e){this.name=e.name,this.blending=e.blending,this.side=e.side,this.vertexColors=e.vertexColors,this.opacity=e.opacity,this.transparent=e.transparent,this.blendSrc=e.blendSrc,this.blendDst=e.blendDst,this.blendEquation=e.blendEquation,this.blendSrcAlpha=e.blendSrcAlpha,this.blendDstAlpha=e.blendDstAlpha,this.blendEquationAlpha=e.blendEquationAlpha,this.blendColor.copy(e.blendColor),this.blendAlpha=e.blendAlpha,this.depthFunc=e.depthFunc,this.depthTest=e.depthTest,this.depthWrite=e.depthWrite,this.stencilWriteMask=e.stencilWriteMask,this.stencilFunc=e.stencilFunc,this.stencilRef=e.stencilRef,this.stencilFuncMask=e.stencilFuncMask,this.stencilFail=e.stencilFail,this.stencilZFail=e.stencilZFail,this.stencilZPass=e.stencilZPass,this.stencilWrite=e.stencilWrite;let t=e.clippingPlanes,n=null;if(t!==null){let i=t.length;n=new Array(i);for(let s=0;s!==i;++s)n[s]=t[s].clone()}return this.clippingPlanes=n,this.clipIntersection=e.clipIntersection,this.clipShadows=e.clipShadows,this.shadowSide=e.shadowSide,this.colorWrite=e.colorWrite,this.precision=e.precision,this.polygonOffset=e.polygonOffset,this.polygonOffsetFactor=e.polygonOffsetFactor,this.polygonOffsetUnits=e.polygonOffsetUnits,this.dithering=e.dithering,this.alphaTest=e.alphaTest,this.alphaHash=e.alphaHash,this.alphaToCoverage=e.alphaToCoverage,this.premultipliedAlpha=e.premultipliedAlpha,this.forceSinglePass=e.forceSinglePass,this.allowOverride=e.allowOverride,this.visible=e.visible,this.toneMapped=e.toneMapped,this.userData=JSON.parse(JSON.stringify(e.userData)),this}dispose(){this.dispatchEvent({type:"dispose"})}set needsUpdate(e){e===!0&&this.version++}};var i0=new D,r0=new D,s0=new D,a0=new _e,o0=new _e,l0=new Ke,c0=new D,h0=new D,u0=new D,d0=new _e,p0=new _e,f0=new _e;var m0=new D,g0=new D;var wi=new D,Ec=new D,io=new D,ki=new D,wc=new D,ro=new D,Ac=new D,fi=class{constructor(e=new D,t=new D(0,0,-1)){this.origin=e,this.direction=t}set(e,t){return this.origin.copy(e),this.direction.copy(t),this}copy(e){return this.origin.copy(e.origin),this.direction.copy(e.direction),this}at(e,t){return t.copy(this.origin).addScaledVector(this.direction,e)}lookAt(e){return this.direction.copy(e).sub(this.origin).normalize(),this}recast(e){return this.origin.copy(this.at(e,wi)),this}closestPointToPoint(e,t){t.subVectors(e,this.origin);let n=t.dot(this.direction);return n<0?t.copy(this.origin):t.copy(this.origin).addScaledVector(this.direction,n)}distanceToPoint(e){return Math.sqrt(this.distanceSqToPoint(e))}distanceSqToPoint(e){let t=wi.subVectors(e,this.origin).dot(this.direction);return t<0?this.origin.distanceToSquared(e):(wi.copy(this.origin).addScaledVector(this.direction,t),wi.distanceToSquared(e))}distanceSqToSegment(e,t,n,i){Ec.copy(e).add(t).multiplyScalar(.5),io.copy(t).sub(e).normalize(),ki.copy(this.origin).sub(Ec);let s=.5*e.distanceTo(t),a=-this.direction.dot(io),o=ki.dot(this.direction),c=-ki.dot(io),l=ki.lengthSq(),h=Math.abs(1-a*a),p,f,m,u;if(h>0)if(p=a*c-o,f=a*o-c,u=s*h,p>=0)if(f>=-u)if(f<=u){let g=1/h;p*=g,f*=g,m=p*(p+a*f+2*o)+f*(a*p+f+2*c)+l}else f=s,p=Math.max(0,-(a*f+o)),m=-p*p+f*(f+2*c)+l;else f=-s,p=Math.max(0,-(a*f+o)),m=-p*p+f*(f+2*c)+l;else f<=-u?(p=Math.max(0,-(-a*s+o)),f=p>0?-s:Math.min(Math.max(-s,-c),s),m=-p*p+f*(f+2*c)+l):f<=u?(p=0,f=Math.min(Math.max(-s,-c),s),m=f*(f+2*c)+l):(p=Math.max(0,-(a*s+o)),f=p>0?s:Math.min(Math.max(-s,-c),s),m=-p*p+f*(f+2*c)+l);else f=a>0?-s:s,p=Math.max(0,-(a*f+o)),m=-p*p+f*(f+2*c)+l;return n&&n.copy(this.origin).addScaledVector(this.direction,p),i&&i.copy(Ec).addScaledVector(io,f),m}intersectSphere(e,t){wi.subVectors(e.center,this.origin);let n=wi.dot(this.direction),i=wi.dot(wi)-n*n,s=e.radius*e.radius;if(i>s)return null;let a=Math.sqrt(s-i),o=n-a,c=n+a;return c<0?null:o<0?this.at(c,t):this.at(o,t)}intersectsSphere(e){return!(e.radius<0)&&this.distanceSqToPoint(e.center)<=e.radius*e.radius}distanceToPlane(e){let t=e.normal.dot(this.direction);if(t===0)return e.distanceToPoint(this.origin)===0?0:null;let n=-(this.origin.dot(e.normal)+e.constant)/t;return n>=0?n:null}intersectPlane(e,t){let n=this.distanceToPlane(e);return n===null?null:this.at(n,t)}intersectsPlane(e){let t=e.distanceToPoint(this.origin);return t===0?!0:e.normal.dot(this.direction)*t<0}intersectBox(e,t){let n,i,s,a,o,c,l=1/this.direction.x,h=1/this.direction.y,p=1/this.direction.z,f=this.origin;return l>=0?(n=(e.min.x-f.x)*l,i=(e.max.x-f.x)*l):(n=(e.max.x-f.x)*l,i=(e.min.x-f.x)*l),h>=0?(s=(e.min.y-f.y)*h,a=(e.max.y-f.y)*h):(s=(e.max.y-f.y)*h,a=(e.min.y-f.y)*h),n>a||s>i?null:((s>n||isNaN(n))&&(n=s),(a<i||isNaN(i))&&(i=a),p>=0?(o=(e.min.z-f.z)*p,c=(e.max.z-f.z)*p):(o=(e.max.z-f.z)*p,c=(e.min.z-f.z)*p),n>c||o>i?null:((o>n||n!=n)&&(n=o),(c<i||i!=i)&&(i=c),i<0?null:this.at(n>=0?n:i,t)))}intersectsBox(e){return this.intersectBox(e,wi)!==null}intersectTriangle(e,t,n,i,s){wc.subVectors(t,e),ro.subVectors(n,e),Ac.crossVectors(wc,ro);let a,o=this.direction.dot(Ac);if(o>0){if(i)return null;a=1}else{if(!(o<0))return null;a=-1,o=-o}ki.subVectors(this.origin,e);let c=a*this.direction.dot(ro.crossVectors(ki,ro));if(c<0)return null;let l=a*this.direction.dot(wc.cross(ki));if(l<0||c+l>o)return null;let h=-a*ki.dot(Ac);return h<0?null:this.at(h/o,s)}applyMatrix4(e){return this.origin.applyMatrix4(e),this.direction.transformDirection(e),this}equals(e){return e.origin.equals(this.origin)&&e.direction.equals(this.direction)}clone(){return new this.constructor().copy(this)}},Jn=class extends Pi{constructor(e){super(),this.isMeshBasicMaterial=!0,this.type="MeshBasicMaterial",this.color=new He(16777215),this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.specularMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Un,this.combine=0,this.reflectivity=1,this.refractionRatio=.98,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.specularMap=e.specularMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.combine=e.combine,this.reflectivity=e.reflectivity,this.refractionRatio=e.refractionRatio,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.fog=e.fog,this}},ad=new Ke,or=new fi,so=new Zn,od=new D,ao=new D,oo=new D,lo=new D,Cc=new D,co=new D,ld=new D,ho=new D,At=class extends Ft{constructor(e=new bt,t=new Jn){super(),this.isMesh=!0,this.type="Mesh",this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.count=1,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),e.morphTargetInfluences!==void 0&&(this.morphTargetInfluences=e.morphTargetInfluences.slice()),e.morphTargetDictionary!==void 0&&(this.morphTargetDictionary=Object.assign({},e.morphTargetDictionary)),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}updateMorphTargets(){let e=this.geometry.morphAttributes,t=Object.keys(e);if(t.length>0){let n=e[t[0]];if(n!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let i=0,s=n.length;i<s;i++){let a=n[i].name||String(i);this.morphTargetInfluences.push(0),this.morphTargetDictionary[a]=i}}}}getVertexPosition(e,t){let n=this.geometry,i=n.attributes.position,s=n.morphAttributes.position,a=n.morphTargetsRelative;t.fromBufferAttribute(i,e);let o=this.morphTargetInfluences;if(s&&o){co.set(0,0,0);for(let c=0,l=s.length;c<l;c++){let h=o[c],p=s[c];h!==0&&(Cc.fromBufferAttribute(p,e),a?co.addScaledVector(Cc,h):co.addScaledVector(Cc.sub(t),h))}t.add(co)}return t}raycast(e,t){let n=this.geometry,i=this.material,s=this.matrixWorld;if(i!==void 0){if(n.boundingSphere===null&&n.computeBoundingSphere(),so.copy(n.boundingSphere),so.applyMatrix4(s),or.copy(e.ray).recast(e.near),so.containsPoint(or.origin)===!1&&(or.intersectSphere(so,od)===null||or.origin.distanceToSquared(od)>(e.far-e.near)**2))return;ad.copy(s).invert(),or.copy(e.ray).applyMatrix4(ad),n.boundingBox!==null&&or.intersectsBox(n.boundingBox)===!1||this._computeIntersections(e,t,or)}}_computeIntersections(e,t,n){let i,s=this.geometry,a=this.material,o=s.index,c=s.attributes.position,l=s.attributes.uv,h=s.attributes.uv1,p=s.attributes.normal,f=s.groups,m=s.drawRange;if(o!==null)if(Array.isArray(a))for(let u=0,g=f.length;u<g;u++){let x=f[u],_=a[x.materialIndex];for(let v=Math.max(x.start,m.start),S=Math.min(o.count,Math.min(x.start+x.count,m.start+m.count));v<S;v+=3)i=uo(this,_,e,n,l,h,p,o.getX(v),o.getX(v+1),o.getX(v+2)),i&&(i.faceIndex=Math.floor(v/3),i.face.materialIndex=x.materialIndex,t.push(i))}else for(let u=Math.max(0,m.start),g=Math.min(o.count,m.start+m.count);u<g;u+=3)i=uo(this,a,e,n,l,h,p,o.getX(u),o.getX(u+1),o.getX(u+2)),i&&(i.faceIndex=Math.floor(u/3),t.push(i));else if(c!==void 0)if(Array.isArray(a))for(let u=0,g=f.length;u<g;u++){let x=f[u],_=a[x.materialIndex];for(let v=Math.max(x.start,m.start),S=Math.min(c.count,Math.min(x.start+x.count,m.start+m.count));v<S;v+=3)i=uo(this,_,e,n,l,h,p,v,v+1,v+2),i&&(i.faceIndex=Math.floor(v/3),i.face.materialIndex=x.materialIndex,t.push(i))}else for(let u=Math.max(0,m.start),g=Math.min(c.count,m.start+m.count);u<g;u+=3)i=uo(this,a,e,n,l,h,p,u,u+1,u+2),i&&(i.faceIndex=Math.floor(u/3),t.push(i))}};function uo(r,e,t,n,i,s,a,o,c,l){r.getVertexPosition(o,ao),r.getVertexPosition(c,oo),r.getVertexPosition(l,lo);let h=(function(p,f,m,u,g,x,_,v){let S;if(S=f.side===1?u.intersectTriangle(_,x,g,!0,v):u.intersectTriangle(g,x,_,f.side===0,v),S===null)return null;ho.copy(v),ho.applyMatrix4(p.matrixWorld);let E=m.ray.origin.distanceTo(ho);return E<m.near||E>m.far?null:{distance:E,point:ho.clone(),object:p}})(r,e,t,n,ao,oo,lo,ld);if(h){let p=new D;Ai.getBarycoord(ld,ao,oo,lo,p),i&&(h.uv=Ai.getInterpolatedAttribute(i,o,c,l,p,new _e)),s&&(h.uv1=Ai.getInterpolatedAttribute(s,o,c,l,p,new _e)),a&&(h.normal=Ai.getInterpolatedAttribute(a,o,c,l,p,new D),h.normal.dot(n.direction)>0&&h.normal.multiplyScalar(-1));let f={a:o,b:c,c:l,normal:new D,materialIndex:0};Ai.getNormal(ao,oo,lo,f.normal),h.face=f,h.barycoord=p}return h}var _0=new D,v0=new wt,y0=new wt,x0=new D,M0=new Ke,b0=new D,S0=new Zn,T0=new Ke,E0=new fi;var ta=class extends an{constructor(e=null,t=1,n=1,i,s,a,o,c,l=1003,h=1003,p,f){super(null,a,o,c,l,h,i,s,p,f),this.isDataTexture=!0,this.image={data:e,width:t,height:n},this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}},w0=new Ke,A0=new Ke;var na=class extends _n{constructor(e,t,n,i=1){super(e,t,n),this.isInstancedBufferAttribute=!0,this.meshPerAttribute=i}copy(e){return super.copy(e),this.meshPerAttribute=e.meshPerAttribute,this}toJSON(){let e=super.toJSON();return e.meshPerAttribute=this.meshPerAttribute,e.isInstancedBufferAttribute=!0,e}},Hr=new Ke,cd=new Ke,po=[],hd=new $t,zf=new Ke,ks=new At,Vs=new Zn,ri=class extends At{constructor(e,t,n){super(e,t),this.isInstancedMesh=!0,this.instanceMatrix=new na(new Float32Array(16*n),16),this.previousInstanceMatrix=null,this.instanceColor=null,this.morphTexture=null,this.count=n,this.boundingBox=null,this.boundingSphere=null;for(let i=0;i<n;i++)this.setMatrixAt(i,zf)}computeBoundingBox(){let e=this.geometry,t=this.count;this.boundingBox===null&&(this.boundingBox=new $t),e.boundingBox===null&&e.computeBoundingBox(),this.boundingBox.makeEmpty();for(let n=0;n<t;n++)this.getMatrixAt(n,Hr),hd.copy(e.boundingBox).applyMatrix4(Hr),this.boundingBox.union(hd)}computeBoundingSphere(){let e=this.geometry,t=this.count;this.boundingSphere===null&&(this.boundingSphere=new Zn),e.boundingSphere===null&&e.computeBoundingSphere(),this.boundingSphere.makeEmpty();for(let n=0;n<t;n++)this.getMatrixAt(n,Hr),Vs.copy(e.boundingSphere).applyMatrix4(Hr),this.boundingSphere.union(Vs)}copy(e,t){return super.copy(e,t),this.instanceMatrix.copy(e.instanceMatrix),e.previousInstanceMatrix!==null&&(this.previousInstanceMatrix=e.previousInstanceMatrix.clone()),e.morphTexture!==null&&(this.morphTexture=e.morphTexture.clone()),e.instanceColor!==null&&(this.instanceColor=e.instanceColor.clone()),this.count=e.count,e.boundingBox!==null&&(this.boundingBox=e.boundingBox.clone()),e.boundingSphere!==null&&(this.boundingSphere=e.boundingSphere.clone()),this}getColorAt(e,t){t.fromArray(this.instanceColor.array,3*e)}getMatrixAt(e,t){t.fromArray(this.instanceMatrix.array,16*e)}getMorphAt(e,t){let n=t.morphTargetInfluences,i=this.morphTexture.source.data.data,s=e*(n.length+1)+1;for(let a=0;a<n.length;a++)n[a]=i[s+a]}raycast(e,t){let n=this.matrixWorld,i=this.count;if(ks.geometry=this.geometry,ks.material=this.material,ks.material!==void 0&&(this.boundingSphere===null&&this.computeBoundingSphere(),Vs.copy(this.boundingSphere),Vs.applyMatrix4(n),e.ray.intersectsSphere(Vs)!==!1))for(let s=0;s<i;s++){this.getMatrixAt(s,Hr),cd.multiplyMatrices(n,Hr),ks.matrixWorld=cd,ks.raycast(e,po);for(let a=0,o=po.length;a<o;a++){let c=po[a];c.instanceId=s,c.object=this,t.push(c)}po.length=0}}setColorAt(e,t){this.instanceColor===null&&(this.instanceColor=new na(new Float32Array(3*this.instanceMatrix.count).fill(1),3)),t.toArray(this.instanceColor.array,3*e)}setMatrixAt(e,t){t.toArray(this.instanceMatrix.array,16*e)}setMorphAt(e,t){let n=t.morphTargetInfluences,i=n.length+1;this.morphTexture===null&&(this.morphTexture=new ta(new Float32Array(i*this.count),i,this.count,Pl,Kn));let s=this.morphTexture.source.data.data,a=0;for(let l=0;l<n.length;l++)a+=n[l];let o=this.geometry.morphTargetsRelative?1:1-a,c=i*e;s[c]=o,s.set(n,c+1)}updateMorphTargets(){}dispose(){this.dispatchEvent({type:"dispose"}),this.morphTexture!==null&&(this.morphTexture.dispose(),this.morphTexture=null)}},Rc=new D,kf=new D,Vf=new et,Zt=class{constructor(e=new D(1,0,0),t=0){this.isPlane=!0,this.normal=e,this.constant=t}set(e,t){return this.normal.copy(e),this.constant=t,this}setComponents(e,t,n,i){return this.normal.set(e,t,n),this.constant=i,this}setFromNormalAndCoplanarPoint(e,t){return this.normal.copy(e),this.constant=-t.dot(this.normal),this}setFromCoplanarPoints(e,t,n){let i=Rc.subVectors(n,t).cross(kf.subVectors(e,t)).normalize();return this.setFromNormalAndCoplanarPoint(i,e),this}copy(e){return this.normal.copy(e.normal),this.constant=e.constant,this}normalize(){let e=1/this.normal.length();return this.normal.multiplyScalar(e),this.constant*=e,this}negate(){return this.constant*=-1,this.normal.negate(),this}distanceToPoint(e){return this.normal.dot(e)+this.constant}distanceToSphere(e){return this.distanceToPoint(e.center)-e.radius}projectPoint(e,t){return t.copy(e).addScaledVector(this.normal,-this.distanceToPoint(e))}intersectLine(e,t){let n=e.delta(Rc),i=this.normal.dot(n);if(i===0)return this.distanceToPoint(e.start)===0?t.copy(e.start):null;let s=-(e.start.dot(this.normal)+this.constant)/i;return s<0||s>1?null:t.copy(e.start).addScaledVector(n,s)}intersectsLine(e){let t=this.distanceToPoint(e.start),n=this.distanceToPoint(e.end);return t<0&&n>0||n<0&&t>0}intersectsBox(e){return e.intersectsPlane(this)}intersectsSphere(e){return e.intersectsPlane(this)}coplanarPoint(e){return e.copy(this.normal).multiplyScalar(-this.constant)}applyMatrix4(e,t){let n=t||Vf.getNormalMatrix(e),i=this.coplanarPoint(Rc).applyMatrix4(e),s=this.normal.applyMatrix3(n).normalize();return this.constant=-i.dot(s),this}translate(e){return this.constant-=e.dot(this.normal),this}equals(e){return e.normal.equals(this.normal)&&e.constant===this.constant}clone(){return new this.constructor().copy(this)}},lr=new Zn,Gf=new _e(.5,.5),fo=new D,ji=class{constructor(e=new Zt,t=new Zt,n=new Zt,i=new Zt,s=new Zt,a=new Zt){this.planes=[e,t,n,i,s,a]}set(e,t,n,i,s,a){let o=this.planes;return o[0].copy(e),o[1].copy(t),o[2].copy(n),o[3].copy(i),o[4].copy(s),o[5].copy(a),this}copy(e){let t=this.planes;for(let n=0;n<6;n++)t[n].copy(e.planes[n]);return this}setFromProjectionMatrix(e,t=2e3,n=!1){let i=this.planes,s=e.elements,a=s[0],o=s[1],c=s[2],l=s[3],h=s[4],p=s[5],f=s[6],m=s[7],u=s[8],g=s[9],x=s[10],_=s[11],v=s[12],S=s[13],E=s[14],w=s[15];if(i[0].setComponents(l-a,m-h,_-u,w-v).normalize(),i[1].setComponents(l+a,m+h,_+u,w+v).normalize(),i[2].setComponents(l+o,m+p,_+g,w+S).normalize(),i[3].setComponents(l-o,m-p,_-g,w-S).normalize(),n)i[4].setComponents(c,f,x,E).normalize(),i[5].setComponents(l-c,m-f,_-x,w-E).normalize();else if(i[4].setComponents(l-c,m-f,_-x,w-E).normalize(),t===Ri)i[5].setComponents(l+c,m+f,_+x,w+E).normalize();else{if(t!==Zr)throw new Error("THREE.Frustum.setFromProjectionMatrix(): Invalid coordinate system: "+t);i[5].setComponents(c,f,x,E).normalize()}return this}intersectsObject(e){if(e.boundingSphere!==void 0)e.boundingSphere===null&&e.computeBoundingSphere(),lr.copy(e.boundingSphere).applyMatrix4(e.matrixWorld);else{let t=e.geometry;t.boundingSphere===null&&t.computeBoundingSphere(),lr.copy(t.boundingSphere).applyMatrix4(e.matrixWorld)}return this.intersectsSphere(lr)}intersectsSprite(e){lr.center.set(0,0,0);let t=Gf.distanceTo(e.center);return lr.radius=.7071067811865476+t,lr.applyMatrix4(e.matrixWorld),this.intersectsSphere(lr)}intersectsSphere(e){let t=this.planes,n=e.center,i=-e.radius;for(let s=0;s<6;s++)if(t[s].distanceToPoint(n)<i)return!1;return!0}intersectsBox(e){let t=this.planes;for(let n=0;n<6;n++){let i=t[n];if(fo.x=i.normal.x>0?e.max.x:e.min.x,fo.y=i.normal.y>0?e.max.y:e.min.y,fo.z=i.normal.z>0?e.max.z:e.min.z,i.distanceToPoint(fo)<0)return!1}return!0}containsPoint(e){let t=this.planes;for(let n=0;n<6;n++)if(t[n].distanceToPoint(e)<0)return!1;return!0}clone(){return new this.constructor().copy(this)}},ci=new Ke,hi=new ji,Do=class r{constructor(){this.coordinateSystem=Ri}intersectsObject(e,t){if(!t.isArrayCamera||t.cameras.length===0)return!1;for(let n=0;n<t.cameras.length;n++){let i=t.cameras[n];if(ci.multiplyMatrices(i.projectionMatrix,i.matrixWorldInverse),hi.setFromProjectionMatrix(ci,i.coordinateSystem,i.reversedDepth),hi.intersectsObject(e))return!0}return!1}intersectsSprite(e,t){if(!t||!t.cameras||t.cameras.length===0)return!1;for(let n=0;n<t.cameras.length;n++){let i=t.cameras[n];if(ci.multiplyMatrices(i.projectionMatrix,i.matrixWorldInverse),hi.setFromProjectionMatrix(ci,i.coordinateSystem,i.reversedDepth),hi.intersectsSprite(e))return!0}return!1}intersectsSphere(e,t){if(!t||!t.cameras||t.cameras.length===0)return!1;for(let n=0;n<t.cameras.length;n++){let i=t.cameras[n];if(ci.multiplyMatrices(i.projectionMatrix,i.matrixWorldInverse),hi.setFromProjectionMatrix(ci,i.coordinateSystem,i.reversedDepth),hi.intersectsSphere(e))return!0}return!1}intersectsBox(e,t){if(!t||!t.cameras||t.cameras.length===0)return!1;for(let n=0;n<t.cameras.length;n++){let i=t.cameras[n];if(ci.multiplyMatrices(i.projectionMatrix,i.matrixWorldInverse),hi.setFromProjectionMatrix(ci,i.coordinateSystem,i.reversedDepth),hi.intersectsBox(e))return!0}return!1}containsPoint(e,t){if(!t||!t.cameras||t.cameras.length===0)return!1;for(let n=0;n<t.cameras.length;n++){let i=t.cameras[n];if(ci.multiplyMatrices(i.projectionMatrix,i.matrixWorldInverse),hi.setFromProjectionMatrix(ci,i.coordinateSystem,i.reversedDepth),hi.containsPoint(e))return!0}return!1}clone(){return new r}};var Hc=class{constructor(){this.index=0,this.pool=[],this.list=[]}push(e,t,n,i){let s=this.pool,a=this.list;this.index>=s.length&&s.push({start:-1,count:-1,z:-1,index:-1});let o=s[this.index];a.push(o),this.index++,o.start=e,o.count=t,o.z=n,o.index=i}reset(){this.list.length=0,this.index=0}},C0=new Ke,R0=new He(1,1,1),P0=new ji,I0=new Do,L0=new $t,D0=new Zn,U0=new D,N0=new D,O0=new D,F0=new Hc,B0=new At;var ns=class extends Pi{constructor(e){super(),this.isLineBasicMaterial=!0,this.type="LineBasicMaterial",this.color=new He(16777215),this.map=null,this.linewidth=1,this.linecap="round",this.linejoin="round",this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.linewidth=e.linewidth,this.linecap=e.linecap,this.linejoin=e.linejoin,this.fog=e.fog,this}},Uo=new D,No=new D,ud=new Ke,Gs=new fi,mo=new Zn,Pc=new D,dd=new D,Oo=class extends Ft{constructor(e=new bt,t=new ns){super(),this.isLine=!0,this.type="Line",this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}computeLineDistances(){let e=this.geometry;if(e.index===null){let t=e.attributes.position,n=[0];for(let i=1,s=t.count;i<s;i++)Uo.fromBufferAttribute(t,i-1),No.fromBufferAttribute(t,i),n[i]=n[i-1],n[i]+=Uo.distanceTo(No);e.setAttribute("lineDistance",new Xe(n,1))}else Ye("Line.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.");return this}raycast(e,t){let n=this.geometry,i=this.matrixWorld,s=e.params.Line.threshold,a=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),mo.copy(n.boundingSphere),mo.applyMatrix4(i),mo.radius+=s,e.ray.intersectsSphere(mo)===!1)return;ud.copy(i).invert(),Gs.copy(e.ray).applyMatrix4(ud);let o=s/((this.scale.x+this.scale.y+this.scale.z)/3),c=o*o,l=this.isLineSegments?2:1,h=n.index,p=n.attributes.position;if(h!==null){let f=Math.max(0,a.start),m=Math.min(h.count,a.start+a.count);for(let u=f,g=m-1;u<g;u+=l){let x=h.getX(u),_=h.getX(u+1),v=go(this,e,Gs,c,x,_,u);v&&t.push(v)}if(this.isLineLoop){let u=h.getX(m-1),g=h.getX(f),x=go(this,e,Gs,c,u,g,m-1);x&&t.push(x)}}else{let f=Math.max(0,a.start),m=Math.min(p.count,a.start+a.count);for(let u=f,g=m-1;u<g;u+=l){let x=go(this,e,Gs,c,u,u+1,u);x&&t.push(x)}if(this.isLineLoop){let u=go(this,e,Gs,c,m-1,f,m-1);u&&t.push(u)}}}updateMorphTargets(){let e=this.geometry.morphAttributes,t=Object.keys(e);if(t.length>0){let n=e[t[0]];if(n!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let i=0,s=n.length;i<s;i++){let a=n[i].name||String(i);this.morphTargetInfluences.push(0),this.morphTargetDictionary[a]=i}}}}};function go(r,e,t,n,i,s,a){let o=r.geometry.attributes.position;if(Uo.fromBufferAttribute(o,i),No.fromBufferAttribute(o,s),t.distanceSqToSegment(Uo,No,Pc,dd)>n)return;Pc.applyMatrix4(r.matrixWorld);let c=e.ray.origin.distanceTo(Pc);return c<e.near||c>e.far?void 0:{distance:c,point:dd.clone().applyMatrix4(r.matrixWorld),index:a,face:null,faceIndex:null,barycoord:null,object:r}}var pd=new D,fd=new D,ia=class extends Oo{constructor(e,t){super(e,t),this.isLineSegments=!0,this.type="LineSegments"}computeLineDistances(){let e=this.geometry;if(e.index===null){let t=e.attributes.position,n=[];for(let i=0,s=t.count;i<s;i+=2)pd.fromBufferAttribute(t,i),fd.fromBufferAttribute(t,i+1),n[i]=i===0?0:n[i-1],n[i+1]=n[i]+pd.distanceTo(fd);e.setAttribute("lineDistance",new Xe(n,1))}else Ye("LineSegments.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.");return this}};var z0=new Ke,k0=new fi,V0=new Zn,G0=new D;var ra=class extends an{constructor(e=[],t=301,n,i,s,a,o,c,l,h){super(e,t,n,i,s,a,o,c,l,h),this.isCubeTexture=!0,this.flipY=!1}get images(){return this.image}set images(e){this.image=e}},Ii=class extends an{constructor(e,t,n,i,s,a,o,c,l){super(e,t,n,i,s,a,o,c,l),this.isCanvasTexture=!0,this.needsUpdate=!0}},Xi=class extends an{constructor(e,t,n=1014,i,s,a,o=1003,c=1003,l,h=1026,p=1){if(h!==Ki&&h!==1027)throw new Error("DepthTexture format must be either THREE.DepthFormat or THREE.DepthStencilFormat");super({width:e,height:t,depth:p},i,s,a,o,c,h,n,l),this.isDepthTexture=!0,this.flipY=!1,this.generateMipmaps=!1,this.compareFunction=null}copy(e){return super.copy(e),this.source=new Qr(Object.assign({},e.image)),this.compareFunction=e.compareFunction,this}toJSON(e){let t=super.toJSON(e);return this.compareFunction!==null&&(t.compareFunction=this.compareFunction),t}},Fo=class extends Xi{constructor(e,t=1014,n=301,i,s,a=1003,o=1003,c,l=1026){let h={width:e,height:e,depth:1},p=[h,h,h,h,h,h];super(e,e,t,n,i,s,a,o,c,l),this.image=p,this.isCubeDepthTexture=!0,this.isCubeTexture=!0}get images(){return this.image}set images(e){this.image=e}},sa=class extends an{constructor(e=null){super(),this.sourceTexture=e,this.isExternalTexture=!0}copy(e){return super.copy(e),this.sourceTexture=e.sourceTexture,this}},Nn=class r extends bt{constructor(e=1,t=1,n=1,i=1,s=1,a=1){super(),this.type="BoxGeometry",this.parameters={width:e,height:t,depth:n,widthSegments:i,heightSegments:s,depthSegments:a};let o=this;i=Math.floor(i),s=Math.floor(s),a=Math.floor(a);let c=[],l=[],h=[],p=[],f=0,m=0;function u(g,x,_,v,S,E,w,R,z,j,O){let Q=E/z,Y=w/j,k=E/2,X=w/2,K=R/2,te=z+1,oe=j+1,ee=0,xe=0,be=new D;for(let we=0;we<oe;we++){let Se=we*Y-X;for(let se=0;se<te;se++){let de=se*Q-k;be[g]=de*v,be[x]=Se*S,be[_]=K,l.push(be.x,be.y,be.z),be[g]=0,be[x]=0,be[_]=R>0?1:-1,h.push(be.x,be.y,be.z),p.push(se/z),p.push(1-we/j),ee+=1}}for(let we=0;we<j;we++)for(let Se=0;Se<z;Se++){let se=f+Se+te*we,de=f+Se+te*(we+1),ge=f+(Se+1)+te*(we+1),Te=f+(Se+1)+te*we;c.push(se,de,Te),c.push(de,ge,Te),xe+=6}o.addGroup(m,xe,O),m+=xe,f+=ee}u("z","y","x",-1,-1,n,t,e,a,s,0),u("z","y","x",1,-1,n,t,-e,a,s,1),u("x","z","y",1,1,e,n,t,i,a,2),u("x","z","y",1,-1,e,n,-t,i,a,3),u("x","y","z",1,-1,e,t,n,i,s,4),u("x","y","z",-1,-1,e,t,-n,i,s,5),this.setIndex(c),this.setAttribute("position",new Xe(l,3)),this.setAttribute("normal",new Xe(h,3)),this.setAttribute("uv",new Xe(p,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.width,e.height,e.depth,e.widthSegments,e.heightSegments,e.depthSegments)}},Bo=class r extends bt{constructor(e=1,t=1,n=4,i=8,s=1){super(),this.type="CapsuleGeometry",this.parameters={radius:e,height:t,capSegments:n,radialSegments:i,heightSegments:s},t=Math.max(0,t),n=Math.max(1,Math.floor(n)),i=Math.max(3,Math.floor(i)),s=Math.max(1,Math.floor(s));let a=[],o=[],c=[],l=[],h=t/2,p=Math.PI/2*e,f=t,m=2*p+f,u=2*n+s,g=i+1,x=new D,_=new D;for(let v=0;v<=u;v++){let S=0,E=0,w=0,R=0;if(v<=n){let O=v/n,Q=O*Math.PI/2;E=-h-e*Math.cos(Q),w=e*Math.sin(Q),R=-e*Math.cos(Q),S=O*p}else if(v<=n+s){let O=(v-n)/s;E=O*t-h,w=e,R=0,S=p+O*f}else{let O=(v-n-s)/n,Q=O*Math.PI/2;E=h+e*Math.sin(Q),w=e*Math.cos(Q),R=e*Math.sin(Q),S=p+f+O*p}let z=Math.max(0,Math.min(1,S/m)),j=0;v===0?j=.5/i:v===u&&(j=-.5/i);for(let O=0;O<=i;O++){let Q=O/i,Y=Q*Math.PI*2,k=Math.sin(Y),X=Math.cos(Y);_.x=-w*X,_.y=E,_.z=w*k,o.push(_.x,_.y,_.z),x.set(-w*X,R,w*k),x.normalize(),c.push(x.x,x.y,x.z),l.push(Q+j,z)}if(v>0){let O=(v-1)*g;for(let Q=0;Q<i;Q++){let Y=O+Q,k=O+Q+1,X=v*g+Q,K=v*g+Q+1;a.push(Y,k,X),a.push(k,K,X)}}}this.setIndex(a),this.setAttribute("position",new Xe(o,3)),this.setAttribute("normal",new Xe(c,3)),this.setAttribute("uv",new Xe(l,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.radius,e.height,e.capSegments,e.radialSegments,e.heightSegments)}},zo=class r extends bt{constructor(e=1,t=32,n=0,i=2*Math.PI){super(),this.type="CircleGeometry",this.parameters={radius:e,segments:t,thetaStart:n,thetaLength:i},t=Math.max(3,t);let s=[],a=[],o=[],c=[],l=new D,h=new _e;a.push(0,0,0),o.push(0,0,1),c.push(.5,.5);for(let p=0,f=3;p<=t;p++,f+=3){let m=n+p/t*i;l.x=e*Math.cos(m),l.y=e*Math.sin(m),a.push(l.x,l.y,l.z),o.push(0,0,1),h.x=(a[f]/e+1)/2,h.y=(a[f+1]/e+1)/2,c.push(h.x,h.y)}for(let p=1;p<=t;p++)s.push(p,p+1,0);this.setIndex(s),this.setAttribute("position",new Xe(a,3)),this.setAttribute("normal",new Xe(o,3)),this.setAttribute("uv",new Xe(c,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.radius,e.segments,e.thetaStart,e.thetaLength)}},aa=class r extends bt{constructor(e=1,t=1,n=1,i=32,s=1,a=!1,o=0,c=2*Math.PI){super(),this.type="CylinderGeometry",this.parameters={radiusTop:e,radiusBottom:t,height:n,radialSegments:i,heightSegments:s,openEnded:a,thetaStart:o,thetaLength:c};let l=this;i=Math.floor(i),s=Math.floor(s);let h=[],p=[],f=[],m=[],u=0,g=[],x=n/2,_=0;function v(S){let E=u,w=new _e,R=new D,z=0,j=S===!0?e:t,O=S===!0?1:-1;for(let Y=1;Y<=i;Y++)p.push(0,x*O,0),f.push(0,O,0),m.push(.5,.5),u++;let Q=u;for(let Y=0;Y<=i;Y++){let k=Y/i*c+o,X=Math.cos(k),K=Math.sin(k);R.x=j*K,R.y=x*O,R.z=j*X,p.push(R.x,R.y,R.z),f.push(0,O,0),w.x=.5*X+.5,w.y=.5*K*O+.5,m.push(w.x,w.y),u++}for(let Y=0;Y<i;Y++){let k=E+Y,X=Q+Y;S===!0?h.push(X,X+1,k):h.push(X+1,X,k),z+=3}l.addGroup(_,z,S===!0?1:2),_+=z}(function(){let S=new D,E=new D,w=0,R=(t-e)/n;for(let z=0;z<=s;z++){let j=[],O=z/s,Q=O*(t-e)+e;for(let Y=0;Y<=i;Y++){let k=Y/i,X=k*c+o,K=Math.sin(X),te=Math.cos(X);E.x=Q*K,E.y=-O*n+x,E.z=Q*te,p.push(E.x,E.y,E.z),S.set(K,R,te).normalize(),f.push(S.x,S.y,S.z),m.push(k,1-O),j.push(u++)}g.push(j)}for(let z=0;z<i;z++)for(let j=0;j<s;j++){let O=g[j][z],Q=g[j+1][z],Y=g[j+1][z+1],k=g[j][z+1];(e>0||j!==0)&&(h.push(O,Q,k),w+=3),(t>0||j!==s-1)&&(h.push(Q,Y,k),w+=3)}l.addGroup(_,w,0),_+=w})(),a===!1&&(e>0&&v(!0),t>0&&v(!1)),this.setIndex(h),this.setAttribute("position",new Xe(p,3)),this.setAttribute("normal",new Xe(f,3)),this.setAttribute("uv",new Xe(m,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.radiusTop,e.radiusBottom,e.height,e.radialSegments,e.heightSegments,e.openEnded,e.thetaStart,e.thetaLength)}},ko=class r extends aa{constructor(e=1,t=1,n=32,i=1,s=!1,a=0,o=2*Math.PI){super(0,e,t,n,i,s,a,o),this.type="ConeGeometry",this.parameters={radius:e,height:t,radialSegments:n,heightSegments:i,openEnded:s,thetaStart:a,thetaLength:o}}static fromJSON(e){return new r(e.radius,e.height,e.radialSegments,e.heightSegments,e.openEnded,e.thetaStart,e.thetaLength)}},qi=class r extends bt{constructor(e=[],t=[],n=1,i=0){super(),this.type="PolyhedronGeometry",this.parameters={vertices:e,indices:t,radius:n,detail:i};let s=[],a=[];function o(m,u,g,x){let _=x+1,v=[];for(let S=0;S<=_;S++){v[S]=[];let E=m.clone().lerp(g,S/_),w=u.clone().lerp(g,S/_),R=_-S;for(let z=0;z<=R;z++)v[S][z]=z===0&&S===_?E:E.clone().lerp(w,z/R)}for(let S=0;S<_;S++)for(let E=0;E<2*(_-S)-1;E++){let w=Math.floor(E/2);E%2==0?(c(v[S][w+1]),c(v[S+1][w]),c(v[S][w])):(c(v[S][w+1]),c(v[S+1][w+1]),c(v[S+1][w]))}}function c(m){s.push(m.x,m.y,m.z)}function l(m,u){let g=3*m;u.x=e[g+0],u.y=e[g+1],u.z=e[g+2]}function h(m,u,g,x){x<0&&m.x===1&&(a[u]=m.x-1),g.x===0&&g.z===0&&(a[u]=x/2/Math.PI+.5)}function p(m){return Math.atan2(m.z,-m.x)}function f(m){return Math.atan2(-m.y,Math.sqrt(m.x*m.x+m.z*m.z))}(function(m){let u=new D,g=new D,x=new D;for(let _=0;_<t.length;_+=3)l(t[_+0],u),l(t[_+1],g),l(t[_+2],x),o(u,g,x,m)})(i),(function(m){let u=new D;for(let g=0;g<s.length;g+=3)u.x=s[g+0],u.y=s[g+1],u.z=s[g+2],u.normalize().multiplyScalar(m),s[g+0]=u.x,s[g+1]=u.y,s[g+2]=u.z})(n),(function(){let m=new D;for(let u=0;u<s.length;u+=3){m.x=s[u+0],m.y=s[u+1],m.z=s[u+2];let g=p(m)/2/Math.PI+.5,x=f(m)/Math.PI+.5;a.push(g,1-x)}(function(){let u=new D,g=new D,x=new D,_=new D,v=new _e,S=new _e,E=new _e;for(let w=0,R=0;w<s.length;w+=9,R+=6){u.set(s[w+0],s[w+1],s[w+2]),g.set(s[w+3],s[w+4],s[w+5]),x.set(s[w+6],s[w+7],s[w+8]),v.set(a[R+0],a[R+1]),S.set(a[R+2],a[R+3]),E.set(a[R+4],a[R+5]),_.copy(u).add(g).add(x).divideScalar(3);let z=p(_);h(v,R+0,u,z),h(S,R+2,g,z),h(E,R+4,x,z)}})(),(function(){for(let u=0;u<a.length;u+=6){let g=a[u+0],x=a[u+2],_=a[u+4],v=Math.max(g,x,_),S=Math.min(g,x,_);v>.9&&S<.1&&(g<.2&&(a[u+0]+=1),x<.2&&(a[u+2]+=1),_<.2&&(a[u+4]+=1))}})()})(),this.setAttribute("position",new Xe(s,3)),this.setAttribute("normal",new Xe(s.slice(),3)),this.setAttribute("uv",new Xe(a,2)),i===0?this.computeVertexNormals():this.normalizeNormals()}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.vertices,e.indices,e.radius,e.detail)}},Vo=class r extends qi{constructor(e=1,t=0){let n=(1+Math.sqrt(5))/2,i=1/n;super([-1,-1,-1,-1,-1,1,-1,1,-1,-1,1,1,1,-1,-1,1,-1,1,1,1,-1,1,1,1,0,-i,-n,0,-i,n,0,i,-n,0,i,n,-i,-n,0,-i,n,0,i,-n,0,i,n,0,-n,0,-i,n,0,-i,-n,0,i,n,0,i],[3,11,7,3,7,15,3,15,13,7,19,17,7,17,6,7,6,15,17,4,8,17,8,10,17,10,6,8,0,16,8,16,2,8,2,10,0,12,1,0,1,18,0,18,16,6,10,2,6,2,13,6,13,15,2,16,18,2,18,3,2,3,13,18,1,9,18,9,11,18,11,3,4,14,12,4,12,0,4,0,8,11,9,5,11,5,19,11,19,7,19,5,14,19,14,4,19,4,17,1,12,14,1,14,5,1,5,9],e,t),this.type="DodecahedronGeometry",this.parameters={radius:e,detail:t}}static fromJSON(e){return new r(e.radius,e.detail)}},_o=new D,vo=new D,Ic=new D,yo=new Ai,Go=class extends bt{constructor(e=null,t=1){if(super(),this.type="EdgesGeometry",this.parameters={geometry:e,thresholdAngle:t},e!==null){let i=Math.pow(10,4),s=Math.cos(qr*t),a=e.getIndex(),o=e.getAttribute("position"),c=a?a.count:o.count,l=[0,0,0],h=["a","b","c"],p=new Array(3),f={},m=[];for(let u=0;u<c;u+=3){a?(l[0]=a.getX(u),l[1]=a.getX(u+1),l[2]=a.getX(u+2)):(l[0]=u,l[1]=u+1,l[2]=u+2);let{a:g,b:x,c:_}=yo;if(g.fromBufferAttribute(o,l[0]),x.fromBufferAttribute(o,l[1]),_.fromBufferAttribute(o,l[2]),yo.getNormal(Ic),p[0]=`${Math.round(g.x*i)},${Math.round(g.y*i)},${Math.round(g.z*i)}`,p[1]=`${Math.round(x.x*i)},${Math.round(x.y*i)},${Math.round(x.z*i)}`,p[2]=`${Math.round(_.x*i)},${Math.round(_.y*i)},${Math.round(_.z*i)}`,p[0]!==p[1]&&p[1]!==p[2]&&p[2]!==p[0])for(let v=0;v<3;v++){let S=(v+1)%3,E=p[v],w=p[S],R=yo[h[v]],z=yo[h[S]],j=`${E}_${w}`,O=`${w}_${E}`;O in f&&f[O]?(Ic.dot(f[O].normal)<=s&&(m.push(R.x,R.y,R.z),m.push(z.x,z.y,z.z)),f[O]=null):j in f||(f[j]={index0:l[v],index1:l[S],normal:Ic.clone()})}}for(let u in f)if(f[u]){let{index0:g,index1:x}=f[u];_o.fromBufferAttribute(o,g),vo.fromBufferAttribute(o,x),m.push(_o.x,_o.y,_o.z),m.push(vo.x,vo.y,vo.z)}this.setAttribute("position",new Xe(m,3))}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}},On=class{constructor(){this.type="Curve",this.arcLengthDivisions=200,this.needsUpdate=!1,this.cacheArcLengths=null}getPoint(){Ye("Curve: .getPoint() not implemented.")}getPointAt(e,t){let n=this.getUtoTmapping(e);return this.getPoint(n,t)}getPoints(e=5){let t=[];for(let n=0;n<=e;n++)t.push(this.getPoint(n/e));return t}getSpacedPoints(e=5){let t=[];for(let n=0;n<=e;n++)t.push(this.getPointAt(n/e));return t}getLength(){let e=this.getLengths();return e[e.length-1]}getLengths(e=this.arcLengthDivisions){if(this.cacheArcLengths&&this.cacheArcLengths.length===e+1&&!this.needsUpdate)return this.cacheArcLengths;this.needsUpdate=!1;let t=[],n,i=this.getPoint(0),s=0;t.push(0);for(let a=1;a<=e;a++)n=this.getPoint(a/e),s+=n.distanceTo(i),t.push(s),i=n;return this.cacheArcLengths=t,t}updateArcLengths(){this.needsUpdate=!0,this.getLengths()}getUtoTmapping(e,t=null){let n=this.getLengths(),i=0,s=n.length,a;a=t||e*n[s-1];let o,c=0,l=s-1;for(;c<=l;)if(i=Math.floor(c+(l-c)/2),o=n[i]-a,o<0)c=i+1;else{if(!(o>0)){l=i;break}l=i-1}if(i=l,n[i]===a)return i/(s-1);let h=n[i];return(i+(a-h)/(n[i+1]-h))/(s-1)}getTangent(e,t){let i=e-1e-4,s=e+1e-4;i<0&&(i=0),s>1&&(s=1);let a=this.getPoint(i),o=this.getPoint(s),c=t||(a.isVector2?new _e:new D);return c.copy(o).sub(a).normalize(),c}getTangentAt(e,t){let n=this.getUtoTmapping(e);return this.getTangent(n,t)}computeFrenetFrames(e,t=!1){let n=new D,i=[],s=[],a=[],o=new D,c=new Ke;for(let m=0;m<=e;m++){let u=m/e;i[m]=this.getTangentAt(u,new D)}s[0]=new D,a[0]=new D;let l=Number.MAX_VALUE,h=Math.abs(i[0].x),p=Math.abs(i[0].y),f=Math.abs(i[0].z);h<=l&&(l=h,n.set(1,0,0)),p<=l&&(l=p,n.set(0,1,0)),f<=l&&n.set(0,0,1),o.crossVectors(i[0],n).normalize(),s[0].crossVectors(i[0],o),a[0].crossVectors(i[0],s[0]);for(let m=1;m<=e;m++){if(s[m]=s[m-1].clone(),a[m]=a[m-1].clone(),o.crossVectors(i[m-1],i[m]),o.length()>Number.EPSILON){o.normalize();let u=Math.acos(nt(i[m-1].dot(i[m]),-1,1));s[m].applyMatrix4(c.makeRotationAxis(o,u))}a[m].crossVectors(i[m],s[m])}if(t===!0){let m=Math.acos(nt(s[0].dot(s[e]),-1,1));m/=e,i[0].dot(o.crossVectors(s[0],s[e]))>0&&(m=-m);for(let u=1;u<=e;u++)s[u].applyMatrix4(c.makeRotationAxis(i[u],m*u)),a[u].crossVectors(i[u],s[u])}return{tangents:i,normals:s,binormals:a}}clone(){return new this.constructor().copy(this)}copy(e){return this.arcLengthDivisions=e.arcLengthDivisions,this}toJSON(){let e={metadata:{version:4.7,type:"Curve",generator:"Curve.toJSON"}};return e.arcLengthDivisions=this.arcLengthDivisions,e.type=this.type,e}fromJSON(e){return this.arcLengthDivisions=e.arcLengthDivisions,this}},is=class extends On{constructor(e=0,t=0,n=1,i=1,s=0,a=2*Math.PI,o=!1,c=0){super(),this.isEllipseCurve=!0,this.type="EllipseCurve",this.aX=e,this.aY=t,this.xRadius=n,this.yRadius=i,this.aStartAngle=s,this.aEndAngle=a,this.aClockwise=o,this.aRotation=c}getPoint(e,t=new _e){let n=t,i=2*Math.PI,s=this.aEndAngle-this.aStartAngle,a=Math.abs(s)<Number.EPSILON;for(;s<0;)s+=i;for(;s>i;)s-=i;s<Number.EPSILON&&(s=a?0:i),this.aClockwise!==!0||a||(s===i?s=-i:s-=i);let o=this.aStartAngle+e*s,c=this.aX+this.xRadius*Math.cos(o),l=this.aY+this.yRadius*Math.sin(o);if(this.aRotation!==0){let h=Math.cos(this.aRotation),p=Math.sin(this.aRotation),f=c-this.aX,m=l-this.aY;c=f*h-m*p+this.aX,l=f*p+m*h+this.aY}return n.set(c,l)}copy(e){return super.copy(e),this.aX=e.aX,this.aY=e.aY,this.xRadius=e.xRadius,this.yRadius=e.yRadius,this.aStartAngle=e.aStartAngle,this.aEndAngle=e.aEndAngle,this.aClockwise=e.aClockwise,this.aRotation=e.aRotation,this}toJSON(){let e=super.toJSON();return e.aX=this.aX,e.aY=this.aY,e.xRadius=this.xRadius,e.yRadius=this.yRadius,e.aStartAngle=this.aStartAngle,e.aEndAngle=this.aEndAngle,e.aClockwise=this.aClockwise,e.aRotation=this.aRotation,e}fromJSON(e){return super.fromJSON(e),this.aX=e.aX,this.aY=e.aY,this.xRadius=e.xRadius,this.yRadius=e.yRadius,this.aStartAngle=e.aStartAngle,this.aEndAngle=e.aEndAngle,this.aClockwise=e.aClockwise,this.aRotation=e.aRotation,this}},Ho=class extends is{constructor(e,t,n,i,s,a){super(e,t,n,n,i,s,a),this.isArcCurve=!0,this.type="ArcCurve"}};function tu(){let r=0,e=0,t=0,n=0;function i(s,a,o,c){r=s,e=o,t=-3*s+3*a-2*o-c,n=2*s-2*a+o+c}return{initCatmullRom:function(s,a,o,c,l){i(a,o,l*(o-s),l*(c-a))},initNonuniformCatmullRom:function(s,a,o,c,l,h,p){let f=(a-s)/l-(o-s)/(l+h)+(o-a)/h,m=(o-a)/h-(c-a)/(h+p)+(c-o)/p;f*=h,m*=h,i(a,o,f,m)},calc:function(s){let a=s*s;return r+e*s+t*a+n*(a*s)}}}var xo=new D,Lc=new tu,Dc=new tu,Uc=new tu,dr=class extends On{constructor(e=[],t=!1,n="centripetal",i=.5){super(),this.isCatmullRomCurve3=!0,this.type="CatmullRomCurve3",this.points=e,this.closed=t,this.curveType=n,this.tension=i}getPoint(e,t=new D){let n=t,i=this.points,s=i.length,a=(s-(this.closed?0:1))*e,o,c,l=Math.floor(a),h=a-l;this.closed?l+=l>0?0:(Math.floor(Math.abs(l)/s)+1)*s:h===0&&l===s-1&&(l=s-2,h=1),this.closed||l>0?o=i[(l-1)%s]:(xo.subVectors(i[0],i[1]).add(i[0]),o=xo);let p=i[l%s],f=i[(l+1)%s];if(this.closed||l+2<s?c=i[(l+2)%s]:(xo.subVectors(i[s-1],i[s-2]).add(i[s-1]),c=xo),this.curveType==="centripetal"||this.curveType==="chordal"){let m=this.curveType==="chordal"?.5:.25,u=Math.pow(o.distanceToSquared(p),m),g=Math.pow(p.distanceToSquared(f),m),x=Math.pow(f.distanceToSquared(c),m);g<1e-4&&(g=1),u<1e-4&&(u=g),x<1e-4&&(x=g),Lc.initNonuniformCatmullRom(o.x,p.x,f.x,c.x,u,g,x),Dc.initNonuniformCatmullRom(o.y,p.y,f.y,c.y,u,g,x),Uc.initNonuniformCatmullRom(o.z,p.z,f.z,c.z,u,g,x)}else this.curveType==="catmullrom"&&(Lc.initCatmullRom(o.x,p.x,f.x,c.x,this.tension),Dc.initCatmullRom(o.y,p.y,f.y,c.y,this.tension),Uc.initCatmullRom(o.z,p.z,f.z,c.z,this.tension));return n.set(Lc.calc(h),Dc.calc(h),Uc.calc(h)),n}copy(e){super.copy(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let i=e.points[t];this.points.push(i.clone())}return this.closed=e.closed,this.curveType=e.curveType,this.tension=e.tension,this}toJSON(){let e=super.toJSON();e.points=[];for(let t=0,n=this.points.length;t<n;t++){let i=this.points[t];e.points.push(i.toArray())}return e.closed=this.closed,e.curveType=this.curveType,e.tension=this.tension,e}fromJSON(e){super.fromJSON(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let i=e.points[t];this.points.push(new D().fromArray(i))}return this.closed=e.closed,this.curveType=e.curveType,this.tension=e.tension,this}};function md(r,e,t,n,i){let s=.5*(n-e),a=.5*(i-t),o=r*r;return(2*t-2*n+s+a)*(r*o)+(-3*t+3*n-2*s-a)*o+s*r+t}function js(r,e,t,n){return(function(i,s){let a=1-i;return a*a*s})(r,e)+(function(i,s){return 2*(1-i)*i*s})(r,t)+(function(i,s){return i*i*s})(r,n)}function Xs(r,e,t,n,i){return(function(s,a){let o=1-s;return o*o*o*a})(r,e)+(function(s,a){let o=1-s;return 3*o*o*s*a})(r,t)+(function(s,a){return 3*(1-s)*s*s*a})(r,n)+(function(s,a){return s*s*s*a})(r,i)}var oa=class extends On{constructor(e=new _e,t=new _e,n=new _e,i=new _e){super(),this.isCubicBezierCurve=!0,this.type="CubicBezierCurve",this.v0=e,this.v1=t,this.v2=n,this.v3=i}getPoint(e,t=new _e){let n=t,i=this.v0,s=this.v1,a=this.v2,o=this.v3;return n.set(Xs(e,i.x,s.x,a.x,o.x),Xs(e,i.y,s.y,a.y,o.y)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this.v3.copy(e.v3),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e.v3=this.v3.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this.v3.fromArray(e.v3),this}},Wo=class extends On{constructor(e=new D,t=new D,n=new D,i=new D){super(),this.isCubicBezierCurve3=!0,this.type="CubicBezierCurve3",this.v0=e,this.v1=t,this.v2=n,this.v3=i}getPoint(e,t=new D){let n=t,i=this.v0,s=this.v1,a=this.v2,o=this.v3;return n.set(Xs(e,i.x,s.x,a.x,o.x),Xs(e,i.y,s.y,a.y,o.y),Xs(e,i.z,s.z,a.z,o.z)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this.v3.copy(e.v3),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e.v3=this.v3.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this.v3.fromArray(e.v3),this}},la=class extends On{constructor(e=new _e,t=new _e){super(),this.isLineCurve=!0,this.type="LineCurve",this.v1=e,this.v2=t}getPoint(e,t=new _e){let n=t;return e===1?n.copy(this.v2):(n.copy(this.v2).sub(this.v1),n.multiplyScalar(e).add(this.v1)),n}getPointAt(e,t){return this.getPoint(e,t)}getTangent(e,t=new _e){return t.subVectors(this.v2,this.v1).normalize()}getTangentAt(e,t){return this.getTangent(e,t)}copy(e){return super.copy(e),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},jo=class extends On{constructor(e=new D,t=new D){super(),this.isLineCurve3=!0,this.type="LineCurve3",this.v1=e,this.v2=t}getPoint(e,t=new D){let n=t;return e===1?n.copy(this.v2):(n.copy(this.v2).sub(this.v1),n.multiplyScalar(e).add(this.v1)),n}getPointAt(e,t){return this.getPoint(e,t)}getTangent(e,t=new D){return t.subVectors(this.v2,this.v1).normalize()}getTangentAt(e,t){return this.getTangent(e,t)}copy(e){return super.copy(e),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},ca=class extends On{constructor(e=new _e,t=new _e,n=new _e){super(),this.isQuadraticBezierCurve=!0,this.type="QuadraticBezierCurve",this.v0=e,this.v1=t,this.v2=n}getPoint(e,t=new _e){let n=t,i=this.v0,s=this.v1,a=this.v2;return n.set(js(e,i.x,s.x,a.x),js(e,i.y,s.y,a.y)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},ha=class extends On{constructor(e=new D,t=new D,n=new D){super(),this.isQuadraticBezierCurve3=!0,this.type="QuadraticBezierCurve3",this.v0=e,this.v1=t,this.v2=n}getPoint(e,t=new D){let n=t,i=this.v0,s=this.v1,a=this.v2;return n.set(js(e,i.x,s.x,a.x),js(e,i.y,s.y,a.y),js(e,i.z,s.z,a.z)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},ua=class extends On{constructor(e=[]){super(),this.isSplineCurve=!0,this.type="SplineCurve",this.points=e}getPoint(e,t=new _e){let n=t,i=this.points,s=(i.length-1)*e,a=Math.floor(s),o=s-a,c=i[a===0?a:a-1],l=i[a],h=i[a>i.length-2?i.length-1:a+1],p=i[a>i.length-3?i.length-1:a+2];return n.set(md(o,c.x,l.x,h.x,p.x),md(o,c.y,l.y,h.y,p.y)),n}copy(e){super.copy(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let i=e.points[t];this.points.push(i.clone())}return this}toJSON(){let e=super.toJSON();e.points=[];for(let t=0,n=this.points.length;t<n;t++){let i=this.points[t];e.points.push(i.toArray())}return e}fromJSON(e){super.fromJSON(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let i=e.points[t];this.points.push(new _e().fromArray(i))}return this}},Xo=Object.freeze({__proto__:null,ArcCurve:Ho,CatmullRomCurve3:dr,CubicBezierCurve:oa,CubicBezierCurve3:Wo,EllipseCurve:is,LineCurve:la,LineCurve3:jo,QuadraticBezierCurve:ca,QuadraticBezierCurve3:ha,SplineCurve:ua}),qo=class extends On{constructor(){super(),this.type="CurvePath",this.curves=[],this.autoClose=!1}add(e){this.curves.push(e)}closePath(){let e=this.curves[0].getPoint(0),t=this.curves[this.curves.length-1].getPoint(1);if(!e.equals(t)){let n=e.isVector2===!0?"LineCurve":"LineCurve3";this.curves.push(new Xo[n](t,e))}return this}getPoint(e,t){let n=e*this.getLength(),i=this.getCurveLengths(),s=0;for(;s<i.length;){if(i[s]>=n){let a=i[s]-n,o=this.curves[s],c=o.getLength(),l=c===0?0:1-a/c;return o.getPointAt(l,t)}s++}return null}getLength(){let e=this.getCurveLengths();return e[e.length-1]}updateArcLengths(){this.needsUpdate=!0,this.cacheLengths=null,this.getCurveLengths()}getCurveLengths(){if(this.cacheLengths&&this.cacheLengths.length===this.curves.length)return this.cacheLengths;let e=[],t=0;for(let n=0,i=this.curves.length;n<i;n++)t+=this.curves[n].getLength(),e.push(t);return this.cacheLengths=e,e}getSpacedPoints(e=40){let t=[];for(let n=0;n<=e;n++)t.push(this.getPoint(n/e));return this.autoClose&&t.push(t[0]),t}getPoints(e=12){let t=[],n;for(let i=0,s=this.curves;i<s.length;i++){let a=s[i],o=a.isEllipseCurve?2*e:a.isLineCurve||a.isLineCurve3?1:a.isSplineCurve?e*a.points.length:e,c=a.getPoints(o);for(let l=0;l<c.length;l++){let h=c[l];n&&n.equals(h)||(t.push(h),n=h)}}return this.autoClose&&t.length>1&&!t[t.length-1].equals(t[0])&&t.push(t[0]),t}copy(e){super.copy(e),this.curves=[];for(let t=0,n=e.curves.length;t<n;t++){let i=e.curves[t];this.curves.push(i.clone())}return this.autoClose=e.autoClose,this}toJSON(){let e=super.toJSON();e.autoClose=this.autoClose,e.curves=[];for(let t=0,n=this.curves.length;t<n;t++){let i=this.curves[t];e.curves.push(i.toJSON())}return e}fromJSON(e){super.fromJSON(e),this.autoClose=e.autoClose,this.curves=[];for(let t=0,n=e.curves.length;t<n;t++){let i=e.curves[t];this.curves.push(new Xo[i.type]().fromJSON(i))}return this}},da=class extends qo{constructor(e){super(),this.type="Path",this.currentPoint=new _e,e&&this.setFromPoints(e)}setFromPoints(e){this.moveTo(e[0].x,e[0].y);for(let t=1,n=e.length;t<n;t++)this.lineTo(e[t].x,e[t].y);return this}moveTo(e,t){return this.currentPoint.set(e,t),this}lineTo(e,t){let n=new la(this.currentPoint.clone(),new _e(e,t));return this.curves.push(n),this.currentPoint.set(e,t),this}quadraticCurveTo(e,t,n,i){let s=new ca(this.currentPoint.clone(),new _e(e,t),new _e(n,i));return this.curves.push(s),this.currentPoint.set(n,i),this}bezierCurveTo(e,t,n,i,s,a){let o=new oa(this.currentPoint.clone(),new _e(e,t),new _e(n,i),new _e(s,a));return this.curves.push(o),this.currentPoint.set(s,a),this}splineThru(e){let t=[this.currentPoint.clone()].concat(e),n=new ua(t);return this.curves.push(n),this.currentPoint.copy(e[e.length-1]),this}arc(e,t,n,i,s,a){let o=this.currentPoint.x,c=this.currentPoint.y;return this.absarc(e+o,t+c,n,i,s,a),this}absarc(e,t,n,i,s,a){return this.absellipse(e,t,n,n,i,s,a),this}ellipse(e,t,n,i,s,a,o,c){let l=this.currentPoint.x,h=this.currentPoint.y;return this.absellipse(e+l,t+h,n,i,s,a,o,c),this}absellipse(e,t,n,i,s,a,o,c){let l=new is(e,t,n,i,s,a,o,c);if(this.curves.length>0){let p=l.getPoint(0);p.equals(this.currentPoint)||this.lineTo(p.x,p.y)}this.curves.push(l);let h=l.getPoint(1);return this.currentPoint.copy(h),this}copy(e){return super.copy(e),this.currentPoint.copy(e.currentPoint),this}toJSON(){let e=super.toJSON();return e.currentPoint=this.currentPoint.toArray(),e}fromJSON(e){return super.fromJSON(e),this.currentPoint.fromArray(e.currentPoint),this}},pa=class extends da{constructor(e){super(e),this.uuid=vr(),this.type="Shape",this.holes=[]}getPointsHoles(e){let t=[];for(let n=0,i=this.holes.length;n<i;n++)t[n]=this.holes[n].getPoints(e);return t}extractPoints(e){return{shape:this.getPoints(e),holes:this.getPointsHoles(e)}}copy(e){super.copy(e),this.holes=[];for(let t=0,n=e.holes.length;t<n;t++){let i=e.holes[t];this.holes.push(i.clone())}return this}toJSON(){let e=super.toJSON();e.uuid=this.uuid,e.holes=[];for(let t=0,n=this.holes.length;t<n;t++){let i=this.holes[t];e.holes.push(i.toJSON())}return e}fromJSON(e){super.fromJSON(e),this.uuid=e.uuid,this.holes=[];for(let t=0,n=e.holes.length;t<n;t++){let i=e.holes[t];this.holes.push(new da().fromJSON(i))}return this}};function Hf(r,e,t=2){let n=e&&e.length,i=n?e[0]*t:r.length,s=gd(r,0,i,t,!0),a=[];if(!s||s.next===s.prev)return a;let o,c,l;if(n&&(s=(function(h,p,f,m){let u=[];for(let g=0,x=p.length;g<x;g++){let _=gd(h,p[g]*m,g<x-1?p[g+1]*m:h.length,m,!1);_===_.next&&(_.steiner=!0),u.push(Kf(_))}u.sort(Yf);for(let g=0;g<u.length;g++)f=Zf(u[g],f);return f})(r,e,s,t)),r.length>80*t){o=r[0],c=r[1];let h=o,p=c;for(let f=t;f<i;f+=t){let m=r[f],u=r[f+1];m<o&&(o=m),u<c&&(c=u),m>h&&(h=m),u>p&&(p=u)}l=Math.max(h-o,p-c),l=l!==0?32767/l:0}return fa(s,a,t,o,c,l,0),a}function gd(r,e,t,n,i){let s;if(i===(function(a,o,c,l){let h=0;for(let p=o,f=c-l;p<c;p+=l)h+=(a[f]-a[p])*(a[p+1]+a[f+1]),f=p;return h})(r,e,t,n)>0)for(let a=e;a<t;a+=n)s=_d(a/n|0,r[a],r[a+1],s);else for(let a=t-n;a>=e;a-=n)s=_d(a/n|0,r[a],r[a+1],s);return s&&rs(s,s.next)&&(ga(s),s=s.next),s}function pr(r,e){if(!r)return r;e||(e=r);let t,n=r;do if(t=!1,n.steiner||!rs(n,n.next)&&Rt(n.prev,n,n.next)!==0)n=n.next;else{if(ga(n),n=e=n.prev,n===n.next)break;t=!0}while(t||n!==e);return e}function fa(r,e,t,n,i,s,a){if(!r)return;!a&&s&&(function(c,l,h,p){let f=c;do f.z===0&&(f.z=Wc(f.x,f.y,l,h,p)),f.prevZ=f.prev,f.nextZ=f.next,f=f.next;while(f!==c);f.prevZ.nextZ=null,f.prevZ=null,(function(m){let u,g=1;do{let x,_=m;m=null;let v=null;for(u=0;_;){u++;let S=_,E=0;for(let R=0;R<g&&(E++,S=S.nextZ,S);R++);let w=g;for(;E>0||w>0&&S;)E!==0&&(w===0||!S||_.z<=S.z)?(x=_,_=_.nextZ,E--):(x=S,S=S.nextZ,w--),v?v.nextZ=x:m=x,x.prevZ=v,v=x;_=S}v.nextZ=null,g*=2}while(u>1)})(f)})(r,n,i,s);let o=r;for(;r.prev!==r.next;){let c=r.prev,l=r.next;if(s?jf(r,n,i,s):Wf(r))e.push(c.i,r.i,l.i),ga(r),r=l.next,o=l.next;else if((r=l)===o){a?a===1?fa(r=Xf(pr(r),e),e,t,n,i,s,2):a===2&&qf(r,e,t,n,i,s):fa(pr(r),e,t,n,i,s,1);break}}}function Wf(r){let e=r.prev,t=r,n=r.next;if(Rt(e,t,n)>=0)return!1;let i=e.x,s=t.x,a=n.x,o=e.y,c=t.y,l=n.y,h=Math.min(i,s,a),p=Math.min(o,c,l),f=Math.max(i,s,a),m=Math.max(o,c,l),u=n.next;for(;u!==e;){if(u.x>=h&&u.x<=f&&u.y>=p&&u.y<=m&&Hs(i,o,s,c,a,l,u.x,u.y)&&Rt(u.prev,u,u.next)>=0)return!1;u=u.next}return!0}function jf(r,e,t,n){let i=r.prev,s=r,a=r.next;if(Rt(i,s,a)>=0)return!1;let o=i.x,c=s.x,l=a.x,h=i.y,p=s.y,f=a.y,m=Math.min(o,c,l),u=Math.min(h,p,f),g=Math.max(o,c,l),x=Math.max(h,p,f),_=Wc(m,u,e,t,n),v=Wc(g,x,e,t,n),S=r.prevZ,E=r.nextZ;for(;S&&S.z>=_&&E&&E.z<=v;){if(S.x>=m&&S.x<=g&&S.y>=u&&S.y<=x&&S!==i&&S!==a&&Hs(o,h,c,p,l,f,S.x,S.y)&&Rt(S.prev,S,S.next)>=0||(S=S.prevZ,E.x>=m&&E.x<=g&&E.y>=u&&E.y<=x&&E!==i&&E!==a&&Hs(o,h,c,p,l,f,E.x,E.y)&&Rt(E.prev,E,E.next)>=0))return!1;E=E.nextZ}for(;S&&S.z>=_;){if(S.x>=m&&S.x<=g&&S.y>=u&&S.y<=x&&S!==i&&S!==a&&Hs(o,h,c,p,l,f,S.x,S.y)&&Rt(S.prev,S,S.next)>=0)return!1;S=S.prevZ}for(;E&&E.z<=v;){if(E.x>=m&&E.x<=g&&E.y>=u&&E.y<=x&&E!==i&&E!==a&&Hs(o,h,c,p,l,f,E.x,E.y)&&Rt(E.prev,E,E.next)>=0)return!1;E=E.nextZ}return!0}function Xf(r,e){let t=r;do{let n=t.prev,i=t.next.next;!rs(n,i)&&gp(n,t,t.next,i)&&ma(n,i)&&ma(i,n)&&(e.push(n.i,t.i,i.i),ga(t),ga(t.next),t=r=i),t=t.next}while(t!==r);return pr(t)}function qf(r,e,t,n,i,s){let a=r;do{let o=a.next.next;for(;o!==a.prev;){if(a.i!==o.i&&$f(a,o)){let c=_p(a,o);return a=pr(a,a.next),c=pr(c,c.next),fa(a,e,t,n,i,s,0),void fa(c,e,t,n,i,s,0)}o=o.next}a=a.next}while(a!==r)}function Yf(r,e){let t=r.x-e.x;return t===0&&(t=r.y-e.y,t===0)&&(t=(r.next.y-r.y)/(r.next.x-r.x)-(e.next.y-e.y)/(e.next.x-e.x)),t}function Zf(r,e){let t=(function(i,s){let a=s,o=i.x,c=i.y,l,h=-1/0;if(rs(i,a))return a;do{if(rs(i,a.next))return a.next;if(c<=a.y&&c>=a.next.y&&a.next.y!==a.y){let g=a.x+(c-a.y)*(a.next.x-a.x)/(a.next.y-a.y);if(g<=o&&g>h&&(h=g,l=a.x<a.next.x?a:a.next,g===o))return l}a=a.next}while(a!==s);if(!l)return null;let p=l,f=l.x,m=l.y,u=1/0;a=l;do{if(o>=a.x&&a.x>=f&&o!==a.x&&mp(c<m?o:h,c,f,m,c<m?h:o,c,a.x,a.y)){let g=Math.abs(c-a.y)/(o-a.x);ma(a,i)&&(g<u||g===u&&(a.x>l.x||a.x===l.x&&Jf(l,a)))&&(l=a,u=g)}a=a.next}while(a!==p);return l})(r,e);if(!t)return e;let n=_p(t,r);return pr(n,n.next),pr(t,t.next)}function Jf(r,e){return Rt(r.prev,r,e.prev)<0&&Rt(e.next,r,r.next)<0}function Wc(r,e,t,n,i){return(r=1431655765&((r=858993459&((r=252645135&((r=16711935&((r=(r-t)*i|0)|r<<8))|r<<4))|r<<2))|r<<1))|(e=1431655765&((e=858993459&((e=252645135&((e=16711935&((e=(e-n)*i|0)|e<<8))|e<<4))|e<<2))|e<<1))<<1}function Kf(r){let e=r,t=r;do(e.x<t.x||e.x===t.x&&e.y<t.y)&&(t=e),e=e.next;while(e!==r);return t}function mp(r,e,t,n,i,s,a,o){return(i-a)*(e-o)>=(r-a)*(s-o)&&(r-a)*(n-o)>=(t-a)*(e-o)&&(t-a)*(s-o)>=(i-a)*(n-o)}function Hs(r,e,t,n,i,s,a,o){return!(r===a&&e===o)&&mp(r,e,t,n,i,s,a,o)}function $f(r,e){return r.next.i!==e.i&&r.prev.i!==e.i&&!(function(t,n){let i=t;do{if(i.i!==t.i&&i.next.i!==t.i&&i.i!==n.i&&i.next.i!==n.i&&gp(i,i.next,t,n))return!0;i=i.next}while(i!==t);return!1})(r,e)&&(ma(r,e)&&ma(e,r)&&(function(t,n){let i=t,s=!1,a=(t.x+n.x)/2,o=(t.y+n.y)/2;do i.y>o!=i.next.y>o&&i.next.y!==i.y&&a<(i.next.x-i.x)*(o-i.y)/(i.next.y-i.y)+i.x&&(s=!s),i=i.next;while(i!==t);return s})(r,e)&&(Rt(r.prev,r,e.prev)||Rt(r,e.prev,e))||rs(r,e)&&Rt(r.prev,r,r.next)>0&&Rt(e.prev,e,e.next)>0)}function Rt(r,e,t){return(e.y-r.y)*(t.x-e.x)-(e.x-r.x)*(t.y-e.y)}function rs(r,e){return r.x===e.x&&r.y===e.y}function gp(r,e,t,n){let i=bo(Rt(r,e,t)),s=bo(Rt(r,e,n)),a=bo(Rt(t,n,r)),o=bo(Rt(t,n,e));return i!==s&&a!==o||!(i!==0||!Mo(r,t,e))||!(s!==0||!Mo(r,n,e))||!(a!==0||!Mo(t,r,n))||!(o!==0||!Mo(t,e,n))}function Mo(r,e,t){return e.x<=Math.max(r.x,t.x)&&e.x>=Math.min(r.x,t.x)&&e.y<=Math.max(r.y,t.y)&&e.y>=Math.min(r.y,t.y)}function bo(r){return r>0?1:r<0?-1:0}function ma(r,e){return Rt(r.prev,r,r.next)<0?Rt(r,e,r.next)>=0&&Rt(r,r.prev,e)>=0:Rt(r,e,r.prev)<0||Rt(r,r.next,e)<0}function _p(r,e){let t=jc(r.i,r.x,r.y),n=jc(e.i,e.x,e.y),i=r.next,s=e.prev;return r.next=e,e.prev=r,t.next=i,i.prev=t,n.next=t,t.prev=n,s.next=n,n.prev=s,n}function _d(r,e,t,n){let i=jc(r,e,t);return n?(i.next=n.next,i.prev=n,n.next.prev=i,n.next=i):(i.prev=i,i.next=i),i}function ga(r){r.next.prev=r.prev,r.prev.next=r.next,r.prevZ&&(r.prevZ.nextZ=r.nextZ),r.nextZ&&(r.nextZ.prevZ=r.prevZ)}function jc(r,e,t){return{i:r,x:e,y:t,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}var Xc=class{static triangulate(e,t,n=2){return Hf(e,t,n)}},di=class r{static area(e){let t=e.length,n=0;for(let i=t-1,s=0;s<t;i=s++)n+=e[i].x*e[s].y-e[s].x*e[i].y;return .5*n}static isClockWise(e){return r.area(e)<0}static triangulateShape(e,t){let n=[],i=[],s=[];vd(e),yd(n,e);let a=e.length;t.forEach(vd);for(let c=0;c<t.length;c++)i.push(a),a+=t[c].length,yd(n,t[c]);let o=Xc.triangulate(n,i);for(let c=0;c<o.length;c+=3)s.push(o.slice(c,c+3));return s}};function vd(r){let e=r.length;e>2&&r[e-1].equals(r[0])&&r.pop()}function yd(r,e){for(let t=0;t<e.length;t++)r.push(e[t].x),r.push(e[t].y)}var Yo=class r extends bt{constructor(e=new pa([new _e(.5,.5),new _e(-.5,.5),new _e(-.5,-.5),new _e(.5,-.5)]),t={}){super(),this.type="ExtrudeGeometry",this.parameters={shapes:e,options:t},e=Array.isArray(e)?e:[e];let n=this,i=[],s=[];for(let o=0,c=e.length;o<c;o++)a(e[o]);function a(o){let c=[],l=t.curveSegments!==void 0?t.curveSegments:12,h=t.steps!==void 0?t.steps:1,p=t.depth!==void 0?t.depth:1,f=t.bevelEnabled===void 0||t.bevelEnabled,m=t.bevelThickness!==void 0?t.bevelThickness:.2,u=t.bevelSize!==void 0?t.bevelSize:m-.1,g=t.bevelOffset!==void 0?t.bevelOffset:0,x=t.bevelSegments!==void 0?t.bevelSegments:3,_=t.extrudePath,v=t.UVGenerator!==void 0?t.UVGenerator:Qf,S,E,w,R,z,j=!1;if(_){S=_.getSpacedPoints(h),j=!0,f=!1;let G=!!_.isCatmullRomCurve3&&_.closed;E=_.computeFrenetFrames(h,G),w=new D,R=new D,z=new D}f||(x=0,m=0,u=0,g=0);let O=o.extractPoints(l),Q=O.shape,Y=O.holes;if(!di.isClockWise(Q)){Q=Q.reverse();for(let G=0,T=Y.length;G<T;G++){let N=Y[G];di.isClockWise(N)&&(Y[G]=N.reverse())}}function k(G){let T=10000000000000001e-36,N=G[0];for(let B=1;B<=G.length;B++){let P=B%G.length,V=G[P],H=V.x-N.x,F=V.y-N.y,$=H*H+F*F,M=Math.max(Math.abs(V.x),Math.abs(V.y),Math.abs(N.x),Math.abs(N.y));$<=T*M*M?(G.splice(P,1),B--):N=V}}k(Q),Y.forEach(k);let X=Y.length,K=Q;for(let G=0;G<X;G++){let T=Y[G];Q=Q.concat(T)}function te(G,T,N){return T||Je("ExtrudeGeometry: vec does not exist"),G.clone().addScaledVector(T,N)}let oe=Q.length;function ee(G,T,N){let B,P,V,H=G.x-T.x,F=G.y-T.y,$=N.x-G.x,M=N.y-G.y,ne=H*H+F*F,le=H*M-F*$;if(Math.abs(le)>Number.EPSILON){let ye=Math.sqrt(ne),Ne=Math.sqrt($*$+M*M),Fe=T.x-F/ye,Oe=T.y+H/ye,ke=((N.x-M/Ne-Fe)*M-(N.y+$/Ne-Oe)*$)/(H*M-F*$);B=Fe+H*ke-G.x,P=Oe+F*ke-G.y;let Pe=B*B+P*P;if(Pe<=2)return new _e(B,P);V=Math.sqrt(Pe/2)}else{let ye=!1;H>Number.EPSILON?$>Number.EPSILON&&(ye=!0):H<-Number.EPSILON?$<-Number.EPSILON&&(ye=!0):Math.sign(F)===Math.sign(M)&&(ye=!0),ye?(B=-F,P=H,V=Math.sqrt(ne)):(B=H,P=F,V=Math.sqrt(ne/2))}return new _e(B/V,P/V)}let xe=[];for(let G=0,T=K.length,N=T-1,B=G+1;G<T;G++,N++,B++)N===T&&(N=0),B===T&&(B=0),xe[G]=ee(K[G],K[N],K[B]);let be=[],we,Se,se=xe.concat();for(let G=0,T=X;G<T;G++){let N=Y[G];we=[];for(let B=0,P=N.length,V=P-1,H=B+1;B<P;B++,V++,H++)V===P&&(V=0),H===P&&(H=0),we[B]=ee(N[B],N[V],N[H]);be.push(we),se=se.concat(we)}if(x===0)Se=di.triangulateShape(K,Y);else{let G=[],T=[];for(let N=0;N<x;N++){let B=N/x,P=m*Math.cos(B*Math.PI/2),V=u*Math.sin(B*Math.PI/2)+g;for(let H=0,F=K.length;H<F;H++){let $=te(K[H],xe[H],V);Re($.x,$.y,-P),B===0&&G.push($)}for(let H=0,F=X;H<F;H++){let $=Y[H];we=be[H];let M=[];for(let ne=0,le=$.length;ne<le;ne++){let ye=te($[ne],we[ne],V);Re(ye.x,ye.y,-P),B===0&&M.push(ye)}B===0&&T.push(M)}}Se=di.triangulateShape(G,T)}let de=Se.length,ge=u+g;for(let G=0;G<oe;G++){let T=f?te(Q[G],se[G],ge):Q[G];j?(R.copy(E.normals[0]).multiplyScalar(T.x),w.copy(E.binormals[0]).multiplyScalar(T.y),z.copy(S[0]).add(R).add(w),Re(z.x,z.y,z.z)):Re(T.x,T.y,0)}for(let G=1;G<=h;G++)for(let T=0;T<oe;T++){let N=f?te(Q[T],se[T],ge):Q[T];j?(R.copy(E.normals[G]).multiplyScalar(N.x),w.copy(E.binormals[G]).multiplyScalar(N.y),z.copy(S[G]).add(R).add(w),Re(z.x,z.y,z.z)):Re(N.x,N.y,p/h*G)}for(let G=x-1;G>=0;G--){let T=G/x,N=m*Math.cos(T*Math.PI/2),B=u*Math.sin(T*Math.PI/2)+g;for(let P=0,V=K.length;P<V;P++){let H=te(K[P],xe[P],B);Re(H.x,H.y,p+N)}for(let P=0,V=Y.length;P<V;P++){let H=Y[P];we=be[P];for(let F=0,$=H.length;F<$;F++){let M=te(H[F],we[F],B);j?Re(M.x,M.y+S[h-1].y,S[h-1].x+N):Re(M.x,M.y,p+N)}}}function Te(G,T){let N=G.length;for(;--N>=0;){let B=N,P=N-1;P<0&&(P=G.length-1);for(let V=0,H=h+2*x;V<H;V++){let F=oe*V,$=oe*(V+1);L(T+B+F,T+P+F,T+P+$,T+B+$)}}}function Re(G,T,N){c.push(G),c.push(T),c.push(N)}function ze(G,T,N){C(G),C(T),C(N);let B=i.length/3,P=v.generateTopUV(n,i,B-3,B-2,B-1);J(P[0]),J(P[1]),J(P[2])}function L(G,T,N,B){C(G),C(T),C(B),C(T),C(N),C(B);let P=i.length/3,V=v.generateSideWallUV(n,i,P-6,P-3,P-2,P-1);J(V[0]),J(V[1]),J(V[3]),J(V[1]),J(V[2]),J(V[3])}function C(G){i.push(c[3*G+0]),i.push(c[3*G+1]),i.push(c[3*G+2])}function J(G){s.push(G.x),s.push(G.y)}(function(){let G=i.length/3;if(f){let T=0,N=oe*T;for(let B=0;B<de;B++){let P=Se[B];ze(P[2]+N,P[1]+N,P[0]+N)}T=h+2*x,N=oe*T;for(let B=0;B<de;B++){let P=Se[B];ze(P[0]+N,P[1]+N,P[2]+N)}}else{for(let T=0;T<de;T++){let N=Se[T];ze(N[2],N[1],N[0])}for(let T=0;T<de;T++){let N=Se[T];ze(N[0]+oe*h,N[1]+oe*h,N[2]+oe*h)}}n.addGroup(G,i.length/3-G,0)})(),(function(){let G=i.length/3,T=0;Te(K,T),T+=K.length;for(let N=0,B=Y.length;N<B;N++){let P=Y[N];Te(P,T),T+=P.length}n.addGroup(G,i.length/3-G,1)})()}this.setAttribute("position",new Xe(i,3)),this.setAttribute("uv",new Xe(s,2)),this.computeVertexNormals()}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){let e=super.toJSON();return(function(t,n,i){if(i.shapes=[],Array.isArray(t))for(let s=0,a=t.length;s<a;s++){let o=t[s];i.shapes.push(o.uuid)}else i.shapes.push(t.uuid);return i.options=Object.assign({},n),n.extrudePath!==void 0&&(i.options.extrudePath=n.extrudePath.toJSON()),i})(this.parameters.shapes,this.parameters.options,e)}static fromJSON(e,t){let n=[];for(let s=0,a=e.shapes.length;s<a;s++){let o=t[e.shapes[s]];n.push(o)}let i=e.options.extrudePath;return i!==void 0&&(e.options.extrudePath=new Xo[i.type]().fromJSON(i)),new r(n,e.options)}},Qf={generateTopUV:function(r,e,t,n,i){let s=e[3*t],a=e[3*t+1],o=e[3*n],c=e[3*n+1],l=e[3*i],h=e[3*i+1];return[new _e(s,a),new _e(o,c),new _e(l,h)]},generateSideWallUV:function(r,e,t,n,i,s){let a=e[3*t],o=e[3*t+1],c=e[3*t+2],l=e[3*n],h=e[3*n+1],p=e[3*n+2],f=e[3*i],m=e[3*i+1],u=e[3*i+2],g=e[3*s],x=e[3*s+1],_=e[3*s+2];return Math.abs(o-h)<Math.abs(a-l)?[new _e(a,1-c),new _e(l,1-p),new _e(f,1-u),new _e(g,1-_)]:[new _e(o,1-c),new _e(h,1-p),new _e(m,1-u),new _e(x,1-_)]}},Zo=class r extends qi{constructor(e=1,t=0){let n=(1+Math.sqrt(5))/2;super([-1,n,0,1,n,0,-1,-n,0,1,-n,0,0,-1,n,0,1,n,0,-1,-n,0,1,-n,n,0,-1,n,0,1,-n,0,-1,-n,0,1],[0,11,5,0,5,1,0,1,7,0,7,10,0,10,11,1,5,9,5,11,4,11,10,2,10,7,6,7,1,8,3,9,4,3,4,2,3,2,6,3,6,8,3,8,9,4,9,5,2,4,11,6,2,10,8,6,7,9,8,1],e,t),this.type="IcosahedronGeometry",this.parameters={radius:e,detail:t}}static fromJSON(e){return new r(e.radius,e.detail)}},Jo=class r extends bt{constructor(e=[new _e(0,-.5),new _e(.5,0),new _e(0,.5)],t=12,n=0,i=2*Math.PI){super(),this.type="LatheGeometry",this.parameters={points:e,segments:t,phiStart:n,phiLength:i},t=Math.floor(t),i=nt(i,0,2*Math.PI);let s=[],a=[],o=[],c=[],l=[],h=1/t,p=new D,f=new _e,m=new D,u=new D,g=new D,x=0,_=0;for(let v=0;v<=e.length-1;v++)switch(v){case 0:x=e[v+1].x-e[v].x,_=e[v+1].y-e[v].y,m.x=1*_,m.y=-x,m.z=0*_,g.copy(m),m.normalize(),c.push(m.x,m.y,m.z);break;case e.length-1:c.push(g.x,g.y,g.z);break;default:x=e[v+1].x-e[v].x,_=e[v+1].y-e[v].y,m.x=1*_,m.y=-x,m.z=0*_,u.copy(m),m.x+=g.x,m.y+=g.y,m.z+=g.z,m.normalize(),c.push(m.x,m.y,m.z),g.copy(u)}for(let v=0;v<=t;v++){let S=n+v*h*i,E=Math.sin(S),w=Math.cos(S);for(let R=0;R<=e.length-1;R++){p.x=e[R].x*E,p.y=e[R].y,p.z=e[R].x*w,a.push(p.x,p.y,p.z),f.x=v/t,f.y=R/(e.length-1),o.push(f.x,f.y);let z=c[3*R+0]*E,j=c[3*R+1],O=c[3*R+0]*w;l.push(z,j,O)}}for(let v=0;v<t;v++)for(let S=0;S<e.length-1;S++){let E=S+v*e.length,w=E,R=E+e.length,z=E+e.length+1,j=E+1;s.push(w,R,j),s.push(z,j,R)}this.setIndex(s),this.setAttribute("position",new Xe(a,3)),this.setAttribute("uv",new Xe(o,2)),this.setAttribute("normal",new Xe(l,3))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.points,e.segments,e.phiStart,e.phiLength)}},Ko=class r extends qi{constructor(e=1,t=0){super([1,0,0,-1,0,0,0,1,0,0,-1,0,0,0,1,0,0,-1],[0,2,4,0,4,3,0,3,5,0,5,2,1,2,5,1,5,3,1,3,4,1,4,2],e,t),this.type="OctahedronGeometry",this.parameters={radius:e,detail:t}}static fromJSON(e){return new r(e.radius,e.detail)}},Fn=class r extends bt{constructor(e=1,t=1,n=1,i=1){super(),this.type="PlaneGeometry",this.parameters={width:e,height:t,widthSegments:n,heightSegments:i};let s=e/2,a=t/2,o=Math.floor(n),c=Math.floor(i),l=o+1,h=c+1,p=e/o,f=t/c,m=[],u=[],g=[],x=[];for(let _=0;_<h;_++){let v=_*f-a;for(let S=0;S<l;S++){let E=S*p-s;u.push(E,-v,0),g.push(0,0,1),x.push(S/o),x.push(1-_/c)}}for(let _=0;_<c;_++)for(let v=0;v<o;v++){let S=v+l*_,E=v+l*(_+1),w=v+1+l*(_+1),R=v+1+l*_;m.push(S,E,R),m.push(E,w,R)}this.setIndex(m),this.setAttribute("position",new Xe(u,3)),this.setAttribute("normal",new Xe(g,3)),this.setAttribute("uv",new Xe(x,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.width,e.height,e.widthSegments,e.heightSegments)}},$o=class r extends bt{constructor(e=.5,t=1,n=32,i=1,s=0,a=2*Math.PI){super(),this.type="RingGeometry",this.parameters={innerRadius:e,outerRadius:t,thetaSegments:n,phiSegments:i,thetaStart:s,thetaLength:a},n=Math.max(3,n);let o=[],c=[],l=[],h=[],p=e,f=(t-e)/(i=Math.max(1,i)),m=new D,u=new _e;for(let g=0;g<=i;g++){for(let x=0;x<=n;x++){let _=s+x/n*a;m.x=p*Math.cos(_),m.y=p*Math.sin(_),c.push(m.x,m.y,m.z),l.push(0,0,1),u.x=(m.x/t+1)/2,u.y=(m.y/t+1)/2,h.push(u.x,u.y)}p+=f}for(let g=0;g<i;g++){let x=g*(n+1);for(let _=0;_<n;_++){let v=_+x,S=v,E=v+n+1,w=v+n+2,R=v+1;o.push(S,E,R),o.push(E,w,R)}}this.setIndex(o),this.setAttribute("position",new Xe(c,3)),this.setAttribute("normal",new Xe(l,3)),this.setAttribute("uv",new Xe(h,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.innerRadius,e.outerRadius,e.thetaSegments,e.phiSegments,e.thetaStart,e.thetaLength)}},Qo=class r extends bt{constructor(e=new pa([new _e(0,.5),new _e(-.5,-.5),new _e(.5,-.5)]),t=12){super(),this.type="ShapeGeometry",this.parameters={shapes:e,curveSegments:t};let n=[],i=[],s=[],a=[],o=0,c=0;if(Array.isArray(e)===!1)l(e);else for(let h=0;h<e.length;h++)l(e[h]),this.addGroup(o,c,h),o+=c,c=0;function l(h){let p=i.length/3,f=h.extractPoints(t),m=f.shape,u=f.holes;di.isClockWise(m)===!1&&(m=m.reverse());for(let x=0,_=u.length;x<_;x++){let v=u[x];di.isClockWise(v)===!0&&(u[x]=v.reverse())}let g=di.triangulateShape(m,u);for(let x=0,_=u.length;x<_;x++){let v=u[x];m=m.concat(v)}for(let x=0,_=m.length;x<_;x++){let v=m[x];i.push(v.x,v.y,0),s.push(0,0,1),a.push(v.x,v.y)}for(let x=0,_=g.length;x<_;x++){let v=g[x],S=v[0]+p,E=v[1]+p,w=v[2]+p;n.push(S,E,w),c+=3}}this.setIndex(n),this.setAttribute("position",new Xe(i,3)),this.setAttribute("normal",new Xe(s,3)),this.setAttribute("uv",new Xe(a,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){let e=super.toJSON();return(function(t,n){if(n.shapes=[],Array.isArray(t))for(let i=0,s=t.length;i<s;i++){let a=t[i];n.shapes.push(a.uuid)}else n.shapes.push(t.uuid);return n})(this.parameters.shapes,e)}static fromJSON(e,t){let n=[];for(let i=0,s=e.shapes.length;i<s;i++){let a=t[e.shapes[i]];n.push(a)}return new r(n,e.curveSegments)}},el=class r extends bt{constructor(e=1,t=32,n=16,i=0,s=2*Math.PI,a=0,o=Math.PI){super(),this.type="SphereGeometry",this.parameters={radius:e,widthSegments:t,heightSegments:n,phiStart:i,phiLength:s,thetaStart:a,thetaLength:o},t=Math.max(3,Math.floor(t)),n=Math.max(2,Math.floor(n));let c=Math.min(a+o,Math.PI),l=0,h=[],p=new D,f=new D,m=[],u=[],g=[],x=[];for(let _=0;_<=n;_++){let v=[],S=_/n,E=0;_===0&&a===0?E=.5/t:_===n&&c===Math.PI&&(E=-.5/t);for(let w=0;w<=t;w++){let R=w/t;p.x=-e*Math.cos(i+R*s)*Math.sin(a+S*o),p.y=e*Math.cos(a+S*o),p.z=e*Math.sin(i+R*s)*Math.sin(a+S*o),u.push(p.x,p.y,p.z),f.copy(p).normalize(),g.push(f.x,f.y,f.z),x.push(R+E,1-S),v.push(l++)}h.push(v)}for(let _=0;_<n;_++)for(let v=0;v<t;v++){let S=h[_][v+1],E=h[_][v],w=h[_+1][v],R=h[_+1][v+1];(_!==0||a>0)&&m.push(S,E,R),(_!==n-1||c<Math.PI)&&m.push(E,w,R)}this.setIndex(m),this.setAttribute("position",new Xe(u,3)),this.setAttribute("normal",new Xe(g,3)),this.setAttribute("uv",new Xe(x,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.radius,e.widthSegments,e.heightSegments,e.phiStart,e.phiLength,e.thetaStart,e.thetaLength)}},tl=class r extends qi{constructor(e=1,t=0){super([1,1,1,-1,-1,1,-1,1,-1,1,-1,-1],[2,1,0,0,3,2,1,3,0,2,3,1],e,t),this.type="TetrahedronGeometry",this.parameters={radius:e,detail:t}}static fromJSON(e){return new r(e.radius,e.detail)}},nl=class r extends bt{constructor(e=1,t=.4,n=12,i=48,s=2*Math.PI,a=0,o=2*Math.PI){super(),this.type="TorusGeometry",this.parameters={radius:e,tube:t,radialSegments:n,tubularSegments:i,arc:s,thetaStart:a,thetaLength:o},n=Math.floor(n),i=Math.floor(i);let c=[],l=[],h=[],p=[],f=new D,m=new D,u=new D;for(let g=0;g<=n;g++){let x=a+g/n*o;for(let _=0;_<=i;_++){let v=_/i*s;m.x=(e+t*Math.cos(x))*Math.cos(v),m.y=(e+t*Math.cos(x))*Math.sin(v),m.z=t*Math.sin(x),l.push(m.x,m.y,m.z),f.x=e*Math.cos(v),f.y=e*Math.sin(v),u.subVectors(m,f).normalize(),h.push(u.x,u.y,u.z),p.push(_/i),p.push(g/n)}}for(let g=1;g<=n;g++)for(let x=1;x<=i;x++){let _=(i+1)*g+x-1,v=(i+1)*(g-1)+x-1,S=(i+1)*(g-1)+x,E=(i+1)*g+x;c.push(_,v,E),c.push(v,S,E)}this.setIndex(c),this.setAttribute("position",new Xe(l,3)),this.setAttribute("normal",new Xe(h,3)),this.setAttribute("uv",new Xe(p,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.radius,e.tube,e.radialSegments,e.tubularSegments,e.arc)}},il=class r extends bt{constructor(e=1,t=.4,n=64,i=8,s=2,a=3){super(),this.type="TorusKnotGeometry",this.parameters={radius:e,tube:t,tubularSegments:n,radialSegments:i,p:s,q:a},n=Math.floor(n),i=Math.floor(i);let o=[],c=[],l=[],h=[],p=new D,f=new D,m=new D,u=new D,g=new D,x=new D,_=new D;for(let S=0;S<=n;++S){let E=S/n*s*Math.PI*2;v(E,s,a,e,m),v(E+.01,s,a,e,u),x.subVectors(u,m),_.addVectors(u,m),g.crossVectors(x,_),_.crossVectors(g,x),g.normalize(),_.normalize();for(let w=0;w<=i;++w){let R=w/i*Math.PI*2,z=-t*Math.cos(R),j=t*Math.sin(R);p.x=m.x+(z*_.x+j*g.x),p.y=m.y+(z*_.y+j*g.y),p.z=m.z+(z*_.z+j*g.z),c.push(p.x,p.y,p.z),f.subVectors(p,m).normalize(),l.push(f.x,f.y,f.z),h.push(S/n),h.push(w/i)}}for(let S=1;S<=n;S++)for(let E=1;E<=i;E++){let w=(i+1)*(S-1)+(E-1),R=(i+1)*S+(E-1),z=(i+1)*S+E,j=(i+1)*(S-1)+E;o.push(w,R,j),o.push(R,z,j)}function v(S,E,w,R,z){let j=Math.cos(S),O=Math.sin(S),Q=w/E*S,Y=Math.cos(Q);z.x=R*(2+Y)*.5*j,z.y=R*(2+Y)*O*.5,z.z=R*Math.sin(Q)*.5}this.setIndex(o),this.setAttribute("position",new Xe(c,3)),this.setAttribute("normal",new Xe(l,3)),this.setAttribute("uv",new Xe(h,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new r(e.radius,e.tube,e.tubularSegments,e.radialSegments,e.p,e.q)}},rl=class r extends bt{constructor(e=new ha(new D(-1,-1,0),new D(-1,1,0),new D(1,1,0)),t=64,n=1,i=8,s=!1){super(),this.type="TubeGeometry",this.parameters={path:e,tubularSegments:t,radius:n,radialSegments:i,closed:s};let a=e.computeFrenetFrames(t,s);this.tangents=a.tangents,this.normals=a.normals,this.binormals=a.binormals;let o=new D,c=new D,l=new _e,h=new D,p=[],f=[],m=[],u=[];function g(x){h=e.getPointAt(x/t,h);let _=a.normals[x],v=a.binormals[x];for(let S=0;S<=i;S++){let E=S/i*Math.PI*2,w=Math.sin(E),R=-Math.cos(E);c.x=R*_.x+w*v.x,c.y=R*_.y+w*v.y,c.z=R*_.z+w*v.z,c.normalize(),f.push(c.x,c.y,c.z),o.x=h.x+n*c.x,o.y=h.y+n*c.y,o.z=h.z+n*c.z,p.push(o.x,o.y,o.z)}}(function(){for(let x=0;x<t;x++)g(x);g(s===!1?t:0),(function(){for(let x=0;x<=t;x++)for(let _=0;_<=i;_++)l.x=x/t,l.y=_/i,m.push(l.x,l.y)})(),(function(){for(let x=1;x<=t;x++)for(let _=1;_<=i;_++){let v=(i+1)*(x-1)+(_-1),S=(i+1)*x+(_-1),E=(i+1)*x+_,w=(i+1)*(x-1)+_;u.push(v,S,w),u.push(S,E,w)}})()})(),this.setIndex(u),this.setAttribute("position",new Xe(p,3)),this.setAttribute("normal",new Xe(f,3)),this.setAttribute("uv",new Xe(m,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){let e=super.toJSON();return e.path=this.parameters.path.toJSON(),e}static fromJSON(e){return new r(new Xo[e.path.type]().fromJSON(e.path),e.tubularSegments,e.radius,e.radialSegments,e.closed)}},sl=class extends bt{constructor(e=null){if(super(),this.type="WireframeGeometry",this.parameters={geometry:e},e!==null){let t=[],n=new Set,i=new D,s=new D;if(e.index!==null){let a=e.attributes.position,o=e.index,c=e.groups;c.length===0&&(c=[{start:0,count:o.count,materialIndex:0}]);for(let l=0,h=c.length;l<h;++l){let p=c[l],f=p.start;for(let m=f,u=f+p.count;m<u;m+=3)for(let g=0;g<3;g++){let x=o.getX(m+g),_=o.getX(m+(g+1)%3);i.fromBufferAttribute(a,x),s.fromBufferAttribute(a,_),xd(i,s,n)===!0&&(t.push(i.x,i.y,i.z),t.push(s.x,s.y,s.z))}}}else{let a=e.attributes.position;for(let o=0,c=a.count/3;o<c;o++)for(let l=0;l<3;l++){let h=3*o+l,p=3*o+(l+1)%3;i.fromBufferAttribute(a,h),s.fromBufferAttribute(a,p),xd(i,s,n)===!0&&(t.push(i.x,i.y,i.z),t.push(s.x,s.y,s.z))}}this.setAttribute("position",new Xe(t,3))}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}};function xd(r,e,t){let n=`${r.x},${r.y},${r.z}-${e.x},${e.y},${e.z}`,i=`${e.x},${e.y},${e.z}-${r.x},${r.y},${r.z}`;return t.has(n)!==!0&&t.has(i)!==!0&&(t.add(n),t.add(i),!0)}var H0=Object.freeze({__proto__:null,BoxGeometry:Nn,CapsuleGeometry:Bo,CircleGeometry:zo,ConeGeometry:ko,CylinderGeometry:aa,DodecahedronGeometry:Vo,EdgesGeometry:Go,ExtrudeGeometry:Yo,IcosahedronGeometry:Zo,LatheGeometry:Jo,OctahedronGeometry:Ko,PlaneGeometry:Fn,PolyhedronGeometry:qi,RingGeometry:$o,ShapeGeometry:Qo,SphereGeometry:el,TetrahedronGeometry:tl,TorusGeometry:nl,TorusKnotGeometry:il,TubeGeometry:rl,WireframeGeometry:sl});function yr(r){let e={};for(let t in r){e[t]={};for(let n in r[t]){let i=r[t][n];i&&(i.isColor||i.isMatrix3||i.isMatrix4||i.isVector2||i.isVector3||i.isVector4||i.isTexture||i.isQuaternion)?i.isRenderTargetTexture?(Ye("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),e[t][n]=null):e[t][n]=i.clone():Array.isArray(i)?e[t][n]=i.slice():e[t][n]=i}}return e}function on(r){let e={};for(let t=0;t<r.length;t++){let n=yr(r[t]);for(let i in n)e[i]=n[i]}return e}function nu(r){let e=r.getRenderTarget();return e===null?r.outputColorSpace:e.isXRRenderTarget===!0?e.texture.colorSpace:ut.workingColorSpace}var vp={clone:yr,merge:on},Bn=class extends Pi{constructor(e){super(),this.isShaderMaterial=!0,this.type="ShaderMaterial",this.defines={},this.uniforms={},this.uniformsGroups=[],this.vertexShader=`void main() {
	gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
}`,this.fragmentShader=`void main() {
	gl_FragColor = vec4( 1.0, 0.0, 0.0, 1.0 );
}`,this.linewidth=1,this.wireframe=!1,this.wireframeLinewidth=1,this.fog=!1,this.lights=!1,this.clipping=!1,this.forceSinglePass=!0,this.extensions={clipCullDistance:!1,multiDraw:!1},this.defaultAttributeValues={color:[1,1,1],uv:[0,0],uv1:[0,0]},this.index0AttributeName=void 0,this.uniformsNeedUpdate=!1,this.glslVersion=null,e!==void 0&&this.setValues(e)}copy(e){return super.copy(e),this.fragmentShader=e.fragmentShader,this.vertexShader=e.vertexShader,this.uniforms=yr(e.uniforms),this.uniformsGroups=(function(t){let n=[];for(let i=0;i<t.length;i++)n.push(t[i].clone());return n})(e.uniformsGroups),this.defines=Object.assign({},e.defines),this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.fog=e.fog,this.lights=e.lights,this.clipping=e.clipping,this.extensions=Object.assign({},e.extensions),this.glslVersion=e.glslVersion,this.defaultAttributeValues=Object.assign({},e.defaultAttributeValues),this.index0AttributeName=e.index0AttributeName,this.uniformsNeedUpdate=e.uniformsNeedUpdate,this}toJSON(e){let t=super.toJSON(e);t.glslVersion=this.glslVersion,t.uniforms={};for(let i in this.uniforms){let s=this.uniforms[i].value;s&&s.isTexture?t.uniforms[i]={type:"t",value:s.toJSON(e).uuid}:s&&s.isColor?t.uniforms[i]={type:"c",value:s.getHex()}:s&&s.isVector2?t.uniforms[i]={type:"v2",value:s.toArray()}:s&&s.isVector3?t.uniforms[i]={type:"v3",value:s.toArray()}:s&&s.isVector4?t.uniforms[i]={type:"v4",value:s.toArray()}:s&&s.isMatrix3?t.uniforms[i]={type:"m3",value:s.toArray()}:s&&s.isMatrix4?t.uniforms[i]={type:"m4",value:s.toArray()}:t.uniforms[i]={value:s}}Object.keys(this.defines).length>0&&(t.defines=this.defines),t.vertexShader=this.vertexShader,t.fragmentShader=this.fragmentShader,t.lights=this.lights,t.clipping=this.clipping;let n={};for(let i in this.extensions)this.extensions[i]===!0&&(n[i]=!0);return Object.keys(n).length>0&&(t.extensions=n),t}},al=class extends Bn{constructor(e){super(e),this.isRawShaderMaterial=!0,this.type="RawShaderMaterial"}},Sn=class extends Pi{constructor(e){super(),this.isMeshStandardMaterial=!0,this.type="MeshStandardMaterial",this.defines={STANDARD:""},this.color=new He(16777215),this.roughness=1,this.metalness=0,this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.emissive=new He(0),this.emissiveIntensity=1,this.emissiveMap=null,this.bumpMap=null,this.bumpScale=1,this.normalMap=null,this.normalMapType=0,this.normalScale=new _e(1,1),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.roughnessMap=null,this.metalnessMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Un,this.envMapIntensity=1,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.flatShading=!1,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.defines={STANDARD:""},this.color.copy(e.color),this.roughness=e.roughness,this.metalness=e.metalness,this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.emissive.copy(e.emissive),this.emissiveMap=e.emissiveMap,this.emissiveIntensity=e.emissiveIntensity,this.bumpMap=e.bumpMap,this.bumpScale=e.bumpScale,this.normalMap=e.normalMap,this.normalMapType=e.normalMapType,this.normalScale.copy(e.normalScale),this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.roughnessMap=e.roughnessMap,this.metalnessMap=e.metalnessMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.envMapIntensity=e.envMapIntensity,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.flatShading=e.flatShading,this.fog=e.fog,this}};var ol=class extends Pi{constructor(e){super(),this.isMeshDepthMaterial=!0,this.type="MeshDepthMaterial",this.depthPacking=3200,this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.wireframe=!1,this.wireframeLinewidth=1,this.setValues(e)}copy(e){return super.copy(e),this.depthPacking=e.depthPacking,this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this}},ll=class extends Pi{constructor(e){super(),this.isMeshDistanceMaterial=!0,this.type="MeshDistanceMaterial",this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.setValues(e)}copy(e){return super.copy(e),this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this}};function So(r,e){return r&&r.constructor!==e?typeof e.BYTES_PER_ELEMENT=="number"?new e(r):Array.prototype.slice.call(r):r}var Yi=class{constructor(e,t,n,i){this.parameterPositions=e,this._cachedIndex=0,this.resultBuffer=i!==void 0?i:new t.constructor(n),this.sampleValues=t,this.valueSize=n,this.settings=null,this.DefaultSettings_={}}evaluate(e){let t=this.parameterPositions,n=this._cachedIndex,i=t[n],s=t[n-1];n:{e:{let a;t:{i:if(!(e<i)){for(let o=n+2;;){if(i===void 0){if(e<s)break i;return n=t.length,this._cachedIndex=n,this.copySampleValue_(n-1)}if(n===o)break;if(s=i,i=t[++n],e<i)break e}a=t.length;break t}if(!(e>=s)){let o=t[1];e<o&&(n=2,s=o);for(let c=n-2;;){if(s===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(n===c)break;if(i=s,s=t[--n-1],e>=s)break e}a=n,n=0;break t}break n}for(;n<a;){let o=n+a>>>1;e<t[o]?a=o:n=o+1}if(i=t[n],s=t[n-1],s===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(i===void 0)return n=t.length,this._cachedIndex=n,this.copySampleValue_(n-1)}this._cachedIndex=n,this.intervalChanged_(n,s,i)}return this.interpolate_(n,s,e,i)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(e){let t=this.resultBuffer,n=this.sampleValues,i=this.valueSize,s=e*i;for(let a=0;a!==i;++a)t[a]=n[s+a];return t}interpolate_(){throw new Error("call to abstract method")}intervalChanged_(){}},cl=class extends Yi{constructor(e,t,n,i){super(e,t,n,i),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:Bc,endingEnd:Bc}}intervalChanged_(e,t,n){let i=this.parameterPositions,s=e-2,a=e+1,o=i[s],c=i[a];if(o===void 0)switch(this.getSettings_().endingStart){case zc:s=e,o=2*t-n;break;case kc:s=i.length-2,o=t+i[s]-i[s+1];break;default:s=e,o=n}if(c===void 0)switch(this.getSettings_().endingEnd){case zc:a=e,c=2*n-t;break;case kc:a=1,c=n+i[1]-i[0];break;default:a=e-1,c=t}let l=.5*(n-t),h=this.valueSize;this._weightPrev=l/(t-o),this._weightNext=l/(c-n),this._offsetPrev=s*h,this._offsetNext=a*h}interpolate_(e,t,n,i){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,c=e*o,l=c-o,h=this._offsetPrev,p=this._offsetNext,f=this._weightPrev,m=this._weightNext,u=(n-t)/(i-t),g=u*u,x=g*u,_=-f*x+2*f*g-f*u,v=(1+f)*x+(-1.5-2*f)*g+(-.5+f)*u+1,S=(-1-m)*x+(1.5+m)*g+.5*u,E=m*x-m*g;for(let w=0;w!==o;++w)s[w]=_*a[h+w]+v*a[l+w]+S*a[c+w]+E*a[p+w];return s}},hl=class extends Yi{constructor(e,t,n,i){super(e,t,n,i)}interpolate_(e,t,n,i){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,c=e*o,l=c-o,h=(n-t)/(i-t),p=1-h;for(let f=0;f!==o;++f)s[f]=a[l+f]*p+a[c+f]*h;return s}},ul=class extends Yi{constructor(e,t,n,i){super(e,t,n,i)}interpolate_(e){return this.copySampleValue_(e-1)}},dl=class extends Yi{interpolate_(e,t,n,i){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,c=e*o,l=c-o,h=this.settings||this.DefaultSettings_,p=h.inTangents,f=h.outTangents;if(!p||!f){let g=(n-t)/(i-t),x=1-g;for(let _=0;_!==o;++_)s[_]=a[l+_]*x+a[c+_]*g;return s}let m=2*o,u=e-1;for(let g=0;g!==o;++g){let x=a[l+g],_=a[c+g],v=u*m+2*g,S=f[v],E=f[v+1],w=e*m+2*g,R=p[w],z=p[w+1],j,O,Q,Y,k,X=(n-t)/(i-t);for(let K=0;K<8;K++){j=X*X,O=j*X,Q=1-X,Y=Q*Q,k=Y*Q;let te=k*t+3*Y*X*S+3*Q*j*R+O*i-n;if(Math.abs(te)<1e-10)break;let oe=3*Y*(S-t)+6*Q*X*(R-S)+3*j*(i-R);if(Math.abs(oe)<1e-10)break;X-=te/oe,X=Math.max(0,Math.min(1,X))}s[g]=k*x+3*Y*X*E+3*Q*j*z+O*_}return s}},Ln=class{constructor(e,t,n,i){if(e===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(t===void 0||t.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+e);this.name=e,this.times=So(t,this.TimeBufferType),this.values=So(n,this.ValueBufferType),this.setInterpolation(i||this.DefaultInterpolation)}static toJSON(e){let t=e.constructor,n;if(t.toJSON!==this.toJSON)n=t.toJSON(e);else{n={name:e.name,times:So(e.times,Array),values:So(e.values,Array)};let i=e.getInterpolation();i!==e.DefaultInterpolation&&(n.interpolation=i)}return n.type=e.ValueTypeName,n}InterpolantFactoryMethodDiscrete(e){return new ul(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodLinear(e){return new hl(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodSmooth(e){return new cl(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodBezier(e){let t=new dl(this.times,this.values,this.getValueSize(),e);return this.settings&&(t.settings=this.settings),t}setInterpolation(e){let t;switch(e){case qs:t=this.InterpolantFactoryMethodDiscrete;break;case Ro:t=this.InterpolantFactoryMethodLinear;break;case wo:t=this.InterpolantFactoryMethodSmooth;break;case Fc:t=this.InterpolantFactoryMethodBezier}if(t===void 0){let n="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0){if(e===this.DefaultInterpolation)throw new Error(n);this.setInterpolation(this.DefaultInterpolation)}return Ye("KeyframeTrack:",n),this}return this.createInterpolant=t,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return qs;case this.InterpolantFactoryMethodLinear:return Ro;case this.InterpolantFactoryMethodSmooth:return wo;case this.InterpolantFactoryMethodBezier:return Fc}}getValueSize(){return this.values.length/this.times.length}shift(e){if(e!==0){let t=this.times;for(let n=0,i=t.length;n!==i;++n)t[n]+=e}return this}scale(e){if(e!==1){let t=this.times;for(let n=0,i=t.length;n!==i;++n)t[n]*=e}return this}trim(e,t){let n=this.times,i=n.length,s=0,a=i-1;for(;s!==i&&n[s]<e;)++s;for(;a!==-1&&n[a]>t;)--a;if(++a,s!==0||a!==i){s>=a&&(a=Math.max(a,1),s=a-1);let o=this.getValueSize();this.times=n.slice(s,a),this.values=this.values.slice(s*o,a*o)}return this}validate(){let e=!0,t=this.getValueSize();t-Math.floor(t)!==0&&(Je("KeyframeTrack: Invalid value size in track.",this),e=!1);let n=this.times,i=this.values,s=n.length;s===0&&(Je("KeyframeTrack: Track is empty.",this),e=!1);let a=null;for(let o=0;o!==s;o++){let c=n[o];if(typeof c=="number"&&isNaN(c)){Je("KeyframeTrack: Time is not a valid number.",this,o,c),e=!1;break}if(a!==null&&a>c){Je("KeyframeTrack: Out of order keys.",this,o,c,a),e=!1;break}a=c}if(i!==void 0&&Sf(i))for(let o=0,c=i.length;o!==c;++o){let l=i[o];if(isNaN(l)){Je("KeyframeTrack: Value is not a valid number.",this,o,l),e=!1;break}}return e}optimize(){let e=this.times.slice(),t=this.values.slice(),n=this.getValueSize(),i=this.getInterpolation()===wo,s=e.length-1,a=1;for(let o=1;o<s;++o){let c=!1,l=e[o];if(l!==e[o+1]&&(o!==1||l!==e[0]))if(i)c=!0;else{let h=o*n,p=h-n,f=h+n;for(let m=0;m!==n;++m){let u=t[h+m];if(u!==t[p+m]||u!==t[f+m]){c=!0;break}}}if(c){if(o!==a){e[a]=e[o];let h=o*n,p=a*n;for(let f=0;f!==n;++f)t[p+f]=t[h+f]}++a}}if(s>0){e[a]=e[s];for(let o=s*n,c=a*n,l=0;l!==n;++l)t[c+l]=t[o+l];++a}return a!==e.length?(this.times=e.slice(0,a),this.values=t.slice(0,a*n)):(this.times=e,this.values=t),this}clone(){let e=this.times.slice(),t=this.values.slice(),n=new this.constructor(this.name,e,t);return n.createInterpolant=this.createInterpolant,n}};Ln.prototype.ValueTypeName="",Ln.prototype.TimeBufferType=Float32Array,Ln.prototype.ValueBufferType=Float32Array,Ln.prototype.DefaultInterpolation=Ro;var Gi=class extends Ln{constructor(e,t,n){super(e,t,n)}};Gi.prototype.ValueTypeName="bool",Gi.prototype.ValueBufferType=Array,Gi.prototype.DefaultInterpolation=qs,Gi.prototype.InterpolantFactoryMethodLinear=void 0,Gi.prototype.InterpolantFactoryMethodSmooth=void 0;var pl=class extends Ln{constructor(e,t,n,i){super(e,t,n,i)}};pl.prototype.ValueTypeName="color";var fl=class extends Ln{constructor(e,t,n,i){super(e,t,n,i)}};fl.prototype.ValueTypeName="number";var ml=class extends Yi{constructor(e,t,n,i){super(e,t,n,i)}interpolate_(e,t,n,i){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,c=(n-t)/(i-t),l=e*o;for(let h=l+o;l!==h;l+=4)kt.slerpFlat(s,0,a,l-o,a,l,c);return s}},_a=class extends Ln{constructor(e,t,n,i){super(e,t,n,i)}InterpolantFactoryMethodLinear(e){return new ml(this.times,this.values,this.getValueSize(),e)}};_a.prototype.ValueTypeName="quaternion",_a.prototype.InterpolantFactoryMethodSmooth=void 0;var Hi=class extends Ln{constructor(e,t,n){super(e,t,n)}};Hi.prototype.ValueTypeName="string",Hi.prototype.ValueBufferType=Array,Hi.prototype.DefaultInterpolation=qs,Hi.prototype.InterpolantFactoryMethodLinear=void 0,Hi.prototype.InterpolantFactoryMethodSmooth=void 0;var gl=class extends Ln{constructor(e,t,n,i){super(e,t,n,i)}};gl.prototype.ValueTypeName="vector";var Ao={enabled:!1,files:{},add:function(r,e){this.enabled!==!1&&(Md(r)||(this.files[r]=e))},get:function(r){if(this.enabled!==!1&&!Md(r))return this.files[r]},remove:function(r){delete this.files[r]},clear:function(){this.files={}}};function Md(r){try{let e=r.slice(r.indexOf(":")+1);return new URL(e).protocol==="blob:"}catch{return!1}}var _l=class{constructor(e,t,n){let i=this,s,a=!1,o=0,c=0,l=[];this.onStart=void 0,this.onLoad=e,this.onProgress=t,this.onError=n,this._abortController=null,this.itemStart=function(h){c++,a===!1&&i.onStart!==void 0&&i.onStart(h,o,c),a=!0},this.itemEnd=function(h){o++,i.onProgress!==void 0&&i.onProgress(h,o,c),o===c&&(a=!1,i.onLoad!==void 0&&i.onLoad())},this.itemError=function(h){i.onError!==void 0&&i.onError(h)},this.resolveURL=function(h){return s?s(h):h},this.setURLModifier=function(h){return s=h,this},this.addHandler=function(h,p){return l.push(h,p),this},this.removeHandler=function(h){let p=l.indexOf(h);return p!==-1&&l.splice(p,2),this},this.getHandler=function(h){for(let p=0,f=l.length;p<f;p+=2){let m=l[p],u=l[p+1];if(m.global&&(m.lastIndex=0),m.test(h))return u}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},yp=new _l,ss=class{constructor(e){this.manager=e!==void 0?e:yp,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(e,t){let n=this;return new Promise(function(i,s){n.load(e,i,t,s)})}parse(){}setCrossOrigin(e){return this.crossOrigin=e,this}setWithCredentials(e){return this.withCredentials=e,this}setPath(e){return this.path=e,this}setResourcePath(e){return this.resourcePath=e,this}setRequestHeader(e){return this.requestHeader=e,this}abort(){return this}};ss.DEFAULT_MATERIAL_NAME="__DEFAULT";var Wr=new WeakMap,vl=class extends ss{constructor(e){super(e)}load(e,t,n,i){this.path!==void 0&&(e=this.path+e),e=this.manager.resolveURL(e);let s=this,a=Ao.get(`image:${e}`);if(a!==void 0){if(a.complete===!0)s.manager.itemStart(e),setTimeout(function(){t&&t(a),s.manager.itemEnd(e)},0);else{let p=Wr.get(a);p===void 0&&(p=[],Wr.set(a,p)),p.push({onLoad:t,onError:i})}return a}let o=Jr("img");function c(){h(),t&&t(this);let p=Wr.get(this)||[];for(let f=0;f<p.length;f++){let m=p[f];m.onLoad&&m.onLoad(this)}Wr.delete(this),s.manager.itemEnd(e)}function l(p){h(),i&&i(p),Ao.remove(`image:${e}`);let f=Wr.get(this)||[];for(let m=0;m<f.length;m++){let u=f[m];u.onError&&u.onError(p)}Wr.delete(this),s.manager.itemError(e),s.manager.itemEnd(e)}function h(){o.removeEventListener("load",c,!1),o.removeEventListener("error",l,!1)}return o.addEventListener("load",c,!1),o.addEventListener("error",l,!1),e.slice(0,5)!=="data:"&&this.crossOrigin!==void 0&&(o.crossOrigin=this.crossOrigin),Ao.add(`image:${e}`,o),s.manager.itemStart(e),o.src=e,o}};var va=class extends ss{constructor(e){super(e)}load(e,t,n,i){let s=new an,a=new vl(this.manager);return a.setCrossOrigin(this.crossOrigin),a.setPath(this.path),a.load(e,function(o){s.image=o,s.needsUpdate=!0,t!==void 0&&t(s)},n,i),s}},as=class extends Ft{constructor(e,t=1){super(),this.isLight=!0,this.type="Light",this.color=new He(e),this.intensity=t}dispose(){this.dispatchEvent({type:"dispose"})}copy(e,t){return super.copy(e,t),this.color.copy(e.color),this.intensity=e.intensity,this}toJSON(e){let t=super.toJSON(e);return t.object.color=this.color.getHex(),t.object.intensity=this.intensity,t}},ya=class extends as{constructor(e,t,n){super(e,n),this.isHemisphereLight=!0,this.type="HemisphereLight",this.position.copy(Ft.DEFAULT_UP),this.updateMatrix(),this.groundColor=new He(t)}copy(e,t){return super.copy(e,t),this.groundColor.copy(e.groundColor),this}toJSON(e){let t=super.toJSON(e);return t.object.groundColor=this.groundColor.getHex(),t}},Nc=new Ke,bd=new D,Sd=new D,yl=class{constructor(e){this.camera=e,this.intensity=1,this.bias=0,this.biasNode=null,this.normalBias=0,this.radius=1,this.blurSamples=8,this.mapSize=new _e(512,512),this.mapType=zn,this.map=null,this.mapPass=null,this.matrix=new Ke,this.autoUpdate=!0,this.needsUpdate=!1,this._frustum=new ji,this._frameExtents=new _e(1,1),this._viewportCount=1,this._viewports=[new wt(0,0,1,1)]}getViewportCount(){return this._viewportCount}getFrustum(){return this._frustum}updateMatrices(e){let t=this.camera,n=this.matrix;bd.setFromMatrixPosition(e.matrixWorld),t.position.copy(bd),Sd.setFromMatrixPosition(e.target.matrixWorld),t.lookAt(Sd),t.updateMatrixWorld(),Nc.multiplyMatrices(t.projectionMatrix,t.matrixWorldInverse),this._frustum.setFromProjectionMatrix(Nc,t.coordinateSystem,t.reversedDepth),t.coordinateSystem===Zr||t.reversedDepth?n.set(.5,0,0,.5,0,.5,0,.5,0,0,1,0,0,0,0,1):n.set(.5,0,0,.5,0,.5,0,.5,0,0,.5,.5,0,0,0,1),n.multiply(Nc)}getViewport(e){return this._viewports[e]}getFrameExtents(){return this._frameExtents}dispose(){this.map&&this.map.dispose(),this.mapPass&&this.mapPass.dispose()}copy(e){return this.camera=e.camera.clone(),this.intensity=e.intensity,this.bias=e.bias,this.radius=e.radius,this.autoUpdate=e.autoUpdate,this.needsUpdate=e.needsUpdate,this.normalBias=e.normalBias,this.blurSamples=e.blurSamples,this.mapSize.copy(e.mapSize),this.biasNode=e.biasNode,this}clone(){return new this.constructor().copy(this)}toJSON(){let e={};return this.intensity!==1&&(e.intensity=this.intensity),this.bias!==0&&(e.bias=this.bias),this.normalBias!==0&&(e.normalBias=this.normalBias),this.radius!==1&&(e.radius=this.radius),this.mapSize.x===512&&this.mapSize.y===512||(e.mapSize=this.mapSize.toArray()),e.camera=this.camera.toJSON(!1).object,delete e.camera.matrix,e}},To=new D,Eo=new kt,ui=new D,os=class extends Ft{constructor(){super(),this.isCamera=!0,this.type="Camera",this.matrixWorldInverse=new Ke,this.projectionMatrix=new Ke,this.projectionMatrixInverse=new Ke,this.coordinateSystem=Ri,this._reversedDepth=!1}get reversedDepth(){return this._reversedDepth}copy(e,t){return super.copy(e,t),this.matrixWorldInverse.copy(e.matrixWorldInverse),this.projectionMatrix.copy(e.projectionMatrix),this.projectionMatrixInverse.copy(e.projectionMatrixInverse),this.coordinateSystem=e.coordinateSystem,this}getWorldDirection(e){return super.getWorldDirection(e).negate()}updateMatrixWorld(e){super.updateMatrixWorld(e),this.matrixWorld.decompose(To,Eo,ui),ui.x===1&&ui.y===1&&ui.z===1?this.matrixWorldInverse.copy(this.matrixWorld).invert():this.matrixWorldInverse.compose(To,Eo,ui.set(1,1,1)).invert()}updateWorldMatrix(e,t){super.updateWorldMatrix(e,t),this.matrixWorld.decompose(To,Eo,ui),ui.x===1&&ui.y===1&&ui.z===1?this.matrixWorldInverse.copy(this.matrixWorld).invert():this.matrixWorldInverse.compose(To,Eo,ui.set(1,1,1)).invert()}clone(){return new this.constructor().copy(this)}},Vi=new D,Td=new _e,Ed=new _e,Jt=class extends os{constructor(e=50,t=1,n=.1,i=2e3){super(),this.isPerspectiveCamera=!0,this.type="PerspectiveCamera",this.fov=e,this.zoom=1,this.near=n,this.far=i,this.focus=10,this.aspect=t,this.view=null,this.filmGauge=35,this.filmOffset=0,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.fov=e.fov,this.zoom=e.zoom,this.near=e.near,this.far=e.far,this.focus=e.focus,this.aspect=e.aspect,this.view=e.view===null?null:Object.assign({},e.view),this.filmGauge=e.filmGauge,this.filmOffset=e.filmOffset,this}setFocalLength(e){let t=.5*this.getFilmHeight()/e;this.fov=2*$r*Math.atan(t),this.updateProjectionMatrix()}getFocalLength(){let e=Math.tan(.5*qr*this.fov);return .5*this.getFilmHeight()/e}getEffectiveFOV(){return 2*$r*Math.atan(Math.tan(.5*qr*this.fov)/this.zoom)}getFilmWidth(){return this.filmGauge*Math.min(this.aspect,1)}getFilmHeight(){return this.filmGauge/Math.max(this.aspect,1)}getViewBounds(e,t,n){Vi.set(-1,-1,.5).applyMatrix4(this.projectionMatrixInverse),t.set(Vi.x,Vi.y).multiplyScalar(-e/Vi.z),Vi.set(1,1,.5).applyMatrix4(this.projectionMatrixInverse),n.set(Vi.x,Vi.y).multiplyScalar(-e/Vi.z)}getViewSize(e,t){return this.getViewBounds(e,Td,Ed),t.subVectors(Ed,Td)}setViewOffset(e,t,n,i,s,a){this.aspect=e/t,this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=i,this.view.width=s,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){let e=this.near,t=e*Math.tan(.5*qr*this.fov)/this.zoom,n=2*t,i=this.aspect*n,s=-.5*i,a=this.view;if(this.view!==null&&this.view.enabled){let c=a.fullWidth,l=a.fullHeight;s+=a.offsetX*i/c,t-=a.offsetY*n/l,i*=a.width/c,n*=a.height/l}let o=this.filmOffset;o!==0&&(s+=e*o/this.getFilmWidth()),this.projectionMatrix.makePerspective(s,s+i,t,t-n,e,this.far,this.coordinateSystem,this.reversedDepth),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){let t=super.toJSON(e);return t.object.fov=this.fov,t.object.zoom=this.zoom,t.object.near=this.near,t.object.far=this.far,t.object.focus=this.focus,t.object.aspect=this.aspect,this.view!==null&&(t.object.view=Object.assign({},this.view)),t.object.filmGauge=this.filmGauge,t.object.filmOffset=this.filmOffset,t}};var qc=class extends yl{constructor(){super(new Jt(90,1,.5,500)),this.isPointLightShadow=!0}},ls=class extends as{constructor(e,t,n=0,i=2){super(e,t),this.isPointLight=!0,this.type="PointLight",this.distance=n,this.decay=i,this.shadow=new qc}get power(){return 4*this.intensity*Math.PI}set power(e){this.intensity=e/(4*Math.PI)}dispose(){super.dispose(),this.shadow.dispose()}copy(e,t){return super.copy(e,t),this.distance=e.distance,this.decay=e.decay,this.shadow=e.shadow.clone(),this}toJSON(e){let t=super.toJSON(e);return t.object.distance=this.distance,t.object.decay=this.decay,t.object.shadow=this.shadow.toJSON(),t}},cs=class extends os{constructor(e=-1,t=1,n=1,i=-1,s=.1,a=2e3){super(),this.isOrthographicCamera=!0,this.type="OrthographicCamera",this.zoom=1,this.view=null,this.left=e,this.right=t,this.top=n,this.bottom=i,this.near=s,this.far=a,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.left=e.left,this.right=e.right,this.top=e.top,this.bottom=e.bottom,this.near=e.near,this.far=e.far,this.zoom=e.zoom,this.view=e.view===null?null:Object.assign({},e.view),this}setViewOffset(e,t,n,i,s,a){this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=i,this.view.width=s,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){let e=(this.right-this.left)/(2*this.zoom),t=(this.top-this.bottom)/(2*this.zoom),n=(this.right+this.left)/2,i=(this.top+this.bottom)/2,s=n-e,a=n+e,o=i+t,c=i-t;if(this.view!==null&&this.view.enabled){let l=(this.right-this.left)/this.view.fullWidth/this.zoom,h=(this.top-this.bottom)/this.view.fullHeight/this.zoom;s+=l*this.view.offsetX,a=s+l*this.view.width,o-=h*this.view.offsetY,c=o-h*this.view.height}this.projectionMatrix.makeOrthographic(s,a,o,c,this.near,this.far,this.coordinateSystem,this.reversedDepth),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){let t=super.toJSON(e);return t.object.zoom=this.zoom,t.object.left=this.left,t.object.right=this.right,t.object.top=this.top,t.object.bottom=this.bottom,t.object.near=this.near,t.object.far=this.far,this.view!==null&&(t.object.view=Object.assign({},this.view)),t}},Yc=class extends yl{constructor(){super(new cs(-5,5,5,-5,.5,500)),this.isDirectionalLightShadow=!0}},hs=class extends as{constructor(e,t){super(e,t),this.isDirectionalLight=!0,this.type="DirectionalLight",this.position.copy(Ft.DEFAULT_UP),this.updateMatrix(),this.target=new Ft,this.shadow=new Yc}dispose(){super.dispose(),this.shadow.dispose()}copy(e){return super.copy(e),this.target=e.target.clone(),this.shadow=e.shadow.clone(),this}toJSON(e){let t=super.toJSON(e);return t.object.shadow=this.shadow.toJSON(),t.object.target=this.target.uuid,t}};var W0=new Ke,j0=new Ke,X0=new Ke;var jr=-90,xl=class extends Ft{constructor(e,t,n){super(),this.type="CubeCamera",this.renderTarget=n,this.coordinateSystem=null,this.activeMipmapLevel=0;let i=new Jt(jr,1,e,t);i.layers=this.layers,this.add(i);let s=new Jt(jr,1,e,t);s.layers=this.layers,this.add(s);let a=new Jt(jr,1,e,t);a.layers=this.layers,this.add(a);let o=new Jt(jr,1,e,t);o.layers=this.layers,this.add(o);let c=new Jt(jr,1,e,t);c.layers=this.layers,this.add(c);let l=new Jt(jr,1,e,t);l.layers=this.layers,this.add(l)}updateCoordinateSystem(){let e=this.coordinateSystem,t=this.children.concat(),[n,i,s,a,o,c]=t;for(let l of t)this.remove(l);if(e===Ri)n.up.set(0,1,0),n.lookAt(1,0,0),i.up.set(0,1,0),i.lookAt(-1,0,0),s.up.set(0,0,-1),s.lookAt(0,1,0),a.up.set(0,0,1),a.lookAt(0,-1,0),o.up.set(0,1,0),o.lookAt(0,0,1),c.up.set(0,1,0),c.lookAt(0,0,-1);else{if(e!==Zr)throw new Error("THREE.CubeCamera.updateCoordinateSystem(): Invalid coordinate system: "+e);n.up.set(0,-1,0),n.lookAt(-1,0,0),i.up.set(0,-1,0),i.lookAt(1,0,0),s.up.set(0,0,1),s.lookAt(0,1,0),a.up.set(0,0,-1),a.lookAt(0,-1,0),o.up.set(0,-1,0),o.lookAt(0,0,1),c.up.set(0,-1,0),c.lookAt(0,0,-1)}for(let l of t)this.add(l),l.updateMatrixWorld()}update(e,t){this.parent===null&&this.updateMatrixWorld();let{renderTarget:n,activeMipmapLevel:i}=this;this.coordinateSystem!==e.coordinateSystem&&(this.coordinateSystem=e.coordinateSystem,this.updateCoordinateSystem());let[s,a,o,c,l,h]=this.children,p=e.getRenderTarget(),f=e.getActiveCubeFace(),m=e.getActiveMipmapLevel(),u=e.xr.enabled;e.xr.enabled=!1;let g=n.texture.generateMipmaps;n.texture.generateMipmaps=!1;let x=!1;x=e.isWebGLRenderer===!0?e.state.buffers.depth.getReversed():e.reversedDepthBuffer,e.setRenderTarget(n,0,i),x&&e.autoClear===!1&&e.clearDepth(),e.render(t,s),e.setRenderTarget(n,1,i),x&&e.autoClear===!1&&e.clearDepth(),e.render(t,a),e.setRenderTarget(n,2,i),x&&e.autoClear===!1&&e.clearDepth(),e.render(t,o),e.setRenderTarget(n,3,i),x&&e.autoClear===!1&&e.clearDepth(),e.render(t,c),e.setRenderTarget(n,4,i),x&&e.autoClear===!1&&e.clearDepth(),e.render(t,l),n.texture.generateMipmaps=g,e.setRenderTarget(n,5,i),x&&e.autoClear===!1&&e.clearDepth(),e.render(t,h),e.setRenderTarget(p,f,m),e.xr.enabled=u,n.texture.needsPMREMUpdate=!0}},Ml=class extends Jt{constructor(e=[]){super(),this.isArrayCamera=!0,this.isMultiViewCamera=!1,this.cameras=e}};var q0=new D,Y0=new kt,Z0=new D,J0=new D,K0=new D;var $0=new D,Q0=new kt,e_=new D,t_=new D;var iu="\\[\\]\\.:\\/",em=new RegExp("["+iu+"]","g"),Oc="[^"+iu+"]",tm="[^"+iu.replace("\\.","")+"]",nm=new RegExp("^"+/((?:WC+[\/:])*)/.source.replace("WC",Oc)+/(WCOD+)?/.source.replace("WCOD",tm)+/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",Oc)+/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",Oc)+"$"),im=["material","materials","bones","map"],Et=class r{constructor(e,t,n){this.path=t,this.parsedPath=n||r.parseTrackName(t),this.node=r.findNode(e,this.parsedPath.nodeName),this.rootNode=e,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(e,t,n){return e&&e.isAnimationObjectGroup?new r.Composite(e,t,n):new r(e,t,n)}static sanitizeNodeName(e){return e.replace(/\s/g,"_").replace(em,"")}static parseTrackName(e){let t=nm.exec(e);if(t===null)throw new Error("PropertyBinding: Cannot parse trackName: "+e);let n={nodeName:t[2],objectName:t[3],objectIndex:t[4],propertyName:t[5],propertyIndex:t[6]},i=n.nodeName&&n.nodeName.lastIndexOf(".");if(i!==void 0&&i!==-1){let s=n.nodeName.substring(i+1);im.indexOf(s)!==-1&&(n.nodeName=n.nodeName.substring(0,i),n.objectName=s)}if(n.propertyName===null||n.propertyName.length===0)throw new Error("PropertyBinding: can not parse propertyName from trackName: "+e);return n}static findNode(e,t){if(t===void 0||t===""||t==="."||t===-1||t===e.name||t===e.uuid)return e;if(e.skeleton){let n=e.skeleton.getBoneByName(t);if(n!==void 0)return n}if(e.children){let n=function(s){for(let a=0;a<s.length;a++){let o=s[a];if(o.name===t||o.uuid===t)return o;let c=n(o.children);if(c)return c}return null},i=n(e.children);if(i)return i}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(e,t){e[t]=this.targetObject[this.propertyName]}_getValue_array(e,t){let n=this.resolvedProperty;for(let i=0,s=n.length;i!==s;++i)e[t++]=n[i]}_getValue_arrayElement(e,t){e[t]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(e,t){this.resolvedProperty.toArray(e,t)}_setValue_direct(e,t){this.targetObject[this.propertyName]=e[t]}_setValue_direct_setNeedsUpdate(e,t){this.targetObject[this.propertyName]=e[t],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(e,t){this.targetObject[this.propertyName]=e[t],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(e,t){let n=this.resolvedProperty;for(let i=0,s=n.length;i!==s;++i)n[i]=e[t++]}_setValue_array_setNeedsUpdate(e,t){let n=this.resolvedProperty;for(let i=0,s=n.length;i!==s;++i)n[i]=e[t++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(e,t){let n=this.resolvedProperty;for(let i=0,s=n.length;i!==s;++i)n[i]=e[t++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(e,t){this.resolvedProperty[this.propertyIndex]=e[t]}_setValue_arrayElement_setNeedsUpdate(e,t){this.resolvedProperty[this.propertyIndex]=e[t],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(e,t){this.resolvedProperty[this.propertyIndex]=e[t],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(e,t){this.resolvedProperty.fromArray(e,t)}_setValue_fromArray_setNeedsUpdate(e,t){this.resolvedProperty.fromArray(e,t),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(e,t){this.resolvedProperty.fromArray(e,t),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(e,t){this.bind(),this.getValue(e,t)}_setValue_unbound(e,t){this.bind(),this.setValue(e,t)}bind(){let e=this.node,t=this.parsedPath,n=t.objectName,i=t.propertyName,s=t.propertyIndex;if(e||(e=r.findNode(this.rootNode,t.nodeName),this.node=e),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!e)return void Ye("PropertyBinding: No target node found for track: "+this.path+".");if(n){let l=t.objectIndex;switch(n){case"materials":if(!e.material)return void Je("PropertyBinding: Can not bind to material as node does not have a material.",this);if(!e.material.materials)return void Je("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);e=e.material.materials;break;case"bones":if(!e.skeleton)return void Je("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);e=e.skeleton.bones;for(let h=0;h<e.length;h++)if(e[h].name===l){l=h;break}break;case"map":if("map"in e){e=e.map;break}if(!e.material)return void Je("PropertyBinding: Can not bind to material as node does not have a material.",this);if(!e.material.map)return void Je("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);e=e.material.map;break;default:if(e[n]===void 0)return void Je("PropertyBinding: Can not bind to objectName of node undefined.",this);e=e[n]}if(l!==void 0){if(e[l]===void 0)return void Je("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,e);e=e[l]}}let a=e[i];if(a===void 0)return void Je("PropertyBinding: Trying to update property for track: "+t.nodeName+"."+i+" but it wasn't found.",e);let o=this.Versioning.None;this.targetObject=e,e.isMaterial===!0?o=this.Versioning.NeedsUpdate:e.isObject3D===!0&&(o=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(s!==void 0){if(i==="morphTargetInfluences"){if(!e.geometry)return void Je("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);if(!e.geometry.morphAttributes)return void Je("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);e.morphTargetDictionary[s]!==void 0&&(s=e.morphTargetDictionary[s])}c=this.BindingType.ArrayElement,this.resolvedProperty=a,this.propertyIndex=s}else a.fromArray!==void 0&&a.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=a):Array.isArray(a)?(c=this.BindingType.EntireArray,this.resolvedProperty=a):this.propertyName=i;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][o]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};Et.Composite=class{constructor(r,e,t){let n=t||Et.parseTrackName(e);this._targetGroup=r,this._bindings=r.subscribe_(e,n)}getValue(r,e){this.bind();let t=this._targetGroup.nCachedObjects_,n=this._bindings[t];n!==void 0&&n.getValue(r,e)}setValue(r,e){let t=this._bindings;for(let n=this._targetGroup.nCachedObjects_,i=t.length;n!==i;++n)t[n].setValue(r,e)}bind(){let r=this._bindings;for(let e=this._targetGroup.nCachedObjects_,t=r.length;e!==t;++e)r[e].bind()}unbind(){let r=this._bindings;for(let e=this._targetGroup.nCachedObjects_,t=r.length;e!==t;++e)r[e].unbind()}},Et.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3},Et.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2},Et.prototype.GetterByBindingType=[Et.prototype._getValue_direct,Et.prototype._getValue_array,Et.prototype._getValue_arrayElement,Et.prototype._getValue_toArray],Et.prototype.SetterByBindingTypeAndVersioning=[[Et.prototype._setValue_direct,Et.prototype._setValue_direct_setNeedsUpdate,Et.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[Et.prototype._setValue_array,Et.prototype._setValue_array_setNeedsUpdate,Et.prototype._setValue_array_setMatrixWorldNeedsUpdate],[Et.prototype._setValue_arrayElement,Et.prototype._setValue_arrayElement_setNeedsUpdate,Et.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[Et.prototype._setValue_fromArray,Et.prototype._setValue_fromArray_setNeedsUpdate,Et.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var n_=new Float32Array(1);var wd=new Ke,us=class{constructor(e,t,n=0,i=1/0){this.ray=new fi(e,t),this.near=n,this.far=i,this.camera=null,this.layers=new es,this.params={Mesh:{},Line:{threshold:1},LOD:{},Points:{threshold:1},Sprite:{}}}set(e,t){this.ray.set(e,t)}setFromCamera(e,t){t.isPerspectiveCamera?(this.ray.origin.setFromMatrixPosition(t.matrixWorld),this.ray.direction.set(e.x,e.y,.5).unproject(t).sub(this.ray.origin).normalize(),this.camera=t):t.isOrthographicCamera?(this.ray.origin.set(e.x,e.y,(t.near+t.far)/(t.near-t.far)).unproject(t),this.ray.direction.set(0,0,-1).transformDirection(t.matrixWorld),this.camera=t):Je("Raycaster: Unsupported camera type: "+t.type)}setFromXRController(e){return wd.identity().extractRotation(e.matrixWorld),this.ray.origin.setFromMatrixPosition(e.matrixWorld),this.ray.direction.set(0,0,-1).applyMatrix4(wd),this}intersectObject(e,t=!0,n=[]){return Zc(e,this,n,t),n.sort(Ad),n}intersectObjects(e,t=!0,n=[]){for(let i=0,s=e.length;i<s;i++)Zc(e[i],this,n,t);return n.sort(Ad),n}};function Ad(r,e){return r.distance-e.distance}function Zc(r,e,t,n){let i=!0;if(r.layers.test(e.layers)&&r.raycast(e,t)===!1&&(i=!1),i===!0&&n===!0){let s=r.children;for(let a=0,o=s.length;a<o;a++)Zc(s[a],e,t,!0)}}var ds=class{constructor(e=1,t=0,n=0){this.radius=e,this.phi=t,this.theta=n}set(e,t,n){return this.radius=e,this.phi=t,this.theta=n,this}copy(e){return this.radius=e.radius,this.phi=e.phi,this.theta=e.theta,this}makeSafe(){return this.phi=nt(this.phi,1e-6,Math.PI-1e-6),this}setFromVector3(e){return this.setFromCartesianCoords(e.x,e.y,e.z)}setFromCartesianCoords(e,t,n){return this.radius=Math.sqrt(e*e+t*t+n*n),this.radius===0?(this.theta=0,this.phi=0):(this.theta=Math.atan2(e,n),this.phi=Math.acos(nt(t/this.radius,-1,1))),this}clone(){return new this.constructor().copy(this)}};var i_=new _e;var r_=new D,s_=new D,a_=new D,o_=new D,l_=new D,c_=new D,h_=new D;var u_=new D;var d_=new D,p_=new Ke,f_=new Ke;var m_=new D,g_=new He,__=new He;var xa=class extends ia{constructor(e=10,t=10,n=4473924,i=8947848){n=new He(n),i=new He(i);let s=t/2,a=e/t,o=e/2,c=[],l=[];for(let p=0,f=0,m=-o;p<=t;p++,m+=a){c.push(-o,0,m,o,0,m),c.push(m,0,-o,m,0,o);let u=p===s?n:i;u.toArray(l,f),f+=3,u.toArray(l,f),f+=3,u.toArray(l,f),f+=3,u.toArray(l,f),f+=3}let h=new bt;h.setAttribute("position",new Xe(c,3)),h.setAttribute("color",new Xe(l,3)),super(h,new ns({vertexColors:!0,toneMapped:!1})),this.type="GridHelper"}dispose(){this.geometry.dispose(),this.material.dispose()}};var v_=new D,y_=new D,x_=new D;var M_=new D,b_=new os;var S_=new $t;var Ma=class extends ia{constructor(e,t=16776960){let n=new Uint16Array([0,1,1,2,2,3,3,0,4,5,5,6,6,7,7,4,0,4,1,5,2,6,3,7]),i=new bt;i.setIndex(new _n(n,1)),i.setAttribute("position",new Xe([1,1,1,-1,1,1,-1,-1,1,1,-1,1,1,1,-1,-1,1,-1,-1,-1,-1,1,-1,-1],3)),super(i,new ns({color:t,toneMapped:!1})),this.box=e,this.type="Box3Helper",this.geometry.computeBoundingSphere()}updateMatrixWorld(e){let t=this.box;t.isEmpty()||(t.getCenter(this.position),t.getSize(this.scale),this.scale.multiplyScalar(.5),super.updateMatrixWorld(e))}dispose(){this.geometry.dispose(),this.material.dispose()}};var T_=new D;var ba=class extends pi{constructor(e,t=null){super(),this.object=e,this.domElement=t,this.enabled=!0,this.state=-1,this.keys={},this.mouseButtons={LEFT:null,MIDDLE:null,RIGHT:null},this.touches={ONE:null,TWO:null}}connect(e){e!==void 0?(this.domElement!==null&&this.disconnect(),this.domElement=e):Ye("Controls: connect() now requires an element.")}disconnect(){}dispose(){}update(){}};function ru(r,e,t,n){let i=(function(s){switch(s){case zn:case fh:return{byteLength:1,components:1};case _s:case mh:case gi:return{byteLength:2,components:1};case Cl:case Rl:return{byteLength:2,components:4};case Li:case Al:case Kn:return{byteLength:4,components:1};case gh:case _h:return{byteLength:4,components:3}}throw new Error(`Unknown texture type ${s}.`)})(n);switch(t){case 1021:return r*e;case Pl:case Il:return r*e/i.components*i.byteLength;case 1030:case 1031:return r*e*2/i.components*i.byteLength;case 1022:return r*e*3/i.components*i.byteLength;case ai:case 1033:return r*e*4/i.components*i.byteLength;case 33776:case 33777:return Math.floor((r+3)/4)*Math.floor((e+3)/4)*8;case 33778:case 33779:return Math.floor((r+3)/4)*Math.floor((e+3)/4)*16;case 35841:case 35843:return Math.max(r,16)*Math.max(e,8)/4;case 35840:case 35842:return Math.max(r,8)*Math.max(e,8)/2;case 36196:case 37492:case 37488:case 37489:return Math.floor((r+3)/4)*Math.floor((e+3)/4)*8;case 37496:case 37490:case 37491:case 37808:return Math.floor((r+3)/4)*Math.floor((e+3)/4)*16;case 37809:return Math.floor((r+4)/5)*Math.floor((e+3)/4)*16;case 37810:return Math.floor((r+4)/5)*Math.floor((e+4)/5)*16;case 37811:return Math.floor((r+5)/6)*Math.floor((e+4)/5)*16;case 37812:return Math.floor((r+5)/6)*Math.floor((e+5)/6)*16;case 37813:return Math.floor((r+7)/8)*Math.floor((e+4)/5)*16;case 37814:return Math.floor((r+7)/8)*Math.floor((e+5)/6)*16;case 37815:return Math.floor((r+7)/8)*Math.floor((e+7)/8)*16;case 37816:return Math.floor((r+9)/10)*Math.floor((e+4)/5)*16;case 37817:return Math.floor((r+9)/10)*Math.floor((e+5)/6)*16;case 37818:return Math.floor((r+9)/10)*Math.floor((e+7)/8)*16;case 37819:return Math.floor((r+9)/10)*Math.floor((e+9)/10)*16;case 37820:return Math.floor((r+11)/12)*Math.floor((e+9)/10)*16;case 37821:return Math.floor((r+11)/12)*Math.floor((e+11)/12)*16;case 36492:case 36494:case 36495:return Math.ceil(r/4)*Math.ceil(e/4)*16;case 36283:case 36284:return Math.ceil(r/4)*Math.ceil(e/4)*8;case 36285:case 36286:return Math.ceil(r/4)*Math.ceil(e/4)*16}throw new Error(`Unable to determine texture byte length for ${t} format.`)}typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"183"}})),typeof window<"u"&&(window.__THREE__?Ye("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="183");function Gp(){let r=null,e=!1,t=null,n=null;function i(s,a){t(s,a),n=r.requestAnimationFrame(i)}return{start:function(){e!==!0&&t!==null&&(n=r.requestAnimationFrame(i),e=!0)},stop:function(){r.cancelAnimationFrame(n),e=!1},setAnimationLoop:function(s){t=s},setContext:function(s){r=s}}}function sm(r){let e=new WeakMap;return{get:function(t){return t.isInterleavedBufferAttribute&&(t=t.data),e.get(t)},remove:function(t){t.isInterleavedBufferAttribute&&(t=t.data);let n=e.get(t);n&&(r.deleteBuffer(n.buffer),e.delete(t))},update:function(t,n){if(t.isInterleavedBufferAttribute&&(t=t.data),t.isGLBufferAttribute){let s=e.get(t);return void((!s||s.version<t.version)&&e.set(t,{buffer:t.buffer,type:t.type,bytesPerElement:t.elementSize,version:t.version}))}let i=e.get(t);if(i===void 0)e.set(t,(function(s,a){let o=s.array,c=s.usage,l=o.byteLength,h=r.createBuffer(),p;if(r.bindBuffer(a,h),r.bufferData(a,o,c),s.onUploadCallback(),o instanceof Float32Array)p=r.FLOAT;else if(typeof Float16Array<"u"&&o instanceof Float16Array)p=r.HALF_FLOAT;else if(o instanceof Uint16Array)p=s.isFloat16BufferAttribute?r.HALF_FLOAT:r.UNSIGNED_SHORT;else if(o instanceof Int16Array)p=r.SHORT;else if(o instanceof Uint32Array)p=r.UNSIGNED_INT;else if(o instanceof Int32Array)p=r.INT;else if(o instanceof Int8Array)p=r.BYTE;else if(o instanceof Uint8Array)p=r.UNSIGNED_BYTE;else{if(!(o instanceof Uint8ClampedArray))throw new Error("THREE.WebGLAttributes: Unsupported buffer data format: "+o);p=r.UNSIGNED_BYTE}return{buffer:h,type:p,bytesPerElement:o.BYTES_PER_ELEMENT,version:s.version,size:l}})(t,n));else if(i.version<t.version){if(i.size!==t.array.byteLength)throw new Error("THREE.WebGLAttributes: The size of the buffer attribute's array buffer does not match the original size. Resizing buffer attributes is not supported.");(function(s,a,o){let c=a.array,l=a.updateRanges;if(r.bindBuffer(o,s),l.length===0)r.bufferSubData(o,0,c);else{l.sort((p,f)=>p.start-f.start);let h=0;for(let p=1;p<l.length;p++){let f=l[h],m=l[p];m.start<=f.start+f.count+1?f.count=Math.max(f.count,m.start+m.count-f.start):(++h,l[h]=m)}l.length=h+1;for(let p=0,f=l.length;p<f;p++){let m=l[p];r.bufferSubData(o,m.start*c.BYTES_PER_ELEMENT,c,m.start,m.count)}a.clearUpdateRanges()}a.onUploadCallback()})(i.buffer,t,n),i.version=t.version}}}}var st={alphahash_fragment:`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,alphahash_pars_fragment:`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,alphamap_fragment:`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,alphamap_pars_fragment:`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,alphatest_fragment:`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,alphatest_pars_fragment:`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,aomap_fragment:`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,aomap_pars_fragment:`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,batching_pars_vertex:`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,batching_vertex:`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,begin_vertex:`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,beginnormal_vertex:`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,bsdfs:`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,iridescence_fragment:`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,bumpmap_pars_fragment:`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,clipping_planes_fragment:`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,clipping_planes_pars_fragment:`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,clipping_planes_pars_vertex:`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,clipping_planes_vertex:`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,color_fragment:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,color_pars_fragment:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,color_pars_vertex:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,color_vertex:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,common:`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
vec3 inverseTransformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( vec4( dir, 0.0 ) * matrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,cube_uv_reflection_fragment:`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,defaultnormal_vertex:`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
	#ifdef FLIP_SIDED
		transformedTangent = - transformedTangent;
	#endif
#endif`,displacementmap_pars_vertex:`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,displacementmap_vertex:`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,emissivemap_fragment:`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,emissivemap_pars_fragment:`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,colorspace_fragment:"gl_FragColor = linearToOutputTexel( gl_FragColor );",colorspace_pars_fragment:`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,envmap_fragment:`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = inverseTransformDirection( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * vec3( flipEnvMap * reflectVec.x, reflectVec.yz ) );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,envmap_common_pars_fragment:`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform float flipEnvMap;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,envmap_pars_fragment:`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,envmap_pars_vertex:`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,envmap_physical_pars_fragment:`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = inverseTransformDirection( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = inverseTransformDirection( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
#endif`,envmap_vertex:`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = inverseTransformDirection( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,fog_vertex:`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,fog_pars_vertex:`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,fog_fragment:`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,fog_pars_fragment:`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,gradientmap_pars_fragment:`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,lightmap_pars_fragment:`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,lights_lambert_fragment:`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,lights_lambert_pars_fragment:`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,lights_pars_begin:`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = inverseTransformDirection( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif`,lights_toon_fragment:`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,lights_toon_pars_fragment:`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,lights_phong_fragment:`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,lights_phong_pars_fragment:`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,lights_physical_fragment:`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,lights_physical_pars_fragment:`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0;
		vec3 iridescenceFresnelDielectric;
		vec3 iridescenceFresnelMetallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		float v = 0.5 / ( gv + gl );
		return v;
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
vec3 BRDF_GGX_Multiscatter( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 singleScatter = BRDF_GGX( lightDir, viewDir, normal, material );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 dfgV = texture2D( dfgLUT, vec2( material.roughness, dotNV ) ).rg;
	vec2 dfgL = texture2D( dfgLUT, vec2( material.roughness, dotNL ) ).rg;
	vec3 FssEss_V = material.specularColorBlended * dfgV.x + material.specularF90 * dfgV.y;
	vec3 FssEss_L = material.specularColorBlended * dfgL.x + material.specularF90 * dfgL.y;
	float Ess_V = dfgV.x + dfgV.y;
	float Ess_L = dfgL.x + dfgL.y;
	float Ems_V = 1.0 - Ess_V;
	float Ems_L = 1.0 - Ess_L;
	vec3 Favg = material.specularColorBlended + ( 1.0 - material.specularColorBlended ) * 0.047619;
	vec3 Fms = FssEss_V * FssEss_L * Favg / ( 1.0 - Ems_V * Ems_L * Favg + EPSILON );
	float compensationFactor = Ems_V * Ems_L;
	vec3 multiScatter = Fms * compensationFactor;
	return singleScatter + multiScatter;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	reflectedLight.directSpecular += irradiance * BRDF_GGX_Multiscatter( directLight.direction, geometryViewDir, geometryNormal, material );
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.iridescence, material.iridescenceFresnelDielectric, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceFresnelMetallic, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,lights_fragment_begin:`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		material.iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		material.iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( material.iridescenceFresnelDielectric, material.iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0 = Schlick_to_F0( material.iridescenceFresnel, 1.0, dotNVi );
	}
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,lights_fragment_maps:`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		radiance += getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		radiance += getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,lights_fragment_end:`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,logdepthbuf_fragment:`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,logdepthbuf_pars_fragment:`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,logdepthbuf_pars_vertex:`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,logdepthbuf_vertex:`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,map_fragment:`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,map_pars_fragment:`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,map_particle_fragment:`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,map_particle_pars_fragment:`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,metalnessmap_fragment:`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,metalnessmap_pars_fragment:`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,morphinstance_vertex:`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,morphcolor_vertex:`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,morphnormal_vertex:`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,morphtarget_pars_vertex:`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,morphtarget_vertex:`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,normal_fragment_begin:`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#if defined( DOUBLE_SIDED ) && ! defined( FLAT_SHADED )
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#if defined( DOUBLE_SIDED ) && ! defined( FLAT_SHADED )
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,normal_fragment_maps:`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,normal_pars_fragment:`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,normal_pars_vertex:`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,normal_vertex:`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
	#endif
#endif`,normalmap_pars_fragment:`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,clearcoat_normal_fragment_begin:`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,clearcoat_normal_fragment_maps:`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,clearcoat_pars_fragment:`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,iridescence_pars_fragment:`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,opaque_fragment:`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,packing:`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,premultiplied_alpha_fragment:`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,project_vertex:`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,dithering_fragment:`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,dithering_pars_fragment:`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,roughnessmap_fragment:`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,roughnessmap_pars_fragment:`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,shadowmap_pars_fragment:`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,shadowmap_pars_vertex:`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,shadowmap_vertex:`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	vec3 shadowWorldNormal = inverseTransformDirection( transformedNormal, viewMatrix );
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,shadowmask_pars_fragment:`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,skinbase_vertex:`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,skinning_pars_vertex:`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,skinning_vertex:`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,skinnormal_vertex:`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,specularmap_fragment:`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,specularmap_pars_fragment:`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,tonemapping_fragment:`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,tonemapping_pars_fragment:`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,transmission_fragment:`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = inverseTransformDirection( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,transmission_pars_fragment:`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,uv_pars_fragment:`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,uv_pars_vertex:`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,uv_vertex:`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,worldpos_vertex:`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,background_vert:`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,background_frag:`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,backgroundCube_vert:`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,backgroundCube_frag:`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float flipEnvMap;
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vec3( flipEnvMap * vWorldDirection.x, vWorldDirection.yz ) );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,cube_vert:`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,cube_frag:`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,depth_vert:`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,depth_frag:`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,distance_vert:`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,distance_frag:`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main () {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,equirect_vert:`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,equirect_frag:`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,linedashed_vert:`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,linedashed_frag:`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,meshbasic_vert:`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,meshbasic_frag:`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshlambert_vert:`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,meshlambert_frag:`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshmatcap_vert:`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,meshmatcap_frag:`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshnormal_vert:`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,meshnormal_frag:`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,meshphong_vert:`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,meshphong_frag:`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshphysical_vert:`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,meshphysical_frag:`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshtoon_vert:`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,meshtoon_frag:`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,points_vert:`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,points_frag:`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,shadow_vert:`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,shadow_frag:`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,sprite_vert:`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,sprite_frag:`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`},Ce={common:{diffuse:{value:new He(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new et},alphaMap:{value:null},alphaMapTransform:{value:new et},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new et}},envmap:{envMap:{value:null},envMapRotation:{value:new et},flipEnvMap:{value:-1},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new et}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new et}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new et},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new et},normalScale:{value:new _e(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new et},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new et}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new et}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new et}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new He(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null}},points:{diffuse:{value:new He(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new et},alphaTest:{value:0},uvTransform:{value:new et}},sprite:{diffuse:{value:new He(16777215)},opacity:{value:1},center:{value:new _e(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new et},alphaMap:{value:null},alphaMapTransform:{value:new et},alphaTest:{value:0}}},vi={basic:{uniforms:on([Ce.common,Ce.specularmap,Ce.envmap,Ce.aomap,Ce.lightmap,Ce.fog]),vertexShader:st.meshbasic_vert,fragmentShader:st.meshbasic_frag},lambert:{uniforms:on([Ce.common,Ce.specularmap,Ce.envmap,Ce.aomap,Ce.lightmap,Ce.emissivemap,Ce.bumpmap,Ce.normalmap,Ce.displacementmap,Ce.fog,Ce.lights,{emissive:{value:new He(0)},envMapIntensity:{value:1}}]),vertexShader:st.meshlambert_vert,fragmentShader:st.meshlambert_frag},phong:{uniforms:on([Ce.common,Ce.specularmap,Ce.envmap,Ce.aomap,Ce.lightmap,Ce.emissivemap,Ce.bumpmap,Ce.normalmap,Ce.displacementmap,Ce.fog,Ce.lights,{emissive:{value:new He(0)},specular:{value:new He(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:st.meshphong_vert,fragmentShader:st.meshphong_frag},standard:{uniforms:on([Ce.common,Ce.envmap,Ce.aomap,Ce.lightmap,Ce.emissivemap,Ce.bumpmap,Ce.normalmap,Ce.displacementmap,Ce.roughnessmap,Ce.metalnessmap,Ce.fog,Ce.lights,{emissive:{value:new He(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:st.meshphysical_vert,fragmentShader:st.meshphysical_frag},toon:{uniforms:on([Ce.common,Ce.aomap,Ce.lightmap,Ce.emissivemap,Ce.bumpmap,Ce.normalmap,Ce.displacementmap,Ce.gradientmap,Ce.fog,Ce.lights,{emissive:{value:new He(0)}}]),vertexShader:st.meshtoon_vert,fragmentShader:st.meshtoon_frag},matcap:{uniforms:on([Ce.common,Ce.bumpmap,Ce.normalmap,Ce.displacementmap,Ce.fog,{matcap:{value:null}}]),vertexShader:st.meshmatcap_vert,fragmentShader:st.meshmatcap_frag},points:{uniforms:on([Ce.points,Ce.fog]),vertexShader:st.points_vert,fragmentShader:st.points_frag},dashed:{uniforms:on([Ce.common,Ce.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:st.linedashed_vert,fragmentShader:st.linedashed_frag},depth:{uniforms:on([Ce.common,Ce.displacementmap]),vertexShader:st.depth_vert,fragmentShader:st.depth_frag},normal:{uniforms:on([Ce.common,Ce.bumpmap,Ce.normalmap,Ce.displacementmap,{opacity:{value:1}}]),vertexShader:st.meshnormal_vert,fragmentShader:st.meshnormal_frag},sprite:{uniforms:on([Ce.sprite,Ce.fog]),vertexShader:st.sprite_vert,fragmentShader:st.sprite_frag},background:{uniforms:{uvTransform:{value:new et},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:st.background_vert,fragmentShader:st.background_frag},backgroundCube:{uniforms:{envMap:{value:null},flipEnvMap:{value:-1},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new et}},vertexShader:st.backgroundCube_vert,fragmentShader:st.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:st.cube_vert,fragmentShader:st.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:st.equirect_vert,fragmentShader:st.equirect_frag},distance:{uniforms:on([Ce.common,Ce.displacementmap,{referencePosition:{value:new D},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:st.distance_vert,fragmentShader:st.distance_frag},shadow:{uniforms:on([Ce.lights,Ce.fog,{color:{value:new He(0)},opacity:{value:1}}]),vertexShader:st.shadow_vert,fragmentShader:st.shadow_frag}};vi.physical={uniforms:on([vi.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new et},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new et},clearcoatNormalScale:{value:new _e(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new et},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new et},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new et},sheen:{value:0},sheenColor:{value:new He(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new et},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new et},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new et},transmissionSamplerSize:{value:new _e},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new et},attenuationDistance:{value:0},attenuationColor:{value:new He(0)},specularColor:{value:new He(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new et},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new et},anisotropyVector:{value:new _e},anisotropyMap:{value:null},anisotropyMapTransform:{value:new et}}]),vertexShader:st.meshphysical_vert,fragmentShader:st.meshphysical_frag};var Bl={r:0,b:0,g:0},xr=new Un,am=new Ke;function om(r,e,t,n,i,s){let a=new He(0),o,c,l=i===!0?0:1,h=null,p=0,f=null;function m(g){let x=g.isScene===!0?g.background:null;if(x&&x.isTexture){let _=g.backgroundBlurriness>0;x=e.get(x,_)}return x}function u(g,x){g.getRGB(Bl,nu(r)),t.buffers.color.setClear(Bl.r,Bl.g,Bl.b,x,s)}return{getClearColor:function(){return a},setClearColor:function(g,x=1){a.set(g),l=x,u(a,l)},getClearAlpha:function(){return l},setClearAlpha:function(g){l=g,u(a,l)},render:function(g){let x=!1,_=m(g);_===null?u(a,l):_&&_.isColor&&(u(_,1),x=!0);let v=r.xr.getEnvironmentBlendMode();v==="additive"?t.buffers.color.setClear(0,0,0,1,s):v==="alpha-blend"&&t.buffers.color.setClear(0,0,0,0,s),(r.autoClear||x)&&(t.buffers.depth.setTest(!0),t.buffers.depth.setMask(!0),t.buffers.color.setMask(!0),r.clear(r.autoClearColor,r.autoClearDepth,r.autoClearStencil))},addToRenderList:function(g,x){let _=m(x);_&&(_.isCubeTexture||_.mapping===wa)?(c===void 0&&(c=new At(new Nn(1,1,1),new Bn({name:"BackgroundCubeMaterial",uniforms:yr(vi.backgroundCube.uniforms),vertexShader:vi.backgroundCube.vertexShader,fragmentShader:vi.backgroundCube.fragmentShader,side:Tn,depthTest:!1,depthWrite:!1,fog:!1,allowOverride:!1})),c.geometry.deleteAttribute("normal"),c.geometry.deleteAttribute("uv"),c.onBeforeRender=function(v,S,E){this.matrixWorld.copyPosition(E.matrixWorld)},Object.defineProperty(c.material,"envMap",{get:function(){return this.uniforms.envMap.value}}),n.update(c)),xr.copy(x.backgroundRotation),xr.x*=-1,xr.y*=-1,xr.z*=-1,_.isCubeTexture&&_.isRenderTargetTexture===!1&&(xr.y*=-1,xr.z*=-1),c.material.uniforms.envMap.value=_,c.material.uniforms.flipEnvMap.value=_.isCubeTexture&&_.isRenderTargetTexture===!1?-1:1,c.material.uniforms.backgroundBlurriness.value=x.backgroundBlurriness,c.material.uniforms.backgroundIntensity.value=x.backgroundIntensity,c.material.uniforms.backgroundRotation.value.setFromMatrix4(am.makeRotationFromEuler(xr)),c.material.toneMapped=ut.getTransfer(_.colorSpace)!==gt,h===_&&p===_.version&&f===r.toneMapping||(c.material.needsUpdate=!0,h=_,p=_.version,f=r.toneMapping),c.layers.enableAll(),g.unshift(c,c.geometry,c.material,0,0,null)):_&&_.isTexture&&(o===void 0&&(o=new At(new Fn(2,2),new Bn({name:"BackgroundMaterial",uniforms:yr(vi.background.uniforms),vertexShader:vi.background.vertexShader,fragmentShader:vi.background.fragmentShader,side:fs,depthTest:!1,depthWrite:!1,fog:!1,allowOverride:!1})),o.geometry.deleteAttribute("normal"),Object.defineProperty(o.material,"map",{get:function(){return this.uniforms.t2D.value}}),n.update(o)),o.material.uniforms.t2D.value=_,o.material.uniforms.backgroundIntensity.value=x.backgroundIntensity,o.material.toneMapped=ut.getTransfer(_.colorSpace)!==gt,_.matrixAutoUpdate===!0&&_.updateMatrix(),o.material.uniforms.uvTransform.value.copy(_.matrix),h===_&&p===_.version&&f===r.toneMapping||(o.material.needsUpdate=!0,h=_,p=_.version,f=r.toneMapping),o.layers.enableAll(),g.unshift(o,o.geometry,o.material,0,0,null))},dispose:function(){c!==void 0&&(c.geometry.dispose(),c.material.dispose(),c=void 0),o!==void 0&&(o.geometry.dispose(),o.material.dispose(),o=void 0)}}}function lm(r,e){let t=r.getParameter(r.MAX_VERTEX_ATTRIBS),n={},i=l(null),s=i,a=!1;function o(_){return r.bindVertexArray(_)}function c(_){return r.deleteVertexArray(_)}function l(_){let v=[],S=[],E=[];for(let w=0;w<t;w++)v[w]=0,S[w]=0,E[w]=0;return{geometry:null,program:null,wireframe:!1,newAttributes:v,enabledAttributes:S,attributeDivisors:E,object:_,attributes:{},index:null}}function h(){let _=s.newAttributes;for(let v=0,S=_.length;v<S;v++)_[v]=0}function p(_){f(_,0)}function f(_,v){let S=s.newAttributes,E=s.enabledAttributes,w=s.attributeDivisors;S[_]=1,E[_]===0&&(r.enableVertexAttribArray(_),E[_]=1),w[_]!==v&&(r.vertexAttribDivisor(_,v),w[_]=v)}function m(){let _=s.newAttributes,v=s.enabledAttributes;for(let S=0,E=v.length;S<E;S++)v[S]!==_[S]&&(r.disableVertexAttribArray(S),v[S]=0)}function u(_,v,S,E,w,R,z){z===!0?r.vertexAttribIPointer(_,v,S,w,R):r.vertexAttribPointer(_,v,S,E,w,R)}function g(){x(),a=!0,s!==i&&(s=i,o(s.object))}function x(){i.geometry=null,i.program=null,i.wireframe=!1}return{setup:function(_,v,S,E,w){let R=!1,z=(function(j,O,Q,Y){let k=Y.wireframe===!0,X=n[O.id];X===void 0&&(X={},n[O.id]=X);let K=j.isInstancedMesh===!0?j.id:0,te=X[K];te===void 0&&(te={},X[K]=te);let oe=te[Q.id];oe===void 0&&(oe={},te[Q.id]=oe);let ee=oe[k];return ee===void 0&&(ee=l(r.createVertexArray()),oe[k]=ee),ee})(_,E,S,v);s!==z&&(s=z,o(s.object)),R=(function(j,O,Q,Y){let k=s.attributes,X=O.attributes,K=0,te=Q.getAttributes();for(let oe in te)if(te[oe].location>=0){let ee=k[oe],xe=X[oe];if(xe===void 0&&(oe==="instanceMatrix"&&j.instanceMatrix&&(xe=j.instanceMatrix),oe==="instanceColor"&&j.instanceColor&&(xe=j.instanceColor)),ee===void 0||ee.attribute!==xe||xe&&ee.data!==xe.data)return!0;K++}return s.attributesNum!==K||s.index!==Y})(_,E,S,w),R&&(function(j,O,Q,Y){let k={},X=O.attributes,K=0,te=Q.getAttributes();for(let oe in te)if(te[oe].location>=0){let ee=X[oe];ee===void 0&&(oe==="instanceMatrix"&&j.instanceMatrix&&(ee=j.instanceMatrix),oe==="instanceColor"&&j.instanceColor&&(ee=j.instanceColor));let xe={};xe.attribute=ee,ee&&ee.data&&(xe.data=ee.data),k[oe]=xe,K++}s.attributes=k,s.attributesNum=K,s.index=Y})(_,E,S,w),w!==null&&e.update(w,r.ELEMENT_ARRAY_BUFFER),(R||a)&&(a=!1,(function(j,O,Q,Y){h();let k=Y.attributes,X=Q.getAttributes(),K=O.defaultAttributeValues;for(let te in X){let oe=X[te];if(oe.location>=0){let ee=k[te];if(ee===void 0&&(te==="instanceMatrix"&&j.instanceMatrix&&(ee=j.instanceMatrix),te==="instanceColor"&&j.instanceColor&&(ee=j.instanceColor)),ee!==void 0){let xe=ee.normalized,be=ee.itemSize,we=e.get(ee);if(we===void 0)continue;let Se=we.buffer,se=we.type,de=we.bytesPerElement,ge=se===r.INT||se===r.UNSIGNED_INT||ee.gpuType===Al;if(ee.isInterleavedBufferAttribute){let Te=ee.data,Re=Te.stride,ze=ee.offset;if(Te.isInstancedInterleavedBuffer){for(let L=0;L<oe.locationSize;L++)f(oe.location+L,Te.meshPerAttribute);j.isInstancedMesh!==!0&&Y._maxInstanceCount===void 0&&(Y._maxInstanceCount=Te.meshPerAttribute*Te.count)}else for(let L=0;L<oe.locationSize;L++)p(oe.location+L);r.bindBuffer(r.ARRAY_BUFFER,Se);for(let L=0;L<oe.locationSize;L++)u(oe.location+L,be/oe.locationSize,se,xe,Re*de,(ze+be/oe.locationSize*L)*de,ge)}else{if(ee.isInstancedBufferAttribute){for(let Te=0;Te<oe.locationSize;Te++)f(oe.location+Te,ee.meshPerAttribute);j.isInstancedMesh!==!0&&Y._maxInstanceCount===void 0&&(Y._maxInstanceCount=ee.meshPerAttribute*ee.count)}else for(let Te=0;Te<oe.locationSize;Te++)p(oe.location+Te);r.bindBuffer(r.ARRAY_BUFFER,Se);for(let Te=0;Te<oe.locationSize;Te++)u(oe.location+Te,be/oe.locationSize,se,xe,be*de,be/oe.locationSize*Te*de,ge)}}else if(K!==void 0){let xe=K[te];if(xe!==void 0)switch(xe.length){case 2:r.vertexAttrib2fv(oe.location,xe);break;case 3:r.vertexAttrib3fv(oe.location,xe);break;case 4:r.vertexAttrib4fv(oe.location,xe);break;default:r.vertexAttrib1fv(oe.location,xe)}}}}m()})(_,v,S,E),w!==null&&r.bindBuffer(r.ELEMENT_ARRAY_BUFFER,e.get(w).buffer))},reset:g,resetDefaultState:x,dispose:function(){g();for(let _ in n){let v=n[_];for(let S in v){let E=v[S];for(let w in E){let R=E[w];for(let z in R)c(R[z].object),delete R[z];delete E[w]}}delete n[_]}},releaseStatesOfGeometry:function(_){if(n[_.id]===void 0)return;let v=n[_.id];for(let S in v){let E=v[S];for(let w in E){let R=E[w];for(let z in R)c(R[z].object),delete R[z];delete E[w]}}delete n[_.id]},releaseStatesOfObject:function(_){for(let v in n){let S=n[v],E=_.isInstancedMesh===!0?_.id:0,w=S[E];if(w!==void 0){for(let R in w){let z=w[R];for(let j in z)c(z[j].object),delete z[j];delete w[R]}delete S[E],Object.keys(S).length===0&&delete n[v]}}},releaseStatesOfProgram:function(_){for(let v in n){let S=n[v];for(let E in S){let w=S[E];if(w[_.id]===void 0)continue;let R=w[_.id];for(let z in R)c(R[z].object),delete R[z];delete w[_.id]}}},initAttributes:h,enableAttribute:p,disableUnusedAttributes:m}}function cm(r,e,t){let n;function i(s,a,o){o!==0&&(r.drawArraysInstanced(n,s,a,o),t.update(a,n,o))}this.setMode=function(s){n=s},this.render=function(s,a){r.drawArrays(n,s,a),t.update(a,n,1)},this.renderInstances=i,this.renderMultiDraw=function(s,a,o){if(o===0)return;e.get("WEBGL_multi_draw").multiDrawArraysWEBGL(n,s,0,a,0,o);let c=0;for(let l=0;l<o;l++)c+=a[l];t.update(c,n,1)},this.renderMultiDrawInstances=function(s,a,o,c){if(o===0)return;let l=e.get("WEBGL_multi_draw");if(l===null)for(let h=0;h<s.length;h++)i(s[h],a[h],c[h]);else{l.multiDrawArraysInstancedWEBGL(n,s,0,a,0,c,0,o);let h=0;for(let p=0;p<o;p++)h+=a[p]*c[p];t.update(h,n,1)}}}function hm(r,e,t,n){let i;function s(c){if(c==="highp"){if(r.getShaderPrecisionFormat(r.VERTEX_SHADER,r.HIGH_FLOAT).precision>0&&r.getShaderPrecisionFormat(r.FRAGMENT_SHADER,r.HIGH_FLOAT).precision>0)return"highp";c="mediump"}return c==="mediump"&&r.getShaderPrecisionFormat(r.VERTEX_SHADER,r.MEDIUM_FLOAT).precision>0&&r.getShaderPrecisionFormat(r.FRAGMENT_SHADER,r.MEDIUM_FLOAT).precision>0?"mediump":"lowp"}let a=t.precision!==void 0?t.precision:"highp",o=s(a);return o!==a&&(Ye("WebGLRenderer:",a,"not supported, using",o,"instead."),a=o),{isWebGL2:!0,getMaxAnisotropy:function(){if(i!==void 0)return i;if(e.has("EXT_texture_filter_anisotropic")===!0){let c=e.get("EXT_texture_filter_anisotropic");i=r.getParameter(c.MAX_TEXTURE_MAX_ANISOTROPY_EXT)}else i=0;return i},getMaxPrecision:s,textureFormatReadable:function(c){return c===ai||n.convert(c)===r.getParameter(r.IMPLEMENTATION_COLOR_READ_FORMAT)},textureTypeReadable:function(c){let l=c===gi&&(e.has("EXT_color_buffer_half_float")||e.has("EXT_color_buffer_float"));return!(c!==zn&&n.convert(c)!==r.getParameter(r.IMPLEMENTATION_COLOR_READ_TYPE)&&c!==Kn&&!l)},precision:a,logarithmicDepthBuffer:t.logarithmicDepthBuffer===!0,reversedDepthBuffer:t.reversedDepthBuffer===!0&&e.has("EXT_clip_control"),maxTextures:r.getParameter(r.MAX_TEXTURE_IMAGE_UNITS),maxVertexTextures:r.getParameter(r.MAX_VERTEX_TEXTURE_IMAGE_UNITS),maxTextureSize:r.getParameter(r.MAX_TEXTURE_SIZE),maxCubemapSize:r.getParameter(r.MAX_CUBE_MAP_TEXTURE_SIZE),maxAttributes:r.getParameter(r.MAX_VERTEX_ATTRIBS),maxVertexUniforms:r.getParameter(r.MAX_VERTEX_UNIFORM_VECTORS),maxVaryings:r.getParameter(r.MAX_VARYING_VECTORS),maxFragmentUniforms:r.getParameter(r.MAX_FRAGMENT_UNIFORM_VECTORS),maxSamples:r.getParameter(r.MAX_SAMPLES),samples:r.getParameter(r.SAMPLES)}}function um(r){let e=this,t=null,n=0,i=!1,s=!1,a=new Zt,o=new et,c={value:null,needsUpdate:!1};function l(h,p,f,m){let u=h!==null?h.length:0,g=null;if(u!==0){if(g=c.value,m!==!0||g===null){let x=f+4*u,_=p.matrixWorldInverse;o.getNormalMatrix(_),(g===null||g.length<x)&&(g=new Float32Array(x));for(let v=0,S=f;v!==u;++v,S+=4)a.copy(h[v]).applyMatrix4(_,o),a.normal.toArray(g,S),g[S+3]=a.constant}c.value=g,c.needsUpdate=!0}return e.numPlanes=u,e.numIntersection=0,g}this.uniform=c,this.numPlanes=0,this.numIntersection=0,this.init=function(h,p){let f=h.length!==0||p||n!==0||i;return i=p,n=h.length,f},this.beginShadows=function(){s=!0,l(null)},this.endShadows=function(){s=!1},this.setGlobalState=function(h,p){t=l(h,p,0)},this.setState=function(h,p,f){let m=h.clippingPlanes,u=h.clipIntersection,g=h.clipShadows,x=r.get(h);if(!i||m===null||m.length===0||s&&!g)s?l(null):(function(){c.value!==t&&(c.value=t,c.needsUpdate=n>0),e.numPlanes=n,e.numIntersection=0})();else{let _=s?0:n,v=4*_,S=x.clippingState||null;c.value=S,S=l(m,p,v,f);for(let E=0;E!==v;++E)S[E]=t[E];x.clippingState=S,this.numIntersection=u?this.numPlanes:0,this.numPlanes+=_}}}var xp=[.125,.215,.35,.446,.526,.582],Ca=20,Ra=new cs,Mp=new He,su=null,au=0,ou=0,lu=!1,dm=new D,kl=class{constructor(e){this._renderer=e,this._pingPongRenderTarget=null,this._lodMax=0,this._cubeSize=0,this._sizeLods=[],this._sigmas=[],this._lodMeshes=[],this._backgroundBox=null,this._cubemapMaterial=null,this._equirectMaterial=null,this._blurMaterial=null,this._ggxMaterial=null}fromScene(e,t=0,n=.1,i=100,s={}){let{size:a=256,position:o=dm}=s;su=this._renderer.getRenderTarget(),au=this._renderer.getActiveCubeFace(),ou=this._renderer.getActiveMipmapLevel(),lu=this._renderer.xr.enabled,this._renderer.xr.enabled=!1,this._setSize(a);let c=this._allocateTargets();return c.depthBuffer=!0,this._sceneToCubeUV(e,n,i,c,o),t>0&&this._blur(c,0,0,t),this._applyPMREM(c),this._cleanup(c),c}fromEquirectangular(e,t=null){return this._fromTexture(e,t)}fromCubemap(e,t=null){return this._fromTexture(e,t)}compileCubemapShader(){this._cubemapMaterial===null&&(this._cubemapMaterial=Tp(),this._compileMaterial(this._cubemapMaterial))}compileEquirectangularShader(){this._equirectMaterial===null&&(this._equirectMaterial=Sp(),this._compileMaterial(this._equirectMaterial))}dispose(){this._dispose(),this._cubemapMaterial!==null&&this._cubemapMaterial.dispose(),this._equirectMaterial!==null&&this._equirectMaterial.dispose(),this._backgroundBox!==null&&(this._backgroundBox.geometry.dispose(),this._backgroundBox.material.dispose())}_setSize(e){this._lodMax=Math.floor(Math.log2(e)),this._cubeSize=Math.pow(2,this._lodMax)}_dispose(){this._blurMaterial!==null&&this._blurMaterial.dispose(),this._ggxMaterial!==null&&this._ggxMaterial.dispose(),this._pingPongRenderTarget!==null&&this._pingPongRenderTarget.dispose();for(let e=0;e<this._lodMeshes.length;e++)this._lodMeshes[e].geometry.dispose()}_cleanup(e){this._renderer.setRenderTarget(su,au,ou),this._renderer.xr.enabled=lu,e.scissorTest=!1,xs(e,0,0,e.width,e.height)}_fromTexture(e,t){e.mapping===gs||e.mapping===fr?this._setSize(e.image.length===0?16:e.image[0].width||e.image[0].image.width):this._setSize(e.image.width/4),su=this._renderer.getRenderTarget(),au=this._renderer.getActiveCubeFace(),ou=this._renderer.getActiveMipmapLevel(),lu=this._renderer.xr.enabled,this._renderer.xr.enabled=!1;let n=t||this._allocateTargets();return this._textureToCubeUV(e,n),this._applyPMREM(n),this._cleanup(n),n}_allocateTargets(){let e=3*Math.max(this._cubeSize,112),t=4*this._cubeSize,n={magFilter:Xt,minFilter:Xt,generateMipmaps:!1,type:gi,format:ai,colorSpace:ur,depthBuffer:!1},i=bp(e,t,n);if(this._pingPongRenderTarget===null||this._pingPongRenderTarget.width!==e||this._pingPongRenderTarget.height!==t){this._pingPongRenderTarget!==null&&this._dispose(),this._pingPongRenderTarget=bp(e,t,n);let{_lodMax:s}=this;({lodMeshes:this._lodMeshes,sizeLods:this._sizeLods,sigmas:this._sigmas}=(function(a){let o=[],c=[],l=[],h=a,p=a-4+1+xp.length;for(let f=0;f<p;f++){let m=Math.pow(2,h);o.push(m);let u=1/m;f>a-4?u=xp[f-a+4-1]:f===0&&(u=0),c.push(u);let g=1/(m-2),x=-g,_=1+g,v=[x,x,_,x,_,_,x,x,_,_,x,_],S=6,E=6,w=3,R=2,z=1,j=new Float32Array(w*E*S),O=new Float32Array(R*E*S),Q=new Float32Array(z*E*S);for(let k=0;k<S;k++){let X=k%3*2/3-1,K=k>2?0:-1,te=[X,K,0,X+2/3,K,0,X+2/3,K+1,0,X,K,0,X+2/3,K+1,0,X,K+1,0];j.set(te,w*E*k),O.set(v,R*E*k);let oe=[k,k,k,k,k,k];Q.set(oe,z*E*k)}let Y=new bt;Y.setAttribute("position",new _n(j,w)),Y.setAttribute("uv",new _n(O,R)),Y.setAttribute("faceIndex",new _n(Q,z)),l.push(new At(Y,null)),h>4&&h--}return{lodMeshes:l,sizeLods:o,sigmas:c}})(s)),this._blurMaterial=(function(a,o,c){let l=new Float32Array(Ca),h=new D(0,1,0);return new Bn({name:"SphericalGaussianBlur",defines:{n:Ca,CUBEUV_TEXEL_WIDTH:1/o,CUBEUV_TEXEL_HEIGHT:1/c,CUBEUV_MAX_MIP:`${a}.0`},uniforms:{envMap:{value:null},samples:{value:1},weights:{value:l},latitudinal:{value:!1},dTheta:{value:0},mipInt:{value:0},poleAxis:{value:h}},vertexShader:Vl(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform int samples;
			uniform float weights[ n ];
			uniform bool latitudinal;
			uniform float dTheta;
			uniform float mipInt;
			uniform vec3 poleAxis;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			vec3 getSample( float theta, vec3 axis ) {

				float cosTheta = cos( theta );
				// Rodrigues' axis-angle rotation
				vec3 sampleDirection = vOutputDirection * cosTheta
					+ cross( axis, vOutputDirection ) * sin( theta )
					+ axis * dot( axis, vOutputDirection ) * ( 1.0 - cosTheta );

				return bilinearCubeUV( envMap, sampleDirection, mipInt );

			}

			void main() {

				vec3 axis = latitudinal ? poleAxis : cross( poleAxis, vOutputDirection );

				if ( all( equal( axis, vec3( 0.0 ) ) ) ) {

					axis = vec3( vOutputDirection.z, 0.0, - vOutputDirection.x );

				}

				axis = normalize( axis );

				gl_FragColor = vec4( 0.0, 0.0, 0.0, 1.0 );
				gl_FragColor.rgb += weights[ 0 ] * getSample( 0.0, axis );

				for ( int i = 1; i < n; i++ ) {

					if ( i >= samples ) {

						break;

					}

					float theta = dTheta * float( i );
					gl_FragColor.rgb += weights[ i ] * getSample( -1.0 * theta, axis );
					gl_FragColor.rgb += weights[ i ] * getSample( theta, axis );

				}

			}
		`,blending:mi,depthTest:!1,depthWrite:!1})})(s,e,t),this._ggxMaterial=(function(a,o,c){return new Bn({name:"PMREMGGXConvolution",defines:{GGX_SAMPLES:256,CUBEUV_TEXEL_WIDTH:1/o,CUBEUV_TEXEL_HEIGHT:1/c,CUBEUV_MAX_MIP:`${a}.0`},uniforms:{envMap:{value:null},roughness:{value:0},mipInt:{value:0}},vertexShader:Vl(),fragmentShader:`

			precision highp float;
			precision highp int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform float roughness;
			uniform float mipInt;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			#define PI 3.14159265359

			// Van der Corput radical inverse
			float radicalInverse_VdC(uint bits) {
				bits = (bits << 16u) | (bits >> 16u);
				bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);
				bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);
				bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);
				bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);
				return float(bits) * 2.3283064365386963e-10; // / 0x100000000
			}

			// Hammersley sequence
			vec2 hammersley(uint i, uint N) {
				return vec2(float(i) / float(N), radicalInverse_VdC(i));
			}

			// GGX VNDF importance sampling (Eric Heitz 2018)
			// "Sampling the GGX Distribution of Visible Normals"
			// https://jcgt.org/published/0007/04/01/
			vec3 importanceSampleGGX_VNDF(vec2 Xi, vec3 V, float roughness) {
				float alpha = roughness * roughness;

				// Section 4.1: Orthonormal basis
				vec3 T1 = vec3(1.0, 0.0, 0.0);
				vec3 T2 = cross(V, T1);

				// Section 4.2: Parameterization of projected area
				float r = sqrt(Xi.x);
				float phi = 2.0 * PI * Xi.y;
				float t1 = r * cos(phi);
				float t2 = r * sin(phi);
				float s = 0.5 * (1.0 + V.z);
				t2 = (1.0 - s) * sqrt(1.0 - t1 * t1) + s * t2;

				// Section 4.3: Reprojection onto hemisphere
				vec3 Nh = t1 * T1 + t2 * T2 + sqrt(max(0.0, 1.0 - t1 * t1 - t2 * t2)) * V;

				// Section 3.4: Transform back to ellipsoid configuration
				return normalize(vec3(alpha * Nh.x, alpha * Nh.y, max(0.0, Nh.z)));
			}

			void main() {
				vec3 N = normalize(vOutputDirection);
				vec3 V = N; // Assume view direction equals normal for pre-filtering

				vec3 prefilteredColor = vec3(0.0);
				float totalWeight = 0.0;

				// For very low roughness, just sample the environment directly
				if (roughness < 0.001) {
					gl_FragColor = vec4(bilinearCubeUV(envMap, N, mipInt), 1.0);
					return;
				}

				// Tangent space basis for VNDF sampling
				vec3 up = abs(N.z) < 0.999 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
				vec3 tangent = normalize(cross(up, N));
				vec3 bitangent = cross(N, tangent);

				for(uint i = 0u; i < uint(GGX_SAMPLES); i++) {
					vec2 Xi = hammersley(i, uint(GGX_SAMPLES));

					// For PMREM, V = N, so in tangent space V is always (0, 0, 1)
					vec3 H_tangent = importanceSampleGGX_VNDF(Xi, vec3(0.0, 0.0, 1.0), roughness);

					// Transform H back to world space
					vec3 H = normalize(tangent * H_tangent.x + bitangent * H_tangent.y + N * H_tangent.z);
					vec3 L = normalize(2.0 * dot(V, H) * H - V);

					float NdotL = max(dot(N, L), 0.0);

					if(NdotL > 0.0) {
						// Sample environment at fixed mip level
						// VNDF importance sampling handles the distribution filtering
						vec3 sampleColor = bilinearCubeUV(envMap, L, mipInt);

						// Weight by NdotL for the split-sum approximation
						// VNDF PDF naturally accounts for the visible microfacet distribution
						prefilteredColor += sampleColor * NdotL;
						totalWeight += NdotL;
					}
				}

				if (totalWeight > 0.0) {
					prefilteredColor = prefilteredColor / totalWeight;
				}

				gl_FragColor = vec4(prefilteredColor, 1.0);
			}
		`,blending:mi,depthTest:!1,depthWrite:!1})})(s,e,t)}return i}_compileMaterial(e){let t=new At(new bt,e);this._renderer.compile(t,Ra)}_sceneToCubeUV(e,t,n,i,s){let a=new Jt(90,1,t,n),o=[1,-1,1,1,1,1],c=[1,1,1,-1,-1,-1],l=this._renderer,h=l.autoClear,p=l.toneMapping;l.getClearColor(Mp),l.toneMapping=si,l.autoClear=!1,l.state.buffers.depth.getReversed()&&(l.setRenderTarget(i),l.clearDepth(),l.setRenderTarget(null)),this._backgroundBox===null&&(this._backgroundBox=new At(new Nn,new Jn({name:"PMREM.Background",side:Tn,depthWrite:!1,depthTest:!1})));let f=this._backgroundBox,m=f.material,u=!1,g=e.background;g?g.isColor&&(m.color.copy(g),e.background=null,u=!0):(m.color.copy(Mp),u=!0);for(let x=0;x<6;x++){let _=x%3;_===0?(a.up.set(0,o[x],0),a.position.set(s.x,s.y,s.z),a.lookAt(s.x+c[x],s.y,s.z)):_===1?(a.up.set(0,0,o[x]),a.position.set(s.x,s.y,s.z),a.lookAt(s.x,s.y+c[x],s.z)):(a.up.set(0,o[x],0),a.position.set(s.x,s.y,s.z),a.lookAt(s.x,s.y,s.z+c[x]));let v=this._cubeSize;xs(i,_*v,x>2?v:0,v,v),l.setRenderTarget(i),u&&l.render(f,a),l.render(e,a)}l.toneMapping=p,l.autoClear=h,e.background=g}_textureToCubeUV(e,t){let n=this._renderer,i=e.mapping===gs||e.mapping===fr;i?(this._cubemapMaterial===null&&(this._cubemapMaterial=Tp()),this._cubemapMaterial.uniforms.flipEnvMap.value=e.isRenderTargetTexture===!1?-1:1):this._equirectMaterial===null&&(this._equirectMaterial=Sp());let s=i?this._cubemapMaterial:this._equirectMaterial,a=this._lodMeshes[0];a.material=s,s.uniforms.envMap.value=e;let o=this._cubeSize;xs(t,0,0,3*o,2*o),n.setRenderTarget(t),n.render(a,Ra)}_applyPMREM(e){let t=this._renderer,n=t.autoClear;t.autoClear=!1;let i=this._lodMeshes.length;for(let s=1;s<i;s++)this._applyGGXFilter(e,s-1,s);t.autoClear=n}_applyGGXFilter(e,t,n){let i=this._renderer,s=this._pingPongRenderTarget,a=this._ggxMaterial,o=this._lodMeshes[n];o.material=a;let c=a.uniforms,l=n/(this._lodMeshes.length-1),h=t/(this._lodMeshes.length-1),p=Math.sqrt(l*l-h*h)*(0+1.25*l),{_lodMax:f}=this,m=this._sizeLods[n],u=3*m*(n>f-4?n-f+4:0),g=4*(this._cubeSize-m);c.envMap.value=e.texture,c.roughness.value=p,c.mipInt.value=f-t,xs(s,u,g,3*m,2*m),i.setRenderTarget(s),i.render(o,Ra),c.envMap.value=s.texture,c.roughness.value=0,c.mipInt.value=f-n,xs(e,u,g,3*m,2*m),i.setRenderTarget(e),i.render(o,Ra)}_blur(e,t,n,i,s){let a=this._pingPongRenderTarget;this._halfBlur(e,a,t,n,i,"latitudinal",s),this._halfBlur(a,e,n,n,i,"longitudinal",s)}_halfBlur(e,t,n,i,s,a,o){let c=this._renderer,l=this._blurMaterial;a!=="latitudinal"&&a!=="longitudinal"&&Je("blur direction must be either latitudinal or longitudinal!");let h=this._lodMeshes[i];h.material=l;let p=l.uniforms,f=this._sizeLods[n]-1,m=isFinite(s)?Math.PI/(2*f):2*Math.PI/39,u=s/m,g=isFinite(s)?1+Math.floor(3*u):Ca;g>Ca&&Ye(`sigmaRadians, ${s}, is too large and will clip, as it requested ${g} samples when the maximum is set to 20`);let x=[],_=0;for(let E=0;E<Ca;++E){let w=E/u,R=Math.exp(-w*w/2);x.push(R),E===0?_+=R:E<g&&(_+=2*R)}for(let E=0;E<x.length;E++)x[E]=x[E]/_;p.envMap.value=e.texture,p.samples.value=g,p.weights.value=x,p.latitudinal.value=a==="latitudinal",o&&(p.poleAxis.value=o);let{_lodMax:v}=this;p.dTheta.value=m,p.mipInt.value=v-n;let S=this._sizeLods[i];xs(t,3*S*(i>v-4?i-v+4:0),4*(this._cubeSize-S),3*S,2*S),c.setRenderTarget(t),c.render(h,Ra)}};function bp(r,e,t){let n=new Dn(r,e,t);return n.texture.mapping=wa,n.texture.name="PMREM.cubeUv",n.scissorTest=!0,n}function xs(r,e,t,n,i){r.viewport.set(e,t,n,i),r.scissor.set(e,t,n,i)}function Sp(){return new Bn({name:"EquirectangularToCubeUV",uniforms:{envMap:{value:null}},vertexShader:Vl(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;

			#include <common>

			void main() {

				vec3 outputDirection = normalize( vOutputDirection );
				vec2 uv = equirectUv( outputDirection );

				gl_FragColor = vec4( texture2D ( envMap, uv ).rgb, 1.0 );

			}
		`,blending:mi,depthTest:!1,depthWrite:!1})}function Tp(){return new Bn({name:"CubemapToCubeUV",uniforms:{envMap:{value:null},flipEnvMap:{value:-1}},vertexShader:Vl(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			uniform float flipEnvMap;

			varying vec3 vOutputDirection;

			uniform samplerCube envMap;

			void main() {

				gl_FragColor = textureCube( envMap, vec3( flipEnvMap * vOutputDirection.x, vOutputDirection.yz ) );

			}
		`,blending:mi,depthTest:!1,depthWrite:!1})}function Vl(){return`

		precision mediump float;
		precision mediump int;

		attribute float faceIndex;

		varying vec3 vOutputDirection;

		// RH coordinate system; PMREM face-indexing convention
		vec3 getDirection( vec2 uv, float face ) {

			uv = 2.0 * uv - 1.0;

			vec3 direction = vec3( uv, 1.0 );

			if ( face == 0.0 ) {

				direction = direction.zyx; // ( 1, v, u ) pos x

			} else if ( face == 1.0 ) {

				direction = direction.xzy;
				direction.xz *= -1.0; // ( -u, 1, -v ) pos y

			} else if ( face == 2.0 ) {

				direction.x *= -1.0; // ( -u, v, 1 ) pos z

			} else if ( face == 3.0 ) {

				direction = direction.zyx;
				direction.xz *= -1.0; // ( -1, v, -u ) neg x

			} else if ( face == 4.0 ) {

				direction = direction.xzy;
				direction.xy *= -1.0; // ( -u, -1, v ) neg y

			} else if ( face == 5.0 ) {

				direction.z *= -1.0; // ( u, v, -1 ) neg z

			}

			return direction;

		}

		void main() {

			vOutputDirection = getDirection( uv, faceIndex );
			gl_Position = vec4( position, 1.0 );

		}
	`}var Gl=class extends Dn{constructor(e=1,t={}){super(e,e,t),this.isWebGLCubeRenderTarget=!0;let n={width:e,height:e,depth:1},i=[n,n,n,n,n,n];this.texture=new ra(i),this._setTextureOptions(t),this.texture.isRenderTargetTexture=!0}fromEquirectangularTexture(e,t){this.texture.type=t.type,this.texture.colorSpace=t.colorSpace,this.texture.generateMipmaps=t.generateMipmaps,this.texture.minFilter=t.minFilter,this.texture.magFilter=t.magFilter;let n={uniforms:{tEquirect:{value:null}},vertexShader:`

				varying vec3 vWorldDirection;

				vec3 transformDirection( in vec3 dir, in mat4 matrix ) {

					return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );

				}

				void main() {

					vWorldDirection = transformDirection( position, modelMatrix );

					#include <begin_vertex>
					#include <project_vertex>

				}
			`,fragmentShader:`

				uniform sampler2D tEquirect;

				varying vec3 vWorldDirection;

				#include <common>

				void main() {

					vec3 direction = normalize( vWorldDirection );

					vec2 sampleUV = equirectUv( direction );

					gl_FragColor = texture2D( tEquirect, sampleUV );

				}
			`},i=new Nn(5,5,5),s=new Bn({name:"CubemapFromEquirect",uniforms:yr(n.uniforms),vertexShader:n.vertexShader,fragmentShader:n.fragmentShader,side:Tn,blending:mi});s.uniforms.tEquirect.value=t;let a=new At(i,s),o=t.minFilter;return t.minFilter===mr&&(t.minFilter=Xt),new xl(1,10,this).update(e,a),t.minFilter=o,a.geometry.dispose(),a.material.dispose(),this}clear(e,t=!0,n=!0,i=!0){let s=e.getRenderTarget();for(let a=0;a<6;a++)e.setRenderTarget(this,a),e.clear(t,n,i);e.setRenderTarget(s)}};function pm(r){let e=new WeakMap,t=new WeakMap,n=null;function i(o,c){return c===Tl?o.mapping=gs:c===El&&(o.mapping=fr),o}function s(o){let c=o.target;c.removeEventListener("dispose",s);let l=e.get(c);l!==void 0&&(e.delete(c),l.dispose())}function a(o){let c=o.target;c.removeEventListener("dispose",a);let l=t.get(c);l!==void 0&&(t.delete(c),l.dispose())}return{get:function(o,c=!1){return o==null?null:c?(function(l){if(l&&l.isTexture){let h=l.mapping,p=h===Tl||h===El,f=h===gs||h===fr;if(p||f){let m=t.get(l),u=m!==void 0?m.texture.pmremVersion:0;if(l.isRenderTargetTexture&&l.pmremVersion!==u)return n===null&&(n=new kl(r)),m=p?n.fromEquirectangular(l,m):n.fromCubemap(l,m),m.texture.pmremVersion=l.pmremVersion,t.set(l,m),m.texture;if(m!==void 0)return m.texture;{let g=l.image;return p&&g&&g.height>0||f&&g&&(function(x){let _=0,v=6;for(let S=0;S<v;S++)x[S]!==void 0&&_++;return _===v})(g)?(n===null&&(n=new kl(r)),m=p?n.fromEquirectangular(l):n.fromCubemap(l),m.texture.pmremVersion=l.pmremVersion,t.set(l,m),l.addEventListener("dispose",a),m.texture):null}}}return l})(o):(function(l){if(l&&l.isTexture){let h=l.mapping;if(h===Tl||h===El){if(e.has(l))return i(e.get(l).texture,l.mapping);{let p=l.image;if(p&&p.height>0){let f=new Gl(p.height);return f.fromEquirectangularTexture(r,l),e.set(l,f),l.addEventListener("dispose",s),i(f.texture,l.mapping)}return null}}}return l})(o)},dispose:function(){e=new WeakMap,t=new WeakMap,n!==null&&(n.dispose(),n=null)}}}function fm(r){let e={};function t(n){if(e[n]!==void 0)return e[n];let i=r.getExtension(n);return e[n]=i,i}return{has:function(n){return t(n)!==null},init:function(){t("EXT_color_buffer_float"),t("WEBGL_clip_cull_distance"),t("OES_texture_float_linear"),t("EXT_color_buffer_half_float"),t("WEBGL_multisampled_render_to_texture"),t("WEBGL_render_shared_exponent")},get:function(n){let i=t(n);return i===null&&Zs("WebGLRenderer: "+n+" extension not supported."),i}}}function mm(r,e,t,n){let i={},s=new WeakMap;function a(c){let l=c.target;l.index!==null&&e.remove(l.index);for(let p in l.attributes)e.remove(l.attributes[p]);l.removeEventListener("dispose",a),delete i[l.id];let h=s.get(l);h&&(e.remove(h),s.delete(l)),n.releaseStatesOfGeometry(l),l.isInstancedBufferGeometry===!0&&delete l._maxInstanceCount,t.memory.geometries--}function o(c){let l=[],h=c.index,p=c.attributes.position,f=0;if(p===void 0)return;if(h!==null){let g=h.array;f=h.version;for(let x=0,_=g.length;x<_;x+=3){let v=g[x+0],S=g[x+1],E=g[x+2];l.push(v,S,S,E,E,v)}}else{let g=p.array;f=p.version;for(let x=0,_=g.length/3-1;x<_;x+=3){let v=x+0,S=x+1,E=x+2;l.push(v,S,S,E,E,v)}}let m=new(p.count>=65535?ea:Qs)(l,1);m.version=f;let u=s.get(c);u&&e.remove(u),s.set(c,m)}return{get:function(c,l){return i[l.id]===!0||(l.addEventListener("dispose",a),i[l.id]=!0,t.memory.geometries++),l},update:function(c){let l=c.attributes;for(let h in l)e.update(l[h],r.ARRAY_BUFFER)},getWireframeAttribute:function(c){let l=s.get(c);if(l){let h=c.index;h!==null&&l.version<h.version&&o(c)}else o(c);return s.get(c)}}}function gm(r,e,t){let n,i,s;function a(o,c,l){l!==0&&(r.drawElementsInstanced(n,c,i,o*s,l),t.update(c,n,l))}this.setMode=function(o){n=o},this.setIndex=function(o){i=o.type,s=o.bytesPerElement},this.render=function(o,c){r.drawElements(n,c,i,o*s),t.update(c,n,1)},this.renderInstances=a,this.renderMultiDraw=function(o,c,l){if(l===0)return;e.get("WEBGL_multi_draw").multiDrawElementsWEBGL(n,c,0,i,o,0,l);let h=0;for(let p=0;p<l;p++)h+=c[p];t.update(h,n,1)},this.renderMultiDrawInstances=function(o,c,l,h){if(l===0)return;let p=e.get("WEBGL_multi_draw");if(p===null)for(let f=0;f<o.length;f++)a(o[f]/s,c[f],h[f]);else{p.multiDrawElementsInstancedWEBGL(n,c,0,i,o,0,h,0,l);let f=0;for(let m=0;m<l;m++)f+=c[m]*h[m];t.update(f,n,1)}}}function _m(r){let e={frame:0,calls:0,triangles:0,points:0,lines:0};return{memory:{geometries:0,textures:0},render:e,programs:null,autoReset:!0,reset:function(){e.calls=0,e.triangles=0,e.points=0,e.lines=0},update:function(t,n,i){switch(e.calls++,n){case r.TRIANGLES:e.triangles+=i*(t/3);break;case r.LINES:e.lines+=i*(t/2);break;case r.LINE_STRIP:e.lines+=i*(t-1);break;case r.LINE_LOOP:e.lines+=i*t;break;case r.POINTS:e.points+=i*t;break;default:Je("WebGLInfo: Unknown draw mode:",n)}}}}function vm(r,e,t){let n=new WeakMap,i=new wt;return{update:function(s,a,o){let c=s.morphTargetInfluences,l=a.morphAttributes.position||a.morphAttributes.normal||a.morphAttributes.color,h=l!==void 0?l.length:0,p=n.get(a);if(p===void 0||p.count!==h){let j=function(){R.dispose(),n.delete(a),a.removeEventListener("dispose",j)};p!==void 0&&p.texture.dispose();let f=a.morphAttributes.position!==void 0,m=a.morphAttributes.normal!==void 0,u=a.morphAttributes.color!==void 0,g=a.morphAttributes.position||[],x=a.morphAttributes.normal||[],_=a.morphAttributes.color||[],v=0;f===!0&&(v=1),m===!0&&(v=2),u===!0&&(v=3);let S=a.attributes.position.count*v,E=1;S>e.maxTextureSize&&(E=Math.ceil(S/e.maxTextureSize),S=e.maxTextureSize);let w=new Float32Array(S*E*4*h),R=new Js(w,S,E,h);R.type=Kn,R.needsUpdate=!0;let z=4*v;for(let O=0;O<h;O++){let Q=g[O],Y=x[O],k=_[O],X=S*E*4*O;for(let K=0;K<Q.count;K++){let te=K*z;f===!0&&(i.fromBufferAttribute(Q,K),w[X+te+0]=i.x,w[X+te+1]=i.y,w[X+te+2]=i.z,w[X+te+3]=0),m===!0&&(i.fromBufferAttribute(Y,K),w[X+te+4]=i.x,w[X+te+5]=i.y,w[X+te+6]=i.z,w[X+te+7]=0),u===!0&&(i.fromBufferAttribute(k,K),w[X+te+8]=i.x,w[X+te+9]=i.y,w[X+te+10]=i.z,w[X+te+11]=k.itemSize===4?i.w:1)}}p={count:h,texture:R,size:new _e(S,E)},n.set(a,p),a.addEventListener("dispose",j)}if(s.isInstancedMesh===!0&&s.morphTexture!==null)o.getUniforms().setValue(r,"morphTexture",s.morphTexture,t);else{let f=0;for(let u=0;u<c.length;u++)f+=c[u];let m=a.morphTargetsRelative?1:1-f;o.getUniforms().setValue(r,"morphTargetBaseInfluence",m),o.getUniforms().setValue(r,"morphTargetInfluences",c)}o.getUniforms().setValue(r,"morphTargetsTexture",p.texture,t),o.getUniforms().setValue(r,"morphTargetsTextureSize",p.size)}}}function ym(r,e,t,n,i){let s=new WeakMap;function a(o){let c=o.target;c.removeEventListener("dispose",a),n.releaseStatesOfObject(c),t.remove(c.instanceMatrix),c.instanceColor!==null&&t.remove(c.instanceColor)}return{update:function(o){let c=i.render.frame,l=o.geometry,h=e.get(o,l);if(s.get(h)!==c&&(e.update(h),s.set(h,c)),o.isInstancedMesh&&(o.hasEventListener("dispose",a)===!1&&o.addEventListener("dispose",a),s.get(o)!==c&&(t.update(o.instanceMatrix,r.ARRAY_BUFFER),o.instanceColor!==null&&t.update(o.instanceColor,r.ARRAY_BUFFER),s.set(o,c))),o.isSkinnedMesh){let p=o.skeleton;s.get(p)!==c&&(p.update(),s.set(p,c))}return h},dispose:function(){s=new WeakMap}}}var xm={[oh]:"LINEAR_TONE_MAPPING",[lh]:"REINHARD_TONE_MAPPING",[ch]:"CINEON_TONE_MAPPING",[Ea]:"ACES_FILMIC_TONE_MAPPING",[uh]:"AGX_TONE_MAPPING",[dh]:"NEUTRAL_TONE_MAPPING",[hh]:"CUSTOM_TONE_MAPPING"};function Mm(r,e,t,n,i){let s=new Dn(e,t,{type:r,depthBuffer:n,stencilBuffer:i}),a=new Dn(e,t,{type:gi,depthBuffer:!1,stencilBuffer:!1}),o=new bt;o.setAttribute("position",new Xe([-1,3,0,-1,-1,0,3,-1,0],3)),o.setAttribute("uv",new Xe([0,2,0,0,2,0],2));let c=new al({uniforms:{tDiffuse:{value:null}},vertexShader:`
			precision highp float;

			uniform mat4 modelViewMatrix;
			uniform mat4 projectionMatrix;

			attribute vec3 position;
			attribute vec2 uv;

			varying vec2 vUv;

			void main() {
				vUv = uv;
				gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
			}`,fragmentShader:`
			precision highp float;

			uniform sampler2D tDiffuse;

			varying vec2 vUv;

			#include <tonemapping_pars_fragment>
			#include <colorspace_pars_fragment>

			void main() {
				gl_FragColor = texture2D( tDiffuse, vUv );

				#ifdef LINEAR_TONE_MAPPING
					gl_FragColor.rgb = LinearToneMapping( gl_FragColor.rgb );
				#elif defined( REINHARD_TONE_MAPPING )
					gl_FragColor.rgb = ReinhardToneMapping( gl_FragColor.rgb );
				#elif defined( CINEON_TONE_MAPPING )
					gl_FragColor.rgb = CineonToneMapping( gl_FragColor.rgb );
				#elif defined( ACES_FILMIC_TONE_MAPPING )
					gl_FragColor.rgb = ACESFilmicToneMapping( gl_FragColor.rgb );
				#elif defined( AGX_TONE_MAPPING )
					gl_FragColor.rgb = AgXToneMapping( gl_FragColor.rgb );
				#elif defined( NEUTRAL_TONE_MAPPING )
					gl_FragColor.rgb = NeutralToneMapping( gl_FragColor.rgb );
				#elif defined( CUSTOM_TONE_MAPPING )
					gl_FragColor.rgb = CustomToneMapping( gl_FragColor.rgb );
				#endif

				#ifdef SRGB_TRANSFER
					gl_FragColor = sRGBTransferOETF( gl_FragColor );
				#endif
			}`,depthTest:!1,depthWrite:!1}),l=new At(o,c),h=new cs(-1,1,1,-1,0,1),p,f=null,m=null,u=!1,g=null,x=[],_=!1;this.setSize=function(v,S){s.setSize(v,S),a.setSize(v,S);for(let E=0;E<x.length;E++){let w=x[E];w.setSize&&w.setSize(v,S)}},this.setEffects=function(v){x=v,_=x.length>0&&x[0].isRenderPass===!0;let S=s.width,E=s.height;for(let w=0;w<x.length;w++){let R=x[w];R.setSize&&R.setSize(S,E)}},this.begin=function(v,S){if(u||v.toneMapping===si&&x.length===0)return!1;if(g=S,S!==null){let E=S.width,w=S.height;s.width===E&&s.height===w||this.setSize(E,w)}return _===!1&&v.setRenderTarget(s),p=v.toneMapping,v.toneMapping=si,!0},this.hasRenderPass=function(){return _},this.end=function(v,S){v.toneMapping=p,u=!0;let E=s,w=a;for(let R=0;R<x.length;R++){let z=x[R];if(z.enabled!==!1&&(z.render(v,w,E,S),z.needsSwap!==!1)){let j=E;E=w,w=j}}if(f!==v.outputColorSpace||m!==v.toneMapping){f=v.outputColorSpace,m=v.toneMapping,c.defines={},ut.getTransfer(f)===gt&&(c.defines.SRGB_TRANSFER="");let R=xm[m];R&&(c.defines[R]=""),c.needsUpdate=!0}c.uniforms.tDiffuse.value=E.texture,v.setRenderTarget(g),v.render(l,h),g=null,u=!1},this.isCompositing=function(){return u},this.dispose=function(){s.dispose(),a.dispose(),o.dispose(),c.dispose()}}var Hp=new an,uu=new Xi(1,1),Wp=new Js,jp=new Lo,Xp=new ra,Ep=[],wp=[],Ap=new Float32Array(16),Cp=new Float32Array(9),Rp=new Float32Array(4);function bs(r,e,t){let n=r[0];if(n<=0||n>0)return r;let i=e*t,s=Ep[i];if(s===void 0&&(s=new Float32Array(i),Ep[i]=s),e!==0){n.toArray(s,0);for(let a=1,o=0;a!==e;++a)o+=t,r[a].toArray(s,o)}return s}function Vt(r,e){if(r.length!==e.length)return!1;for(let t=0,n=r.length;t<n;t++)if(r[t]!==e[t])return!1;return!0}function Gt(r,e){for(let t=0,n=e.length;t<n;t++)r[t]=e[t]}function Wl(r,e){let t=wp[e];t===void 0&&(t=new Int32Array(e),wp[e]=t);for(let n=0;n!==e;++n)t[n]=r.allocateTextureUnit();return t}function bm(r,e){let t=this.cache;t[0]!==e&&(r.uniform1f(this.addr,e),t[0]=e)}function Sm(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y||(r.uniform2f(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Vt(t,e))return;r.uniform2fv(this.addr,e),Gt(t,e)}}function Tm(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y&&t[2]===e.z||(r.uniform3f(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else if(e.r!==void 0)t[0]===e.r&&t[1]===e.g&&t[2]===e.b||(r.uniform3f(this.addr,e.r,e.g,e.b),t[0]=e.r,t[1]=e.g,t[2]=e.b);else{if(Vt(t,e))return;r.uniform3fv(this.addr,e),Gt(t,e)}}function Em(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y&&t[2]===e.z&&t[3]===e.w||(r.uniform4f(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Vt(t,e))return;r.uniform4fv(this.addr,e),Gt(t,e)}}function wm(r,e){let t=this.cache,n=e.elements;if(n===void 0){if(Vt(t,e))return;r.uniformMatrix2fv(this.addr,!1,e),Gt(t,e)}else{if(Vt(t,n))return;Rp.set(n),r.uniformMatrix2fv(this.addr,!1,Rp),Gt(t,n)}}function Am(r,e){let t=this.cache,n=e.elements;if(n===void 0){if(Vt(t,e))return;r.uniformMatrix3fv(this.addr,!1,e),Gt(t,e)}else{if(Vt(t,n))return;Cp.set(n),r.uniformMatrix3fv(this.addr,!1,Cp),Gt(t,n)}}function Cm(r,e){let t=this.cache,n=e.elements;if(n===void 0){if(Vt(t,e))return;r.uniformMatrix4fv(this.addr,!1,e),Gt(t,e)}else{if(Vt(t,n))return;Ap.set(n),r.uniformMatrix4fv(this.addr,!1,Ap),Gt(t,n)}}function Rm(r,e){let t=this.cache;t[0]!==e&&(r.uniform1i(this.addr,e),t[0]=e)}function Pm(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y||(r.uniform2i(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Vt(t,e))return;r.uniform2iv(this.addr,e),Gt(t,e)}}function Im(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y&&t[2]===e.z||(r.uniform3i(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else{if(Vt(t,e))return;r.uniform3iv(this.addr,e),Gt(t,e)}}function Lm(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y&&t[2]===e.z&&t[3]===e.w||(r.uniform4i(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Vt(t,e))return;r.uniform4iv(this.addr,e),Gt(t,e)}}function Dm(r,e){let t=this.cache;t[0]!==e&&(r.uniform1ui(this.addr,e),t[0]=e)}function Um(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y||(r.uniform2ui(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Vt(t,e))return;r.uniform2uiv(this.addr,e),Gt(t,e)}}function Nm(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y&&t[2]===e.z||(r.uniform3ui(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else{if(Vt(t,e))return;r.uniform3uiv(this.addr,e),Gt(t,e)}}function Om(r,e){let t=this.cache;if(e.x!==void 0)t[0]===e.x&&t[1]===e.y&&t[2]===e.z&&t[3]===e.w||(r.uniform4ui(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Vt(t,e))return;r.uniform4uiv(this.addr,e),Gt(t,e)}}function Fm(r,e,t){let n=this.cache,i=t.allocateTextureUnit(),s;n[0]!==i&&(r.uniform1i(this.addr,i),n[0]=i),this.type===r.SAMPLER_2D_SHADOW?(uu.compareFunction=t.isReversedDepthBuffer()?Fl:Ol,s=uu):s=Hp,t.setTexture2D(e||s,i)}function Bm(r,e,t){let n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(r.uniform1i(this.addr,i),n[0]=i),t.setTexture3D(e||jp,i)}function zm(r,e,t){let n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(r.uniform1i(this.addr,i),n[0]=i),t.setTextureCube(e||Xp,i)}function km(r,e,t){let n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(r.uniform1i(this.addr,i),n[0]=i),t.setTexture2DArray(e||Wp,i)}function Vm(r,e){r.uniform1fv(this.addr,e)}function Gm(r,e){let t=bs(e,this.size,2);r.uniform2fv(this.addr,t)}function Hm(r,e){let t=bs(e,this.size,3);r.uniform3fv(this.addr,t)}function Wm(r,e){let t=bs(e,this.size,4);r.uniform4fv(this.addr,t)}function jm(r,e){let t=bs(e,this.size,4);r.uniformMatrix2fv(this.addr,!1,t)}function Xm(r,e){let t=bs(e,this.size,9);r.uniformMatrix3fv(this.addr,!1,t)}function qm(r,e){let t=bs(e,this.size,16);r.uniformMatrix4fv(this.addr,!1,t)}function Ym(r,e){r.uniform1iv(this.addr,e)}function Zm(r,e){r.uniform2iv(this.addr,e)}function Jm(r,e){r.uniform3iv(this.addr,e)}function Km(r,e){r.uniform4iv(this.addr,e)}function $m(r,e){r.uniform1uiv(this.addr,e)}function Qm(r,e){r.uniform2uiv(this.addr,e)}function eg(r,e){r.uniform3uiv(this.addr,e)}function tg(r,e){r.uniform4uiv(this.addr,e)}function ng(r,e,t){let n=this.cache,i=e.length,s=Wl(t,i),a;Vt(n,s)||(r.uniform1iv(this.addr,s),Gt(n,s)),a=this.type===r.SAMPLER_2D_SHADOW?uu:Hp;for(let o=0;o!==i;++o)t.setTexture2D(e[o]||a,s[o])}function ig(r,e,t){let n=this.cache,i=e.length,s=Wl(t,i);Vt(n,s)||(r.uniform1iv(this.addr,s),Gt(n,s));for(let a=0;a!==i;++a)t.setTexture3D(e[a]||jp,s[a])}function rg(r,e,t){let n=this.cache,i=e.length,s=Wl(t,i);Vt(n,s)||(r.uniform1iv(this.addr,s),Gt(n,s));for(let a=0;a!==i;++a)t.setTextureCube(e[a]||Xp,s[a])}function sg(r,e,t){let n=this.cache,i=e.length,s=Wl(t,i);Vt(n,s)||(r.uniform1iv(this.addr,s),Gt(n,s));for(let a=0;a!==i;++a)t.setTexture2DArray(e[a]||Wp,s[a])}var du=class{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.setValue=(function(i){switch(i){case 5126:return bm;case 35664:return Sm;case 35665:return Tm;case 35666:return Em;case 35674:return wm;case 35675:return Am;case 35676:return Cm;case 5124:case 35670:return Rm;case 35667:case 35671:return Pm;case 35668:case 35672:return Im;case 35669:case 35673:return Lm;case 5125:return Dm;case 36294:return Um;case 36295:return Nm;case 36296:return Om;case 35678:case 36198:case 36298:case 36306:case 35682:return Fm;case 35679:case 36299:case 36307:return Bm;case 35680:case 36300:case 36308:case 36293:return zm;case 36289:case 36303:case 36311:case 36292:return km}})(t.type)}},pu=class{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.size=t.size,this.setValue=(function(i){switch(i){case 5126:return Vm;case 35664:return Gm;case 35665:return Hm;case 35666:return Wm;case 35674:return jm;case 35675:return Xm;case 35676:return qm;case 5124:case 35670:return Ym;case 35667:case 35671:return Zm;case 35668:case 35672:return Jm;case 35669:case 35673:return Km;case 5125:return $m;case 36294:return Qm;case 36295:return eg;case 36296:return tg;case 35678:case 36198:case 36298:case 36306:case 35682:return ng;case 35679:case 36299:case 36307:return ig;case 35680:case 36300:case 36308:case 36293:return rg;case 36289:case 36303:case 36311:case 36292:return sg}})(t.type)}},fu=class{constructor(e){this.id=e,this.seq=[],this.map={}}setValue(e,t,n){let i=this.seq;for(let s=0,a=i.length;s!==a;++s){let o=i[s];o.setValue(e,t[o.id],n)}}},cu=/(\w+)(\])?(\[|\.)?/g;function Pp(r,e){r.seq.push(e),r.map[e.id]=e}function ag(r,e,t){let n=r.name,i=n.length;for(cu.lastIndex=0;;){let s=cu.exec(n),a=cu.lastIndex,o=s[1],c=s[2]==="]",l=s[3];if(c&&(o|=0),l===void 0||l==="["&&a+2===i){Pp(t,l===void 0?new du(o,r,e):new pu(o,r,e));break}{let h=t.map[o];h===void 0&&(h=new fu(o),Pp(t,h)),t=h}}}var Ms=class{constructor(e,t){this.seq=[],this.map={};let n=e.getProgramParameter(t,e.ACTIVE_UNIFORMS);for(let a=0;a<n;++a){let o=e.getActiveUniform(t,a);ag(o,e.getUniformLocation(t,o.name),this)}let i=[],s=[];for(let a of this.seq)a.type===e.SAMPLER_2D_SHADOW||a.type===e.SAMPLER_CUBE_SHADOW||a.type===e.SAMPLER_2D_ARRAY_SHADOW?i.push(a):s.push(a);i.length>0&&(this.seq=i.concat(s))}setValue(e,t,n,i){let s=this.map[t];s!==void 0&&s.setValue(e,n,i)}setOptional(e,t,n){let i=t[n];i!==void 0&&this.setValue(e,n,i)}static upload(e,t,n,i){for(let s=0,a=t.length;s!==a;++s){let o=t[s],c=n[o.id];c.needsUpdate!==!1&&o.setValue(e,c.value,i)}}static seqWithValue(e,t){let n=[];for(let i=0,s=e.length;i!==s;++i){let a=e[i];a.id in t&&n.push(a)}return n}};function Ip(r,e,t){let n=r.createShader(e);return r.shaderSource(n,t),r.compileShader(n),n}var og=0,Lp=new et;function Dp(r,e,t){let n=r.getShaderParameter(e,r.COMPILE_STATUS),i=(r.getShaderInfoLog(e)||"").trim();if(n&&i==="")return"";let s=/ERROR: 0:(\d+)/.exec(i);if(s){let a=parseInt(s[1]);return t.toUpperCase()+`

`+i+`

`+(function(o,c){let l=o.split(`
`),h=[],p=Math.max(c-6,0),f=Math.min(c+6,l.length);for(let m=p;m<f;m++){let u=m+1;h.push(`${u===c?">":" "} ${u}: ${l[m]}`)}return h.join(`
`)})(r.getShaderSource(e),a)}return i}function lg(r,e){let t=(function(n){ut._getMatrix(Lp,ut.workingColorSpace,n);let i=`mat3( ${Lp.elements.map(s=>s.toFixed(4))} )`;switch(ut.getTransfer(n)){case Ys:return[i,"LinearTransferOETF"];case gt:return[i,"sRGBTransferOETF"];default:return Ye("WebGLProgram: Unsupported color space: ",n),[i,"LinearTransferOETF"]}})(e);return[`vec4 ${r}( vec4 value ) {`,`	return ${t[1]}( vec4( value.rgb * ${t[0]}, value.a ) );`,"}"].join(`
`)}var cg={[oh]:"Linear",[lh]:"Reinhard",[ch]:"Cineon",[Ea]:"ACESFilmic",[uh]:"AgX",[dh]:"Neutral",[hh]:"Custom"};function hg(r,e){let t=cg[e];return t===void 0?(Ye("WebGLProgram: Unsupported toneMapping:",e),"vec3 "+r+"( vec3 color ) { return LinearToneMapping( color ); }"):"vec3 "+r+"( vec3 color ) { return "+t+"ToneMapping( color ); }"}var zl=new D;function ug(){return ut.getLuminanceCoefficients(zl),["float luminance( const in vec3 rgb ) {",`	const vec3 weights = vec3( ${zl.x.toFixed(4)}, ${zl.y.toFixed(4)}, ${zl.z.toFixed(4)} );`,"	return dot( weights, rgb );","}"].join(`
`)}function Pa(r){return r!==""}function Up(r,e){let t=e.numSpotLightShadows+e.numSpotLightMaps-e.numSpotLightShadowsWithMaps;return r.replace(/NUM_DIR_LIGHTS/g,e.numDirLights).replace(/NUM_SPOT_LIGHTS/g,e.numSpotLights).replace(/NUM_SPOT_LIGHT_MAPS/g,e.numSpotLightMaps).replace(/NUM_SPOT_LIGHT_COORDS/g,t).replace(/NUM_RECT_AREA_LIGHTS/g,e.numRectAreaLights).replace(/NUM_POINT_LIGHTS/g,e.numPointLights).replace(/NUM_HEMI_LIGHTS/g,e.numHemiLights).replace(/NUM_DIR_LIGHT_SHADOWS/g,e.numDirLightShadows).replace(/NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS/g,e.numSpotLightShadowsWithMaps).replace(/NUM_SPOT_LIGHT_SHADOWS/g,e.numSpotLightShadows).replace(/NUM_POINT_LIGHT_SHADOWS/g,e.numPointLightShadows)}function Np(r,e){return r.replace(/NUM_CLIPPING_PLANES/g,e.numClippingPlanes).replace(/UNION_CLIPPING_PLANES/g,e.numClippingPlanes-e.numClipIntersection)}var dg=/^[ \t]*#include +<([\w\d./]+)>/gm;function mu(r){return r.replace(dg,fg)}var pg=new Map;function fg(r,e){let t=st[e];if(t===void 0){let n=pg.get(e);if(n===void 0)throw new Error("Can not resolve #include <"+e+">");t=st[n],Ye('WebGLRenderer: Shader chunk "%s" has been deprecated. Use "%s" instead.',e,n)}return mu(t)}var mg=/#pragma unroll_loop_start\s+for\s*\(\s*int\s+i\s*=\s*(\d+)\s*;\s*i\s*<\s*(\d+)\s*;\s*i\s*\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g;function Op(r){return r.replace(mg,gg)}function gg(r,e,t,n){let i="";for(let s=parseInt(e);s<parseInt(t);s++)i+=n.replace(/\[\s*i\s*\]/g,"[ "+s+" ]").replace(/UNROLLED_LOOP_INDEX/g,s);return i}function Fp(r){let e=`precision ${r.precision} float;
	precision ${r.precision} int;
	precision ${r.precision} sampler2D;
	precision ${r.precision} samplerCube;
	precision ${r.precision} sampler3D;
	precision ${r.precision} sampler2DArray;
	precision ${r.precision} sampler2DShadow;
	precision ${r.precision} samplerCubeShadow;
	precision ${r.precision} sampler2DArrayShadow;
	precision ${r.precision} isampler2D;
	precision ${r.precision} isampler3D;
	precision ${r.precision} isamplerCube;
	precision ${r.precision} isampler2DArray;
	precision ${r.precision} usampler2D;
	precision ${r.precision} usampler3D;
	precision ${r.precision} usamplerCube;
	precision ${r.precision} usampler2DArray;
	`;return r.precision==="highp"?e+=`
#define HIGH_PRECISION`:r.precision==="mediump"?e+=`
#define MEDIUM_PRECISION`:r.precision==="lowp"&&(e+=`
#define LOW_PRECISION`),e}var _g={[Sa]:"SHADOWMAP_TYPE_PCF",[ps]:"SHADOWMAP_TYPE_VSM"},vg={[gs]:"ENVMAP_TYPE_CUBE",[fr]:"ENVMAP_TYPE_CUBE",[wa]:"ENVMAP_TYPE_CUBE_UV"},yg={[fr]:"ENVMAP_MODE_REFRACTION"},xg={[Jd]:"ENVMAP_BLENDING_MULTIPLY",[Kd]:"ENVMAP_BLENDING_MIX",[$d]:"ENVMAP_BLENDING_ADD"};function Mg(r,e,t,n){let i=r.getContext(),s=t.defines,a=t.vertexShader,o=t.fragmentShader,c=(function(Y){return _g[Y.shadowMapType]||"SHADOWMAP_TYPE_BASIC"})(t),l=(function(Y){return Y.envMap===!1?"ENVMAP_TYPE_CUBE":vg[Y.envMapMode]||"ENVMAP_TYPE_CUBE"})(t),h=(function(Y){return Y.envMap===!1?"ENVMAP_MODE_REFLECTION":yg[Y.envMapMode]||"ENVMAP_MODE_REFLECTION"})(t),p=(function(Y){return Y.envMap===!1?"ENVMAP_BLENDING_NONE":xg[Y.combine]||"ENVMAP_BLENDING_NONE"})(t),f=(function(Y){let k=Y.envMapCubeUVHeight;if(k===null)return null;let X=Math.log2(k)-2,K=1/k;return{texelWidth:1/(3*Math.max(Math.pow(2,X),112)),texelHeight:K,maxMip:X}})(t),m=(function(Y){return[Y.extensionClipCullDistance?"#extension GL_ANGLE_clip_cull_distance : require":"",Y.extensionMultiDraw?"#extension GL_ANGLE_multi_draw : require":""].filter(Pa).join(`
`)})(t),u=(function(Y){let k=[];for(let X in Y){let K=Y[X];K!==!1&&k.push("#define "+X+" "+K)}return k.join(`
`)})(s),g=i.createProgram(),x,_,v=t.glslVersion?"#version "+t.glslVersion+`
`:"";t.isRawShaderMaterial?(x=["#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,u].filter(Pa).join(`
`),x.length>0&&(x+=`
`),_=["#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,u].filter(Pa).join(`
`),_.length>0&&(_+=`
`)):(x=[Fp(t),"#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,u,t.extensionClipCullDistance?"#define USE_CLIP_DISTANCE":"",t.batching?"#define USE_BATCHING":"",t.batchingColor?"#define USE_BATCHING_COLOR":"",t.instancing?"#define USE_INSTANCING":"",t.instancingColor?"#define USE_INSTANCING_COLOR":"",t.instancingMorph?"#define USE_INSTANCING_MORPH":"",t.useFog&&t.fog?"#define USE_FOG":"",t.useFog&&t.fogExp2?"#define FOG_EXP2":"",t.map?"#define USE_MAP":"",t.envMap?"#define USE_ENVMAP":"",t.envMap?"#define "+h:"",t.lightMap?"#define USE_LIGHTMAP":"",t.aoMap?"#define USE_AOMAP":"",t.bumpMap?"#define USE_BUMPMAP":"",t.normalMap?"#define USE_NORMALMAP":"",t.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",t.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",t.displacementMap?"#define USE_DISPLACEMENTMAP":"",t.emissiveMap?"#define USE_EMISSIVEMAP":"",t.anisotropy?"#define USE_ANISOTROPY":"",t.anisotropyMap?"#define USE_ANISOTROPYMAP":"",t.clearcoatMap?"#define USE_CLEARCOATMAP":"",t.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",t.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",t.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",t.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",t.specularMap?"#define USE_SPECULARMAP":"",t.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",t.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",t.roughnessMap?"#define USE_ROUGHNESSMAP":"",t.metalnessMap?"#define USE_METALNESSMAP":"",t.alphaMap?"#define USE_ALPHAMAP":"",t.alphaHash?"#define USE_ALPHAHASH":"",t.transmission?"#define USE_TRANSMISSION":"",t.transmissionMap?"#define USE_TRANSMISSIONMAP":"",t.thicknessMap?"#define USE_THICKNESSMAP":"",t.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",t.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",t.mapUv?"#define MAP_UV "+t.mapUv:"",t.alphaMapUv?"#define ALPHAMAP_UV "+t.alphaMapUv:"",t.lightMapUv?"#define LIGHTMAP_UV "+t.lightMapUv:"",t.aoMapUv?"#define AOMAP_UV "+t.aoMapUv:"",t.emissiveMapUv?"#define EMISSIVEMAP_UV "+t.emissiveMapUv:"",t.bumpMapUv?"#define BUMPMAP_UV "+t.bumpMapUv:"",t.normalMapUv?"#define NORMALMAP_UV "+t.normalMapUv:"",t.displacementMapUv?"#define DISPLACEMENTMAP_UV "+t.displacementMapUv:"",t.metalnessMapUv?"#define METALNESSMAP_UV "+t.metalnessMapUv:"",t.roughnessMapUv?"#define ROUGHNESSMAP_UV "+t.roughnessMapUv:"",t.anisotropyMapUv?"#define ANISOTROPYMAP_UV "+t.anisotropyMapUv:"",t.clearcoatMapUv?"#define CLEARCOATMAP_UV "+t.clearcoatMapUv:"",t.clearcoatNormalMapUv?"#define CLEARCOAT_NORMALMAP_UV "+t.clearcoatNormalMapUv:"",t.clearcoatRoughnessMapUv?"#define CLEARCOAT_ROUGHNESSMAP_UV "+t.clearcoatRoughnessMapUv:"",t.iridescenceMapUv?"#define IRIDESCENCEMAP_UV "+t.iridescenceMapUv:"",t.iridescenceThicknessMapUv?"#define IRIDESCENCE_THICKNESSMAP_UV "+t.iridescenceThicknessMapUv:"",t.sheenColorMapUv?"#define SHEEN_COLORMAP_UV "+t.sheenColorMapUv:"",t.sheenRoughnessMapUv?"#define SHEEN_ROUGHNESSMAP_UV "+t.sheenRoughnessMapUv:"",t.specularMapUv?"#define SPECULARMAP_UV "+t.specularMapUv:"",t.specularColorMapUv?"#define SPECULAR_COLORMAP_UV "+t.specularColorMapUv:"",t.specularIntensityMapUv?"#define SPECULAR_INTENSITYMAP_UV "+t.specularIntensityMapUv:"",t.transmissionMapUv?"#define TRANSMISSIONMAP_UV "+t.transmissionMapUv:"",t.thicknessMapUv?"#define THICKNESSMAP_UV "+t.thicknessMapUv:"",t.vertexTangents&&t.flatShading===!1?"#define USE_TANGENT":"",t.vertexColors?"#define USE_COLOR":"",t.vertexAlphas?"#define USE_COLOR_ALPHA":"",t.vertexUv1s?"#define USE_UV1":"",t.vertexUv2s?"#define USE_UV2":"",t.vertexUv3s?"#define USE_UV3":"",t.pointsUvs?"#define USE_POINTS_UV":"",t.flatShading?"#define FLAT_SHADED":"",t.skinning?"#define USE_SKINNING":"",t.morphTargets?"#define USE_MORPHTARGETS":"",t.morphNormals&&t.flatShading===!1?"#define USE_MORPHNORMALS":"",t.morphColors?"#define USE_MORPHCOLORS":"",t.morphTargetsCount>0?"#define MORPHTARGETS_TEXTURE_STRIDE "+t.morphTextureStride:"",t.morphTargetsCount>0?"#define MORPHTARGETS_COUNT "+t.morphTargetsCount:"",t.doubleSided?"#define DOUBLE_SIDED":"",t.flipSided?"#define FLIP_SIDED":"",t.shadowMapEnabled?"#define USE_SHADOWMAP":"",t.shadowMapEnabled?"#define "+c:"",t.sizeAttenuation?"#define USE_SIZEATTENUATION":"",t.numLightProbes>0?"#define USE_LIGHT_PROBES":"",t.logarithmicDepthBuffer?"#define USE_LOGARITHMIC_DEPTH_BUFFER":"",t.reversedDepthBuffer?"#define USE_REVERSED_DEPTH_BUFFER":"","uniform mat4 modelMatrix;","uniform mat4 modelViewMatrix;","uniform mat4 projectionMatrix;","uniform mat4 viewMatrix;","uniform mat3 normalMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;","#ifdef USE_INSTANCING","	attribute mat4 instanceMatrix;","#endif","#ifdef USE_INSTANCING_COLOR","	attribute vec3 instanceColor;","#endif","#ifdef USE_INSTANCING_MORPH","	uniform sampler2D morphTexture;","#endif","attribute vec3 position;","attribute vec3 normal;","attribute vec2 uv;","#ifdef USE_UV1","	attribute vec2 uv1;","#endif","#ifdef USE_UV2","	attribute vec2 uv2;","#endif","#ifdef USE_UV3","	attribute vec2 uv3;","#endif","#ifdef USE_TANGENT","	attribute vec4 tangent;","#endif","#if defined( USE_COLOR_ALPHA )","	attribute vec4 color;","#elif defined( USE_COLOR )","	attribute vec3 color;","#endif","#ifdef USE_SKINNING","	attribute vec4 skinIndex;","	attribute vec4 skinWeight;","#endif",`
`].filter(Pa).join(`
`),_=[Fp(t),"#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,u,t.useFog&&t.fog?"#define USE_FOG":"",t.useFog&&t.fogExp2?"#define FOG_EXP2":"",t.alphaToCoverage?"#define ALPHA_TO_COVERAGE":"",t.map?"#define USE_MAP":"",t.matcap?"#define USE_MATCAP":"",t.envMap?"#define USE_ENVMAP":"",t.envMap?"#define "+l:"",t.envMap?"#define "+h:"",t.envMap?"#define "+p:"",f?"#define CUBEUV_TEXEL_WIDTH "+f.texelWidth:"",f?"#define CUBEUV_TEXEL_HEIGHT "+f.texelHeight:"",f?"#define CUBEUV_MAX_MIP "+f.maxMip+".0":"",t.lightMap?"#define USE_LIGHTMAP":"",t.aoMap?"#define USE_AOMAP":"",t.bumpMap?"#define USE_BUMPMAP":"",t.normalMap?"#define USE_NORMALMAP":"",t.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",t.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",t.emissiveMap?"#define USE_EMISSIVEMAP":"",t.anisotropy?"#define USE_ANISOTROPY":"",t.anisotropyMap?"#define USE_ANISOTROPYMAP":"",t.clearcoat?"#define USE_CLEARCOAT":"",t.clearcoatMap?"#define USE_CLEARCOATMAP":"",t.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",t.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",t.dispersion?"#define USE_DISPERSION":"",t.iridescence?"#define USE_IRIDESCENCE":"",t.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",t.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",t.specularMap?"#define USE_SPECULARMAP":"",t.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",t.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",t.roughnessMap?"#define USE_ROUGHNESSMAP":"",t.metalnessMap?"#define USE_METALNESSMAP":"",t.alphaMap?"#define USE_ALPHAMAP":"",t.alphaTest?"#define USE_ALPHATEST":"",t.alphaHash?"#define USE_ALPHAHASH":"",t.sheen?"#define USE_SHEEN":"",t.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",t.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",t.transmission?"#define USE_TRANSMISSION":"",t.transmissionMap?"#define USE_TRANSMISSIONMAP":"",t.thicknessMap?"#define USE_THICKNESSMAP":"",t.vertexTangents&&t.flatShading===!1?"#define USE_TANGENT":"",t.vertexColors||t.instancingColor?"#define USE_COLOR":"",t.vertexAlphas||t.batchingColor?"#define USE_COLOR_ALPHA":"",t.vertexUv1s?"#define USE_UV1":"",t.vertexUv2s?"#define USE_UV2":"",t.vertexUv3s?"#define USE_UV3":"",t.pointsUvs?"#define USE_POINTS_UV":"",t.gradientMap?"#define USE_GRADIENTMAP":"",t.flatShading?"#define FLAT_SHADED":"",t.doubleSided?"#define DOUBLE_SIDED":"",t.flipSided?"#define FLIP_SIDED":"",t.shadowMapEnabled?"#define USE_SHADOWMAP":"",t.shadowMapEnabled?"#define "+c:"",t.premultipliedAlpha?"#define PREMULTIPLIED_ALPHA":"",t.numLightProbes>0?"#define USE_LIGHT_PROBES":"",t.decodeVideoTexture?"#define DECODE_VIDEO_TEXTURE":"",t.decodeVideoTextureEmissive?"#define DECODE_VIDEO_TEXTURE_EMISSIVE":"",t.logarithmicDepthBuffer?"#define USE_LOGARITHMIC_DEPTH_BUFFER":"",t.reversedDepthBuffer?"#define USE_REVERSED_DEPTH_BUFFER":"","uniform mat4 viewMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;",t.toneMapping!==si?"#define TONE_MAPPING":"",t.toneMapping!==si?st.tonemapping_pars_fragment:"",t.toneMapping!==si?hg("toneMapping",t.toneMapping):"",t.dithering?"#define DITHERING":"",t.opaque?"#define OPAQUE":"",st.colorspace_pars_fragment,lg("linearToOutputTexel",t.outputColorSpace),ug(),t.useDepthPacking?"#define DEPTH_PACKING "+t.depthPacking:"",`
`].filter(Pa).join(`
`)),a=mu(a),a=Up(a,t),a=Np(a,t),o=mu(o),o=Up(o,t),o=Np(o,t),a=Op(a),o=Op(o),t.isRawShaderMaterial!==!0&&(v=`#version 300 es
`,x=[m,"#define attribute in","#define varying out","#define texture2D texture"].join(`
`)+`
`+x,_=["#define varying in",t.glslVersion===Qh?"":"layout(location = 0) out highp vec4 pc_fragColor;",t.glslVersion===Qh?"":"#define gl_FragColor pc_fragColor","#define gl_FragDepthEXT gl_FragDepth","#define texture2D texture","#define textureCube texture","#define texture2DProj textureProj","#define texture2DLodEXT textureLod","#define texture2DProjLodEXT textureProjLod","#define textureCubeLodEXT textureLod","#define texture2DGradEXT textureGrad","#define texture2DProjGradEXT textureProjGrad","#define textureCubeGradEXT textureGrad"].join(`
`)+`
`+_);let S=v+x+a,E=v+_+o,w=Ip(i,i.VERTEX_SHADER,S),R=Ip(i,i.FRAGMENT_SHADER,E);function z(Y){if(r.debug.checkShaderErrors){let k=i.getProgramInfoLog(g)||"",X=i.getShaderInfoLog(w)||"",K=i.getShaderInfoLog(R)||"",te=k.trim(),oe=X.trim(),ee=K.trim(),xe=!0,be=!0;if(i.getProgramParameter(g,i.LINK_STATUS)===!1)if(xe=!1,typeof r.debug.onShaderError=="function")r.debug.onShaderError(i,g,w,R);else{let we=Dp(i,w,"vertex"),Se=Dp(i,R,"fragment");Je("THREE.WebGLProgram: Shader Error "+i.getError()+" - VALIDATE_STATUS "+i.getProgramParameter(g,i.VALIDATE_STATUS)+`

Material Name: `+Y.name+`
Material Type: `+Y.type+`

Program Info Log: `+te+`
`+we+`
`+Se)}else te!==""?Ye("WebGLProgram: Program Info Log:",te):oe!==""&&ee!==""||(be=!1);be&&(Y.diagnostics={runnable:xe,programLog:te,vertexShader:{log:oe,prefix:x},fragmentShader:{log:ee,prefix:_}})}i.deleteShader(w),i.deleteShader(R),j=new Ms(i,g),O=(function(k,X){let K={},te=k.getProgramParameter(X,k.ACTIVE_ATTRIBUTES);for(let oe=0;oe<te;oe++){let ee=k.getActiveAttrib(X,oe),xe=ee.name,be=1;ee.type===k.FLOAT_MAT2&&(be=2),ee.type===k.FLOAT_MAT3&&(be=3),ee.type===k.FLOAT_MAT4&&(be=4),K[xe]={type:ee.type,location:k.getAttribLocation(X,xe),locationSize:be}}return K})(i,g)}let j,O;i.attachShader(g,w),i.attachShader(g,R),t.index0AttributeName!==void 0?i.bindAttribLocation(g,0,t.index0AttributeName):t.morphTargets===!0&&i.bindAttribLocation(g,0,"position"),i.linkProgram(g),this.getUniforms=function(){return j===void 0&&z(this),j},this.getAttributes=function(){return O===void 0&&z(this),O};let Q=t.rendererExtensionParallelShaderCompile===!1;return this.isReady=function(){return Q===!1&&(Q=i.getProgramParameter(g,37297)),Q},this.destroy=function(){n.releaseStatesOfProgram(this),i.deleteProgram(g),this.program=void 0},this.type=t.shaderType,this.name=t.shaderName,this.id=og++,this.cacheKey=e,this.usedTimes=1,this.program=g,this.vertexShader=w,this.fragmentShader=R,this}var bg=0,gu=class{constructor(){this.shaderCache=new Map,this.materialCache=new Map}update(e){let t=e.vertexShader,n=e.fragmentShader,i=this._getShaderStage(t),s=this._getShaderStage(n),a=this._getShaderCacheForMaterial(e);return a.has(i)===!1&&(a.add(i),i.usedTimes++),a.has(s)===!1&&(a.add(s),s.usedTimes++),this}remove(e){let t=this.materialCache.get(e);for(let n of t)n.usedTimes--,n.usedTimes===0&&this.shaderCache.delete(n.code);return this.materialCache.delete(e),this}getVertexShaderID(e){return this._getShaderStage(e.vertexShader).id}getFragmentShaderID(e){return this._getShaderStage(e.fragmentShader).id}dispose(){this.shaderCache.clear(),this.materialCache.clear()}_getShaderCacheForMaterial(e){let t=this.materialCache,n=t.get(e);return n===void 0&&(n=new Set,t.set(e,n)),n}_getShaderStage(e){let t=this.shaderCache,n=t.get(e);return n===void 0&&(n=new _u(e),t.set(e,n)),n}},_u=class{constructor(e){this.id=bg++,this.code=e,this.usedTimes=0}};function Sg(r,e,t,n,i,s){let a=new es,o=new gu,c=new Set,l=[],h=new Map,p=n.logarithmicDepthBuffer,f=n.precision,m={MeshDepthMaterial:"depth",MeshDistanceMaterial:"distance",MeshNormalMaterial:"normal",MeshBasicMaterial:"basic",MeshLambertMaterial:"lambert",MeshPhongMaterial:"phong",MeshToonMaterial:"toon",MeshStandardMaterial:"physical",MeshPhysicalMaterial:"physical",MeshMatcapMaterial:"matcap",LineBasicMaterial:"basic",LineDashedMaterial:"dashed",PointsMaterial:"points",ShadowMaterial:"shadow",SpriteMaterial:"sprite"};function u(g){return c.add(g),g===0?"uv":`uv${g}`}return{getParameters:function(g,x,_,v,S){let E=v.fog,w=S.geometry,R=g.isMeshStandardMaterial||g.isMeshLambertMaterial||g.isMeshPhongMaterial?v.environment:null,z=g.isMeshStandardMaterial||g.isMeshLambertMaterial&&!g.envMap||g.isMeshPhongMaterial&&!g.envMap,j=e.get(g.envMap||R,z),O=j&&j.mapping===wa?j.image.height:null,Q=m[g.type];g.precision!==null&&(f=n.getMaxPrecision(g.precision),f!==g.precision&&Ye("WebGLProgram.getParameters:",g.precision,"not supported, using",f,"instead."));let Y=w.morphAttributes.position||w.morphAttributes.normal||w.morphAttributes.color,k=Y!==void 0?Y.length:0,X,K,te,oe,ee=0;if(w.morphAttributes.position!==void 0&&(ee=1),w.morphAttributes.normal!==void 0&&(ee=2),w.morphAttributes.color!==void 0&&(ee=3),Q){let ft=vi[Q];X=ft.vertexShader,K=ft.fragmentShader}else X=g.vertexShader,K=g.fragmentShader,o.update(g),te=o.getVertexShaderID(g),oe=o.getFragmentShaderID(g);let xe=r.getRenderTarget(),be=r.state.buffers.depth.getReversed(),we=S.isInstancedMesh===!0,Se=S.isBatchedMesh===!0,se=!!g.map,de=!!g.matcap,ge=!!j,Te=!!g.aoMap,Re=!!g.lightMap,ze=!!g.bumpMap,L=!!g.normalMap,C=!!g.displacementMap,J=!!g.emissiveMap,G=!!g.metalnessMap,T=!!g.roughnessMap,N=g.anisotropy>0,B=g.clearcoat>0,P=g.dispersion>0,V=g.iridescence>0,H=g.sheen>0,F=g.transmission>0,$=N&&!!g.anisotropyMap,M=B&&!!g.clearcoatMap,ne=B&&!!g.clearcoatNormalMap,le=B&&!!g.clearcoatRoughnessMap,ye=V&&!!g.iridescenceMap,Ne=V&&!!g.iridescenceThicknessMap,Fe=H&&!!g.sheenColorMap,Oe=H&&!!g.sheenRoughnessMap,ke=!!g.specularMap,Pe=!!g.specularColorMap,Ze=!!g.specularIntensityMap,Qe=F&&!!g.transmissionMap,lt=F&&!!g.thicknessMap,Ae=!!g.gradientMap,We=!!g.alphaMap,Ve=g.alphaTest>0,qt=!!g.alphaHash,ln=!!g.extensions,yt=si;g.toneMapped&&(xe!==null&&xe.isXRRenderTarget!==!0||(yt=r.toneMapping));let ht={shaderID:Q,shaderType:g.type,shaderName:g.name,vertexShader:X,fragmentShader:K,defines:g.defines,customVertexShaderID:te,customFragmentShaderID:oe,isRawShaderMaterial:g.isRawShaderMaterial===!0,glslVersion:g.glslVersion,precision:f,batching:Se,batchingColor:Se&&S._colorsTexture!==null,instancing:we,instancingColor:we&&S.instanceColor!==null,instancingMorph:we&&S.morphTexture!==null,outputColorSpace:xe===null?r.outputColorSpace:xe.isXRRenderTarget===!0?xe.texture.colorSpace:ur,alphaToCoverage:!!g.alphaToCoverage,map:se,matcap:de,envMap:ge,envMapMode:ge&&j.mapping,envMapCubeUVHeight:O,aoMap:Te,lightMap:Re,bumpMap:ze,normalMap:L,displacementMap:C,emissiveMap:J,normalMapObjectSpace:L&&g.normalMapType===ip,normalMapTangentSpace:L&&g.normalMapType===np,metalnessMap:G,roughnessMap:T,anisotropy:N,anisotropyMap:$,clearcoat:B,clearcoatMap:M,clearcoatNormalMap:ne,clearcoatRoughnessMap:le,dispersion:P,iridescence:V,iridescenceMap:ye,iridescenceThicknessMap:Ne,sheen:H,sheenColorMap:Fe,sheenRoughnessMap:Oe,specularMap:ke,specularColorMap:Pe,specularIntensityMap:Ze,transmission:F,transmissionMap:Qe,thicknessMap:lt,gradientMap:Ae,opaque:g.transparent===!1&&g.blending===Ta&&g.alphaToCoverage===!1,alphaMap:We,alphaTest:Ve,alphaHash:qt,combine:g.combine,mapUv:se&&u(g.map.channel),aoMapUv:Te&&u(g.aoMap.channel),lightMapUv:Re&&u(g.lightMap.channel),bumpMapUv:ze&&u(g.bumpMap.channel),normalMapUv:L&&u(g.normalMap.channel),displacementMapUv:C&&u(g.displacementMap.channel),emissiveMapUv:J&&u(g.emissiveMap.channel),metalnessMapUv:G&&u(g.metalnessMap.channel),roughnessMapUv:T&&u(g.roughnessMap.channel),anisotropyMapUv:$&&u(g.anisotropyMap.channel),clearcoatMapUv:M&&u(g.clearcoatMap.channel),clearcoatNormalMapUv:ne&&u(g.clearcoatNormalMap.channel),clearcoatRoughnessMapUv:le&&u(g.clearcoatRoughnessMap.channel),iridescenceMapUv:ye&&u(g.iridescenceMap.channel),iridescenceThicknessMapUv:Ne&&u(g.iridescenceThicknessMap.channel),sheenColorMapUv:Fe&&u(g.sheenColorMap.channel),sheenRoughnessMapUv:Oe&&u(g.sheenRoughnessMap.channel),specularMapUv:ke&&u(g.specularMap.channel),specularColorMapUv:Pe&&u(g.specularColorMap.channel),specularIntensityMapUv:Ze&&u(g.specularIntensityMap.channel),transmissionMapUv:Qe&&u(g.transmissionMap.channel),thicknessMapUv:lt&&u(g.thicknessMap.channel),alphaMapUv:We&&u(g.alphaMap.channel),vertexTangents:!!w.attributes.tangent&&(L||N),vertexColors:g.vertexColors,vertexAlphas:g.vertexColors===!0&&!!w.attributes.color&&w.attributes.color.itemSize===4,pointsUvs:S.isPoints===!0&&!!w.attributes.uv&&(se||We),fog:!!E,useFog:g.fog===!0,fogExp2:!!E&&E.isFogExp2,flatShading:g.wireframe===!1&&(g.flatShading===!0||w.attributes.normal===void 0&&L===!1&&(g.isMeshLambertMaterial||g.isMeshPhongMaterial||g.isMeshStandardMaterial||g.isMeshPhysicalMaterial)),sizeAttenuation:g.sizeAttenuation===!0,logarithmicDepthBuffer:p,reversedDepthBuffer:be,skinning:S.isSkinnedMesh===!0,morphTargets:w.morphAttributes.position!==void 0,morphNormals:w.morphAttributes.normal!==void 0,morphColors:w.morphAttributes.color!==void 0,morphTargetsCount:k,morphTextureStride:ee,numDirLights:x.directional.length,numPointLights:x.point.length,numSpotLights:x.spot.length,numSpotLightMaps:x.spotLightMap.length,numRectAreaLights:x.rectArea.length,numHemiLights:x.hemi.length,numDirLightShadows:x.directionalShadowMap.length,numPointLightShadows:x.pointShadowMap.length,numSpotLightShadows:x.spotShadowMap.length,numSpotLightShadowsWithMaps:x.numSpotLightShadowsWithMaps,numLightProbes:x.numLightProbes,numClippingPlanes:s.numPlanes,numClipIntersection:s.numIntersection,dithering:g.dithering,shadowMapEnabled:r.shadowMap.enabled&&_.length>0,shadowMapType:r.shadowMap.type,toneMapping:yt,decodeVideoTexture:se&&g.map.isVideoTexture===!0&&ut.getTransfer(g.map.colorSpace)===gt,decodeVideoTextureEmissive:J&&g.emissiveMap.isVideoTexture===!0&&ut.getTransfer(g.emissiveMap.colorSpace)===gt,premultipliedAlpha:g.premultipliedAlpha,doubleSided:g.side===En,flipSided:g.side===Tn,useDepthPacking:g.depthPacking>=0,depthPacking:g.depthPacking||0,index0AttributeName:g.index0AttributeName,extensionClipCullDistance:ln&&g.extensions.clipCullDistance===!0&&t.has("WEBGL_clip_cull_distance"),extensionMultiDraw:(ln&&g.extensions.multiDraw===!0||Se)&&t.has("WEBGL_multi_draw"),rendererExtensionParallelShaderCompile:t.has("KHR_parallel_shader_compile"),customProgramCacheKey:g.customProgramCacheKey()};return ht.vertexUv1s=c.has(1),ht.vertexUv2s=c.has(2),ht.vertexUv3s=c.has(3),c.clear(),ht},getProgramCacheKey:function(g){let x=[];if(g.shaderID?x.push(g.shaderID):(x.push(g.customVertexShaderID),x.push(g.customFragmentShaderID)),g.defines!==void 0)for(let _ in g.defines)x.push(_),x.push(g.defines[_]);return g.isRawShaderMaterial===!1&&((function(_,v){_.push(v.precision),_.push(v.outputColorSpace),_.push(v.envMapMode),_.push(v.envMapCubeUVHeight),_.push(v.mapUv),_.push(v.alphaMapUv),_.push(v.lightMapUv),_.push(v.aoMapUv),_.push(v.bumpMapUv),_.push(v.normalMapUv),_.push(v.displacementMapUv),_.push(v.emissiveMapUv),_.push(v.metalnessMapUv),_.push(v.roughnessMapUv),_.push(v.anisotropyMapUv),_.push(v.clearcoatMapUv),_.push(v.clearcoatNormalMapUv),_.push(v.clearcoatRoughnessMapUv),_.push(v.iridescenceMapUv),_.push(v.iridescenceThicknessMapUv),_.push(v.sheenColorMapUv),_.push(v.sheenRoughnessMapUv),_.push(v.specularMapUv),_.push(v.specularColorMapUv),_.push(v.specularIntensityMapUv),_.push(v.transmissionMapUv),_.push(v.thicknessMapUv),_.push(v.combine),_.push(v.fogExp2),_.push(v.sizeAttenuation),_.push(v.morphTargetsCount),_.push(v.morphAttributeCount),_.push(v.numDirLights),_.push(v.numPointLights),_.push(v.numSpotLights),_.push(v.numSpotLightMaps),_.push(v.numHemiLights),_.push(v.numRectAreaLights),_.push(v.numDirLightShadows),_.push(v.numPointLightShadows),_.push(v.numSpotLightShadows),_.push(v.numSpotLightShadowsWithMaps),_.push(v.numLightProbes),_.push(v.shadowMapType),_.push(v.toneMapping),_.push(v.numClippingPlanes),_.push(v.numClipIntersection),_.push(v.depthPacking)})(x,g),(function(_,v){a.disableAll(),v.instancing&&a.enable(0),v.instancingColor&&a.enable(1),v.instancingMorph&&a.enable(2),v.matcap&&a.enable(3),v.envMap&&a.enable(4),v.normalMapObjectSpace&&a.enable(5),v.normalMapTangentSpace&&a.enable(6),v.clearcoat&&a.enable(7),v.iridescence&&a.enable(8),v.alphaTest&&a.enable(9),v.vertexColors&&a.enable(10),v.vertexAlphas&&a.enable(11),v.vertexUv1s&&a.enable(12),v.vertexUv2s&&a.enable(13),v.vertexUv3s&&a.enable(14),v.vertexTangents&&a.enable(15),v.anisotropy&&a.enable(16),v.alphaHash&&a.enable(17),v.batching&&a.enable(18),v.dispersion&&a.enable(19),v.batchingColor&&a.enable(20),v.gradientMap&&a.enable(21),_.push(a.mask),a.disableAll(),v.fog&&a.enable(0),v.useFog&&a.enable(1),v.flatShading&&a.enable(2),v.logarithmicDepthBuffer&&a.enable(3),v.reversedDepthBuffer&&a.enable(4),v.skinning&&a.enable(5),v.morphTargets&&a.enable(6),v.morphNormals&&a.enable(7),v.morphColors&&a.enable(8),v.premultipliedAlpha&&a.enable(9),v.shadowMapEnabled&&a.enable(10),v.doubleSided&&a.enable(11),v.flipSided&&a.enable(12),v.useDepthPacking&&a.enable(13),v.dithering&&a.enable(14),v.transmission&&a.enable(15),v.sheen&&a.enable(16),v.opaque&&a.enable(17),v.pointsUvs&&a.enable(18),v.decodeVideoTexture&&a.enable(19),v.decodeVideoTextureEmissive&&a.enable(20),v.alphaToCoverage&&a.enable(21),_.push(a.mask)})(x,g),x.push(r.outputColorSpace)),x.push(g.customProgramCacheKey),x.join()},getUniforms:function(g){let x=m[g.type],_;if(x){let v=vi[x];_=vp.clone(v.uniforms)}else _=g.uniforms;return _},acquireProgram:function(g,x){let _=h.get(x);return _!==void 0?++_.usedTimes:(_=new Mg(r,x,g,i),l.push(_),h.set(x,_)),_},releaseProgram:function(g){if(--g.usedTimes===0){let x=l.indexOf(g);l[x]=l[l.length-1],l.pop(),h.delete(g.cacheKey),g.destroy()}},releaseShaderCache:function(g){o.remove(g)},programs:l,dispose:function(){o.dispose()}}}function Tg(){let r=new WeakMap;return{has:function(e){return r.has(e)},get:function(e){let t=r.get(e);return t===void 0&&(t={},r.set(e,t)),t},remove:function(e){r.delete(e)},update:function(e,t,n){r.get(e)[t]=n},dispose:function(){r=new WeakMap}}}function Eg(r,e){return r.groupOrder!==e.groupOrder?r.groupOrder-e.groupOrder:r.renderOrder!==e.renderOrder?r.renderOrder-e.renderOrder:r.material.id!==e.material.id?r.material.id-e.material.id:r.materialVariant!==e.materialVariant?r.materialVariant-e.materialVariant:r.z!==e.z?r.z-e.z:r.id-e.id}function Bp(r,e){return r.groupOrder!==e.groupOrder?r.groupOrder-e.groupOrder:r.renderOrder!==e.renderOrder?r.renderOrder-e.renderOrder:r.z!==e.z?e.z-r.z:r.id-e.id}function zp(){let r=[],e=0,t=[],n=[],i=[];function s(o){let c=0;return o.isInstancedMesh&&(c+=2),o.isSkinnedMesh&&(c+=1),c}function a(o,c,l,h,p,f){let m=r[e];return m===void 0?(m={id:o.id,object:o,geometry:c,material:l,materialVariant:s(o),groupOrder:h,renderOrder:o.renderOrder,z:p,group:f},r[e]=m):(m.id=o.id,m.object=o,m.geometry=c,m.material=l,m.materialVariant=s(o),m.groupOrder=h,m.renderOrder=o.renderOrder,m.z=p,m.group=f),e++,m}return{opaque:t,transmissive:n,transparent:i,init:function(){e=0,t.length=0,n.length=0,i.length=0},push:function(o,c,l,h,p,f){let m=a(o,c,l,h,p,f);l.transmission>0?n.push(m):l.transparent===!0?i.push(m):t.push(m)},unshift:function(o,c,l,h,p,f){let m=a(o,c,l,h,p,f);l.transmission>0?n.unshift(m):l.transparent===!0?i.unshift(m):t.unshift(m)},finish:function(){for(let o=e,c=r.length;o<c;o++){let l=r[o];if(l.id===null)break;l.id=null,l.object=null,l.geometry=null,l.material=null,l.group=null}},sort:function(o,c){t.length>1&&t.sort(o||Eg),n.length>1&&n.sort(c||Bp),i.length>1&&i.sort(c||Bp)}}}function wg(){let r=new WeakMap;return{get:function(e,t){let n=r.get(e),i;return n===void 0?(i=new zp,r.set(e,[i])):t>=n.length?(i=new zp,n.push(i)):i=n[t],i},dispose:function(){r=new WeakMap}}}function Ag(){let r={};return{get:function(e){if(r[e.id]!==void 0)return r[e.id];let t;switch(e.type){case"DirectionalLight":t={direction:new D,color:new He};break;case"SpotLight":t={position:new D,direction:new D,color:new He,distance:0,coneCos:0,penumbraCos:0,decay:0};break;case"PointLight":t={position:new D,color:new He,distance:0,decay:0};break;case"HemisphereLight":t={direction:new D,skyColor:new He,groundColor:new He};break;case"RectAreaLight":t={color:new He,position:new D,halfWidth:new D,halfHeight:new D}}return r[e.id]=t,t}}}var Cg=0;function Rg(r,e){return(e.castShadow?2:0)-(r.castShadow?2:0)+(e.map?1:0)-(r.map?1:0)}function Pg(r){let e=new Ag,t=(function(){let o={};return{get:function(c){if(o[c.id]!==void 0)return o[c.id];let l;switch(c.type){case"DirectionalLight":case"SpotLight":l={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new _e};break;case"PointLight":l={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new _e,shadowCameraNear:1,shadowCameraFar:1e3}}return o[c.id]=l,l}}})(),n={version:0,hash:{directionalLength:-1,pointLength:-1,spotLength:-1,rectAreaLength:-1,hemiLength:-1,numDirectionalShadows:-1,numPointShadows:-1,numSpotShadows:-1,numSpotMaps:-1,numLightProbes:-1},ambient:[0,0,0],probe:[],directional:[],directionalShadow:[],directionalShadowMap:[],directionalShadowMatrix:[],spot:[],spotLightMap:[],spotShadow:[],spotShadowMap:[],spotLightMatrix:[],rectArea:[],rectAreaLTC1:null,rectAreaLTC2:null,point:[],pointShadow:[],pointShadowMap:[],pointShadowMatrix:[],hemi:[],numSpotLightShadowsWithMaps:0,numLightProbes:0};for(let o=0;o<9;o++)n.probe.push(new D);let i=new D,s=new Ke,a=new Ke;return{setup:function(o){let c=0,l=0,h=0;for(let z=0;z<9;z++)n.probe[z].set(0,0,0);let p=0,f=0,m=0,u=0,g=0,x=0,_=0,v=0,S=0,E=0,w=0;o.sort(Rg);for(let z=0,j=o.length;z<j;z++){let O=o[z],Q=O.color,Y=O.intensity,k=O.distance,X=null;if(O.shadow&&O.shadow.map&&(X=O.shadow.map.texture.format===ys?O.shadow.map.texture:O.shadow.map.depthTexture||O.shadow.map.texture),O.isAmbientLight)c+=Q.r*Y,l+=Q.g*Y,h+=Q.b*Y;else if(O.isLightProbe){for(let K=0;K<9;K++)n.probe[K].addScaledVector(O.sh.coefficients[K],Y);w++}else if(O.isDirectionalLight){let K=e.get(O);if(K.color.copy(O.color).multiplyScalar(O.intensity),O.castShadow){let te=O.shadow,oe=t.get(O);oe.shadowIntensity=te.intensity,oe.shadowBias=te.bias,oe.shadowNormalBias=te.normalBias,oe.shadowRadius=te.radius,oe.shadowMapSize=te.mapSize,n.directionalShadow[p]=oe,n.directionalShadowMap[p]=X,n.directionalShadowMatrix[p]=O.shadow.matrix,x++}n.directional[p]=K,p++}else if(O.isSpotLight){let K=e.get(O);K.position.setFromMatrixPosition(O.matrixWorld),K.color.copy(Q).multiplyScalar(Y),K.distance=k,K.coneCos=Math.cos(O.angle),K.penumbraCos=Math.cos(O.angle*(1-O.penumbra)),K.decay=O.decay,n.spot[m]=K;let te=O.shadow;if(O.map&&(n.spotLightMap[S]=O.map,S++,te.updateMatrices(O),O.castShadow&&E++),n.spotLightMatrix[m]=te.matrix,O.castShadow){let oe=t.get(O);oe.shadowIntensity=te.intensity,oe.shadowBias=te.bias,oe.shadowNormalBias=te.normalBias,oe.shadowRadius=te.radius,oe.shadowMapSize=te.mapSize,n.spotShadow[m]=oe,n.spotShadowMap[m]=X,v++}m++}else if(O.isRectAreaLight){let K=e.get(O);K.color.copy(Q).multiplyScalar(Y),K.halfWidth.set(.5*O.width,0,0),K.halfHeight.set(0,.5*O.height,0),n.rectArea[u]=K,u++}else if(O.isPointLight){let K=e.get(O);if(K.color.copy(O.color).multiplyScalar(O.intensity),K.distance=O.distance,K.decay=O.decay,O.castShadow){let te=O.shadow,oe=t.get(O);oe.shadowIntensity=te.intensity,oe.shadowBias=te.bias,oe.shadowNormalBias=te.normalBias,oe.shadowRadius=te.radius,oe.shadowMapSize=te.mapSize,oe.shadowCameraNear=te.camera.near,oe.shadowCameraFar=te.camera.far,n.pointShadow[f]=oe,n.pointShadowMap[f]=X,n.pointShadowMatrix[f]=O.shadow.matrix,_++}n.point[f]=K,f++}else if(O.isHemisphereLight){let K=e.get(O);K.skyColor.copy(O.color).multiplyScalar(Y),K.groundColor.copy(O.groundColor).multiplyScalar(Y),n.hemi[g]=K,g++}}u>0&&(r.has("OES_texture_float_linear")===!0?(n.rectAreaLTC1=Ce.LTC_FLOAT_1,n.rectAreaLTC2=Ce.LTC_FLOAT_2):(n.rectAreaLTC1=Ce.LTC_HALF_1,n.rectAreaLTC2=Ce.LTC_HALF_2)),n.ambient[0]=c,n.ambient[1]=l,n.ambient[2]=h;let R=n.hash;R.directionalLength===p&&R.pointLength===f&&R.spotLength===m&&R.rectAreaLength===u&&R.hemiLength===g&&R.numDirectionalShadows===x&&R.numPointShadows===_&&R.numSpotShadows===v&&R.numSpotMaps===S&&R.numLightProbes===w||(n.directional.length=p,n.spot.length=m,n.rectArea.length=u,n.point.length=f,n.hemi.length=g,n.directionalShadow.length=x,n.directionalShadowMap.length=x,n.pointShadow.length=_,n.pointShadowMap.length=_,n.spotShadow.length=v,n.spotShadowMap.length=v,n.directionalShadowMatrix.length=x,n.pointShadowMatrix.length=_,n.spotLightMatrix.length=v+S-E,n.spotLightMap.length=S,n.numSpotLightShadowsWithMaps=E,n.numLightProbes=w,R.directionalLength=p,R.pointLength=f,R.spotLength=m,R.rectAreaLength=u,R.hemiLength=g,R.numDirectionalShadows=x,R.numPointShadows=_,R.numSpotShadows=v,R.numSpotMaps=S,R.numLightProbes=w,n.version=Cg++)},setupView:function(o,c){let l=0,h=0,p=0,f=0,m=0,u=c.matrixWorldInverse;for(let g=0,x=o.length;g<x;g++){let _=o[g];if(_.isDirectionalLight){let v=n.directional[l];v.direction.setFromMatrixPosition(_.matrixWorld),i.setFromMatrixPosition(_.target.matrixWorld),v.direction.sub(i),v.direction.transformDirection(u),l++}else if(_.isSpotLight){let v=n.spot[p];v.position.setFromMatrixPosition(_.matrixWorld),v.position.applyMatrix4(u),v.direction.setFromMatrixPosition(_.matrixWorld),i.setFromMatrixPosition(_.target.matrixWorld),v.direction.sub(i),v.direction.transformDirection(u),p++}else if(_.isRectAreaLight){let v=n.rectArea[f];v.position.setFromMatrixPosition(_.matrixWorld),v.position.applyMatrix4(u),a.identity(),s.copy(_.matrixWorld),s.premultiply(u),a.extractRotation(s),v.halfWidth.set(.5*_.width,0,0),v.halfHeight.set(0,.5*_.height,0),v.halfWidth.applyMatrix4(a),v.halfHeight.applyMatrix4(a),f++}else if(_.isPointLight){let v=n.point[h];v.position.setFromMatrixPosition(_.matrixWorld),v.position.applyMatrix4(u),h++}else if(_.isHemisphereLight){let v=n.hemi[m];v.direction.setFromMatrixPosition(_.matrixWorld),v.direction.transformDirection(u),m++}}},state:n}}function kp(r){let e=new Pg(r),t=[],n=[],i={lightsArray:t,shadowsArray:n,camera:null,lights:e,transmissionRenderTarget:{}};return{init:function(s){i.camera=s,t.length=0,n.length=0},state:i,setupLights:function(){e.setup(t)},setupLightsView:function(s){e.setupView(t,s)},pushLight:function(s){t.push(s)},pushShadow:function(s){n.push(s)}}}function Ig(r){let e=new WeakMap;return{get:function(t,n=0){let i=e.get(t),s;return i===void 0?(s=new kp(r),e.set(t,[s])):n>=i.length?(s=new kp(r),i.push(s)):s=i[n],s},dispose:function(){e=new WeakMap}}}var Lg=[new D(1,0,0),new D(-1,0,0),new D(0,1,0),new D(0,-1,0),new D(0,0,1),new D(0,0,-1)],Dg=[new D(0,-1,0),new D(0,-1,0),new D(0,0,1),new D(0,0,-1),new D(0,-1,0),new D(0,-1,0)],Vp=new Ke,Ia=new D,hu=new D;function Ug(r,e,t){let n=new ji,i=new _e,s=new _e,a=new wt,o=new ol,c=new ll,l={},h=t.maxTextureSize,p={[fs]:Tn,[Tn]:fs,[En]:En},f=new Bn({defines:{VSM_SAMPLES:8},uniforms:{shadow_pass:{value:null},resolution:{value:new _e},radius:{value:4}},vertexShader:`void main() {
	gl_Position = vec4( position, 1.0 );
}`,fragmentShader:`uniform sampler2D shadow_pass;
uniform vec2 resolution;
uniform float radius;
void main() {
	const float samples = float( VSM_SAMPLES );
	float mean = 0.0;
	float squared_mean = 0.0;
	float uvStride = samples <= 1.0 ? 0.0 : 2.0 / ( samples - 1.0 );
	float uvStart = samples <= 1.0 ? 0.0 : - 1.0;
	for ( float i = 0.0; i < samples; i ++ ) {
		float uvOffset = uvStart + i * uvStride;
		#ifdef HORIZONTAL_PASS
			vec2 distribution = texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( uvOffset, 0.0 ) * radius ) / resolution ).rg;
			mean += distribution.x;
			squared_mean += distribution.y * distribution.y + distribution.x * distribution.x;
		#else
			float depth = texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( 0.0, uvOffset ) * radius ) / resolution ).r;
			mean += depth;
			squared_mean += depth * depth;
		#endif
	}
	mean = mean / samples;
	squared_mean = squared_mean / samples;
	float std_dev = sqrt( max( 0.0, squared_mean - mean * mean ) );
	gl_FragColor = vec4( mean, std_dev, 0.0, 1.0 );
}`}),m=f.clone();m.defines.HORIZONTAL_PASS=1;let u=new bt;u.setAttribute("position",new _n(new Float32Array([-1,-1,.5,3,-1,.5,-1,3,.5]),3));let g=new At(u,f),x=this;this.enabled=!1,this.autoUpdate=!0,this.needsUpdate=!1,this.type=Sa;let _=this.type;function v(R,z){let j=e.update(g);f.defines.VSM_SAMPLES!==R.blurSamples&&(f.defines.VSM_SAMPLES=R.blurSamples,m.defines.VSM_SAMPLES=R.blurSamples,f.needsUpdate=!0,m.needsUpdate=!0),R.mapPass===null&&(R.mapPass=new Dn(i.x,i.y,{format:ys,type:gi})),f.uniforms.shadow_pass.value=R.map.depthTexture,f.uniforms.resolution.value=R.mapSize,f.uniforms.radius.value=R.radius,r.setRenderTarget(R.mapPass),r.clear(),r.renderBufferDirect(z,null,j,f,g,null),m.uniforms.shadow_pass.value=R.mapPass.texture,m.uniforms.resolution.value=R.mapSize,m.uniforms.radius.value=R.radius,r.setRenderTarget(R.map),r.clear(),r.renderBufferDirect(z,null,j,m,g,null)}function S(R,z,j,O){let Q=null,Y=j.isPointLight===!0?R.customDistanceMaterial:R.customDepthMaterial;if(Y!==void 0)Q=Y;else if(Q=j.isPointLight===!0?c:o,r.localClippingEnabled&&z.clipShadows===!0&&Array.isArray(z.clippingPlanes)&&z.clippingPlanes.length!==0||z.displacementMap&&z.displacementScale!==0||z.alphaMap&&z.alphaTest>0||z.map&&z.alphaTest>0||z.alphaToCoverage===!0){let k=Q.uuid,X=z.uuid,K=l[k];K===void 0&&(K={},l[k]=K);let te=K[X];te===void 0&&(te=Q.clone(),K[X]=te,z.addEventListener("dispose",w)),Q=te}return Q.visible=z.visible,Q.wireframe=z.wireframe,Q.side=O===ps?z.shadowSide!==null?z.shadowSide:z.side:z.shadowSide!==null?z.shadowSide:p[z.side],Q.alphaMap=z.alphaMap,Q.alphaTest=z.alphaToCoverage===!0?.5:z.alphaTest,Q.map=z.map,Q.clipShadows=z.clipShadows,Q.clippingPlanes=z.clippingPlanes,Q.clipIntersection=z.clipIntersection,Q.displacementMap=z.displacementMap,Q.displacementScale=z.displacementScale,Q.displacementBias=z.displacementBias,Q.wireframeLinewidth=z.wireframeLinewidth,Q.linewidth=z.linewidth,j.isPointLight===!0&&Q.isMeshDistanceMaterial===!0&&(r.properties.get(Q).light=j),Q}function E(R,z,j,O,Q){if(R.visible===!1)return;if(R.layers.test(z.layers)&&(R.isMesh||R.isLine||R.isPoints)&&(R.castShadow||R.receiveShadow&&Q===ps)&&(!R.frustumCulled||n.intersectsObject(R))){R.modelViewMatrix.multiplyMatrices(j.matrixWorldInverse,R.matrixWorld);let k=e.update(R),X=R.material;if(Array.isArray(X)){let K=k.groups;for(let te=0,oe=K.length;te<oe;te++){let ee=K[te],xe=X[ee.materialIndex];if(xe&&xe.visible){let be=S(R,xe,O,Q);R.onBeforeShadow(r,R,z,j,k,be,ee),r.renderBufferDirect(j,null,k,be,R,ee),R.onAfterShadow(r,R,z,j,k,be,ee)}}}else if(X.visible){let K=S(R,X,O,Q);R.onBeforeShadow(r,R,z,j,k,K,null),r.renderBufferDirect(j,null,k,K,R,null),R.onAfterShadow(r,R,z,j,k,K,null)}}let Y=R.children;for(let k=0,X=Y.length;k<X;k++)E(Y[k],z,j,O,Q)}function w(R){R.target.removeEventListener("dispose",w);for(let z in l){let j=l[z],O=R.target.uuid;O in j&&(j[O].dispose(),delete j[O])}}this.render=function(R,z,j){if(x.enabled===!1||x.autoUpdate===!1&&x.needsUpdate===!1||R.length===0)return;this.type===bl&&(Ye("WebGLShadowMap: PCFSoftShadowMap has been deprecated. Using PCFShadowMap instead."),this.type=Sa);let O=r.getRenderTarget(),Q=r.getActiveCubeFace(),Y=r.getActiveMipmapLevel(),k=r.state;k.setBlending(mi),k.buffers.depth.getReversed()===!0?k.buffers.color.setClear(0,0,0,0):k.buffers.color.setClear(1,1,1,1),k.buffers.depth.setTest(!0),k.setScissorTest(!1);let X=_!==this.type;X&&z.traverse(function(K){K.material&&(Array.isArray(K.material)?K.material.forEach(te=>te.needsUpdate=!0):K.material.needsUpdate=!0)});for(let K=0,te=R.length;K<te;K++){let oe=R[K],ee=oe.shadow;if(ee===void 0){Ye("WebGLShadowMap:",oe,"has no shadow.");continue}if(ee.autoUpdate===!1&&ee.needsUpdate===!1)continue;i.copy(ee.mapSize);let xe=ee.getFrameExtents();i.multiply(xe),s.copy(ee.mapSize),(i.x>h||i.y>h)&&(i.x>h&&(s.x=Math.floor(h/xe.x),i.x=s.x*xe.x,ee.mapSize.x=s.x),i.y>h&&(s.y=Math.floor(h/xe.y),i.y=s.y*xe.y,ee.mapSize.y=s.y));let be=r.state.buffers.depth.getReversed();if(ee.camera._reversedDepth=be,ee.map===null||X===!0){if(ee.map!==null&&(ee.map.depthTexture!==null&&(ee.map.depthTexture.dispose(),ee.map.depthTexture=null),ee.map.dispose()),this.type===ps){if(oe.isPointLight){Ye("WebGLShadowMap: VSM shadow maps are not supported for PointLights. Use PCF or BasicShadowMap instead.");continue}ee.map=new Dn(i.x,i.y,{format:ys,type:gi,minFilter:Xt,magFilter:Xt,generateMipmaps:!1}),ee.map.texture.name=oe.name+".shadowMap",ee.map.depthTexture=new Xi(i.x,i.y,Kn),ee.map.depthTexture.name=oe.name+".shadowMapDepth",ee.map.depthTexture.format=Ki,ee.map.depthTexture.compareFunction=null,ee.map.depthTexture.minFilter=Yn,ee.map.depthTexture.magFilter=Yn}else oe.isPointLight?(ee.map=new Gl(i.x),ee.map.depthTexture=new Fo(i.x,Li)):(ee.map=new Dn(i.x,i.y),ee.map.depthTexture=new Xi(i.x,i.y,Li)),ee.map.depthTexture.name=oe.name+".shadowMap",ee.map.depthTexture.format=Ki,this.type===Sa?(ee.map.depthTexture.compareFunction=be?Fl:Ol,ee.map.depthTexture.minFilter=Xt,ee.map.depthTexture.magFilter=Xt):(ee.map.depthTexture.compareFunction=null,ee.map.depthTexture.minFilter=Yn,ee.map.depthTexture.magFilter=Yn);ee.camera.updateProjectionMatrix()}let we=ee.map.isWebGLCubeRenderTarget?6:1;for(let Se=0;Se<we;Se++){if(ee.map.isWebGLCubeRenderTarget)r.setRenderTarget(ee.map,Se),r.clear();else{Se===0&&(r.setRenderTarget(ee.map),r.clear());let se=ee.getViewport(Se);a.set(s.x*se.x,s.y*se.y,s.x*se.z,s.y*se.w),k.viewport(a)}if(oe.isPointLight){let se=ee.camera,de=ee.matrix,ge=oe.distance||se.far;ge!==se.far&&(se.far=ge,se.updateProjectionMatrix()),Ia.setFromMatrixPosition(oe.matrixWorld),se.position.copy(Ia),hu.copy(se.position),hu.add(Lg[Se]),se.up.copy(Dg[Se]),se.lookAt(hu),se.updateMatrixWorld(),de.makeTranslation(-Ia.x,-Ia.y,-Ia.z),Vp.multiplyMatrices(se.projectionMatrix,se.matrixWorldInverse),ee._frustum.setFromProjectionMatrix(Vp,se.coordinateSystem,se.reversedDepth)}else ee.updateMatrices(oe);n=ee.getFrustum(),E(z,j,ee.camera,oe,this.type)}ee.isPointLightShadow!==!0&&this.type===ps&&v(ee,j),ee.needsUpdate=!1}_=this.type,x.needsUpdate=!1,r.setRenderTarget(O,Q,Y)}}function Ng(r,e){let t=new function(){let T=!1,N=new wt,B=null,P=new wt(0,0,0,0);return{setMask:function(V){B===V||T||(r.colorMask(V,V,V,V),B=V)},setLocked:function(V){T=V},setClear:function(V,H,F,$,M){M===!0&&(V*=$,H*=$,F*=$),N.set(V,H,F,$),P.equals(N)===!1&&(r.clearColor(V,H,F,$),P.copy(N))},reset:function(){T=!1,B=null,P.set(-1,0,0,0)}}},n=new function(){let T=!1,N=!1,B=null,P=null,V=null;return{setReversed:function(H){if(N!==H){let F=e.get("EXT_clip_control");H?F.clipControlEXT(F.LOWER_LEFT_EXT,F.ZERO_TO_ONE_EXT):F.clipControlEXT(F.LOWER_LEFT_EXT,F.NEGATIVE_ONE_TO_ONE_EXT),N=H;let $=V;V=null,this.setClear($)}},getReversed:function(){return N},setTest:function(H){H?ge(r.DEPTH_TEST):Te(r.DEPTH_TEST)},setMask:function(H){B===H||T||(r.depthMask(H),B=H)},setFunc:function(H){if(N&&(H=pp[H]),P!==H){switch(H){case eh:r.depthFunc(r.NEVER);break;case th:r.depthFunc(r.ALWAYS);break;case nh:r.depthFunc(r.LESS);break;case Sl:r.depthFunc(r.LEQUAL);break;case ih:r.depthFunc(r.EQUAL);break;case rh:r.depthFunc(r.GEQUAL);break;case sh:r.depthFunc(r.GREATER);break;case ah:r.depthFunc(r.NOTEQUAL);break;default:r.depthFunc(r.LEQUAL)}P=H}},setLocked:function(H){T=H},setClear:function(H){V!==H&&(V=H,N&&(H=1-H),r.clearDepth(H))},reset:function(){T=!1,B=null,P=null,V=null,N=!1}}},i=new function(){let T=!1,N=null,B=null,P=null,V=null,H=null,F=null,$=null,M=null;return{setTest:function(ne){T||(ne?ge(r.STENCIL_TEST):Te(r.STENCIL_TEST))},setMask:function(ne){N===ne||T||(r.stencilMask(ne),N=ne)},setFunc:function(ne,le,ye){B===ne&&P===le&&V===ye||(r.stencilFunc(ne,le,ye),B=ne,P=le,V=ye)},setOp:function(ne,le,ye){H===ne&&F===le&&$===ye||(r.stencilOp(ne,le,ye),H=ne,F=le,$=ye)},setLocked:function(ne){T=ne},setClear:function(ne){M!==ne&&(r.clearStencil(ne),M=ne)},reset:function(){T=!1,N=null,B=null,P=null,V=null,H=null,F=null,$=null,M=null}}},s=new WeakMap,a=new WeakMap,o={},c={},l=new WeakMap,h=[],p=null,f=!1,m=null,u=null,g=null,x=null,_=null,v=null,S=null,E=new He(0,0,0),w=0,R=!1,z=null,j=null,O=null,Q=null,Y=null,k=r.getParameter(r.MAX_COMBINED_TEXTURE_IMAGE_UNITS),X=!1,K=0,te=r.getParameter(r.VERSION);te.indexOf("WebGL")!==-1?(K=parseFloat(/^WebGL (\d)/.exec(te)[1]),X=K>=1):te.indexOf("OpenGL ES")!==-1&&(K=parseFloat(/^OpenGL ES (\d)/.exec(te)[1]),X=K>=2);let oe=null,ee={},xe=r.getParameter(r.SCISSOR_BOX),be=r.getParameter(r.VIEWPORT),we=new wt().fromArray(xe),Se=new wt().fromArray(be);function se(T,N,B,P){let V=new Uint8Array(4),H=r.createTexture();r.bindTexture(T,H),r.texParameteri(T,r.TEXTURE_MIN_FILTER,r.NEAREST),r.texParameteri(T,r.TEXTURE_MAG_FILTER,r.NEAREST);for(let F=0;F<B;F++)T===r.TEXTURE_3D||T===r.TEXTURE_2D_ARRAY?r.texImage3D(N,0,r.RGBA,1,1,P,0,r.RGBA,r.UNSIGNED_BYTE,V):r.texImage2D(N+F,0,r.RGBA,1,1,0,r.RGBA,r.UNSIGNED_BYTE,V);return H}let de={};function ge(T){o[T]!==!0&&(r.enable(T),o[T]=!0)}function Te(T){o[T]!==!1&&(r.disable(T),o[T]=!1)}de[r.TEXTURE_2D]=se(r.TEXTURE_2D,r.TEXTURE_2D,1),de[r.TEXTURE_CUBE_MAP]=se(r.TEXTURE_CUBE_MAP,r.TEXTURE_CUBE_MAP_POSITIVE_X,6),de[r.TEXTURE_2D_ARRAY]=se(r.TEXTURE_2D_ARRAY,r.TEXTURE_2D_ARRAY,1,1),de[r.TEXTURE_3D]=se(r.TEXTURE_3D,r.TEXTURE_3D,1,1),t.setClear(0,0,0,1),n.setClear(1),i.setClear(0),ge(r.DEPTH_TEST),n.setFunc(Sl),C(!1),J(Jc),ge(r.CULL_FACE),L(mi);let Re={[ms]:r.FUNC_ADD,[Id]:r.FUNC_SUBTRACT,[Ld]:r.FUNC_REVERSE_SUBTRACT};Re[Dd]=r.MIN,Re[Ud]=r.MAX;let ze={[Nd]:r.ZERO,[Od]:r.ONE,[Fd]:r.SRC_COLOR,[zd]:r.SRC_ALPHA,[jd]:r.SRC_ALPHA_SATURATE,[Hd]:r.DST_COLOR,[Vd]:r.DST_ALPHA,[Bd]:r.ONE_MINUS_SRC_COLOR,[kd]:r.ONE_MINUS_SRC_ALPHA,[Wd]:r.ONE_MINUS_DST_COLOR,[Gd]:r.ONE_MINUS_DST_ALPHA,[Xd]:r.CONSTANT_COLOR,[qd]:r.ONE_MINUS_CONSTANT_COLOR,[Yd]:r.CONSTANT_ALPHA,[Zd]:r.ONE_MINUS_CONSTANT_ALPHA};function L(T,N,B,P,V,H,F,$,M,ne){if(T!==mi){if(f===!1&&(ge(r.BLEND),f=!0),T===Pd)V=V||N,H=H||B,F=F||P,N===u&&V===_||(r.blendEquationSeparate(Re[N],Re[V]),u=N,_=V),B===g&&P===x&&H===v&&F===S||(r.blendFuncSeparate(ze[B],ze[P],ze[H],ze[F]),g=B,x=P,v=H,S=F),$.equals(E)!==!1&&M===w||(r.blendColor($.r,$.g,$.b,M),E.copy($),w=M),m=T,R=!1;else if(T!==m||ne!==R){if(u===ms&&_===ms||(r.blendEquation(r.FUNC_ADD),u=ms,_=ms),ne)switch(T){case Ta:r.blendFuncSeparate(r.ONE,r.ONE_MINUS_SRC_ALPHA,r.ONE,r.ONE_MINUS_SRC_ALPHA);break;case Kc:r.blendFunc(r.ONE,r.ONE);break;case $c:r.blendFuncSeparate(r.ZERO,r.ONE_MINUS_SRC_COLOR,r.ZERO,r.ONE);break;case Qc:r.blendFuncSeparate(r.DST_COLOR,r.ONE_MINUS_SRC_ALPHA,r.ZERO,r.ONE);break;default:Je("WebGLState: Invalid blending: ",T)}else switch(T){case Ta:r.blendFuncSeparate(r.SRC_ALPHA,r.ONE_MINUS_SRC_ALPHA,r.ONE,r.ONE_MINUS_SRC_ALPHA);break;case Kc:r.blendFuncSeparate(r.SRC_ALPHA,r.ONE,r.ONE,r.ONE);break;case $c:Je("WebGLState: SubtractiveBlending requires material.premultipliedAlpha = true");break;case Qc:Je("WebGLState: MultiplyBlending requires material.premultipliedAlpha = true");break;default:Je("WebGLState: Invalid blending: ",T)}g=null,x=null,v=null,S=null,E.set(0,0,0),w=0,m=T,R=ne}}else f===!0&&(Te(r.BLEND),f=!1)}function C(T){z!==T&&(T?r.frontFace(r.CW):r.frontFace(r.CCW),z=T)}function J(T){T!==Cd?(ge(r.CULL_FACE),T!==j&&(T===Jc?r.cullFace(r.BACK):T===Rd?r.cullFace(r.FRONT):r.cullFace(r.FRONT_AND_BACK))):Te(r.CULL_FACE),j=T}function G(T,N,B){T?(ge(r.POLYGON_OFFSET_FILL),Q===N&&Y===B||(Q=N,Y=B,n.getReversed()&&(N=-N),r.polygonOffset(N,B))):Te(r.POLYGON_OFFSET_FILL)}return{buffers:{color:t,depth:n,stencil:i},enable:ge,disable:Te,bindFramebuffer:function(T,N){return c[T]!==N&&(r.bindFramebuffer(T,N),c[T]=N,T===r.DRAW_FRAMEBUFFER&&(c[r.FRAMEBUFFER]=N),T===r.FRAMEBUFFER&&(c[r.DRAW_FRAMEBUFFER]=N),!0)},drawBuffers:function(T,N){let B=h,P=!1;if(T){B=l.get(N),B===void 0&&(B=[],l.set(N,B));let V=T.textures;if(B.length!==V.length||B[0]!==r.COLOR_ATTACHMENT0){for(let H=0,F=V.length;H<F;H++)B[H]=r.COLOR_ATTACHMENT0+H;B.length=V.length,P=!0}}else B[0]!==r.BACK&&(B[0]=r.BACK,P=!0);P&&r.drawBuffers(B)},useProgram:function(T){return p!==T&&(r.useProgram(T),p=T,!0)},setBlending:L,setMaterial:function(T,N){T.side===En?Te(r.CULL_FACE):ge(r.CULL_FACE);let B=T.side===Tn;N&&(B=!B),C(B),T.blending===Ta&&T.transparent===!1?L(mi):L(T.blending,T.blendEquation,T.blendSrc,T.blendDst,T.blendEquationAlpha,T.blendSrcAlpha,T.blendDstAlpha,T.blendColor,T.blendAlpha,T.premultipliedAlpha),n.setFunc(T.depthFunc),n.setTest(T.depthTest),n.setMask(T.depthWrite),t.setMask(T.colorWrite);let P=T.stencilWrite;i.setTest(P),P&&(i.setMask(T.stencilWriteMask),i.setFunc(T.stencilFunc,T.stencilRef,T.stencilFuncMask),i.setOp(T.stencilFail,T.stencilZFail,T.stencilZPass)),G(T.polygonOffset,T.polygonOffsetFactor,T.polygonOffsetUnits),T.alphaToCoverage===!0?ge(r.SAMPLE_ALPHA_TO_COVERAGE):Te(r.SAMPLE_ALPHA_TO_COVERAGE)},setFlipSided:C,setCullFace:J,setLineWidth:function(T){T!==O&&(X&&r.lineWidth(T),O=T)},setPolygonOffset:G,setScissorTest:function(T){T?ge(r.SCISSOR_TEST):Te(r.SCISSOR_TEST)},activeTexture:function(T){T===void 0&&(T=r.TEXTURE0+k-1),oe!==T&&(r.activeTexture(T),oe=T)},bindTexture:function(T,N,B){B===void 0&&(B=oe===null?r.TEXTURE0+k-1:oe);let P=ee[B];P===void 0&&(P={type:void 0,texture:void 0},ee[B]=P),P.type===T&&P.texture===N||(oe!==B&&(r.activeTexture(B),oe=B),r.bindTexture(T,N||de[T]),P.type=T,P.texture=N)},unbindTexture:function(){let T=ee[oe];T!==void 0&&T.type!==void 0&&(r.bindTexture(T.type,null),T.type=void 0,T.texture=void 0)},compressedTexImage2D:function(){try{r.compressedTexImage2D(...arguments)}catch(T){Je("WebGLState:",T)}},compressedTexImage3D:function(){try{r.compressedTexImage3D(...arguments)}catch(T){Je("WebGLState:",T)}},texImage2D:function(){try{r.texImage2D(...arguments)}catch(T){Je("WebGLState:",T)}},texImage3D:function(){try{r.texImage3D(...arguments)}catch(T){Je("WebGLState:",T)}},updateUBOMapping:function(T,N){let B=a.get(N);B===void 0&&(B=new WeakMap,a.set(N,B));let P=B.get(T);P===void 0&&(P=r.getUniformBlockIndex(N,T.name),B.set(T,P))},uniformBlockBinding:function(T,N){let B=a.get(N).get(T);s.get(N)!==B&&(r.uniformBlockBinding(N,B,T.__bindingPointIndex),s.set(N,B))},texStorage2D:function(){try{r.texStorage2D(...arguments)}catch(T){Je("WebGLState:",T)}},texStorage3D:function(){try{r.texStorage3D(...arguments)}catch(T){Je("WebGLState:",T)}},texSubImage2D:function(){try{r.texSubImage2D(...arguments)}catch(T){Je("WebGLState:",T)}},texSubImage3D:function(){try{r.texSubImage3D(...arguments)}catch(T){Je("WebGLState:",T)}},compressedTexSubImage2D:function(){try{r.compressedTexSubImage2D(...arguments)}catch(T){Je("WebGLState:",T)}},compressedTexSubImage3D:function(){try{r.compressedTexSubImage3D(...arguments)}catch(T){Je("WebGLState:",T)}},scissor:function(T){we.equals(T)===!1&&(r.scissor(T.x,T.y,T.z,T.w),we.copy(T))},viewport:function(T){Se.equals(T)===!1&&(r.viewport(T.x,T.y,T.z,T.w),Se.copy(T))},reset:function(){r.disable(r.BLEND),r.disable(r.CULL_FACE),r.disable(r.DEPTH_TEST),r.disable(r.POLYGON_OFFSET_FILL),r.disable(r.SCISSOR_TEST),r.disable(r.STENCIL_TEST),r.disable(r.SAMPLE_ALPHA_TO_COVERAGE),r.blendEquation(r.FUNC_ADD),r.blendFunc(r.ONE,r.ZERO),r.blendFuncSeparate(r.ONE,r.ZERO,r.ONE,r.ZERO),r.blendColor(0,0,0,0),r.colorMask(!0,!0,!0,!0),r.clearColor(0,0,0,0),r.depthMask(!0),r.depthFunc(r.LESS),n.setReversed(!1),r.clearDepth(1),r.stencilMask(4294967295),r.stencilFunc(r.ALWAYS,0,4294967295),r.stencilOp(r.KEEP,r.KEEP,r.KEEP),r.clearStencil(0),r.cullFace(r.BACK),r.frontFace(r.CCW),r.polygonOffset(0,0),r.activeTexture(r.TEXTURE0),r.bindFramebuffer(r.FRAMEBUFFER,null),r.bindFramebuffer(r.DRAW_FRAMEBUFFER,null),r.bindFramebuffer(r.READ_FRAMEBUFFER,null),r.useProgram(null),r.lineWidth(1),r.scissor(0,0,r.canvas.width,r.canvas.height),r.viewport(0,0,r.canvas.width,r.canvas.height),o={},oe=null,ee={},c={},l=new WeakMap,h=[],p=null,f=!1,m=null,u=null,g=null,x=null,_=null,v=null,S=null,E=new He(0,0,0),w=0,R=!1,z=null,j=null,O=null,Q=null,Y=null,we.set(0,0,r.canvas.width,r.canvas.height),Se.set(0,0,r.canvas.width,r.canvas.height),t.reset(),n.reset(),i.reset()}}}function Og(r,e,t,n,i,s,a){let o=e.has("WEBGL_multisampled_render_to_texture")?e.get("WEBGL_multisampled_render_to_texture"):null,c=typeof navigator<"u"&&/OculusBrowser/g.test(navigator.userAgent),l=new _e,h=new WeakMap,p,f=new WeakMap,m=!1;try{m=typeof OffscreenCanvas<"u"&&new OffscreenCanvas(1,1).getContext("2d")!==null}catch{}function u(L,C){return m?new OffscreenCanvas(L,C):Jr("canvas")}function g(L,C,J){let G=1,T=ze(L);if((T.width>J||T.height>J)&&(G=J/Math.max(T.width,T.height)),G<1){if(typeof HTMLImageElement<"u"&&L instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&L instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&L instanceof ImageBitmap||typeof VideoFrame<"u"&&L instanceof VideoFrame){let N=Math.floor(G*T.width),B=Math.floor(G*T.height);p===void 0&&(p=u(N,B));let P=C?u(N,B):p;return P.width=N,P.height=B,P.getContext("2d").drawImage(L,0,0,N,B),Ye("WebGLRenderer: Texture has been resized from ("+T.width+"x"+T.height+") to ("+N+"x"+B+")."),P}return"data"in L&&Ye("WebGLRenderer: Image in DataTexture is too big ("+T.width+"x"+T.height+")."),L}return L}function x(L){return L.generateMipmaps}function _(L){r.generateMipmap(L)}function v(L){return L.isWebGLCubeRenderTarget?r.TEXTURE_CUBE_MAP:L.isWebGL3DRenderTarget?r.TEXTURE_3D:L.isWebGLArrayRenderTarget||L.isCompressedArrayTexture?r.TEXTURE_2D_ARRAY:r.TEXTURE_2D}function S(L,C,J,G,T=!1){if(L!==null){if(r[L]!==void 0)return r[L];Ye("WebGLRenderer: Attempt to use non-existing WebGL internal format '"+L+"'")}let N=C;if(C===r.RED&&(J===r.FLOAT&&(N=r.R32F),J===r.HALF_FLOAT&&(N=r.R16F),J===r.UNSIGNED_BYTE&&(N=r.R8)),C===r.RED_INTEGER&&(J===r.UNSIGNED_BYTE&&(N=r.R8UI),J===r.UNSIGNED_SHORT&&(N=r.R16UI),J===r.UNSIGNED_INT&&(N=r.R32UI),J===r.BYTE&&(N=r.R8I),J===r.SHORT&&(N=r.R16I),J===r.INT&&(N=r.R32I)),C===r.RG&&(J===r.FLOAT&&(N=r.RG32F),J===r.HALF_FLOAT&&(N=r.RG16F),J===r.UNSIGNED_BYTE&&(N=r.RG8)),C===r.RG_INTEGER&&(J===r.UNSIGNED_BYTE&&(N=r.RG8UI),J===r.UNSIGNED_SHORT&&(N=r.RG16UI),J===r.UNSIGNED_INT&&(N=r.RG32UI),J===r.BYTE&&(N=r.RG8I),J===r.SHORT&&(N=r.RG16I),J===r.INT&&(N=r.RG32I)),C===r.RGB_INTEGER&&(J===r.UNSIGNED_BYTE&&(N=r.RGB8UI),J===r.UNSIGNED_SHORT&&(N=r.RGB16UI),J===r.UNSIGNED_INT&&(N=r.RGB32UI),J===r.BYTE&&(N=r.RGB8I),J===r.SHORT&&(N=r.RGB16I),J===r.INT&&(N=r.RGB32I)),C===r.RGBA_INTEGER&&(J===r.UNSIGNED_BYTE&&(N=r.RGBA8UI),J===r.UNSIGNED_SHORT&&(N=r.RGBA16UI),J===r.UNSIGNED_INT&&(N=r.RGBA32UI),J===r.BYTE&&(N=r.RGBA8I),J===r.SHORT&&(N=r.RGBA16I),J===r.INT&&(N=r.RGBA32I)),C===r.RGB&&(J===r.UNSIGNED_INT_5_9_9_9_REV&&(N=r.RGB9_E5),J===r.UNSIGNED_INT_10F_11F_11F_REV&&(N=r.R11F_G11F_B10F)),C===r.RGBA){let B=T?Ys:ut.getTransfer(G);J===r.FLOAT&&(N=r.RGBA32F),J===r.HALF_FLOAT&&(N=r.RGBA16F),J===r.UNSIGNED_BYTE&&(N=B===gt?r.SRGB8_ALPHA8:r.RGBA8),J===r.UNSIGNED_SHORT_4_4_4_4&&(N=r.RGBA4),J===r.UNSIGNED_SHORT_5_5_5_1&&(N=r.RGB5_A1)}return N!==r.R16F&&N!==r.R32F&&N!==r.RG16F&&N!==r.RG32F&&N!==r.RGBA16F&&N!==r.RGBA32F||e.get("EXT_color_buffer_float"),N}function E(L,C){let J;return L?C===null||C===Li||C===vs?J=r.DEPTH24_STENCIL8:C===Kn?J=r.DEPTH32F_STENCIL8:C===_s&&(J=r.DEPTH24_STENCIL8,Ye("DepthTexture: 16 bit depth attachment is not supported with stencil. Using 24-bit attachment.")):C===null||C===Li||C===vs?J=r.DEPTH_COMPONENT24:C===Kn?J=r.DEPTH_COMPONENT32F:C===_s&&(J=r.DEPTH_COMPONENT16),J}function w(L,C){return x(L)===!0||L.isFramebufferTexture&&L.minFilter!==Yn&&L.minFilter!==Xt?Math.log2(Math.max(C.width,C.height))+1:L.mipmaps!==void 0&&L.mipmaps.length>0?L.mipmaps.length:L.isCompressedTexture&&Array.isArray(L.image)?C.mipmaps.length:1}function R(L){let C=L.target;C.removeEventListener("dispose",R),(function(J){let G=n.get(J);if(G.__webglInit===void 0)return;let T=J.source,N=f.get(T);if(N){let B=N[G.__cacheKey];B.usedTimes--,B.usedTimes===0&&j(J),Object.keys(N).length===0&&f.delete(T)}n.remove(J)})(C),C.isVideoTexture&&h.delete(C)}function z(L){let C=L.target;C.removeEventListener("dispose",z),(function(J){let G=n.get(J);if(J.depthTexture&&(J.depthTexture.dispose(),n.remove(J.depthTexture)),J.isWebGLCubeRenderTarget)for(let N=0;N<6;N++){if(Array.isArray(G.__webglFramebuffer[N]))for(let B=0;B<G.__webglFramebuffer[N].length;B++)r.deleteFramebuffer(G.__webglFramebuffer[N][B]);else r.deleteFramebuffer(G.__webglFramebuffer[N]);G.__webglDepthbuffer&&r.deleteRenderbuffer(G.__webglDepthbuffer[N])}else{if(Array.isArray(G.__webglFramebuffer))for(let N=0;N<G.__webglFramebuffer.length;N++)r.deleteFramebuffer(G.__webglFramebuffer[N]);else r.deleteFramebuffer(G.__webglFramebuffer);if(G.__webglDepthbuffer&&r.deleteRenderbuffer(G.__webglDepthbuffer),G.__webglMultisampledFramebuffer&&r.deleteFramebuffer(G.__webglMultisampledFramebuffer),G.__webglColorRenderbuffer)for(let N=0;N<G.__webglColorRenderbuffer.length;N++)G.__webglColorRenderbuffer[N]&&r.deleteRenderbuffer(G.__webglColorRenderbuffer[N]);G.__webglDepthRenderbuffer&&r.deleteRenderbuffer(G.__webglDepthRenderbuffer)}let T=J.textures;for(let N=0,B=T.length;N<B;N++){let P=n.get(T[N]);P.__webglTexture&&(r.deleteTexture(P.__webglTexture),a.memory.textures--),n.remove(T[N])}n.remove(J)})(C)}function j(L){let C=n.get(L);r.deleteTexture(C.__webglTexture);let J=L.source;delete f.get(J)[C.__cacheKey],a.memory.textures--}let O=0;function Q(L,C){let J=n.get(L);if(L.isVideoTexture&&(function(G){let T=a.render.frame;h.get(G)!==T&&(h.set(G,T),G.update())})(L),L.isRenderTargetTexture===!1&&L.isExternalTexture!==!0&&L.version>0&&J.__version!==L.version){let G=L.image;if(G===null)Ye("WebGLRenderer: Texture marked for update but no image data found.");else{if(G.complete!==!1)return void ee(J,L,C);Ye("WebGLRenderer: Texture marked for update but image is incomplete")}}else L.isExternalTexture&&(J.__webglTexture=L.sourceTexture?L.sourceTexture:null);t.bindTexture(r.TEXTURE_2D,J.__webglTexture,r.TEXTURE0+C)}let Y={[hr]:r.REPEAT,[Wi]:r.CLAMP_TO_EDGE,[Co]:r.MIRRORED_REPEAT},k={[Yn]:r.NEAREST,[Qd]:r.NEAREST_MIPMAP_NEAREST,[Aa]:r.NEAREST_MIPMAP_LINEAR,[Xt]:r.LINEAR,[wl]:r.LINEAR_MIPMAP_NEAREST,[mr]:r.LINEAR_MIPMAP_LINEAR},X={[rp]:r.NEVER,[cp]:r.ALWAYS,[sp]:r.LESS,[Ol]:r.LEQUAL,[ap]:r.EQUAL,[Fl]:r.GEQUAL,[op]:r.GREATER,[lp]:r.NOTEQUAL};function K(L,C){if(C.type!==Kn||e.has("OES_texture_float_linear")!==!1||C.magFilter!==Xt&&C.magFilter!==wl&&C.magFilter!==Aa&&C.magFilter!==mr&&C.minFilter!==Xt&&C.minFilter!==wl&&C.minFilter!==Aa&&C.minFilter!==mr||Ye("WebGLRenderer: Unable to use linear filtering with floating point textures. OES_texture_float_linear not supported on this device."),r.texParameteri(L,r.TEXTURE_WRAP_S,Y[C.wrapS]),r.texParameteri(L,r.TEXTURE_WRAP_T,Y[C.wrapT]),L!==r.TEXTURE_3D&&L!==r.TEXTURE_2D_ARRAY||r.texParameteri(L,r.TEXTURE_WRAP_R,Y[C.wrapR]),r.texParameteri(L,r.TEXTURE_MAG_FILTER,k[C.magFilter]),r.texParameteri(L,r.TEXTURE_MIN_FILTER,k[C.minFilter]),C.compareFunction&&(r.texParameteri(L,r.TEXTURE_COMPARE_MODE,r.COMPARE_REF_TO_TEXTURE),r.texParameteri(L,r.TEXTURE_COMPARE_FUNC,X[C.compareFunction])),e.has("EXT_texture_filter_anisotropic")===!0){if(C.magFilter===Yn||C.minFilter!==Aa&&C.minFilter!==mr||C.type===Kn&&e.has("OES_texture_float_linear")===!1)return;if(C.anisotropy>1||n.get(C).__currentAnisotropy){let J=e.get("EXT_texture_filter_anisotropic");r.texParameterf(L,J.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(C.anisotropy,i.getMaxAnisotropy())),n.get(C).__currentAnisotropy=C.anisotropy}}}function te(L,C){let J=!1;L.__webglInit===void 0&&(L.__webglInit=!0,C.addEventListener("dispose",R));let G=C.source,T=f.get(G);T===void 0&&(T={},f.set(G,T));let N=(function(B){let P=[];return P.push(B.wrapS),P.push(B.wrapT),P.push(B.wrapR||0),P.push(B.magFilter),P.push(B.minFilter),P.push(B.anisotropy),P.push(B.internalFormat),P.push(B.format),P.push(B.type),P.push(B.generateMipmaps),P.push(B.premultiplyAlpha),P.push(B.flipY),P.push(B.unpackAlignment),P.push(B.colorSpace),P.join()})(C);if(N!==L.__cacheKey){T[N]===void 0&&(T[N]={texture:r.createTexture(),usedTimes:0},a.memory.textures++,J=!0),T[N].usedTimes++;let B=T[L.__cacheKey];B!==void 0&&(T[L.__cacheKey].usedTimes--,B.usedTimes===0&&j(C)),L.__cacheKey=N,L.__webglTexture=T[N].texture}return J}function oe(L,C,J){return Math.floor(Math.floor(L/J)/C)}function ee(L,C,J){let G=r.TEXTURE_2D;(C.isDataArrayTexture||C.isCompressedArrayTexture)&&(G=r.TEXTURE_2D_ARRAY),C.isData3DTexture&&(G=r.TEXTURE_3D);let T=te(L,C),N=C.source;t.bindTexture(G,L.__webglTexture,r.TEXTURE0+J);let B=n.get(N);if(N.version!==B.__version||T===!0){t.activeTexture(r.TEXTURE0+J);let P=ut.getPrimaries(ut.workingColorSpace),V=C.colorSpace===_r?null:ut.getPrimaries(C.colorSpace),H=C.colorSpace===_r||P===V?r.NONE:r.BROWSER_DEFAULT_WEBGL;r.pixelStorei(r.UNPACK_FLIP_Y_WEBGL,C.flipY),r.pixelStorei(r.UNPACK_PREMULTIPLY_ALPHA_WEBGL,C.premultiplyAlpha),r.pixelStorei(r.UNPACK_ALIGNMENT,C.unpackAlignment),r.pixelStorei(r.UNPACK_COLORSPACE_CONVERSION_WEBGL,H);let F=g(C.image,!1,i.maxTextureSize);F=Re(C,F);let $=s.convert(C.format,C.colorSpace),M=s.convert(C.type),ne,le=S(C.internalFormat,$,M,C.colorSpace,C.isVideoTexture);K(G,C);let ye=C.mipmaps,Ne=C.isVideoTexture!==!0,Fe=B.__version===void 0||T===!0,Oe=N.dataReady,ke=w(C,F);if(C.isDepthTexture)le=E(C.format===gr,C.type),Fe&&(Ne?t.texStorage2D(r.TEXTURE_2D,1,le,F.width,F.height):t.texImage2D(r.TEXTURE_2D,0,le,F.width,F.height,0,$,M,null));else if(C.isDataTexture)if(ye.length>0){Ne&&Fe&&t.texStorage2D(r.TEXTURE_2D,ke,le,ye[0].width,ye[0].height);for(let Pe=0,Ze=ye.length;Pe<Ze;Pe++)ne=ye[Pe],Ne?Oe&&t.texSubImage2D(r.TEXTURE_2D,Pe,0,0,ne.width,ne.height,$,M,ne.data):t.texImage2D(r.TEXTURE_2D,Pe,le,ne.width,ne.height,0,$,M,ne.data);C.generateMipmaps=!1}else Ne?(Fe&&t.texStorage2D(r.TEXTURE_2D,ke,le,F.width,F.height),Oe&&(function(Pe,Ze,Qe,lt){let Ae=Pe.updateRanges;if(Ae.length===0)t.texSubImage2D(r.TEXTURE_2D,0,0,0,Ze.width,Ze.height,Qe,lt,Ze.data);else{Ae.sort((yt,ht)=>yt.start-ht.start);let We=0;for(let yt=1;yt<Ae.length;yt++){let ht=Ae[We],ft=Ae[yt],cn=ht.start+ht.count,Z=oe(ft.start,Ze.width,4),mt=oe(ht.start,Ze.width,4);ft.start<=cn+1&&Z===mt&&oe(ft.start+ft.count-1,Ze.width,4)===Z?ht.count=Math.max(ht.count,ft.start+ft.count-ht.start):(++We,Ae[We]=ft)}Ae.length=We+1;let Ve=r.getParameter(r.UNPACK_ROW_LENGTH),qt=r.getParameter(r.UNPACK_SKIP_PIXELS),ln=r.getParameter(r.UNPACK_SKIP_ROWS);r.pixelStorei(r.UNPACK_ROW_LENGTH,Ze.width);for(let yt=0,ht=Ae.length;yt<ht;yt++){let ft=Ae[yt],cn=Math.floor(ft.start/4),Z=Math.ceil(ft.count/4),mt=cn%Ze.width,Mt=Math.floor(cn/Ze.width),ct=Z;r.pixelStorei(r.UNPACK_SKIP_PIXELS,mt),r.pixelStorei(r.UNPACK_SKIP_ROWS,Mt),t.texSubImage2D(r.TEXTURE_2D,0,mt,Mt,ct,1,Qe,lt,Ze.data)}Pe.clearUpdateRanges(),r.pixelStorei(r.UNPACK_ROW_LENGTH,Ve),r.pixelStorei(r.UNPACK_SKIP_PIXELS,qt),r.pixelStorei(r.UNPACK_SKIP_ROWS,ln)}})(C,F,$,M)):t.texImage2D(r.TEXTURE_2D,0,le,F.width,F.height,0,$,M,F.data);else if(C.isCompressedTexture)if(C.isCompressedArrayTexture){Ne&&Fe&&t.texStorage3D(r.TEXTURE_2D_ARRAY,ke,le,ye[0].width,ye[0].height,F.depth);for(let Pe=0,Ze=ye.length;Pe<Ze;Pe++)if(ne=ye[Pe],C.format!==ai)if($!==null)if(Ne){if(Oe)if(C.layerUpdates.size>0){let Qe=ru(ne.width,ne.height,C.format,C.type);for(let lt of C.layerUpdates){let Ae=ne.data.subarray(lt*Qe/ne.data.BYTES_PER_ELEMENT,(lt+1)*Qe/ne.data.BYTES_PER_ELEMENT);t.compressedTexSubImage3D(r.TEXTURE_2D_ARRAY,Pe,0,0,lt,ne.width,ne.height,1,$,Ae)}C.clearLayerUpdates()}else t.compressedTexSubImage3D(r.TEXTURE_2D_ARRAY,Pe,0,0,0,ne.width,ne.height,F.depth,$,ne.data)}else t.compressedTexImage3D(r.TEXTURE_2D_ARRAY,Pe,le,ne.width,ne.height,F.depth,0,ne.data,0,0);else Ye("WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()");else Ne?Oe&&t.texSubImage3D(r.TEXTURE_2D_ARRAY,Pe,0,0,0,ne.width,ne.height,F.depth,$,M,ne.data):t.texImage3D(r.TEXTURE_2D_ARRAY,Pe,le,ne.width,ne.height,F.depth,0,$,M,ne.data)}else{Ne&&Fe&&t.texStorage2D(r.TEXTURE_2D,ke,le,ye[0].width,ye[0].height);for(let Pe=0,Ze=ye.length;Pe<Ze;Pe++)ne=ye[Pe],C.format!==ai?$!==null?Ne?Oe&&t.compressedTexSubImage2D(r.TEXTURE_2D,Pe,0,0,ne.width,ne.height,$,ne.data):t.compressedTexImage2D(r.TEXTURE_2D,Pe,le,ne.width,ne.height,0,ne.data):Ye("WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()"):Ne?Oe&&t.texSubImage2D(r.TEXTURE_2D,Pe,0,0,ne.width,ne.height,$,M,ne.data):t.texImage2D(r.TEXTURE_2D,Pe,le,ne.width,ne.height,0,$,M,ne.data)}else if(C.isDataArrayTexture)if(Ne){if(Fe&&t.texStorage3D(r.TEXTURE_2D_ARRAY,ke,le,F.width,F.height,F.depth),Oe)if(C.layerUpdates.size>0){let Pe=ru(F.width,F.height,C.format,C.type);for(let Ze of C.layerUpdates){let Qe=F.data.subarray(Ze*Pe/F.data.BYTES_PER_ELEMENT,(Ze+1)*Pe/F.data.BYTES_PER_ELEMENT);t.texSubImage3D(r.TEXTURE_2D_ARRAY,0,0,0,Ze,F.width,F.height,1,$,M,Qe)}C.clearLayerUpdates()}else t.texSubImage3D(r.TEXTURE_2D_ARRAY,0,0,0,0,F.width,F.height,F.depth,$,M,F.data)}else t.texImage3D(r.TEXTURE_2D_ARRAY,0,le,F.width,F.height,F.depth,0,$,M,F.data);else if(C.isData3DTexture)Ne?(Fe&&t.texStorage3D(r.TEXTURE_3D,ke,le,F.width,F.height,F.depth),Oe&&t.texSubImage3D(r.TEXTURE_3D,0,0,0,0,F.width,F.height,F.depth,$,M,F.data)):t.texImage3D(r.TEXTURE_3D,0,le,F.width,F.height,F.depth,0,$,M,F.data);else if(C.isFramebufferTexture){if(Fe)if(Ne)t.texStorage2D(r.TEXTURE_2D,ke,le,F.width,F.height);else{let Pe=F.width,Ze=F.height;for(let Qe=0;Qe<ke;Qe++)t.texImage2D(r.TEXTURE_2D,Qe,le,Pe,Ze,0,$,M,null),Pe>>=1,Ze>>=1}}else if(ye.length>0){if(Ne&&Fe){let Pe=ze(ye[0]);t.texStorage2D(r.TEXTURE_2D,ke,le,Pe.width,Pe.height)}for(let Pe=0,Ze=ye.length;Pe<Ze;Pe++)ne=ye[Pe],Ne?Oe&&t.texSubImage2D(r.TEXTURE_2D,Pe,0,0,$,M,ne):t.texImage2D(r.TEXTURE_2D,Pe,le,$,M,ne);C.generateMipmaps=!1}else if(Ne){if(Fe){let Pe=ze(F);t.texStorage2D(r.TEXTURE_2D,ke,le,Pe.width,Pe.height)}Oe&&t.texSubImage2D(r.TEXTURE_2D,0,0,0,$,M,F)}else t.texImage2D(r.TEXTURE_2D,0,le,$,M,F);x(C)&&_(G),B.__version=N.version,C.onUpdate&&C.onUpdate(C)}L.__version=C.version}function xe(L,C,J,G,T,N){let B=s.convert(J.format,J.colorSpace),P=s.convert(J.type),V=S(J.internalFormat,B,P,J.colorSpace),H=n.get(C),F=n.get(J);if(F.__renderTarget=C,!H.__hasExternalTextures){let $=Math.max(1,C.width>>N),M=Math.max(1,C.height>>N);T===r.TEXTURE_3D||T===r.TEXTURE_2D_ARRAY?t.texImage3D(T,N,V,$,M,C.depth,0,B,P,null):t.texImage2D(T,N,V,$,M,0,B,P,null)}t.bindFramebuffer(r.FRAMEBUFFER,L),Te(C)?o.framebufferTexture2DMultisampleEXT(r.FRAMEBUFFER,G,T,F.__webglTexture,0,ge(C)):(T===r.TEXTURE_2D||T>=r.TEXTURE_CUBE_MAP_POSITIVE_X&&T<=r.TEXTURE_CUBE_MAP_NEGATIVE_Z)&&r.framebufferTexture2D(r.FRAMEBUFFER,G,T,F.__webglTexture,N),t.bindFramebuffer(r.FRAMEBUFFER,null)}function be(L,C,J){if(r.bindRenderbuffer(r.RENDERBUFFER,L),C.depthBuffer){let G=C.depthTexture,T=G&&G.isDepthTexture?G.type:null,N=E(C.stencilBuffer,T),B=C.stencilBuffer?r.DEPTH_STENCIL_ATTACHMENT:r.DEPTH_ATTACHMENT;Te(C)?o.renderbufferStorageMultisampleEXT(r.RENDERBUFFER,ge(C),N,C.width,C.height):J?r.renderbufferStorageMultisample(r.RENDERBUFFER,ge(C),N,C.width,C.height):r.renderbufferStorage(r.RENDERBUFFER,N,C.width,C.height),r.framebufferRenderbuffer(r.FRAMEBUFFER,B,r.RENDERBUFFER,L)}else{let G=C.textures;for(let T=0;T<G.length;T++){let N=G[T],B=s.convert(N.format,N.colorSpace),P=s.convert(N.type),V=S(N.internalFormat,B,P,N.colorSpace);Te(C)?o.renderbufferStorageMultisampleEXT(r.RENDERBUFFER,ge(C),V,C.width,C.height):J?r.renderbufferStorageMultisample(r.RENDERBUFFER,ge(C),V,C.width,C.height):r.renderbufferStorage(r.RENDERBUFFER,V,C.width,C.height)}}r.bindRenderbuffer(r.RENDERBUFFER,null)}function we(L,C,J){let G=C.isWebGLCubeRenderTarget===!0;if(t.bindFramebuffer(r.FRAMEBUFFER,L),!C.depthTexture||!C.depthTexture.isDepthTexture)throw new Error("renderTarget.depthTexture must be an instance of THREE.DepthTexture");let T=n.get(C.depthTexture);if(T.__renderTarget=C,T.__webglTexture&&C.depthTexture.image.width===C.width&&C.depthTexture.image.height===C.height||(C.depthTexture.image.width=C.width,C.depthTexture.image.height=C.height,C.depthTexture.needsUpdate=!0),G){if(T.__webglInit===void 0&&(T.__webglInit=!0,C.depthTexture.addEventListener("dispose",R)),T.__webglTexture===void 0){T.__webglTexture=r.createTexture(),t.bindTexture(r.TEXTURE_CUBE_MAP,T.__webglTexture),K(r.TEXTURE_CUBE_MAP,C.depthTexture);let H=s.convert(C.depthTexture.format),F=s.convert(C.depthTexture.type),$;C.depthTexture.format===Ki?$=r.DEPTH_COMPONENT24:C.depthTexture.format===gr&&($=r.DEPTH24_STENCIL8);for(let M=0;M<6;M++)r.texImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+M,0,$,C.width,C.height,0,H,F,null)}}else Q(C.depthTexture,0);let N=T.__webglTexture,B=ge(C),P=G?r.TEXTURE_CUBE_MAP_POSITIVE_X+J:r.TEXTURE_2D,V=C.depthTexture.format===gr?r.DEPTH_STENCIL_ATTACHMENT:r.DEPTH_ATTACHMENT;if(C.depthTexture.format===Ki)Te(C)?o.framebufferTexture2DMultisampleEXT(r.FRAMEBUFFER,V,P,N,0,B):r.framebufferTexture2D(r.FRAMEBUFFER,V,P,N,0);else{if(C.depthTexture.format!==gr)throw new Error("Unknown depthTexture format");Te(C)?o.framebufferTexture2DMultisampleEXT(r.FRAMEBUFFER,V,P,N,0,B):r.framebufferTexture2D(r.FRAMEBUFFER,V,P,N,0)}}function Se(L){let C=n.get(L),J=L.isWebGLCubeRenderTarget===!0;if(C.__boundDepthTexture!==L.depthTexture){let G=L.depthTexture;if(C.__depthDisposeCallback&&C.__depthDisposeCallback(),G){let T=()=>{delete C.__boundDepthTexture,delete C.__depthDisposeCallback,G.removeEventListener("dispose",T)};G.addEventListener("dispose",T),C.__depthDisposeCallback=T}C.__boundDepthTexture=G}if(L.depthTexture&&!C.__autoAllocateDepthBuffer)if(J)for(let G=0;G<6;G++)we(C.__webglFramebuffer[G],L,G);else{let G=L.texture.mipmaps;G&&G.length>0?we(C.__webglFramebuffer[0],L,0):we(C.__webglFramebuffer,L,0)}else if(J){C.__webglDepthbuffer=[];for(let G=0;G<6;G++)if(t.bindFramebuffer(r.FRAMEBUFFER,C.__webglFramebuffer[G]),C.__webglDepthbuffer[G]===void 0)C.__webglDepthbuffer[G]=r.createRenderbuffer(),be(C.__webglDepthbuffer[G],L,!1);else{let T=L.stencilBuffer?r.DEPTH_STENCIL_ATTACHMENT:r.DEPTH_ATTACHMENT,N=C.__webglDepthbuffer[G];r.bindRenderbuffer(r.RENDERBUFFER,N),r.framebufferRenderbuffer(r.FRAMEBUFFER,T,r.RENDERBUFFER,N)}}else{let G=L.texture.mipmaps;if(G&&G.length>0?t.bindFramebuffer(r.FRAMEBUFFER,C.__webglFramebuffer[0]):t.bindFramebuffer(r.FRAMEBUFFER,C.__webglFramebuffer),C.__webglDepthbuffer===void 0)C.__webglDepthbuffer=r.createRenderbuffer(),be(C.__webglDepthbuffer,L,!1);else{let T=L.stencilBuffer?r.DEPTH_STENCIL_ATTACHMENT:r.DEPTH_ATTACHMENT,N=C.__webglDepthbuffer;r.bindRenderbuffer(r.RENDERBUFFER,N),r.framebufferRenderbuffer(r.FRAMEBUFFER,T,r.RENDERBUFFER,N)}}t.bindFramebuffer(r.FRAMEBUFFER,null)}let se=[],de=[];function ge(L){return Math.min(i.maxSamples,L.samples)}function Te(L){let C=n.get(L);return L.samples>0&&e.has("WEBGL_multisampled_render_to_texture")===!0&&C.__useRenderToTexture!==!1}function Re(L,C){let J=L.colorSpace,G=L.format,T=L.type;return L.isCompressedTexture===!0||L.isVideoTexture===!0||J!==ur&&J!==_r&&(ut.getTransfer(J)===gt?G===ai&&T===zn||Ye("WebGLTextures: sRGB encoded textures have to use RGBAFormat and UnsignedByteType."):Je("WebGLTextures: Unsupported texture color space:",J)),C}function ze(L){return typeof HTMLImageElement<"u"&&L instanceof HTMLImageElement?(l.width=L.naturalWidth||L.width,l.height=L.naturalHeight||L.height):typeof VideoFrame<"u"&&L instanceof VideoFrame?(l.width=L.displayWidth,l.height=L.displayHeight):(l.width=L.width,l.height=L.height),l}this.allocateTextureUnit=function(){let L=O;return L>=i.maxTextures&&Ye("WebGLTextures: Trying to use "+L+" texture units while this GPU supports only "+i.maxTextures),O+=1,L},this.resetTextureUnits=function(){O=0},this.setTexture2D=Q,this.setTexture2DArray=function(L,C){let J=n.get(L);L.isRenderTargetTexture===!1&&L.version>0&&J.__version!==L.version?ee(J,L,C):(L.isExternalTexture&&(J.__webglTexture=L.sourceTexture?L.sourceTexture:null),t.bindTexture(r.TEXTURE_2D_ARRAY,J.__webglTexture,r.TEXTURE0+C))},this.setTexture3D=function(L,C){let J=n.get(L);L.isRenderTargetTexture===!1&&L.version>0&&J.__version!==L.version?ee(J,L,C):t.bindTexture(r.TEXTURE_3D,J.__webglTexture,r.TEXTURE0+C)},this.setTextureCube=function(L,C){let J=n.get(L);L.isCubeDepthTexture!==!0&&L.version>0&&J.__version!==L.version?(function(G,T,N){if(T.image.length!==6)return;let B=te(G,T),P=T.source;t.bindTexture(r.TEXTURE_CUBE_MAP,G.__webglTexture,r.TEXTURE0+N);let V=n.get(P);if(P.version!==V.__version||B===!0){t.activeTexture(r.TEXTURE0+N);let H=ut.getPrimaries(ut.workingColorSpace),F=T.colorSpace===_r?null:ut.getPrimaries(T.colorSpace),$=T.colorSpace===_r||H===F?r.NONE:r.BROWSER_DEFAULT_WEBGL;r.pixelStorei(r.UNPACK_FLIP_Y_WEBGL,T.flipY),r.pixelStorei(r.UNPACK_PREMULTIPLY_ALPHA_WEBGL,T.premultiplyAlpha),r.pixelStorei(r.UNPACK_ALIGNMENT,T.unpackAlignment),r.pixelStorei(r.UNPACK_COLORSPACE_CONVERSION_WEBGL,$);let M=T.isCompressedTexture||T.image[0].isCompressedTexture,ne=T.image[0]&&T.image[0].isDataTexture,le=[];for(let Ae=0;Ae<6;Ae++)le[Ae]=M||ne?ne?T.image[Ae].image:T.image[Ae]:g(T.image[Ae],!0,i.maxCubemapSize),le[Ae]=Re(T,le[Ae]);let ye=le[0],Ne=s.convert(T.format,T.colorSpace),Fe=s.convert(T.type),Oe=S(T.internalFormat,Ne,Fe,T.colorSpace),ke=T.isVideoTexture!==!0,Pe=V.__version===void 0||B===!0,Ze=P.dataReady,Qe,lt=w(T,ye);if(K(r.TEXTURE_CUBE_MAP,T),M){ke&&Pe&&t.texStorage2D(r.TEXTURE_CUBE_MAP,lt,Oe,ye.width,ye.height);for(let Ae=0;Ae<6;Ae++){Qe=le[Ae].mipmaps;for(let We=0;We<Qe.length;We++){let Ve=Qe[We];T.format!==ai?Ne!==null?ke?Ze&&t.compressedTexSubImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We,0,0,Ve.width,Ve.height,Ne,Ve.data):t.compressedTexImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We,Oe,Ve.width,Ve.height,0,Ve.data):Ye("WebGLRenderer: Attempt to load unsupported compressed texture format in .setTextureCube()"):ke?Ze&&t.texSubImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We,0,0,Ve.width,Ve.height,Ne,Fe,Ve.data):t.texImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We,Oe,Ve.width,Ve.height,0,Ne,Fe,Ve.data)}}}else{if(Qe=T.mipmaps,ke&&Pe){Qe.length>0&&lt++;let Ae=ze(le[0]);t.texStorage2D(r.TEXTURE_CUBE_MAP,lt,Oe,Ae.width,Ae.height)}for(let Ae=0;Ae<6;Ae++)if(ne){ke?Ze&&t.texSubImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,0,0,0,le[Ae].width,le[Ae].height,Ne,Fe,le[Ae].data):t.texImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,0,Oe,le[Ae].width,le[Ae].height,0,Ne,Fe,le[Ae].data);for(let We=0;We<Qe.length;We++){let Ve=Qe[We].image[Ae].image;ke?Ze&&t.texSubImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We+1,0,0,Ve.width,Ve.height,Ne,Fe,Ve.data):t.texImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We+1,Oe,Ve.width,Ve.height,0,Ne,Fe,Ve.data)}}else{ke?Ze&&t.texSubImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,0,0,0,Ne,Fe,le[Ae]):t.texImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,0,Oe,Ne,Fe,le[Ae]);for(let We=0;We<Qe.length;We++){let Ve=Qe[We];ke?Ze&&t.texSubImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We+1,0,0,Ne,Fe,Ve.image[Ae]):t.texImage2D(r.TEXTURE_CUBE_MAP_POSITIVE_X+Ae,We+1,Oe,Ne,Fe,Ve.image[Ae])}}}x(T)&&_(r.TEXTURE_CUBE_MAP),V.__version=P.version,T.onUpdate&&T.onUpdate(T)}G.__version=T.version})(J,L,C):t.bindTexture(r.TEXTURE_CUBE_MAP,J.__webglTexture,r.TEXTURE0+C)},this.rebindTextures=function(L,C,J){let G=n.get(L);C!==void 0&&xe(G.__webglFramebuffer,L,L.texture,r.COLOR_ATTACHMENT0,r.TEXTURE_2D,0),J!==void 0&&Se(L)},this.setupRenderTarget=function(L){let C=L.texture,J=n.get(L),G=n.get(C);L.addEventListener("dispose",z);let T=L.textures,N=L.isWebGLCubeRenderTarget===!0,B=T.length>1;if(B||(G.__webglTexture===void 0&&(G.__webglTexture=r.createTexture()),G.__version=C.version,a.memory.textures++),N){J.__webglFramebuffer=[];for(let P=0;P<6;P++)if(C.mipmaps&&C.mipmaps.length>0){J.__webglFramebuffer[P]=[];for(let V=0;V<C.mipmaps.length;V++)J.__webglFramebuffer[P][V]=r.createFramebuffer()}else J.__webglFramebuffer[P]=r.createFramebuffer()}else{if(C.mipmaps&&C.mipmaps.length>0){J.__webglFramebuffer=[];for(let P=0;P<C.mipmaps.length;P++)J.__webglFramebuffer[P]=r.createFramebuffer()}else J.__webglFramebuffer=r.createFramebuffer();if(B)for(let P=0,V=T.length;P<V;P++){let H=n.get(T[P]);H.__webglTexture===void 0&&(H.__webglTexture=r.createTexture(),a.memory.textures++)}if(L.samples>0&&Te(L)===!1){J.__webglMultisampledFramebuffer=r.createFramebuffer(),J.__webglColorRenderbuffer=[],t.bindFramebuffer(r.FRAMEBUFFER,J.__webglMultisampledFramebuffer);for(let P=0;P<T.length;P++){let V=T[P];J.__webglColorRenderbuffer[P]=r.createRenderbuffer(),r.bindRenderbuffer(r.RENDERBUFFER,J.__webglColorRenderbuffer[P]);let H=s.convert(V.format,V.colorSpace),F=s.convert(V.type),$=S(V.internalFormat,H,F,V.colorSpace,L.isXRRenderTarget===!0),M=ge(L);r.renderbufferStorageMultisample(r.RENDERBUFFER,M,$,L.width,L.height),r.framebufferRenderbuffer(r.FRAMEBUFFER,r.COLOR_ATTACHMENT0+P,r.RENDERBUFFER,J.__webglColorRenderbuffer[P])}r.bindRenderbuffer(r.RENDERBUFFER,null),L.depthBuffer&&(J.__webglDepthRenderbuffer=r.createRenderbuffer(),be(J.__webglDepthRenderbuffer,L,!0)),t.bindFramebuffer(r.FRAMEBUFFER,null)}}if(N){t.bindTexture(r.TEXTURE_CUBE_MAP,G.__webglTexture),K(r.TEXTURE_CUBE_MAP,C);for(let P=0;P<6;P++)if(C.mipmaps&&C.mipmaps.length>0)for(let V=0;V<C.mipmaps.length;V++)xe(J.__webglFramebuffer[P][V],L,C,r.COLOR_ATTACHMENT0,r.TEXTURE_CUBE_MAP_POSITIVE_X+P,V);else xe(J.__webglFramebuffer[P],L,C,r.COLOR_ATTACHMENT0,r.TEXTURE_CUBE_MAP_POSITIVE_X+P,0);x(C)&&_(r.TEXTURE_CUBE_MAP),t.unbindTexture()}else if(B){for(let P=0,V=T.length;P<V;P++){let H=T[P],F=n.get(H),$=r.TEXTURE_2D;(L.isWebGL3DRenderTarget||L.isWebGLArrayRenderTarget)&&($=L.isWebGL3DRenderTarget?r.TEXTURE_3D:r.TEXTURE_2D_ARRAY),t.bindTexture($,F.__webglTexture),K($,H),xe(J.__webglFramebuffer,L,H,r.COLOR_ATTACHMENT0+P,$,0),x(H)&&_($)}t.unbindTexture()}else{let P=r.TEXTURE_2D;if((L.isWebGL3DRenderTarget||L.isWebGLArrayRenderTarget)&&(P=L.isWebGL3DRenderTarget?r.TEXTURE_3D:r.TEXTURE_2D_ARRAY),t.bindTexture(P,G.__webglTexture),K(P,C),C.mipmaps&&C.mipmaps.length>0)for(let V=0;V<C.mipmaps.length;V++)xe(J.__webglFramebuffer[V],L,C,r.COLOR_ATTACHMENT0,P,V);else xe(J.__webglFramebuffer,L,C,r.COLOR_ATTACHMENT0,P,0);x(C)&&_(P),t.unbindTexture()}L.depthBuffer&&Se(L)},this.updateRenderTargetMipmap=function(L){let C=L.textures;for(let J=0,G=C.length;J<G;J++){let T=C[J];if(x(T)){let N=v(L),B=n.get(T).__webglTexture;t.bindTexture(N,B),_(N),t.unbindTexture()}}},this.updateMultisampleRenderTarget=function(L){if(L.samples>0){if(Te(L)===!1){let C=L.textures,J=L.width,G=L.height,T=r.COLOR_BUFFER_BIT,N=L.stencilBuffer?r.DEPTH_STENCIL_ATTACHMENT:r.DEPTH_ATTACHMENT,B=n.get(L),P=C.length>1;if(P)for(let H=0;H<C.length;H++)t.bindFramebuffer(r.FRAMEBUFFER,B.__webglMultisampledFramebuffer),r.framebufferRenderbuffer(r.FRAMEBUFFER,r.COLOR_ATTACHMENT0+H,r.RENDERBUFFER,null),t.bindFramebuffer(r.FRAMEBUFFER,B.__webglFramebuffer),r.framebufferTexture2D(r.DRAW_FRAMEBUFFER,r.COLOR_ATTACHMENT0+H,r.TEXTURE_2D,null,0);t.bindFramebuffer(r.READ_FRAMEBUFFER,B.__webglMultisampledFramebuffer);let V=L.texture.mipmaps;V&&V.length>0?t.bindFramebuffer(r.DRAW_FRAMEBUFFER,B.__webglFramebuffer[0]):t.bindFramebuffer(r.DRAW_FRAMEBUFFER,B.__webglFramebuffer);for(let H=0;H<C.length;H++){if(L.resolveDepthBuffer&&(L.depthBuffer&&(T|=r.DEPTH_BUFFER_BIT),L.stencilBuffer&&L.resolveStencilBuffer&&(T|=r.STENCIL_BUFFER_BIT)),P){r.framebufferRenderbuffer(r.READ_FRAMEBUFFER,r.COLOR_ATTACHMENT0,r.RENDERBUFFER,B.__webglColorRenderbuffer[H]);let F=n.get(C[H]).__webglTexture;r.framebufferTexture2D(r.DRAW_FRAMEBUFFER,r.COLOR_ATTACHMENT0,r.TEXTURE_2D,F,0)}r.blitFramebuffer(0,0,J,G,0,0,J,G,T,r.NEAREST),c===!0&&(se.length=0,de.length=0,se.push(r.COLOR_ATTACHMENT0+H),L.depthBuffer&&L.resolveDepthBuffer===!1&&(se.push(N),de.push(N),r.invalidateFramebuffer(r.DRAW_FRAMEBUFFER,de)),r.invalidateFramebuffer(r.READ_FRAMEBUFFER,se))}if(t.bindFramebuffer(r.READ_FRAMEBUFFER,null),t.bindFramebuffer(r.DRAW_FRAMEBUFFER,null),P)for(let H=0;H<C.length;H++){t.bindFramebuffer(r.FRAMEBUFFER,B.__webglMultisampledFramebuffer),r.framebufferRenderbuffer(r.FRAMEBUFFER,r.COLOR_ATTACHMENT0+H,r.RENDERBUFFER,B.__webglColorRenderbuffer[H]);let F=n.get(C[H]).__webglTexture;t.bindFramebuffer(r.FRAMEBUFFER,B.__webglFramebuffer),r.framebufferTexture2D(r.DRAW_FRAMEBUFFER,r.COLOR_ATTACHMENT0+H,r.TEXTURE_2D,F,0)}t.bindFramebuffer(r.DRAW_FRAMEBUFFER,B.__webglMultisampledFramebuffer)}else if(L.depthBuffer&&L.resolveDepthBuffer===!1&&c){let C=L.stencilBuffer?r.DEPTH_STENCIL_ATTACHMENT:r.DEPTH_ATTACHMENT;r.invalidateFramebuffer(r.DRAW_FRAMEBUFFER,[C])}}},this.setupDepthRenderbuffer=Se,this.setupFrameBufferTexture=xe,this.useMultisampledRTT=Te,this.isReversedDepthBuffer=function(){return t.buffers.depth.getReversed()}}function Fg(r,e){return{convert:function(t,n=_r){let i,s=ut.getTransfer(n);if(t===zn)return r.UNSIGNED_BYTE;if(t===Cl)return r.UNSIGNED_SHORT_4_4_4_4;if(t===Rl)return r.UNSIGNED_SHORT_5_5_5_1;if(t===gh)return r.UNSIGNED_INT_5_9_9_9_REV;if(t===_h)return r.UNSIGNED_INT_10F_11F_11F_REV;if(t===fh)return r.BYTE;if(t===mh)return r.SHORT;if(t===_s)return r.UNSIGNED_SHORT;if(t===Al)return r.INT;if(t===Li)return r.UNSIGNED_INT;if(t===Kn)return r.FLOAT;if(t===gi)return r.HALF_FLOAT;if(t===ep)return r.ALPHA;if(t===tp)return r.RGB;if(t===ai)return r.RGBA;if(t===Ki)return r.DEPTH_COMPONENT;if(t===gr)return r.DEPTH_STENCIL;if(t===Pl)return r.RED;if(t===Il)return r.RED_INTEGER;if(t===ys)return r.RG;if(t===vh)return r.RG_INTEGER;if(t===yh)return r.RGBA_INTEGER;if(t===Ll||t===Dl||t===Ul||t===Nl)if(s===gt){if(i=e.get("WEBGL_compressed_texture_s3tc_srgb"),i===null)return null;if(t===Ll)return i.COMPRESSED_SRGB_S3TC_DXT1_EXT;if(t===Dl)return i.COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT;if(t===Ul)return i.COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT;if(t===Nl)return i.COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT}else{if(i=e.get("WEBGL_compressed_texture_s3tc"),i===null)return null;if(t===Ll)return i.COMPRESSED_RGB_S3TC_DXT1_EXT;if(t===Dl)return i.COMPRESSED_RGBA_S3TC_DXT1_EXT;if(t===Ul)return i.COMPRESSED_RGBA_S3TC_DXT3_EXT;if(t===Nl)return i.COMPRESSED_RGBA_S3TC_DXT5_EXT}if(t===xh||t===Mh||t===bh||t===Sh){if(i=e.get("WEBGL_compressed_texture_pvrtc"),i===null)return null;if(t===xh)return i.COMPRESSED_RGB_PVRTC_4BPPV1_IMG;if(t===Mh)return i.COMPRESSED_RGB_PVRTC_2BPPV1_IMG;if(t===bh)return i.COMPRESSED_RGBA_PVRTC_4BPPV1_IMG;if(t===Sh)return i.COMPRESSED_RGBA_PVRTC_2BPPV1_IMG}if(t===Th||t===Eh||t===wh||t===Ah||t===Ch||t===Rh||t===Ph){if(i=e.get("WEBGL_compressed_texture_etc"),i===null)return null;if(t===Th||t===Eh)return s===gt?i.COMPRESSED_SRGB8_ETC2:i.COMPRESSED_RGB8_ETC2;if(t===wh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:i.COMPRESSED_RGBA8_ETC2_EAC;if(t===Ah)return i.COMPRESSED_R11_EAC;if(t===Ch)return i.COMPRESSED_SIGNED_R11_EAC;if(t===Rh)return i.COMPRESSED_RG11_EAC;if(t===Ph)return i.COMPRESSED_SIGNED_RG11_EAC}if(t===Ih||t===Lh||t===Dh||t===Uh||t===Nh||t===Oh||t===Fh||t===Bh||t===zh||t===kh||t===Vh||t===Gh||t===Hh||t===Wh){if(i=e.get("WEBGL_compressed_texture_astc"),i===null)return null;if(t===Ih)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_4x4_KHR:i.COMPRESSED_RGBA_ASTC_4x4_KHR;if(t===Lh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_5x4_KHR:i.COMPRESSED_RGBA_ASTC_5x4_KHR;if(t===Dh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_5x5_KHR:i.COMPRESSED_RGBA_ASTC_5x5_KHR;if(t===Uh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_6x5_KHR:i.COMPRESSED_RGBA_ASTC_6x5_KHR;if(t===Nh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_6x6_KHR:i.COMPRESSED_RGBA_ASTC_6x6_KHR;if(t===Oh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_8x5_KHR:i.COMPRESSED_RGBA_ASTC_8x5_KHR;if(t===Fh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_8x6_KHR:i.COMPRESSED_RGBA_ASTC_8x6_KHR;if(t===Bh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_8x8_KHR:i.COMPRESSED_RGBA_ASTC_8x8_KHR;if(t===zh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x5_KHR:i.COMPRESSED_RGBA_ASTC_10x5_KHR;if(t===kh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x6_KHR:i.COMPRESSED_RGBA_ASTC_10x6_KHR;if(t===Vh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x8_KHR:i.COMPRESSED_RGBA_ASTC_10x8_KHR;if(t===Gh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x10_KHR:i.COMPRESSED_RGBA_ASTC_10x10_KHR;if(t===Hh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_12x10_KHR:i.COMPRESSED_RGBA_ASTC_12x10_KHR;if(t===Wh)return s===gt?i.COMPRESSED_SRGB8_ALPHA8_ASTC_12x12_KHR:i.COMPRESSED_RGBA_ASTC_12x12_KHR}if(t===jh||t===Xh||t===qh){if(i=e.get("EXT_texture_compression_bptc"),i===null)return null;if(t===jh)return s===gt?i.COMPRESSED_SRGB_ALPHA_BPTC_UNORM_EXT:i.COMPRESSED_RGBA_BPTC_UNORM_EXT;if(t===Xh)return i.COMPRESSED_RGB_BPTC_SIGNED_FLOAT_EXT;if(t===qh)return i.COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT_EXT}if(t===Yh||t===Zh||t===Jh||t===Kh){if(i=e.get("EXT_texture_compression_rgtc"),i===null)return null;if(t===Yh)return i.COMPRESSED_RED_RGTC1_EXT;if(t===Zh)return i.COMPRESSED_SIGNED_RED_RGTC1_EXT;if(t===Jh)return i.COMPRESSED_RED_GREEN_RGTC2_EXT;if(t===Kh)return i.COMPRESSED_SIGNED_RED_GREEN_RGTC2_EXT}return t===vs?r.UNSIGNED_INT_24_8:r[t]!==void 0?r[t]:null}}}var vu=class{constructor(){this.texture=null,this.mesh=null,this.depthNear=0,this.depthFar=0}init(e,t){if(this.texture===null){let n=new sa(e.texture);e.depthNear===t.depthNear&&e.depthFar===t.depthFar||(this.depthNear=e.depthNear,this.depthFar=e.depthFar),this.texture=n}}getMesh(e){if(this.texture!==null&&this.mesh===null){let t=e.cameras[0].viewport,n=new Bn({vertexShader:`
void main() {

	gl_Position = vec4( position, 1.0 );

}`,fragmentShader:`
uniform sampler2DArray depthColor;
uniform float depthWidth;
uniform float depthHeight;

void main() {

	vec2 coord = vec2( gl_FragCoord.x / depthWidth, gl_FragCoord.y / depthHeight );

	if ( coord.x >= 1.0 ) {

		gl_FragDepth = texture( depthColor, vec3( coord.x - 1.0, coord.y, 1 ) ).r;

	} else {

		gl_FragDepth = texture( depthColor, vec3( coord.x, coord.y, 0 ) ).r;

	}

}`,uniforms:{depthColor:{value:this.texture},depthWidth:{value:t.z},depthHeight:{value:t.w}}});this.mesh=new At(new Fn(20,20),n)}return this.mesh}reset(){this.texture=null,this.mesh=null}getDepthTexture(){return this.texture}},yu=class extends pi{constructor(e,t){super();let n=this,i=null,s=1,a=null,o="local-floor",c=1,l=null,h=null,p=null,f=null,m=null,u=null,g=typeof XRWebGLBinding<"u",x=new vu,_={},v=t.getContextAttributes(),S=null,E=null,w=[],R=[],z=new _e,j=null,O=new Jt;O.viewport=new wt;let Q=new Jt;Q.viewport=new wt;let Y=[O,Q],k=new Ml,X=null,K=null;function te(de){let ge=R.indexOf(de.inputSource);if(ge===-1)return;let Te=w[ge];Te!==void 0&&(Te.update(de.inputSource,de.frame,l||a),Te.dispatchEvent({type:de.type,data:de.inputSource}))}function oe(){i.removeEventListener("select",te),i.removeEventListener("selectstart",te),i.removeEventListener("selectend",te),i.removeEventListener("squeeze",te),i.removeEventListener("squeezestart",te),i.removeEventListener("squeezeend",te),i.removeEventListener("end",oe),i.removeEventListener("inputsourceschange",ee);for(let de=0;de<w.length;de++){let ge=R[de];ge!==null&&(R[de]=null,w[de].disconnect(ge))}X=null,K=null,x.reset();for(let de in _)delete _[de];e.setRenderTarget(S),m=null,f=null,p=null,i=null,E=null,se.stop(),n.isPresenting=!1,e.setPixelRatio(j),e.setSize(z.width,z.height,!1),n.dispatchEvent({type:"sessionend"})}function ee(de){for(let ge=0;ge<de.removed.length;ge++){let Te=de.removed[ge],Re=R.indexOf(Te);Re>=0&&(R[Re]=null,w[Re].disconnect(Te))}for(let ge=0;ge<de.added.length;ge++){let Te=de.added[ge],Re=R.indexOf(Te);if(Re===-1){for(let L=0;L<w.length;L++){if(L>=R.length){R.push(Te),Re=L;break}if(R[L]===null){R[L]=Te,Re=L;break}}if(Re===-1)break}let ze=w[Re];ze&&ze.connect(Te)}}this.cameraAutoUpdate=!0,this.enabled=!1,this.isPresenting=!1,this.getController=function(de){let ge=w[de];return ge===void 0&&(ge=new ts,w[de]=ge),ge.getTargetRaySpace()},this.getControllerGrip=function(de){let ge=w[de];return ge===void 0&&(ge=new ts,w[de]=ge),ge.getGripSpace()},this.getHand=function(de){let ge=w[de];return ge===void 0&&(ge=new ts,w[de]=ge),ge.getHandSpace()},this.setFramebufferScaleFactor=function(de){s=de,n.isPresenting===!0&&Ye("WebXRManager: Cannot change framebuffer scale while presenting.")},this.setReferenceSpaceType=function(de){o=de,n.isPresenting===!0&&Ye("WebXRManager: Cannot change reference space type while presenting.")},this.getReferenceSpace=function(){return l||a},this.setReferenceSpace=function(de){l=de},this.getBaseLayer=function(){return f!==null?f:m},this.getBinding=function(){return p===null&&g&&(p=new XRWebGLBinding(i,t)),p},this.getFrame=function(){return u},this.getSession=function(){return i},this.setSession=async function(de){if(i=de,i!==null){if(S=e.getRenderTarget(),i.addEventListener("select",te),i.addEventListener("selectstart",te),i.addEventListener("selectend",te),i.addEventListener("squeeze",te),i.addEventListener("squeezestart",te),i.addEventListener("squeezeend",te),i.addEventListener("end",oe),i.addEventListener("inputsourceschange",ee),v.xrCompatible!==!0&&await t.makeXRCompatible(),j=e.getPixelRatio(),e.getSize(z),g&&"createProjectionLayer"in XRWebGLBinding.prototype){let ge=null,Te=null,Re=null;v.depth&&(Re=v.stencil?t.DEPTH24_STENCIL8:t.DEPTH_COMPONENT24,ge=v.stencil?gr:Ki,Te=v.stencil?vs:Li);let ze={colorFormat:t.RGBA8,depthFormat:Re,scaleFactor:s};p=this.getBinding(),f=p.createProjectionLayer(ze),i.updateRenderState({layers:[f]}),e.setPixelRatio(1),e.setSize(f.textureWidth,f.textureHeight,!1),E=new Dn(f.textureWidth,f.textureHeight,{format:ai,type:zn,depthTexture:new Xi(f.textureWidth,f.textureHeight,Te,void 0,void 0,void 0,void 0,void 0,void 0,ge),stencilBuffer:v.stencil,colorSpace:e.outputColorSpace,samples:v.antialias?4:0,resolveDepthBuffer:f.ignoreDepthValues===!1,resolveStencilBuffer:f.ignoreDepthValues===!1})}else{let ge={antialias:v.antialias,alpha:!0,depth:v.depth,stencil:v.stencil,framebufferScaleFactor:s};m=new XRWebGLLayer(i,t,ge),i.updateRenderState({baseLayer:m}),e.setPixelRatio(1),e.setSize(m.framebufferWidth,m.framebufferHeight,!1),E=new Dn(m.framebufferWidth,m.framebufferHeight,{format:ai,type:zn,colorSpace:e.outputColorSpace,stencilBuffer:v.stencil,resolveDepthBuffer:m.ignoreDepthValues===!1,resolveStencilBuffer:m.ignoreDepthValues===!1})}E.isXRRenderTarget=!0,this.setFoveation(c),l=null,a=await i.requestReferenceSpace(o),se.setContext(i),se.start(),n.isPresenting=!0,n.dispatchEvent({type:"sessionstart"})}},this.getEnvironmentBlendMode=function(){if(i!==null)return i.environmentBlendMode},this.getDepthTexture=function(){return x.getDepthTexture()};let xe=new D,be=new D;function we(de,ge){ge===null?de.matrixWorld.copy(de.matrix):de.matrixWorld.multiplyMatrices(ge.matrixWorld,de.matrix),de.matrixWorldInverse.copy(de.matrixWorld).invert()}this.updateCamera=function(de){if(i===null)return;let ge=de.near,Te=de.far;x.texture!==null&&(x.depthNear>0&&(ge=x.depthNear),x.depthFar>0&&(Te=x.depthFar)),k.near=Q.near=O.near=ge,k.far=Q.far=O.far=Te,X===k.near&&K===k.far||(i.updateRenderState({depthNear:k.near,depthFar:k.far}),X=k.near,K=k.far),k.layers.mask=6|de.layers.mask,O.layers.mask=-5&k.layers.mask,Q.layers.mask=-3&k.layers.mask;let Re=de.parent,ze=k.cameras;we(k,Re);for(let L=0;L<ze.length;L++)we(ze[L],Re);ze.length===2?(function(L,C,J){xe.setFromMatrixPosition(C.matrixWorld),be.setFromMatrixPosition(J.matrixWorld);let G=xe.distanceTo(be),T=C.projectionMatrix.elements,N=J.projectionMatrix.elements,B=T[14]/(T[10]-1),P=T[14]/(T[10]+1),V=(T[9]+1)/T[5],H=(T[9]-1)/T[5],F=(T[8]-1)/T[0],$=(N[8]+1)/N[0],M=B*F,ne=B*$,le=G/(-F+$),ye=le*-F;if(C.matrixWorld.decompose(L.position,L.quaternion,L.scale),L.translateX(ye),L.translateZ(le),L.matrixWorld.compose(L.position,L.quaternion,L.scale),L.matrixWorldInverse.copy(L.matrixWorld).invert(),T[10]===-1)L.projectionMatrix.copy(C.projectionMatrix),L.projectionMatrixInverse.copy(C.projectionMatrixInverse);else{let Ne=B+le,Fe=P+le,Oe=M-ye,ke=ne+(G-ye),Pe=V*P/Fe*Ne,Ze=H*P/Fe*Ne;L.projectionMatrix.makePerspective(Oe,ke,Pe,Ze,Ne,Fe),L.projectionMatrixInverse.copy(L.projectionMatrix).invert()}})(k,O,Q):k.projectionMatrix.copy(O.projectionMatrix),(function(L,C,J){J===null?L.matrix.copy(C.matrixWorld):(L.matrix.copy(J.matrixWorld),L.matrix.invert(),L.matrix.multiply(C.matrixWorld)),L.matrix.decompose(L.position,L.quaternion,L.scale),L.updateMatrixWorld(!0),L.projectionMatrix.copy(C.projectionMatrix),L.projectionMatrixInverse.copy(C.projectionMatrixInverse),L.isPerspectiveCamera&&(L.fov=2*$r*Math.atan(1/L.projectionMatrix.elements[5]),L.zoom=1)})(de,k,Re)},this.getCamera=function(){return k},this.getFoveation=function(){if(f!==null||m!==null)return c},this.setFoveation=function(de){c=de,f!==null&&(f.fixedFoveation=de),m!==null&&m.fixedFoveation!==void 0&&(m.fixedFoveation=de)},this.hasDepthSensing=function(){return x.texture!==null},this.getDepthSensingMesh=function(){return x.getMesh(k)},this.getCameraTexture=function(de){return _[de]};let Se=null,se=new Gp;se.setAnimationLoop(function(de,ge){if(h=ge.getViewerPose(l||a),u=ge,h!==null){let Te=h.views;m!==null&&(e.setRenderTargetFramebuffer(E,m.framebuffer),e.setRenderTarget(E));let Re=!1;Te.length!==k.cameras.length&&(k.cameras.length=0,Re=!0);for(let L=0;L<Te.length;L++){let C=Te[L],J=null;if(m!==null)J=m.getViewport(C);else{let T=p.getViewSubImage(f,C);J=T.viewport,L===0&&(e.setRenderTargetTextures(E,T.colorTexture,T.depthStencilTexture),e.setRenderTarget(E))}let G=Y[L];G===void 0&&(G=new Jt,G.layers.enable(L),G.viewport=new wt,Y[L]=G),G.matrix.fromArray(C.transform.matrix),G.matrix.decompose(G.position,G.quaternion,G.scale),G.projectionMatrix.fromArray(C.projectionMatrix),G.projectionMatrixInverse.copy(G.projectionMatrix).invert(),G.viewport.set(J.x,J.y,J.width,J.height),L===0&&(k.matrix.copy(G.matrix),k.matrix.decompose(k.position,k.quaternion,k.scale)),Re===!0&&k.cameras.push(G)}let ze=i.enabledFeatures;if(ze&&ze.includes("depth-sensing")&&i.depthUsage=="gpu-optimized"&&g){p=n.getBinding();let L=p.getDepthInformation(Te[0]);L&&L.isValid&&L.texture&&x.init(L,i.renderState)}if(ze&&ze.includes("camera-access")&&g){e.state.unbindTexture(),p=n.getBinding();for(let L=0;L<Te.length;L++){let C=Te[L].camera;if(C){let J=_[C];J||(J=new sa,_[C]=J);let G=p.getCameraImage(C);J.sourceTexture=G}}}}for(let Te=0;Te<w.length;Te++){let Re=R[Te],ze=w[Te];Re!==null&&ze!==void 0&&ze.update(Re,ge,l||a)}Se&&Se(de,ge),ge.detectedPlanes&&n.dispatchEvent({type:"planesdetected",data:ge}),u=null}),this.setAnimationLoop=function(de){Se=de},this.dispose=function(){}}},Mr=new Un,Bg=new Ke;function zg(r,e){function t(i,s){i.matrixAutoUpdate===!0&&i.updateMatrix(),s.value.copy(i.matrix)}function n(i,s){i.opacity.value=s.opacity,s.color&&i.diffuse.value.copy(s.color),s.emissive&&i.emissive.value.copy(s.emissive).multiplyScalar(s.emissiveIntensity),s.map&&(i.map.value=s.map,t(s.map,i.mapTransform)),s.alphaMap&&(i.alphaMap.value=s.alphaMap,t(s.alphaMap,i.alphaMapTransform)),s.bumpMap&&(i.bumpMap.value=s.bumpMap,t(s.bumpMap,i.bumpMapTransform),i.bumpScale.value=s.bumpScale,s.side===Tn&&(i.bumpScale.value*=-1)),s.normalMap&&(i.normalMap.value=s.normalMap,t(s.normalMap,i.normalMapTransform),i.normalScale.value.copy(s.normalScale),s.side===Tn&&i.normalScale.value.negate()),s.displacementMap&&(i.displacementMap.value=s.displacementMap,t(s.displacementMap,i.displacementMapTransform),i.displacementScale.value=s.displacementScale,i.displacementBias.value=s.displacementBias),s.emissiveMap&&(i.emissiveMap.value=s.emissiveMap,t(s.emissiveMap,i.emissiveMapTransform)),s.specularMap&&(i.specularMap.value=s.specularMap,t(s.specularMap,i.specularMapTransform)),s.alphaTest>0&&(i.alphaTest.value=s.alphaTest);let a=e.get(s),o=a.envMap,c=a.envMapRotation;o&&(i.envMap.value=o,Mr.copy(c),Mr.x*=-1,Mr.y*=-1,Mr.z*=-1,o.isCubeTexture&&o.isRenderTargetTexture===!1&&(Mr.y*=-1,Mr.z*=-1),i.envMapRotation.value.setFromMatrix4(Bg.makeRotationFromEuler(Mr)),i.flipEnvMap.value=o.isCubeTexture&&o.isRenderTargetTexture===!1?-1:1,i.reflectivity.value=s.reflectivity,i.ior.value=s.ior,i.refractionRatio.value=s.refractionRatio),s.lightMap&&(i.lightMap.value=s.lightMap,i.lightMapIntensity.value=s.lightMapIntensity,t(s.lightMap,i.lightMapTransform)),s.aoMap&&(i.aoMap.value=s.aoMap,i.aoMapIntensity.value=s.aoMapIntensity,t(s.aoMap,i.aoMapTransform))}return{refreshFogUniforms:function(i,s){s.color.getRGB(i.fogColor.value,nu(r)),s.isFog?(i.fogNear.value=s.near,i.fogFar.value=s.far):s.isFogExp2&&(i.fogDensity.value=s.density)},refreshMaterialUniforms:function(i,s,a,o,c){s.isMeshBasicMaterial?n(i,s):s.isMeshLambertMaterial?(n(i,s),s.envMap&&(i.envMapIntensity.value=s.envMapIntensity)):s.isMeshToonMaterial?(n(i,s),(function(l,h){h.gradientMap&&(l.gradientMap.value=h.gradientMap)})(i,s)):s.isMeshPhongMaterial?(n(i,s),(function(l,h){l.specular.value.copy(h.specular),l.shininess.value=Math.max(h.shininess,1e-4)})(i,s),s.envMap&&(i.envMapIntensity.value=s.envMapIntensity)):s.isMeshStandardMaterial?(n(i,s),(function(l,h){l.metalness.value=h.metalness,h.metalnessMap&&(l.metalnessMap.value=h.metalnessMap,t(h.metalnessMap,l.metalnessMapTransform)),l.roughness.value=h.roughness,h.roughnessMap&&(l.roughnessMap.value=h.roughnessMap,t(h.roughnessMap,l.roughnessMapTransform)),h.envMap&&(l.envMapIntensity.value=h.envMapIntensity)})(i,s),s.isMeshPhysicalMaterial&&(function(l,h,p){l.ior.value=h.ior,h.sheen>0&&(l.sheenColor.value.copy(h.sheenColor).multiplyScalar(h.sheen),l.sheenRoughness.value=h.sheenRoughness,h.sheenColorMap&&(l.sheenColorMap.value=h.sheenColorMap,t(h.sheenColorMap,l.sheenColorMapTransform)),h.sheenRoughnessMap&&(l.sheenRoughnessMap.value=h.sheenRoughnessMap,t(h.sheenRoughnessMap,l.sheenRoughnessMapTransform))),h.clearcoat>0&&(l.clearcoat.value=h.clearcoat,l.clearcoatRoughness.value=h.clearcoatRoughness,h.clearcoatMap&&(l.clearcoatMap.value=h.clearcoatMap,t(h.clearcoatMap,l.clearcoatMapTransform)),h.clearcoatRoughnessMap&&(l.clearcoatRoughnessMap.value=h.clearcoatRoughnessMap,t(h.clearcoatRoughnessMap,l.clearcoatRoughnessMapTransform)),h.clearcoatNormalMap&&(l.clearcoatNormalMap.value=h.clearcoatNormalMap,t(h.clearcoatNormalMap,l.clearcoatNormalMapTransform),l.clearcoatNormalScale.value.copy(h.clearcoatNormalScale),h.side===Tn&&l.clearcoatNormalScale.value.negate())),h.dispersion>0&&(l.dispersion.value=h.dispersion),h.iridescence>0&&(l.iridescence.value=h.iridescence,l.iridescenceIOR.value=h.iridescenceIOR,l.iridescenceThicknessMinimum.value=h.iridescenceThicknessRange[0],l.iridescenceThicknessMaximum.value=h.iridescenceThicknessRange[1],h.iridescenceMap&&(l.iridescenceMap.value=h.iridescenceMap,t(h.iridescenceMap,l.iridescenceMapTransform)),h.iridescenceThicknessMap&&(l.iridescenceThicknessMap.value=h.iridescenceThicknessMap,t(h.iridescenceThicknessMap,l.iridescenceThicknessMapTransform))),h.transmission>0&&(l.transmission.value=h.transmission,l.transmissionSamplerMap.value=p.texture,l.transmissionSamplerSize.value.set(p.width,p.height),h.transmissionMap&&(l.transmissionMap.value=h.transmissionMap,t(h.transmissionMap,l.transmissionMapTransform)),l.thickness.value=h.thickness,h.thicknessMap&&(l.thicknessMap.value=h.thicknessMap,t(h.thicknessMap,l.thicknessMapTransform)),l.attenuationDistance.value=h.attenuationDistance,l.attenuationColor.value.copy(h.attenuationColor)),h.anisotropy>0&&(l.anisotropyVector.value.set(h.anisotropy*Math.cos(h.anisotropyRotation),h.anisotropy*Math.sin(h.anisotropyRotation)),h.anisotropyMap&&(l.anisotropyMap.value=h.anisotropyMap,t(h.anisotropyMap,l.anisotropyMapTransform))),l.specularIntensity.value=h.specularIntensity,l.specularColor.value.copy(h.specularColor),h.specularColorMap&&(l.specularColorMap.value=h.specularColorMap,t(h.specularColorMap,l.specularColorMapTransform)),h.specularIntensityMap&&(l.specularIntensityMap.value=h.specularIntensityMap,t(h.specularIntensityMap,l.specularIntensityMapTransform))})(i,s,c)):s.isMeshMatcapMaterial?(n(i,s),(function(l,h){h.matcap&&(l.matcap.value=h.matcap)})(i,s)):s.isMeshDepthMaterial?n(i,s):s.isMeshDistanceMaterial?(n(i,s),(function(l,h){let p=e.get(h).light;l.referencePosition.value.setFromMatrixPosition(p.matrixWorld),l.nearDistance.value=p.shadow.camera.near,l.farDistance.value=p.shadow.camera.far})(i,s)):s.isMeshNormalMaterial?n(i,s):s.isLineBasicMaterial?((function(l,h){l.diffuse.value.copy(h.color),l.opacity.value=h.opacity,h.map&&(l.map.value=h.map,t(h.map,l.mapTransform))})(i,s),s.isLineDashedMaterial&&(function(l,h){l.dashSize.value=h.dashSize,l.totalSize.value=h.dashSize+h.gapSize,l.scale.value=h.scale})(i,s)):s.isPointsMaterial?(function(l,h,p,f){l.diffuse.value.copy(h.color),l.opacity.value=h.opacity,l.size.value=h.size*p,l.scale.value=.5*f,h.map&&(l.map.value=h.map,t(h.map,l.uvTransform)),h.alphaMap&&(l.alphaMap.value=h.alphaMap,t(h.alphaMap,l.alphaMapTransform)),h.alphaTest>0&&(l.alphaTest.value=h.alphaTest)})(i,s,a,o):s.isSpriteMaterial?(function(l,h){l.diffuse.value.copy(h.color),l.opacity.value=h.opacity,l.rotation.value=h.rotation,h.map&&(l.map.value=h.map,t(h.map,l.mapTransform)),h.alphaMap&&(l.alphaMap.value=h.alphaMap,t(h.alphaMap,l.alphaMapTransform)),h.alphaTest>0&&(l.alphaTest.value=h.alphaTest)})(i,s):s.isShadowMaterial?(i.color.value.copy(s.color),i.opacity.value=s.opacity):s.isShaderMaterial&&(s.uniformsNeedUpdate=!1)}}}function kg(r,e,t,n){let i={},s={},a=[],o=r.getParameter(r.MAX_UNIFORM_BUFFER_BINDINGS);function c(p,f,m,u){let g=p.value,x=f+"_"+m;if(u[x]===void 0)return u[x]=typeof g=="number"||typeof g=="boolean"?g:g.clone(),!0;{let _=u[x];if(typeof g=="number"||typeof g=="boolean"){if(_!==g)return u[x]=g,!0}else if(_.equals(g)===!1)return _.copy(g),!0}return!1}function l(p){let f={boundary:0,storage:0};return typeof p=="number"||typeof p=="boolean"?(f.boundary=4,f.storage=4):p.isVector2?(f.boundary=8,f.storage=8):p.isVector3||p.isColor?(f.boundary=16,f.storage=12):p.isVector4?(f.boundary=16,f.storage=16):p.isMatrix3?(f.boundary=48,f.storage=48):p.isMatrix4?(f.boundary=64,f.storage=64):p.isTexture?Ye("WebGLRenderer: Texture samplers can not be part of an uniforms group."):Ye("WebGLRenderer: Unsupported uniform value type.",p),f}function h(p){let f=p.target;f.removeEventListener("dispose",h);let m=a.indexOf(f.__bindingPointIndex);a.splice(m,1),r.deleteBuffer(i[f.id]),delete i[f.id],delete s[f.id]}return{bind:function(p,f){let m=f.program;n.uniformBlockBinding(p,m)},update:function(p,f){let m=i[p.id];m===void 0&&((function(x){let _=x.uniforms,v=0,S=16;for(let w=0,R=_.length;w<R;w++){let z=Array.isArray(_[w])?_[w]:[_[w]];for(let j=0,O=z.length;j<O;j++){let Q=z[j],Y=Array.isArray(Q.value)?Q.value:[Q.value];for(let k=0,X=Y.length;k<X;k++){let K=l(Y[k]),te=v%S,oe=te%K.boundary,ee=te+oe;v+=oe,ee!==0&&S-ee<K.storage&&(v+=S-ee),Q.__data=new Float32Array(K.storage/Float32Array.BYTES_PER_ELEMENT),Q.__offset=v,v+=K.storage}}}let E=v%S;E>0&&(v+=S-E),x.__size=v,x.__cache={}})(p),m=(function(x){let _=(function(){for(let w=0;w<o;w++)if(a.indexOf(w)===-1)return a.push(w),w;return Je("WebGLRenderer: Maximum number of simultaneously usable uniforms groups reached."),0})();x.__bindingPointIndex=_;let v=r.createBuffer(),S=x.__size,E=x.usage;return r.bindBuffer(r.UNIFORM_BUFFER,v),r.bufferData(r.UNIFORM_BUFFER,S,E),r.bindBuffer(r.UNIFORM_BUFFER,null),r.bindBufferBase(r.UNIFORM_BUFFER,_,v),v})(p),i[p.id]=m,p.addEventListener("dispose",h));let u=f.program;n.updateUBOMapping(p,u);let g=e.render.frame;s[p.id]!==g&&((function(x){let _=i[x.id],v=x.uniforms,S=x.__cache;r.bindBuffer(r.UNIFORM_BUFFER,_);for(let E=0,w=v.length;E<w;E++){let R=Array.isArray(v[E])?v[E]:[v[E]];for(let z=0,j=R.length;z<j;z++){let O=R[z];if(c(O,E,z,S)===!0){let Q=O.__offset,Y=Array.isArray(O.value)?O.value:[O.value],k=0;for(let X=0;X<Y.length;X++){let K=Y[X],te=l(K);typeof K=="number"||typeof K=="boolean"?(O.__data[0]=K,r.bufferSubData(r.UNIFORM_BUFFER,Q+k,O.__data)):K.isMatrix3?(O.__data[0]=K.elements[0],O.__data[1]=K.elements[1],O.__data[2]=K.elements[2],O.__data[3]=0,O.__data[4]=K.elements[3],O.__data[5]=K.elements[4],O.__data[6]=K.elements[5],O.__data[7]=0,O.__data[8]=K.elements[6],O.__data[9]=K.elements[7],O.__data[10]=K.elements[8],O.__data[11]=0):(K.toArray(O.__data,k),k+=te.storage/Float32Array.BYTES_PER_ELEMENT)}r.bufferSubData(r.UNIFORM_BUFFER,Q,O.__data)}}}r.bindBuffer(r.UNIFORM_BUFFER,null)})(p),s[p.id]=g)},dispose:function(){for(let p in i)r.deleteBuffer(i[p]);a=[],i={},s={}}}}var Vg=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]),_i=null,Hl=class{constructor(e={}){let{canvas:t=hp(),context:n=null,depth:i=!0,stencil:s=!1,alpha:a=!1,antialias:o=!1,premultipliedAlpha:c=!0,preserveDrawingBuffer:l=!1,powerPreference:h="default",failIfMajorPerformanceCaveat:p=!1,reversedDepthBuffer:f=!1,outputBufferType:m=zn}=e,u;if(this.isWebGLRenderer=!0,n!==null){if(typeof WebGLRenderingContext<"u"&&n instanceof WebGLRenderingContext)throw new Error("THREE.WebGLRenderer: WebGL 1 is not supported since r163.");u=n.getContextAttributes().alpha}else u=a;let g=m,x=new Set([yh,vh,Il]),_=new Set([zn,Li,_s,vs,Cl,Rl]),v=new Uint32Array(4),S=new Int32Array(4),E=null,w=null,R=[],z=[],j=null;this.domElement=t,this.debug={checkShaderErrors:!0,onShaderError:null},this.autoClear=!0,this.autoClearColor=!0,this.autoClearDepth=!0,this.autoClearStencil=!0,this.sortObjects=!0,this.clippingPlanes=[],this.localClippingEnabled=!1,this.toneMapping=si,this.toneMappingExposure=1,this.transmissionResolutionScale=1;let O=this,Q=!1;this._outputColorSpace=Ut;let Y=0,k=0,X=null,K=-1,te=null,oe=new wt,ee=new wt,xe=null,be=new He(0),we=0,Se=t.width,se=t.height,de=1,ge=null,Te=null,Re=new wt(0,0,Se,se),ze=new wt(0,0,Se,se),L=!1,C=new ji,J=!1,G=!1,T=new Ke,N=new D,B=new wt,P={background:null,fog:null,environment:null,overrideMaterial:null,isScene:!0},V=!1;function H(){return X===null?de:1}let F,$,M,ne,le,ye,Ne,Fe,Oe,ke,Pe,Ze,Qe,lt,Ae,We,Ve,qt,ln,yt,ht,ft,cn,Z=n;function mt(U,ie){return t.getContext(U,ie)}try{let U={alpha:!0,depth:i,stencil:s,antialias:o,premultipliedAlpha:c,preserveDrawingBuffer:l,powerPreference:h,failIfMajorPerformanceCaveat:p};if("setAttribute"in t&&t.setAttribute("data-engine",`three.js r${"183"}`),t.addEventListener("webglcontextlost",An,!1),t.addEventListener("webglcontextrestored",Cn,!1),t.addEventListener("webglcontextcreationerror",kn,!1),Z===null){let ie="webgl2";if(Z=mt(ie,U),Z===null)throw mt(ie)?new Error("Error creating WebGL context with your selected attributes."):new Error("Error creating WebGL context.")}}catch(U){throw Je("WebGLRenderer: "+U.message),U}function Mt(){F=new fm(Z),F.init(),ht=new Fg(Z,F),$=new hm(Z,F,e,ht),M=new Ng(Z,F),$.reversedDepthBuffer&&f&&M.buffers.depth.setReversed(!0),ne=new _m(Z),le=new Tg,ye=new Og(Z,F,M,le,$,ht,ne),Ne=new pm(O),Fe=new sm(Z),ft=new lm(Z,Fe),Oe=new mm(Z,Fe,ne,ft),ke=new ym(Z,Oe,Fe,ft,ne),qt=new vm(Z,$,ye),Ae=new um(le),Pe=new Sg(O,Ne,F,$,ft,Ae),Ze=new zg(O,le),Qe=new wg,lt=new Ig(F),Ve=new om(O,Ne,M,ke,u,c),We=new Ug(O,ke,$),cn=new kg(Z,ne,$,M),ln=new cm(Z,F,ne),yt=new gm(Z,F,ne),ne.programs=Pe.programs,O.capabilities=$,O.extensions=F,O.properties=le,O.renderLists=Qe,O.shadowMap=We,O.state=M,O.info=ne}Mt(),g!==zn&&(j=new Mm(g,t.width,t.height,i,s));let ct=new yu(O,Z);function An(U){U.preventDefault(),eu("WebGLRenderer: Context Lost."),Q=!0}function Cn(){eu("WebGLRenderer: Context Restored."),Q=!1;let U=ne.autoReset,ie=We.enabled,ue=We.autoUpdate,fe=We.needsUpdate,he=We.type;Mt(),ne.autoReset=U,We.enabled=ie,We.autoUpdate=ue,We.needsUpdate=fe,We.type=he}function kn(U){Je("WebGLRenderer: A WebGL context could not be created. Reason: ",U.statusMessage)}function oi(U){let ie=U.target;ie.removeEventListener("dispose",oi),(function(ue){(function(fe){let he=le.get(fe).programs;he!==void 0&&(he.forEach(function(ve){Pe.releaseProgram(ve)}),fe.isShaderMaterial&&Pe.releaseShaderCache(fe))})(ue),le.remove(ue)})(ie)}function Ct(U,ie,ue){U.transparent===!0&&U.side===En&&U.forceSinglePass===!1?(U.side=Tn,U.needsUpdate=!0,Ui(U,ie,ue),U.side=fs,U.needsUpdate=!0,Ui(U,ie,ue),U.side=En):Ui(U,ie,ue)}this.xr=ct,this.getContext=function(){return Z},this.getContextAttributes=function(){return Z.getContextAttributes()},this.forceContextLoss=function(){let U=F.get("WEBGL_lose_context");U&&U.loseContext()},this.forceContextRestore=function(){let U=F.get("WEBGL_lose_context");U&&U.restoreContext()},this.getPixelRatio=function(){return de},this.setPixelRatio=function(U){U!==void 0&&(de=U,this.setSize(Se,se,!1))},this.getSize=function(U){return U.set(Se,se)},this.setSize=function(U,ie,ue=!0){ct.isPresenting?Ye("WebGLRenderer: Can't change size while VR device is presenting."):(Se=U,se=ie,t.width=Math.floor(U*de),t.height=Math.floor(ie*de),ue===!0&&(t.style.width=U+"px",t.style.height=ie+"px"),j!==null&&j.setSize(t.width,t.height),this.setViewport(0,0,U,ie))},this.getDrawingBufferSize=function(U){return U.set(Se*de,se*de).floor()},this.setDrawingBufferSize=function(U,ie,ue){Se=U,se=ie,de=ue,t.width=Math.floor(U*ue),t.height=Math.floor(ie*ue),this.setViewport(0,0,U,ie)},this.setEffects=function(U){if(g!==zn){if(U){for(let ie=0;ie<U.length;ie++)if(U[ie].isOutputPass===!0){console.warn("THREE.WebGLRenderer: OutputPass is not needed in setEffects(). Tone mapping and color space conversion are applied automatically.");break}}j.setEffects(U||[])}else console.error("THREE.WebGLRenderer: setEffects() requires outputBufferType set to HalfFloatType or FloatType.")},this.getCurrentViewport=function(U){return U.copy(oe)},this.getViewport=function(U){return U.copy(Re)},this.setViewport=function(U,ie,ue,fe){U.isVector4?Re.set(U.x,U.y,U.z,U.w):Re.set(U,ie,ue,fe),M.viewport(oe.copy(Re).multiplyScalar(de).round())},this.getScissor=function(U){return U.copy(ze)},this.setScissor=function(U,ie,ue,fe){U.isVector4?ze.set(U.x,U.y,U.z,U.w):ze.set(U,ie,ue,fe),M.scissor(ee.copy(ze).multiplyScalar(de).round())},this.getScissorTest=function(){return L},this.setScissorTest=function(U){M.setScissorTest(L=U)},this.setOpaqueSort=function(U){ge=U},this.setTransparentSort=function(U){Te=U},this.getClearColor=function(U){return U.copy(Ve.getClearColor())},this.setClearColor=function(){Ve.setClearColor(...arguments)},this.getClearAlpha=function(){return Ve.getClearAlpha()},this.setClearAlpha=function(){Ve.setClearAlpha(...arguments)},this.clear=function(U=!0,ie=!0,ue=!0){let fe=0;if(U){let he=!1;if(X!==null){let ve=X.texture.format;he=x.has(ve)}if(he){let ve=X.texture.type,Me=_.has(ve),Ie=Ve.getClearColor(),Ue=Ve.getClearAlpha(),Ee=Ie.r,at=Ie.g,$e=Ie.b;Me?(v[0]=Ee,v[1]=at,v[2]=$e,v[3]=Ue,Z.clearBufferuiv(Z.COLOR,0,v)):(S[0]=Ee,S[1]=at,S[2]=$e,S[3]=Ue,Z.clearBufferiv(Z.COLOR,0,S))}else fe|=Z.COLOR_BUFFER_BIT}ie&&(fe|=Z.DEPTH_BUFFER_BIT),ue&&(fe|=Z.STENCIL_BUFFER_BIT,this.state.buffers.stencil.setMask(4294967295)),fe!==0&&Z.clear(fe)},this.clearColor=function(){this.clear(!0,!1,!1)},this.clearDepth=function(){this.clear(!1,!0,!1)},this.clearStencil=function(){this.clear(!1,!1,!0)},this.dispose=function(){t.removeEventListener("webglcontextlost",An,!1),t.removeEventListener("webglcontextrestored",Cn,!1),t.removeEventListener("webglcontextcreationerror",kn,!1),Ve.dispose(),Qe.dispose(),lt.dispose(),le.dispose(),Ne.dispose(),ke.dispose(),ft.dispose(),cn.dispose(),Pe.dispose(),ct.dispose(),ct.removeEventListener("sessionstart",Di),ct.removeEventListener("sessionend",Da),yi.stop()},this.renderBufferDirect=function(U,ie,ue,fe,he,ve){ie===null&&(ie=P);let Me=he.isMesh&&he.matrixWorld.determinant()<0,Ie=(function(Le,it,St,qe,Be){it.isScene!==!0&&(it=P),ye.resetTextureUnits();let Yt=it.fog,yn=qe.isMeshStandardMaterial||qe.isMeshLambertMaterial||qe.isMeshPhongMaterial?it.environment:null,xn=X===null?O.outputColorSpace:X.isXRRenderTarget===!0?X.texture.colorSpace:ur,Wt=qe.isMeshStandardMaterial||qe.isMeshLambertMaterial&&!qe.envMap||qe.isMeshPhongMaterial&&!qe.envMap,Lt=Ne.get(qe.envMap||yn,Wt),dn=qe.vertexColors===!0&&!!St.attributes.color&&St.attributes.color.itemSize===4,Qt=!!St.attributes.tangent&&(!!qe.normalMap||qe.anisotropy>0),en=!!St.morphAttributes.position,tn=!!St.morphAttributes.normal,nr=!!St.morphAttributes.color,wr=si;qe.toneMapped&&(X!==null&&X.isXRRenderTarget!==!0||(wr=O.toneMapping));let nn=St.morphAttributes.position||St.morphAttributes.normal||St.morphAttributes.color,Ts=nn!==void 0?nn.length:0,tt=le.get(qe),Qn=w.state.lights;if(J===!0&&(G===!0||Le!==te)){let fn=Le===te&&qe.id===K;Ae.setState(qe,Le,fn)}let Mn=!1;qe.version===tt.__version?tt.needsLights&&tt.lightsStateVersion!==Qn.state.version||tt.outputColorSpace!==xn||Be.isBatchedMesh&&tt.batching===!1?Mn=!0:Be.isBatchedMesh||tt.batching!==!0?Be.isBatchedMesh&&tt.batchingColor===!0&&Be.colorTexture===null||Be.isBatchedMesh&&tt.batchingColor===!1&&Be.colorTexture!==null||Be.isInstancedMesh&&tt.instancing===!1?Mn=!0:Be.isInstancedMesh||tt.instancing!==!0?Be.isSkinnedMesh&&tt.skinning===!1?Mn=!0:Be.isSkinnedMesh||tt.skinning!==!0?Be.isInstancedMesh&&tt.instancingColor===!0&&Be.instanceColor===null||Be.isInstancedMesh&&tt.instancingColor===!1&&Be.instanceColor!==null||Be.isInstancedMesh&&tt.instancingMorph===!0&&Be.morphTexture===null||Be.isInstancedMesh&&tt.instancingMorph===!1&&Be.morphTexture!==null||tt.envMap!==Lt||qe.fog===!0&&tt.fog!==Yt?Mn=!0:tt.numClippingPlanes===void 0||tt.numClippingPlanes===Ae.numPlanes&&tt.numIntersection===Ae.numIntersection?(tt.vertexAlphas!==dn||tt.vertexTangents!==Qt||tt.morphTargets!==en||tt.morphNormals!==tn||tt.morphColors!==nr||tt.toneMapping!==wr||tt.morphTargetsCount!==Ts)&&(Mn=!0):Mn=!0:Mn=!0:Mn=!0:Mn=!0:(Mn=!0,tt.__version=qe.version);let Vn=tt.currentProgram;Mn===!0&&(Vn=Ui(qe,it,Be));let Bt=!1,Gn=!1,xi=!1,vt=Vn.getUniforms(),Hn=tt.uniforms;if(M.useProgram(Vn.program)&&(Bt=!0,Gn=!0,xi=!0),qe.id!==K&&(K=qe.id,Gn=!0),Bt||te!==Le){M.buffers.depth.getReversed()&&Le.reversedDepth!==!0&&(Le._reversedDepth=!0,Le.updateProjectionMatrix()),vt.setValue(Z,"projectionMatrix",Le.projectionMatrix),vt.setValue(Z,"viewMatrix",Le.matrixWorldInverse);let fn=vt.map.cameraPosition;fn!==void 0&&fn.setValue(Z,N.setFromMatrixPosition(Le.matrixWorld)),$.logarithmicDepthBuffer&&vt.setValue(Z,"logDepthBufFC",2/(Math.log(Le.far+1)/Math.LN2)),(qe.isMeshPhongMaterial||qe.isMeshToonMaterial||qe.isMeshLambertMaterial||qe.isMeshBasicMaterial||qe.isMeshStandardMaterial||qe.isShaderMaterial)&&vt.setValue(Z,"isOrthographic",Le.isOrthographicCamera===!0),te!==Le&&(te=Le,Gn=!0,xi=!0)}if(tt.needsLights&&(Qn.state.directionalShadowMap.length>0&&vt.setValue(Z,"directionalShadowMap",Qn.state.directionalShadowMap,ye),Qn.state.spotShadowMap.length>0&&vt.setValue(Z,"spotShadowMap",Qn.state.spotShadowMap,ye),Qn.state.pointShadowMap.length>0&&vt.setValue(Z,"pointShadowMap",Qn.state.pointShadowMap,ye)),Be.isSkinnedMesh){vt.setOptional(Z,Be,"bindMatrix"),vt.setOptional(Z,Be,"bindMatrixInverse");let fn=Be.skeleton;fn&&(fn.boneTexture===null&&fn.computeBoneTexture(),vt.setValue(Z,"boneTexture",fn.boneTexture,ye))}Be.isBatchedMesh&&(vt.setOptional(Z,Be,"batchingTexture"),vt.setValue(Z,"batchingTexture",Be._matricesTexture,ye),vt.setOptional(Z,Be,"batchingIdTexture"),vt.setValue(Z,"batchingIdTexture",Be._indirectTexture,ye),vt.setOptional(Z,Be,"batchingColorTexture"),Be._colorsTexture!==null&&vt.setValue(Z,"batchingColorTexture",Be._colorsTexture,ye));let pn=St.morphAttributes;pn.position===void 0&&pn.normal===void 0&&pn.color===void 0||qt.update(Be,St,Vn),(Gn||tt.receiveShadow!==Be.receiveShadow)&&(tt.receiveShadow=Be.receiveShadow,vt.setValue(Z,"receiveShadow",Be.receiveShadow)),(qe.isMeshStandardMaterial||qe.isMeshLambertMaterial||qe.isMeshPhongMaterial)&&qe.envMap===null&&it.environment!==null&&(Hn.envMapIntensity.value=it.environmentIntensity),Hn.dfgLUT!==void 0&&(Hn.dfgLUT.value=(_i===null&&(_i=new ta(Vg,16,16,ys,gi),_i.name="DFG_LUT",_i.minFilter=Xt,_i.magFilter=Xt,_i.wrapS=Wi,_i.wrapT=Wi,_i.generateMipmaps=!1,_i.needsUpdate=!0),_i)),Gn&&(vt.setValue(Z,"toneMappingExposure",O.toneMappingExposure),tt.needsLights&&(Rn=xi,(bn=Hn).ambientLightColor.needsUpdate=Rn,bn.lightProbe.needsUpdate=Rn,bn.directionalLights.needsUpdate=Rn,bn.directionalLightShadows.needsUpdate=Rn,bn.pointLights.needsUpdate=Rn,bn.pointLightShadows.needsUpdate=Rn,bn.spotLights.needsUpdate=Rn,bn.spotLightShadows.needsUpdate=Rn,bn.rectAreaLights.needsUpdate=Rn,bn.hemisphereLights.needsUpdate=Rn),Yt&&qe.fog===!0&&Ze.refreshFogUniforms(Hn,Yt),Ze.refreshMaterialUniforms(Hn,qe,de,se,w.state.transmissionRenderTarget[Le.id]),Ms.upload(Z,Tr(tt),Hn,ye));var bn,Rn;if(qe.isShaderMaterial&&qe.uniformsNeedUpdate===!0&&(Ms.upload(Z,Tr(tt),Hn,ye),qe.uniformsNeedUpdate=!1),qe.isSpriteMaterial&&vt.setValue(Z,"center",Be.center),vt.setValue(Z,"modelViewMatrix",Be.modelViewMatrix),vt.setValue(Z,"normalMatrix",Be.normalMatrix),vt.setValue(Z,"modelMatrix",Be.matrixWorld),qe.isShaderMaterial||qe.isRawShaderMaterial){let fn=qe.uniformsGroups;for(let Dt=0,Zl=fn.length;Dt<Zl;Dt++){let Es=fn[Dt];cn.update(Es,Vn),cn.bind(Es,Vn)}}return Vn})(U,ie,ue,fe,he);M.setMaterial(fe,Me);let Ue=ue.index,Ee=1;if(fe.wireframe===!0){if(Ue=Oe.getWireframeAttribute(ue),Ue===void 0)return;Ee=2}let at=ue.drawRange,$e=ue.attributes.position,Ge=at.start*Ee,ot=(at.start+at.count)*Ee;ve!==null&&(Ge=Math.max(Ge,ve.start*Ee),ot=Math.min(ot,(ve.start+ve.count)*Ee)),Ue!==null?(Ge=Math.max(Ge,0),ot=Math.min(ot,Ue.count)):$e!=null&&(Ge=Math.max(Ge,0),ot=Math.min(ot,$e.count));let Tt=ot-Ge;if(Tt<0||Tt===1/0)return;let _t;ft.setup(he,fe,Ie,ue,Ue);let dt=ln;if(Ue!==null&&(_t=Fe.get(Ue),dt=yt,dt.setIndex(_t)),he.isMesh)fe.wireframe===!0?(M.setLineWidth(fe.wireframeLinewidth*H()),dt.setMode(Z.LINES)):dt.setMode(Z.TRIANGLES);else if(he.isLine){let Le=fe.linewidth;Le===void 0&&(Le=1),M.setLineWidth(Le*H()),he.isLineSegments?dt.setMode(Z.LINES):he.isLineLoop?dt.setMode(Z.LINE_LOOP):dt.setMode(Z.LINE_STRIP)}else he.isPoints?dt.setMode(Z.POINTS):he.isSprite&&dt.setMode(Z.TRIANGLES);if(he.isBatchedMesh)if(he._multiDrawInstances!==null)Zs("WebGLRenderer: renderMultiDrawInstances has been deprecated and will be removed in r184. Append to renderMultiDraw arguments and use indirection."),dt.renderMultiDrawInstances(he._multiDrawStarts,he._multiDrawCounts,he._multiDrawCount,he._multiDrawInstances);else if(F.get("WEBGL_multi_draw"))dt.renderMultiDraw(he._multiDrawStarts,he._multiDrawCounts,he._multiDrawCount);else{let Le=he._multiDrawStarts,it=he._multiDrawCounts,St=he._multiDrawCount,qe=Ue?Fe.get(Ue).bytesPerElement:1,Be=le.get(fe).currentProgram.getUniforms();for(let Yt=0;Yt<St;Yt++)Be.setValue(Z,"_gl_DrawID",Yt),dt.render(Le[Yt]/qe,it[Yt])}else if(he.isInstancedMesh)dt.renderInstances(Ge,Tt,he.count);else if(ue.isInstancedBufferGeometry){let Le=ue._maxInstanceCount!==void 0?ue._maxInstanceCount:1/0,it=Math.min(ue.instanceCount,Le);dt.renderInstances(Ge,Tt,it)}else dt.render(Ge,Tt)},this.compile=function(U,ie,ue=null){ue===null&&(ue=U),w=lt.get(ue),w.init(ie),z.push(w),ue.traverseVisible(function(he){he.isLight&&he.layers.test(ie.layers)&&(w.pushLight(he),he.castShadow&&w.pushShadow(he))}),U!==ue&&U.traverseVisible(function(he){he.isLight&&he.layers.test(ie.layers)&&(w.pushLight(he),he.castShadow&&w.pushShadow(he))}),w.setupLights();let fe=new Set;return U.traverse(function(he){if(!(he.isMesh||he.isPoints||he.isLine||he.isSprite))return;let ve=he.material;if(ve)if(Array.isArray(ve))for(let Me=0;Me<ve.length;Me++){let Ie=ve[Me];Ct(Ie,ue,he),fe.add(Ie)}else Ct(ve,ue,he),fe.add(ve)}),w=z.pop(),fe},this.compileAsync=function(U,ie,ue=null){let fe=this.compile(U,ie,ue);return new Promise(he=>{function ve(){fe.forEach(function(Me){le.get(Me).currentProgram.isReady()&&fe.delete(Me)}),fe.size!==0?setTimeout(ve,10):he(U)}F.get("KHR_parallel_shader_compile")!==null?ve():setTimeout(ve,10)})};let hn=null;function Di(){yi.stop()}function Da(){yi.start()}let yi=new Gp;function er(U,ie,ue,fe){if(U.visible===!1)return;if(U.layers.test(ie.layers)){if(U.isGroup)ue=U.renderOrder;else if(U.isLOD)U.autoUpdate===!0&&U.update(ie);else if(U.isLight)w.pushLight(U),U.castShadow&&w.pushShadow(U);else if(U.isSprite){if(!U.frustumCulled||C.intersectsSprite(U)){fe&&B.setFromMatrixPosition(U.matrixWorld).applyMatrix4(T);let ve=ke.update(U),Me=U.material;Me.visible&&E.push(U,ve,Me,ue,B.z,null)}}else if((U.isMesh||U.isLine||U.isPoints)&&(!U.frustumCulled||C.intersectsObject(U))){let ve=ke.update(U),Me=U.material;if(fe&&(U.boundingSphere!==void 0?(U.boundingSphere===null&&U.computeBoundingSphere(),B.copy(U.boundingSphere.center)):(ve.boundingSphere===null&&ve.computeBoundingSphere(),B.copy(ve.boundingSphere.center)),B.applyMatrix4(U.matrixWorld).applyMatrix4(T)),Array.isArray(Me)){let Ie=ve.groups;for(let Ue=0,Ee=Ie.length;Ue<Ee;Ue++){let at=Ie[Ue],$e=Me[at.materialIndex];$e&&$e.visible&&E.push(U,ve,$e,ue,B.z,at)}}else Me.visible&&E.push(U,ve,Me,ue,B.z,null)}}let he=U.children;for(let ve=0,Me=he.length;ve<Me;ve++)er(he[ve],ie,ue,fe)}function tr(U,ie,ue,fe){let{opaque:he,transmissive:ve,transparent:Me}=U;w.setupLightsView(ue),J===!0&&Ae.setGlobalState(O.clippingPlanes,ue),fe&&M.viewport(oe.copy(fe)),he.length>0&&un(he,ie,ue),ve.length>0&&un(ve,ie,ue),Me.length>0&&un(Me,ie,ue),M.buffers.depth.setTest(!0),M.buffers.depth.setMask(!0),M.buffers.color.setMask(!0),M.setPolygonOffset(!1)}function br(U,ie,ue,fe){if((ue.isScene===!0?ue.overrideMaterial:null)!==null)return;if(w.state.transmissionRenderTarget[fe.id]===void 0){let $e=F.has("EXT_color_buffer_half_float")||F.has("EXT_color_buffer_float");w.state.transmissionRenderTarget[fe.id]=new Dn(1,1,{generateMipmaps:!0,type:$e?gi:zn,minFilter:mr,samples:$.samples,stencilBuffer:s,resolveDepthBuffer:!1,resolveStencilBuffer:!1,colorSpace:ut.workingColorSpace})}let he=w.state.transmissionRenderTarget[fe.id],ve=fe.viewport||oe;he.setSize(ve.z*O.transmissionResolutionScale,ve.w*O.transmissionResolutionScale);let Me=O.getRenderTarget(),Ie=O.getActiveCubeFace(),Ue=O.getActiveMipmapLevel();O.setRenderTarget(he),O.getClearColor(be),we=O.getClearAlpha(),we<1&&O.setClearColor(16777215,.5),O.clear(),V&&Ve.render(ue);let Ee=O.toneMapping;O.toneMapping=si;let at=fe.viewport;if(fe.viewport!==void 0&&(fe.viewport=void 0),w.setupLightsView(fe),J===!0&&Ae.setGlobalState(O.clippingPlanes,fe),un(U,ue,fe),ye.updateMultisampleRenderTarget(he),ye.updateRenderTargetMipmap(he),F.has("WEBGL_multisampled_render_to_texture")===!1){let $e=!1;for(let Ge=0,ot=ie.length;Ge<ot;Ge++){let Tt=ie[Ge],{object:_t,geometry:dt,material:Le,group:it}=Tt;if(Le.side===En&&_t.layers.test(fe.layers)){let St=Le.side;Le.side=Tn,Le.needsUpdate=!0,Sr(_t,ue,fe,dt,Le,it),Le.side=St,Le.needsUpdate=!0,$e=!0}}$e===!0&&(ye.updateMultisampleRenderTarget(he),ye.updateRenderTargetMipmap(he))}O.setRenderTarget(Me,Ie,Ue),O.setClearColor(be,we),at!==void 0&&(fe.viewport=at),O.toneMapping=Ee}function un(U,ie,ue){let fe=ie.isScene===!0?ie.overrideMaterial:null;for(let he=0,ve=U.length;he<ve;he++){let Me=U[he],{object:Ie,geometry:Ue,group:Ee}=Me,at=Me.material;at.allowOverride===!0&&fe!==null&&(at=fe),Ie.layers.test(ue.layers)&&Sr(Ie,ie,ue,Ue,at,Ee)}}function Sr(U,ie,ue,fe,he,ve){U.onBeforeRender(O,ie,ue,fe,he,ve),U.modelViewMatrix.multiplyMatrices(ue.matrixWorldInverse,U.matrixWorld),U.normalMatrix.getNormalMatrix(U.modelViewMatrix),he.onBeforeRender(O,ie,ue,fe,U,ve),he.transparent===!0&&he.side===En&&he.forceSinglePass===!1?(he.side=Tn,he.needsUpdate=!0,O.renderBufferDirect(ue,ie,fe,he,U,ve),he.side=fs,he.needsUpdate=!0,O.renderBufferDirect(ue,ie,fe,he,U,ve),he.side=En):O.renderBufferDirect(ue,ie,fe,he,U,ve),U.onAfterRender(O,ie,ue,fe,he,ve)}function Ui(U,ie,ue){ie.isScene!==!0&&(ie=P);let fe=le.get(U),he=w.state.lights,ve=w.state.shadowsArray,Me=he.state.version,Ie=Pe.getParameters(U,he.state,ve,ie,ue),Ue=Pe.getProgramCacheKey(Ie),Ee=fe.programs;fe.environment=U.isMeshStandardMaterial||U.isMeshLambertMaterial||U.isMeshPhongMaterial?ie.environment:null,fe.fog=ie.fog;let at=U.isMeshStandardMaterial||U.isMeshLambertMaterial&&!U.envMap||U.isMeshPhongMaterial&&!U.envMap;fe.envMap=Ne.get(U.envMap||fe.environment,at),fe.envMapRotation=fe.environment!==null&&U.envMap===null?ie.environmentRotation:U.envMapRotation,Ee===void 0&&(U.addEventListener("dispose",oi),Ee=new Map,fe.programs=Ee);let $e=Ee.get(Ue);if($e!==void 0){if(fe.currentProgram===$e&&fe.lightsStateVersion===Me)return li(U,Ie),$e}else Ie.uniforms=Pe.getUniforms(U),U.onBeforeCompile(Ie,O),$e=Pe.acquireProgram(Ie,Ue),Ee.set(Ue,$e),fe.uniforms=Ie.uniforms;let Ge=fe.uniforms;return(U.isShaderMaterial||U.isRawShaderMaterial)&&U.clipping!==!0||(Ge.clippingPlanes=Ae.uniform),li(U,Ie),fe.needsLights=(function(ot){return ot.isMeshLambertMaterial||ot.isMeshToonMaterial||ot.isMeshPhongMaterial||ot.isMeshStandardMaterial||ot.isShadowMaterial||ot.isShaderMaterial&&ot.lights===!0})(U),fe.lightsStateVersion=Me,fe.needsLights&&(Ge.ambientLightColor.value=he.state.ambient,Ge.lightProbe.value=he.state.probe,Ge.directionalLights.value=he.state.directional,Ge.directionalLightShadows.value=he.state.directionalShadow,Ge.spotLights.value=he.state.spot,Ge.spotLightShadows.value=he.state.spotShadow,Ge.rectAreaLights.value=he.state.rectArea,Ge.ltc_1.value=he.state.rectAreaLTC1,Ge.ltc_2.value=he.state.rectAreaLTC2,Ge.pointLights.value=he.state.point,Ge.pointLightShadows.value=he.state.pointShadow,Ge.hemisphereLights.value=he.state.hemi,Ge.directionalShadowMatrix.value=he.state.directionalShadowMatrix,Ge.spotLightMatrix.value=he.state.spotLightMatrix,Ge.spotLightMap.value=he.state.spotLightMap,Ge.pointShadowMatrix.value=he.state.pointShadowMatrix),fe.currentProgram=$e,fe.uniformsList=null,$e}function Tr(U){if(U.uniformsList===null){let ie=U.currentProgram.getUniforms();U.uniformsList=Ms.seqWithValue(ie.seq,U.uniforms)}return U.uniformsList}function li(U,ie){let ue=le.get(U);ue.outputColorSpace=ie.outputColorSpace,ue.batching=ie.batching,ue.batchingColor=ie.batchingColor,ue.instancing=ie.instancing,ue.instancingColor=ie.instancingColor,ue.instancingMorph=ie.instancingMorph,ue.skinning=ie.skinning,ue.morphTargets=ie.morphTargets,ue.morphNormals=ie.morphNormals,ue.morphColors=ie.morphColors,ue.morphTargetsCount=ie.morphTargetsCount,ue.numClippingPlanes=ie.numClippingPlanes,ue.numIntersection=ie.numClipIntersection,ue.vertexAlphas=ie.vertexAlphas,ue.vertexTangents=ie.vertexTangents,ue.toneMapping=ie.toneMapping}yi.setAnimationLoop(function(U){hn&&hn(U)}),typeof self<"u"&&yi.setContext(self),this.setAnimationLoop=function(U){hn=U,ct.setAnimationLoop(U),U===null?yi.stop():yi.start()},ct.addEventListener("sessionstart",Di),ct.addEventListener("sessionend",Da),this.render=function(U,ie){if(ie!==void 0&&ie.isCamera!==!0)return void Je("WebGLRenderer.render: camera is not an instance of THREE.Camera.");if(Q===!0)return;let ue=ct.enabled===!0&&ct.isPresenting===!0,fe=j!==null&&(X===null||ue)&&j.begin(O,X);if(U.matrixWorldAutoUpdate===!0&&U.updateMatrixWorld(),ie.parent===null&&ie.matrixWorldAutoUpdate===!0&&ie.updateMatrixWorld(),ct.enabled!==!0||ct.isPresenting!==!0||j!==null&&j.isCompositing()!==!1||(ct.cameraAutoUpdate===!0&&ct.updateCamera(ie),ie=ct.getCamera()),U.isScene===!0&&U.onBeforeRender(O,U,ie,X),w=lt.get(U,z.length),w.init(ie),z.push(w),T.multiplyMatrices(ie.projectionMatrix,ie.matrixWorldInverse),C.setFromProjectionMatrix(T,Ri,ie.reversedDepth),G=this.localClippingEnabled,J=Ae.init(this.clippingPlanes,G),E=Qe.get(U,R.length),E.init(),R.push(E),ct.enabled===!0&&ct.isPresenting===!0){let ve=O.xr.getDepthSensingMesh();ve!==null&&er(ve,ie,-1/0,O.sortObjects)}er(U,ie,0,O.sortObjects),E.finish(),O.sortObjects===!0&&E.sort(ge,Te),V=ct.enabled===!1||ct.isPresenting===!1||ct.hasDepthSensing()===!1,V&&Ve.addToRenderList(E,U),this.info.render.frame++,J===!0&&Ae.beginShadows();let he=w.state.shadowsArray;if(We.render(he,U,ie),J===!0&&Ae.endShadows(),this.info.autoReset===!0&&this.info.reset(),(fe&&j.hasRenderPass())===!1){let ve=E.opaque,Me=E.transmissive;if(w.setupLights(),ie.isArrayCamera){let Ie=ie.cameras;if(Me.length>0)for(let Ue=0,Ee=Ie.length;Ue<Ee;Ue++)br(ve,Me,U,Ie[Ue]);V&&Ve.render(U);for(let Ue=0,Ee=Ie.length;Ue<Ee;Ue++){let at=Ie[Ue];tr(E,U,at,at.viewport)}}else Me.length>0&&br(ve,Me,U,ie),V&&Ve.render(U),tr(E,U,ie)}X!==null&&k===0&&(ye.updateMultisampleRenderTarget(X),ye.updateRenderTargetMipmap(X)),fe&&j.end(O),U.isScene===!0&&U.onAfterRender(O,U,ie),ft.resetDefaultState(),K=-1,te=null,z.pop(),z.length>0?(w=z[z.length-1],J===!0&&Ae.setGlobalState(O.clippingPlanes,w.state.camera)):w=null,R.pop(),E=R.length>0?R[R.length-1]:null},this.getActiveCubeFace=function(){return Y},this.getActiveMipmapLevel=function(){return k},this.getRenderTarget=function(){return X},this.setRenderTargetTextures=function(U,ie,ue){let fe=le.get(U);fe.__autoAllocateDepthBuffer=U.resolveDepthBuffer===!1,fe.__autoAllocateDepthBuffer===!1&&(fe.__useRenderToTexture=!1),le.get(U.texture).__webglTexture=ie,le.get(U.depthTexture).__webglTexture=fe.__autoAllocateDepthBuffer?void 0:ue,fe.__hasExternalTextures=!0},this.setRenderTargetFramebuffer=function(U,ie){let ue=le.get(U);ue.__webglFramebuffer=ie,ue.__useDefaultFramebuffer=ie===void 0};let Er=Z.createFramebuffer();this.setRenderTarget=function(U,ie=0,ue=0){X=U,Y=ie,k=ue;let fe=null,he=!1,ve=!1;if(U){let Me=le.get(U);if(Me.__useDefaultFramebuffer!==void 0)return M.bindFramebuffer(Z.FRAMEBUFFER,Me.__webglFramebuffer),oe.copy(U.viewport),ee.copy(U.scissor),xe=U.scissorTest,M.viewport(oe),M.scissor(ee),M.setScissorTest(xe),void(K=-1);if(Me.__webglFramebuffer===void 0)ye.setupRenderTarget(U);else if(Me.__hasExternalTextures)ye.rebindTextures(U,le.get(U.texture).__webglTexture,le.get(U.depthTexture).__webglTexture);else if(U.depthBuffer){let Ee=U.depthTexture;if(Me.__boundDepthTexture!==Ee){if(Ee!==null&&le.has(Ee)&&(U.width!==Ee.image.width||U.height!==Ee.image.height))throw new Error("WebGLRenderTarget: Attached DepthTexture is initialized to the incorrect size.");ye.setupDepthRenderbuffer(U)}}let Ie=U.texture;(Ie.isData3DTexture||Ie.isDataArrayTexture||Ie.isCompressedArrayTexture)&&(ve=!0);let Ue=le.get(U).__webglFramebuffer;U.isWebGLCubeRenderTarget?(fe=Array.isArray(Ue[ie])?Ue[ie][ue]:Ue[ie],he=!0):fe=U.samples>0&&ye.useMultisampledRTT(U)===!1?le.get(U).__webglMultisampledFramebuffer:Array.isArray(Ue)?Ue[ue]:Ue,oe.copy(U.viewport),ee.copy(U.scissor),xe=U.scissorTest}else oe.copy(Re).multiplyScalar(de).floor(),ee.copy(ze).multiplyScalar(de).floor(),xe=L;if(ue!==0&&(fe=Er),M.bindFramebuffer(Z.FRAMEBUFFER,fe)&&M.drawBuffers(U,fe),M.viewport(oe),M.scissor(ee),M.setScissorTest(xe),he){let Me=le.get(U.texture);Z.framebufferTexture2D(Z.FRAMEBUFFER,Z.COLOR_ATTACHMENT0,Z.TEXTURE_CUBE_MAP_POSITIVE_X+ie,Me.__webglTexture,ue)}else if(ve){let Me=ie;for(let Ie=0;Ie<U.textures.length;Ie++){let Ue=le.get(U.textures[Ie]);Z.framebufferTextureLayer(Z.FRAMEBUFFER,Z.COLOR_ATTACHMENT0+Ie,Ue.__webglTexture,ue,Me)}}else if(U!==null&&ue!==0){let Me=le.get(U.texture);Z.framebufferTexture2D(Z.FRAMEBUFFER,Z.COLOR_ATTACHMENT0,Z.TEXTURE_2D,Me.__webglTexture,ue)}K=-1},this.readRenderTargetPixels=function(U,ie,ue,fe,he,ve,Me,Ie=0){if(!U||!U.isWebGLRenderTarget)return void Je("WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");let Ue=le.get(U).__webglFramebuffer;if(U.isWebGLCubeRenderTarget&&Me!==void 0&&(Ue=Ue[Me]),Ue){M.bindFramebuffer(Z.FRAMEBUFFER,Ue);try{let Ee=U.textures[Ie],at=Ee.format,$e=Ee.type;if(U.textures.length>1&&Z.readBuffer(Z.COLOR_ATTACHMENT0+Ie),!$.textureFormatReadable(at))return void Je("WebGLRenderer.readRenderTargetPixels: renderTarget is not in RGBA or implementation defined format.");if(!$.textureTypeReadable($e))return void Je("WebGLRenderer.readRenderTargetPixels: renderTarget is not in UnsignedByteType or implementation defined type.");ie>=0&&ie<=U.width-fe&&ue>=0&&ue<=U.height-he&&Z.readPixels(ie,ue,fe,he,ht.convert(at),ht.convert($e),ve)}finally{let Ee=X!==null?le.get(X).__webglFramebuffer:null;M.bindFramebuffer(Z.FRAMEBUFFER,Ee)}}},this.readRenderTargetPixelsAsync=async function(U,ie,ue,fe,he,ve,Me,Ie=0){if(!U||!U.isWebGLRenderTarget)throw new Error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");let Ue=le.get(U).__webglFramebuffer;if(U.isWebGLCubeRenderTarget&&Me!==void 0&&(Ue=Ue[Me]),Ue){if(ie>=0&&ie<=U.width-fe&&ue>=0&&ue<=U.height-he){M.bindFramebuffer(Z.FRAMEBUFFER,Ue);let Ee=U.textures[Ie],at=Ee.format,$e=Ee.type;if(U.textures.length>1&&Z.readBuffer(Z.COLOR_ATTACHMENT0+Ie),!$.textureFormatReadable(at))throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in RGBA or implementation defined format.");if(!$.textureTypeReadable($e))throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in UnsignedByteType or implementation defined type.");let Ge=Z.createBuffer();Z.bindBuffer(Z.PIXEL_PACK_BUFFER,Ge),Z.bufferData(Z.PIXEL_PACK_BUFFER,ve.byteLength,Z.STREAM_READ),Z.readPixels(ie,ue,fe,he,ht.convert(at),ht.convert($e),0);let ot=X!==null?le.get(X).__webglFramebuffer:null;M.bindFramebuffer(Z.FRAMEBUFFER,ot);let Tt=Z.fenceSync(Z.SYNC_GPU_COMMANDS_COMPLETE,0);return Z.flush(),await dp(Z,Tt,4),Z.bindBuffer(Z.PIXEL_PACK_BUFFER,Ge),Z.getBufferSubData(Z.PIXEL_PACK_BUFFER,0,ve),Z.deleteBuffer(Ge),Z.deleteSync(Tt),ve}throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: requested read bounds are out of range.")}},this.copyFramebufferToTexture=function(U,ie=null,ue=0){let fe=Math.pow(2,-ue),he=Math.floor(U.image.width*fe),ve=Math.floor(U.image.height*fe),Me=ie!==null?ie.x:0,Ie=ie!==null?ie.y:0;ye.setTexture2D(U,0),Z.copyTexSubImage2D(Z.TEXTURE_2D,ue,0,0,Me,Ie,he,ve),M.unbindTexture()};let vn=Z.createFramebuffer(),$n=Z.createFramebuffer();this.copyTextureToTexture=function(U,ie,ue=null,fe=null,he=0,ve=0){let Me,Ie,Ue,Ee,at,$e,Ge,ot,Tt,_t=U.isCompressedTexture?U.mipmaps[ve]:U.image;if(ue!==null)Me=ue.max.x-ue.min.x,Ie=ue.max.y-ue.min.y,Ue=ue.isBox3?ue.max.z-ue.min.z:1,Ee=ue.min.x,at=ue.min.y,$e=ue.isBox3?ue.min.z:0;else{let Lt=Math.pow(2,-he);Me=Math.floor(_t.width*Lt),Ie=Math.floor(_t.height*Lt),Ue=U.isDataArrayTexture?_t.depth:U.isData3DTexture?Math.floor(_t.depth*Lt):1,Ee=0,at=0,$e=0}fe!==null?(Ge=fe.x,ot=fe.y,Tt=fe.z):(Ge=0,ot=0,Tt=0);let dt=ht.convert(ie.format),Le=ht.convert(ie.type),it;ie.isData3DTexture?(ye.setTexture3D(ie,0),it=Z.TEXTURE_3D):ie.isDataArrayTexture||ie.isCompressedArrayTexture?(ye.setTexture2DArray(ie,0),it=Z.TEXTURE_2D_ARRAY):(ye.setTexture2D(ie,0),it=Z.TEXTURE_2D),Z.pixelStorei(Z.UNPACK_FLIP_Y_WEBGL,ie.flipY),Z.pixelStorei(Z.UNPACK_PREMULTIPLY_ALPHA_WEBGL,ie.premultiplyAlpha),Z.pixelStorei(Z.UNPACK_ALIGNMENT,ie.unpackAlignment);let St=Z.getParameter(Z.UNPACK_ROW_LENGTH),qe=Z.getParameter(Z.UNPACK_IMAGE_HEIGHT),Be=Z.getParameter(Z.UNPACK_SKIP_PIXELS),Yt=Z.getParameter(Z.UNPACK_SKIP_ROWS),yn=Z.getParameter(Z.UNPACK_SKIP_IMAGES);Z.pixelStorei(Z.UNPACK_ROW_LENGTH,_t.width),Z.pixelStorei(Z.UNPACK_IMAGE_HEIGHT,_t.height),Z.pixelStorei(Z.UNPACK_SKIP_PIXELS,Ee),Z.pixelStorei(Z.UNPACK_SKIP_ROWS,at),Z.pixelStorei(Z.UNPACK_SKIP_IMAGES,$e);let xn=U.isDataArrayTexture||U.isData3DTexture,Wt=ie.isDataArrayTexture||ie.isData3DTexture;if(U.isDepthTexture){let Lt=le.get(U),dn=le.get(ie),Qt=le.get(Lt.__renderTarget),en=le.get(dn.__renderTarget);M.bindFramebuffer(Z.READ_FRAMEBUFFER,Qt.__webglFramebuffer),M.bindFramebuffer(Z.DRAW_FRAMEBUFFER,en.__webglFramebuffer);for(let tn=0;tn<Ue;tn++)xn&&(Z.framebufferTextureLayer(Z.READ_FRAMEBUFFER,Z.COLOR_ATTACHMENT0,le.get(U).__webglTexture,he,$e+tn),Z.framebufferTextureLayer(Z.DRAW_FRAMEBUFFER,Z.COLOR_ATTACHMENT0,le.get(ie).__webglTexture,ve,Tt+tn)),Z.blitFramebuffer(Ee,at,Me,Ie,Ge,ot,Me,Ie,Z.DEPTH_BUFFER_BIT,Z.NEAREST);M.bindFramebuffer(Z.READ_FRAMEBUFFER,null),M.bindFramebuffer(Z.DRAW_FRAMEBUFFER,null)}else if(he!==0||U.isRenderTargetTexture||le.has(U)){let Lt=le.get(U),dn=le.get(ie);M.bindFramebuffer(Z.READ_FRAMEBUFFER,vn),M.bindFramebuffer(Z.DRAW_FRAMEBUFFER,$n);for(let Qt=0;Qt<Ue;Qt++)xn?Z.framebufferTextureLayer(Z.READ_FRAMEBUFFER,Z.COLOR_ATTACHMENT0,Lt.__webglTexture,he,$e+Qt):Z.framebufferTexture2D(Z.READ_FRAMEBUFFER,Z.COLOR_ATTACHMENT0,Z.TEXTURE_2D,Lt.__webglTexture,he),Wt?Z.framebufferTextureLayer(Z.DRAW_FRAMEBUFFER,Z.COLOR_ATTACHMENT0,dn.__webglTexture,ve,Tt+Qt):Z.framebufferTexture2D(Z.DRAW_FRAMEBUFFER,Z.COLOR_ATTACHMENT0,Z.TEXTURE_2D,dn.__webglTexture,ve),he!==0?Z.blitFramebuffer(Ee,at,Me,Ie,Ge,ot,Me,Ie,Z.COLOR_BUFFER_BIT,Z.NEAREST):Wt?Z.copyTexSubImage3D(it,ve,Ge,ot,Tt+Qt,Ee,at,Me,Ie):Z.copyTexSubImage2D(it,ve,Ge,ot,Ee,at,Me,Ie);M.bindFramebuffer(Z.READ_FRAMEBUFFER,null),M.bindFramebuffer(Z.DRAW_FRAMEBUFFER,null)}else Wt?U.isDataTexture||U.isData3DTexture?Z.texSubImage3D(it,ve,Ge,ot,Tt,Me,Ie,Ue,dt,Le,_t.data):ie.isCompressedArrayTexture?Z.compressedTexSubImage3D(it,ve,Ge,ot,Tt,Me,Ie,Ue,dt,_t.data):Z.texSubImage3D(it,ve,Ge,ot,Tt,Me,Ie,Ue,dt,Le,_t):U.isDataTexture?Z.texSubImage2D(Z.TEXTURE_2D,ve,Ge,ot,Me,Ie,dt,Le,_t.data):U.isCompressedTexture?Z.compressedTexSubImage2D(Z.TEXTURE_2D,ve,Ge,ot,_t.width,_t.height,dt,_t.data):Z.texSubImage2D(Z.TEXTURE_2D,ve,Ge,ot,Me,Ie,dt,Le,_t);Z.pixelStorei(Z.UNPACK_ROW_LENGTH,St),Z.pixelStorei(Z.UNPACK_IMAGE_HEIGHT,qe),Z.pixelStorei(Z.UNPACK_SKIP_PIXELS,Be),Z.pixelStorei(Z.UNPACK_SKIP_ROWS,Yt),Z.pixelStorei(Z.UNPACK_SKIP_IMAGES,yn),ve===0&&ie.generateMipmaps&&Z.generateMipmap(it),M.unbindTexture()},this.initRenderTarget=function(U){le.get(U).__webglFramebuffer===void 0&&ye.setupRenderTarget(U)},this.initTexture=function(U){U.isCubeTexture?ye.setTextureCube(U,0):U.isData3DTexture?ye.setTexture3D(U,0):U.isDataArrayTexture||U.isCompressedArrayTexture?ye.setTexture2DArray(U,0):ye.setTexture2D(U,0),M.unbindTexture()},this.resetState=function(){Y=0,k=0,X=null,M.reset(),ft.reset()},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}get coordinateSystem(){return Ri}get outputColorSpace(){return this._outputColorSpace}set outputColorSpace(e){this._outputColorSpace=e;let t=this.getContext();t.drawingBufferColorSpace=ut._getDrawingBufferColorSpace(e),t.unpackColorSpace=ut._getUnpackColorSpace()}};var qp={type:"change"},Mu={type:"start"},Zp={type:"end"},jl=new fi,Yp=new Zt,Gg=Math.cos(70*pt.DEG2RAD),Ht=new D,wn=2*Math.PI,xt={NONE:-1,ROTATE:0,DOLLY:1,PAN:2,TOUCH_ROTATE:3,TOUCH_PAN:4,TOUCH_DOLLY_PAN:5,TOUCH_DOLLY_ROTATE:6},xu=1e-6,Xl=class extends ba{constructor(e,t=null){super(e,t),this.state=xt.NONE,this.target=new D,this.cursor=new D,this.minDistance=0,this.maxDistance=1/0,this.minZoom=0,this.maxZoom=1/0,this.minTargetRadius=0,this.maxTargetRadius=1/0,this.minPolarAngle=0,this.maxPolarAngle=Math.PI,this.minAzimuthAngle=-1/0,this.maxAzimuthAngle=1/0,this.enableDamping=!1,this.dampingFactor=.05,this.enableZoom=!0,this.zoomSpeed=1,this.enableRotate=!0,this.rotateSpeed=1,this.keyRotateSpeed=1,this.enablePan=!0,this.panSpeed=1,this.screenSpacePanning=!0,this.keyPanSpeed=7,this.zoomToCursor=!1,this.autoRotate=!1,this.autoRotateSpeed=2,this.keys={LEFT:"ArrowLeft",UP:"ArrowUp",RIGHT:"ArrowRight",BOTTOM:"ArrowDown"},this.mouseButtons={LEFT:Zi.ROTATE,MIDDLE:Zi.DOLLY,RIGHT:Zi.PAN},this.touches={ONE:Ji.ROTATE,TWO:Ji.DOLLY_PAN},this.target0=this.target.clone(),this.position0=this.object.position.clone(),this.zoom0=this.object.zoom,this._cursorStyle="auto",this._domElementKeyEvents=null,this._lastPosition=new D,this._lastQuaternion=new kt,this._lastTargetPosition=new D,this._quat=new kt().setFromUnitVectors(e.up,new D(0,1,0)),this._quatInverse=this._quat.clone().invert(),this._spherical=new ds,this._sphericalDelta=new ds,this._scale=1,this._panOffset=new D,this._rotateStart=new _e,this._rotateEnd=new _e,this._rotateDelta=new _e,this._panStart=new _e,this._panEnd=new _e,this._panDelta=new _e,this._dollyStart=new _e,this._dollyEnd=new _e,this._dollyDelta=new _e,this._dollyDirection=new D,this._mouse=new _e,this._performCursorZoom=!1,this._pointers=[],this._pointerPositions={},this._controlActive=!1,this._onPointerMove=Wg.bind(this),this._onPointerDown=Hg.bind(this),this._onPointerUp=jg.bind(this),this._onContextMenu=$g.bind(this),this._onMouseWheel=Yg.bind(this),this._onKeyDown=Zg.bind(this),this._onTouchStart=Jg.bind(this),this._onTouchMove=Kg.bind(this),this._onMouseDown=Xg.bind(this),this._onMouseMove=qg.bind(this),this._interceptControlDown=Qg.bind(this),this._interceptControlUp=e0.bind(this),this.domElement!==null&&this.connect(this.domElement),this.update()}set cursorStyle(e){this._cursorStyle=e,e==="grab"?this.domElement.style.cursor="grab":this.domElement.style.cursor="auto"}get cursorStyle(){return this._cursorStyle}connect(e){super.connect(e),this.domElement.addEventListener("pointerdown",this._onPointerDown),this.domElement.addEventListener("pointercancel",this._onPointerUp),this.domElement.addEventListener("contextmenu",this._onContextMenu),this.domElement.addEventListener("wheel",this._onMouseWheel,{passive:!1}),this.domElement.getRootNode().addEventListener("keydown",this._interceptControlDown,{passive:!0,capture:!0}),this.domElement.style.touchAction="none"}disconnect(){this.domElement.removeEventListener("pointerdown",this._onPointerDown),this.domElement.ownerDocument.removeEventListener("pointermove",this._onPointerMove),this.domElement.ownerDocument.removeEventListener("pointerup",this._onPointerUp),this.domElement.removeEventListener("pointercancel",this._onPointerUp),this.domElement.removeEventListener("wheel",this._onMouseWheel),this.domElement.removeEventListener("contextmenu",this._onContextMenu),this.stopListenToKeyEvents(),this.domElement.getRootNode().removeEventListener("keydown",this._interceptControlDown,{capture:!0}),this.domElement.style.touchAction="auto"}dispose(){this.disconnect()}getPolarAngle(){return this._spherical.phi}getAzimuthalAngle(){return this._spherical.theta}getDistance(){return this.object.position.distanceTo(this.target)}listenToKeyEvents(e){e.addEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=e}stopListenToKeyEvents(){this._domElementKeyEvents!==null&&(this._domElementKeyEvents.removeEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=null)}saveState(){this.target0.copy(this.target),this.position0.copy(this.object.position),this.zoom0=this.object.zoom}reset(){this.target.copy(this.target0),this.object.position.copy(this.position0),this.object.zoom=this.zoom0,this.object.updateProjectionMatrix(),this.dispatchEvent(qp),this.update(),this.state=xt.NONE}pan(e,t){this._pan(e,t),this.update()}dollyIn(e){this._dollyIn(e),this.update()}dollyOut(e){this._dollyOut(e),this.update()}rotateLeft(e){this._rotateLeft(e),this.update()}rotateUp(e){this._rotateUp(e),this.update()}update(e=null){let t=this.object.position;Ht.copy(t).sub(this.target),Ht.applyQuaternion(this._quat),this._spherical.setFromVector3(Ht),this.autoRotate&&this.state===xt.NONE&&this._rotateLeft(this._getAutoRotationAngle(e)),this.enableDamping?(this._spherical.theta+=this._sphericalDelta.theta*this.dampingFactor,this._spherical.phi+=this._sphericalDelta.phi*this.dampingFactor):(this._spherical.theta+=this._sphericalDelta.theta,this._spherical.phi+=this._sphericalDelta.phi);let n=this.minAzimuthAngle,i=this.maxAzimuthAngle;isFinite(n)&&isFinite(i)&&(n<-Math.PI?n+=wn:n>Math.PI&&(n-=wn),i<-Math.PI?i+=wn:i>Math.PI&&(i-=wn),n<=i?this._spherical.theta=Math.max(n,Math.min(i,this._spherical.theta)):this._spherical.theta=this._spherical.theta>(n+i)/2?Math.max(n,this._spherical.theta):Math.min(i,this._spherical.theta)),this._spherical.phi=Math.max(this.minPolarAngle,Math.min(this.maxPolarAngle,this._spherical.phi)),this._spherical.makeSafe(),this.enableDamping===!0?this.target.addScaledVector(this._panOffset,this.dampingFactor):this.target.add(this._panOffset),this.target.sub(this.cursor),this.target.clampLength(this.minTargetRadius,this.maxTargetRadius),this.target.add(this.cursor);let s=!1;if(this.zoomToCursor&&this._performCursorZoom||this.object.isOrthographicCamera)this._spherical.radius=this._clampDistance(this._spherical.radius);else{let a=this._spherical.radius;this._spherical.radius=this._clampDistance(this._spherical.radius*this._scale),s=a!=this._spherical.radius}if(Ht.setFromSpherical(this._spherical),Ht.applyQuaternion(this._quatInverse),t.copy(this.target).add(Ht),this.object.lookAt(this.target),this.enableDamping===!0?(this._sphericalDelta.theta*=1-this.dampingFactor,this._sphericalDelta.phi*=1-this.dampingFactor,this._panOffset.multiplyScalar(1-this.dampingFactor)):(this._sphericalDelta.set(0,0,0),this._panOffset.set(0,0,0)),this.zoomToCursor&&this._performCursorZoom){let a=null;if(this.object.isPerspectiveCamera){let o=Ht.length();a=this._clampDistance(o*this._scale);let c=o-a;this.object.position.addScaledVector(this._dollyDirection,c),this.object.updateMatrixWorld(),s=!!c}else if(this.object.isOrthographicCamera){let o=new D(this._mouse.x,this._mouse.y,0);o.unproject(this.object);let c=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),this.object.updateProjectionMatrix(),s=c!==this.object.zoom;let l=new D(this._mouse.x,this._mouse.y,0);l.unproject(this.object),this.object.position.sub(l).add(o),this.object.updateMatrixWorld(),a=Ht.length()}else console.warn("WARNING: OrbitControls.js encountered an unknown camera type - zoom to cursor disabled."),this.zoomToCursor=!1;a!==null&&(this.screenSpacePanning?this.target.set(0,0,-1).transformDirection(this.object.matrix).multiplyScalar(a).add(this.object.position):(jl.origin.copy(this.object.position),jl.direction.set(0,0,-1).transformDirection(this.object.matrix),Math.abs(this.object.up.dot(jl.direction))<Gg?this.object.lookAt(this.target):(Yp.setFromNormalAndCoplanarPoint(this.object.up,this.target),jl.intersectPlane(Yp,this.target))))}else if(this.object.isOrthographicCamera){let a=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),a!==this.object.zoom&&(this.object.updateProjectionMatrix(),s=!0)}return this._scale=1,this._performCursorZoom=!1,s||this._lastPosition.distanceToSquared(this.object.position)>xu||8*(1-this._lastQuaternion.dot(this.object.quaternion))>xu||this._lastTargetPosition.distanceToSquared(this.target)>xu?(this.dispatchEvent(qp),this._lastPosition.copy(this.object.position),this._lastQuaternion.copy(this.object.quaternion),this._lastTargetPosition.copy(this.target),!0):!1}_getAutoRotationAngle(e){return e!==null?wn/60*this.autoRotateSpeed*e:wn/60/60*this.autoRotateSpeed}_getZoomScale(e){let t=Math.abs(e*.01);return Math.pow(.95,this.zoomSpeed*t)}_rotateLeft(e){this._sphericalDelta.theta-=e}_rotateUp(e){this._sphericalDelta.phi-=e}_panLeft(e,t){Ht.setFromMatrixColumn(t,0),Ht.multiplyScalar(-e),this._panOffset.add(Ht)}_panUp(e,t){this.screenSpacePanning===!0?Ht.setFromMatrixColumn(t,1):(Ht.setFromMatrixColumn(t,0),Ht.crossVectors(this.object.up,Ht)),Ht.multiplyScalar(e),this._panOffset.add(Ht)}_pan(e,t){let n=this.domElement;if(this.object.isPerspectiveCamera){let i=this.object.position;Ht.copy(i).sub(this.target);let s=Ht.length();s*=Math.tan(this.object.fov/2*Math.PI/180),this._panLeft(2*e*s/n.clientHeight,this.object.matrix),this._panUp(2*t*s/n.clientHeight,this.object.matrix)}else this.object.isOrthographicCamera?(this._panLeft(e*(this.object.right-this.object.left)/this.object.zoom/n.clientWidth,this.object.matrix),this._panUp(t*(this.object.top-this.object.bottom)/this.object.zoom/n.clientHeight,this.object.matrix)):(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - pan disabled."),this.enablePan=!1)}_dollyOut(e){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale/=e:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_dollyIn(e){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale*=e:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_updateZoomParameters(e,t){if(!this.zoomToCursor)return;this._performCursorZoom=!0;let n=this.domElement.getBoundingClientRect(),i=e-n.left,s=t-n.top,a=n.width,o=n.height;this._mouse.x=i/a*2-1,this._mouse.y=-(s/o)*2+1,this._dollyDirection.set(this._mouse.x,this._mouse.y,1).unproject(this.object).sub(this.object.position).normalize()}_clampDistance(e){return Math.max(this.minDistance,Math.min(this.maxDistance,e))}_handleMouseDownRotate(e){this._rotateStart.set(e.clientX,e.clientY)}_handleMouseDownDolly(e){this._updateZoomParameters(e.clientX,e.clientX),this._dollyStart.set(e.clientX,e.clientY)}_handleMouseDownPan(e){this._panStart.set(e.clientX,e.clientY)}_handleMouseMoveRotate(e){this._rotateEnd.set(e.clientX,e.clientY),this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);let t=this.domElement;this._rotateLeft(wn*this._rotateDelta.x/t.clientHeight),this._rotateUp(wn*this._rotateDelta.y/t.clientHeight),this._rotateStart.copy(this._rotateEnd),this.update()}_handleMouseMoveDolly(e){this._dollyEnd.set(e.clientX,e.clientY),this._dollyDelta.subVectors(this._dollyEnd,this._dollyStart),this._dollyDelta.y>0?this._dollyOut(this._getZoomScale(this._dollyDelta.y)):this._dollyDelta.y<0&&this._dollyIn(this._getZoomScale(this._dollyDelta.y)),this._dollyStart.copy(this._dollyEnd),this.update()}_handleMouseMovePan(e){this._panEnd.set(e.clientX,e.clientY),this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd),this.update()}_handleMouseWheel(e){this._updateZoomParameters(e.clientX,e.clientY),e.deltaY<0?this._dollyIn(this._getZoomScale(e.deltaY)):e.deltaY>0&&this._dollyOut(this._getZoomScale(e.deltaY)),this.update()}_handleKeyDown(e){let t=!1;switch(e.code){case this.keys.UP:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateUp(wn*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(0,this.keyPanSpeed),t=!0;break;case this.keys.BOTTOM:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateUp(-wn*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(0,-this.keyPanSpeed),t=!0;break;case this.keys.LEFT:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateLeft(wn*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(this.keyPanSpeed,0),t=!0;break;case this.keys.RIGHT:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateLeft(-wn*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(-this.keyPanSpeed,0),t=!0;break}t&&(e.preventDefault(),this.update())}_handleTouchStartRotate(e){if(this._pointers.length===1)this._rotateStart.set(e.pageX,e.pageY);else{let t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),i=.5*(e.pageY+t.y);this._rotateStart.set(n,i)}}_handleTouchStartPan(e){if(this._pointers.length===1)this._panStart.set(e.pageX,e.pageY);else{let t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),i=.5*(e.pageY+t.y);this._panStart.set(n,i)}}_handleTouchStartDolly(e){let t=this._getSecondPointerPosition(e),n=e.pageX-t.x,i=e.pageY-t.y,s=Math.sqrt(n*n+i*i);this._dollyStart.set(0,s)}_handleTouchStartDollyPan(e){this.enableZoom&&this._handleTouchStartDolly(e),this.enablePan&&this._handleTouchStartPan(e)}_handleTouchStartDollyRotate(e){this.enableZoom&&this._handleTouchStartDolly(e),this.enableRotate&&this._handleTouchStartRotate(e)}_handleTouchMoveRotate(e){if(this._pointers.length==1)this._rotateEnd.set(e.pageX,e.pageY);else{let n=this._getSecondPointerPosition(e),i=.5*(e.pageX+n.x),s=.5*(e.pageY+n.y);this._rotateEnd.set(i,s)}this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);let t=this.domElement;this._rotateLeft(wn*this._rotateDelta.x/t.clientHeight),this._rotateUp(wn*this._rotateDelta.y/t.clientHeight),this._rotateStart.copy(this._rotateEnd)}_handleTouchMovePan(e){if(this._pointers.length===1)this._panEnd.set(e.pageX,e.pageY);else{let t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),i=.5*(e.pageY+t.y);this._panEnd.set(n,i)}this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd)}_handleTouchMoveDolly(e){let t=this._getSecondPointerPosition(e),n=e.pageX-t.x,i=e.pageY-t.y,s=Math.sqrt(n*n+i*i);this._dollyEnd.set(0,s),this._dollyDelta.set(0,Math.pow(this._dollyEnd.y/this._dollyStart.y,this.zoomSpeed)),this._dollyOut(this._dollyDelta.y),this._dollyStart.copy(this._dollyEnd);let a=(e.pageX+t.x)*.5,o=(e.pageY+t.y)*.5;this._updateZoomParameters(a,o)}_handleTouchMoveDollyPan(e){this.enableZoom&&this._handleTouchMoveDolly(e),this.enablePan&&this._handleTouchMovePan(e)}_handleTouchMoveDollyRotate(e){this.enableZoom&&this._handleTouchMoveDolly(e),this.enableRotate&&this._handleTouchMoveRotate(e)}_addPointer(e){this._pointers.push(e.pointerId)}_removePointer(e){delete this._pointerPositions[e.pointerId];for(let t=0;t<this._pointers.length;t++)if(this._pointers[t]==e.pointerId){this._pointers.splice(t,1);return}}_isTrackingPointer(e){for(let t=0;t<this._pointers.length;t++)if(this._pointers[t]==e.pointerId)return!0;return!1}_trackPointer(e){let t=this._pointerPositions[e.pointerId];t===void 0&&(t=new _e,this._pointerPositions[e.pointerId]=t),t.set(e.pageX,e.pageY)}_getSecondPointerPosition(e){let t=e.pointerId===this._pointers[0]?this._pointers[1]:this._pointers[0];return this._pointerPositions[t]}_customWheelEvent(e){let t=e.deltaMode,n={clientX:e.clientX,clientY:e.clientY,deltaY:e.deltaY};switch(t){case 1:n.deltaY*=16;break;case 2:n.deltaY*=100;break}return e.ctrlKey&&!this._controlActive&&(n.deltaY*=10),n}};function Hg(r){this.enabled!==!1&&(this._pointers.length===0&&(this.domElement.setPointerCapture(r.pointerId),this.domElement.ownerDocument.addEventListener("pointermove",this._onPointerMove),this.domElement.ownerDocument.addEventListener("pointerup",this._onPointerUp)),!this._isTrackingPointer(r)&&(this._addPointer(r),r.pointerType==="touch"?this._onTouchStart(r):this._onMouseDown(r),this._cursorStyle==="grab"&&(this.domElement.style.cursor="grabbing")))}function Wg(r){this.enabled!==!1&&(r.pointerType==="touch"?this._onTouchMove(r):this._onMouseMove(r))}function jg(r){switch(this._removePointer(r),this._pointers.length){case 0:this.domElement.releasePointerCapture(r.pointerId),this.domElement.ownerDocument.removeEventListener("pointermove",this._onPointerMove),this.domElement.ownerDocument.removeEventListener("pointerup",this._onPointerUp),this.dispatchEvent(Zp),this.state=xt.NONE,this._cursorStyle==="grab"&&(this.domElement.style.cursor="grab");break;case 1:let e=this._pointers[0],t=this._pointerPositions[e];this._onTouchStart({pointerId:e,pageX:t.x,pageY:t.y});break}}function Xg(r){let e;switch(r.button){case 0:e=this.mouseButtons.LEFT;break;case 1:e=this.mouseButtons.MIDDLE;break;case 2:e=this.mouseButtons.RIGHT;break;default:e=-1}switch(e){case Zi.DOLLY:if(this.enableZoom===!1)return;this._handleMouseDownDolly(r),this.state=xt.DOLLY;break;case Zi.ROTATE:if(r.ctrlKey||r.metaKey||r.shiftKey){if(this.enablePan===!1)return;this._handleMouseDownPan(r),this.state=xt.PAN}else{if(this.enableRotate===!1)return;this._handleMouseDownRotate(r),this.state=xt.ROTATE}break;case Zi.PAN:if(r.ctrlKey||r.metaKey||r.shiftKey){if(this.enableRotate===!1)return;this._handleMouseDownRotate(r),this.state=xt.ROTATE}else{if(this.enablePan===!1)return;this._handleMouseDownPan(r),this.state=xt.PAN}break;default:this.state=xt.NONE}this.state!==xt.NONE&&this.dispatchEvent(Mu)}function qg(r){switch(this.state){case xt.ROTATE:if(this.enableRotate===!1)return;this._handleMouseMoveRotate(r);break;case xt.DOLLY:if(this.enableZoom===!1)return;this._handleMouseMoveDolly(r);break;case xt.PAN:if(this.enablePan===!1)return;this._handleMouseMovePan(r);break}}function Yg(r){this.enabled===!1||this.enableZoom===!1||this.state!==xt.NONE||(r.preventDefault(),this.dispatchEvent(Mu),this._handleMouseWheel(this._customWheelEvent(r)),this.dispatchEvent(Zp))}function Zg(r){this.enabled!==!1&&this._handleKeyDown(r)}function Jg(r){switch(this._trackPointer(r),this._pointers.length){case 1:switch(this.touches.ONE){case Ji.ROTATE:if(this.enableRotate===!1)return;this._handleTouchStartRotate(r),this.state=xt.TOUCH_ROTATE;break;case Ji.PAN:if(this.enablePan===!1)return;this._handleTouchStartPan(r),this.state=xt.TOUCH_PAN;break;default:this.state=xt.NONE}break;case 2:switch(this.touches.TWO){case Ji.DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchStartDollyPan(r),this.state=xt.TOUCH_DOLLY_PAN;break;case Ji.DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchStartDollyRotate(r),this.state=xt.TOUCH_DOLLY_ROTATE;break;default:this.state=xt.NONE}break;default:this.state=xt.NONE}this.state!==xt.NONE&&this.dispatchEvent(Mu)}function Kg(r){switch(this._trackPointer(r),this.state){case xt.TOUCH_ROTATE:if(this.enableRotate===!1)return;this._handleTouchMoveRotate(r),this.update();break;case xt.TOUCH_PAN:if(this.enablePan===!1)return;this._handleTouchMovePan(r),this.update();break;case xt.TOUCH_DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchMoveDollyPan(r),this.update();break;case xt.TOUCH_DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchMoveDollyRotate(r),this.update();break;default:this.state=xt.NONE}}function $g(r){this.enabled!==!1&&r.preventDefault()}function Qg(r){r.key==="Control"&&(this._controlActive=!0,this.domElement.getRootNode().addEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}function e0(r){r.key==="Control"&&(this._controlActive=!1,this.domElement.getRootNode().removeEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}var $i=pt.clamp,ql=(r,e,t)=>pt.smoothstep(t,r,e),Jp=(r,e,t=.35,n=.6)=>ql(0,t,r)*(1-ql(e-n,e,r));function Kp(r,e){let t=new Nn(1,1,1),n=[],i=[],s=(F,$,M)=>new He(F).lerp(new He($),M),a=F=>{let $=new Sn({color:F,roughness:.86});return n.push($),$},o=a(e.skin),c=a(s(e.skin,"#d97778",.28)),l=a(e.hair),h=a(s(e.hair,"#e6c49a",.17)),p=a(e.top),f=a(s(e.top,"#263941",.2)),m=a(e.bottom),u=a(s(e.bottom,"#e9dfcf",.14)),g=a("#30323b"),x=a("#302a30"),_=a("#fff9e9");function v(F,$,M,ne){let le=new At(t,ne);return le.position.set(...$),le.scale.set(...M),le.castShadow=!0,le.receiveShadow=!0,le.userData.station="resident",F.add(le),i.push(le),le}function S(F,$,M){let ne=new Kt;return ne.name=$,ne.position.set(...M),F.add(ne),ne}let E=S(r,"hips",[0,.76,0]);v(E,[0,.065,0],[.4,.19,.28],m);let w=S(E,"chest",[0,.12,0]);v(w,[0,.22,0],[.44,.43,.3],p),v(w,[0,.4,-.005],[.39,.1,.28],p),v(w,[0,.025,.002],[.46,.07,.32],f),v(w,[0,.45,.018],[.19,.08,.21],_),v(w,[0,.49,0],[.15,.1,.17],o),v(w,[.115,.255,.157],[.11,.1,.018],f),v(w,[.115,.3,.171],[.12,.022,.025],_);let R=S(w,"head",[0,.58,0]);v(R,[0,.11,0],[.55,.5,.46],o),v(R,[0,.105,.015],[.61,.36,.46],o),v(R,[0,-.15,.015],[.43,.075,.4],o),v(R,[0,.375,-.025],[.62,.1,.51],l),v(R,[-.025,.443,-.04],[.46,.06,.4],l),v(R,[0,.16,-.234],[.59,.4,.1],l);let z=[],j=[],O=[],Q=[],Y=[],k=(F,$,M,ne=l)=>{let le=S(R,"hair-lock",F);return le.userData.lean=M,z.push(le),v(le,[0,-$[1]/2,0],$,ne),le};k([-.215,.345,.227],[.18,.18,.09],-.14),k([-.06,.38,.244],[.15,.12,.075],-.19,h),k([.075,.365,.24],[.12,.105,.07],-.12),k([.225,.34,.18],[.12,.23,.17],.12);for(let F of[-1,1]){v(R,[F*.32,.05,-.002],[.09,.12,.12],o),v(R,[F*.344,.05,.047],[.025,.06,.03],c),k([F*.286,.3,-.032],[.095,.29,.35],F*.035);let $=S(R,"eye",[F*.124,.105,.253]);j.push($),v($,[0,0,0],[.11,.12,.018],_);let M=S($,"pupil",[0,0,.014]);O.push(M),v(M,[0,-.003,0],[.063,.088,.02],x),v(M,[-.014,.025,.013],[.022,.026,.01],_),v($,[0,.065,.004],[.115,.018,.02],l);let ne=S(R,"brow",[F*.125,.227,.256]);Q.push(ne),v(ne,[0,0,0],[.106,.025,.021],l),v(R,[F*.212,-.032,.253],[.077,.035,.014],c);let le=v(R,[F*.045,-.092,.251],[.018,.018,.017],x);Y.push(le)}if(v(R,[0,.013,.263],[.046,.048,.04],o),v(R,[0,-.105,.25],[.078,.018,.018],x),e.hair_style!=="short"){let F=e.hair_style==="long";for(let $ of[-1,1])k([$*.285,.12,-.1],[.14,F?.7:.35,.28],$*-.025),k([$*.19,.07,-.262],[.23,F?.73:.31,.13],$*.04)}if(e.accessory==="glasses"){for(let F of[-1,1]){for(let $ of[.02,.195])v(R,[F*.133,$,.289],[.226,.022,.025],g);for(let $ of[.031,.235])v(R,[F*$,.108,.289],[.022,.178,.025],g);v(R,[F*.285,.158,.115],[.025,.025,.34],g)}v(R,[0,.13,.289],[.065,.022,.025],g)}let X=[],K=[],te=[],oe=[],ee=[],xe=[];for(let F of[-1,1]){let $=S(w,"shoulder",[F*.29,.38,0]);X.push($),v($,[0,-.105,0],[.17,.25,.23],p);let M=S($,"elbow",[0,-.23,0]);K.push(M),v(M,[0,-.095,0],[.145,.21,.18],p),v(M,[0,-.19,0],[.15,.06,.185],f);let ne=S(M,"hand",[0,-.245,.006]);te.push(ne),v(ne,[0,0,0],[.13,.13,.155],o),v(ne,[-F*.064,.015,.029],[.045,.075,.08],o);let le=S(E,"hip",[F*.125,0,0]);oe.push(le),v(le,[0,-.17,0],[.175,.35,.235],m);let ye=S(le,"knee",[0,-.37,0]);ee.push(ye),v(ye,[0,-.135,0],[.155,.29,.215],m),v(ye,[0,-.27,0],[.165,.04,.225],u);let Ne=S(ye,"ankle",[0,-.33,0]);xe.push(Ne),v(Ne,[0,.005,.05],[.2,.11,.31],g),v(Ne,[0,-.045,.056],[.21,.032,.32],_),v(Ne,[0,.064,.11],[.12,.015,.07],_)}let be=0,we=0,Se=0,se=2.1,de=-10,ge=1.3,Te=0,Re=0,ze=0,L=0,C=0,J=6.5,G=-20,T=0,N=37,B=!1,P=()=>(N=Math.imul(N,1664525)+1013904223>>>0,N/4294967296);function V(F,$,M,ne,le){let Fe=ne-M,Oe=$i(Math.hypot(Fe,$),.08,.37+.33-.001),ke=Math.acos($i((Oe*Oe-.37*.37-.33*.33)/(2*.37*.33),-1,1)),Pe=Math.atan2(-$,Fe)-Math.atan2(.33*Math.sin(ke),.37+.33*Math.cos(ke));oe[F].rotation.x=pt.lerp(Pe,-Math.PI/2,le),ee[F].rotation.x=pt.lerp(ke,Math.PI/2,le),xe[F].rotation.x=-(oe[F].rotation.x+ee[F].rotation.x)}function H(F,{distance:$=0,speed:M=0,sitting:ne=0,attention:le=0,gazeYaw:ye=0,gazePitch:Ne=0,turnRate:Fe=0,reduced:Oe=!1}={}){Oe||(be+=F),we+=$/(e.height||1)*Math.PI*2;let ke=(mt,Mt,ct)=>Oe?Mt:pt.damp(mt,Mt,ct,F);Se=Oe?0:ke(Se,$i(M/.85,0,1),9),!Oe&&be>=se&&(de=be,se=be+2.6+P()*3.6),!Oe&&be>=ge&&(Te=(P()-.5)*.85,Re=(P()-.5)*.16,ge=be+2.4+P()*3.8),!Oe&&be>=J&&(G=be,T=(T+1)%3,J=be+7+P()*5);let Pe=be-G,Ze=Oe?0:Jp(Pe,3.6,.8,1)*(1-Se),Qe=3.2-le,lt=Oe||le<=0?0:Jp(Qe,3.2,.3,.75),Ae=lt*ql(.12,.48,Qe),We=Oe?0:Math.sin(be*2.15)*.006,Ve=Oe?0:Math.sin(be*.68)*.018*(1-Se)*(1-ne),qt=ne*(1-lt),ln=qt*Ze*+(T===1),yt=qt*Ze*+(T===2),ht=(1-ne)*Ze*+(T===0)*(1-lt),ft=Oe?0:lt;C=ke(C,$i(ye*.45,-.72,.72)*ft+Math.sin(we)*.045*Se,5);let cn=Oe?0:pt.lerp(Te*(1-Se*.65),$i(ye-C,-1.15,1.15),ft);ze=ke(ze,cn,5),L=ke(L,Oe?.12*ne:(.16+Re)*qt-ln*.13+Ne*ft+Re*(1-ne)*(1-ft),5),E.position.set(Ve,.76-.048*Se*(1-ne)+Math.cos(we*2)*.01*Se*(1-ne),.09*ne),w.position.y=.12+We,w.rotation.set(.075*Se+.14*qt-.08*ht,C,-Ve*1.3+Math.sin(we)*.025*Se-$i(Fe,-2,2)*.025*Se),w.scale.y=1+We*.65,R.rotation.set(L,ze,(Oe?0:Math.sin(be*.71)*.025)+.095*lt-.075*ln),j.forEach((mt,Mt)=>{let ct=be-de-Mt*.012,An=Oe||ct<0||ct>.19?0:Math.sin(ct/.19*Math.PI);mt.scale.y=Math.max(.07,1-An*.97-lt*.12),O[Mt].position.x=Oe?0:$i(cn-ze,-.6,.6)*.034+ze*.014,O[Mt].position.y=Oe?0:-L*.04,Q[Mt].rotation.z=(Mt?-1:1)*(.035+lt*.13+ln*.1),Q[Mt].position.y=.227+lt*.018,Y[Mt].position.y=-.09+lt*.013});for(let mt=0;mt<2;mt++){let Mt=mt?1:-1,ct=((we/(Math.PI*2)+mt*.5)%1+1)%1,An=ct<.6,Cn=(ct-.6)/.4,kn=An?.3-ct/.6*.6:-.3+ql(0,1,Cn)*.6,oi=An?0:Math.sin(Cn*Math.PI)*.145;V(mt,kn*Se+Mt*.017*(1-Se),.061+oi*Se,E.position.y,ne),oe[mt].rotation.z=Ve*1.3*(1-ne);let Ct=Math.sin(we+mt*Math.PI+.25)*Se,hn=-1.37+((e.height||1)-1)*.9;X[mt].rotation.set(Ct*.48*(1-ne)+hn*qt-ht*1.15,-Mt*.07*qt,Mt*(.07+.06*Se+.45*ht)),K[mt].rotation.set(-.12-Math.max(0,-Ct)*.35-.55*qt-ht*.55,0,0),te[mt].rotation.set(-.08*qt,0,0)}X[0].rotation.x+=ln*.12,K[0].rotation.x-=ln*.72,X[1].rotation.y-=yt*.3,te[1].rotation.z+=yt*.12,X[1].rotation.x=pt.lerp(X[1].rotation.x,-.35,Ae),X[1].rotation.z=pt.lerp(X[1].rotation.z,1.05,Ae),K[1].rotation.z=Ae*(1.35+Math.sin(Qe*13)*.2),K[1].rotation.x=pt.lerp(K[1].rotation.x,-.3,Ae),te[1].rotation.z+=Ae*Math.sin(Qe*13-.45)*.2,z.forEach((mt,Mt)=>{mt.rotation.z=mt.userData.lean+(Oe?0:Math.sin(be*2.15-Mt*.7)*.012+Math.sin(we-.6)*Se*.035),mt.rotation.x=Oe?0:-L*.1+Math.sin(we-.8)*Se*.035+$i(Fe,-2,2)*(Mt%2?.025:-.025)});let Z=!Oe||!B;return B=Oe,Z}return{meshes:i,pose:H,dispose(){r.clear(),t.dispose(),n.forEach(F=>F.dispose())}}}function $p(r,e){let t=new Kt;r.add(t);let n=new Fn(2.4,2.4),i=new Jn({transparent:!0,alphaTest:.12,depthWrite:!0,side:En,toneMapped:!1}),s=new At(n,i);t.add(s),s.position.y=(e.foot_y-128)*2.4/256,s.userData.station="resident";let a=!1,o=!1,c=!1,l=null,h=0,p="idle",f=-1,m=1,u=new va().load(e.atlas,x=>{if(a){x.dispose();return}let _=document.createElement("canvas");_.width=x.image.width,_.height=x.image.height;let v=_.getContext("2d",{willReadFrequently:!0});v.drawImage(x.image,0,0),l=v.getImageData(0,0,_.width,_.height),o=!0,i.map=x,i.needsUpdate=!0,f=-1},void 0,()=>{c=!0});u.colorSpace=Ut,u.generateMipmaps=!1,u.minFilter=u.magFilter=Xt,u.repeat.set(1/e.columns,1/e.rows),s.visible=!1;let g=s.raycast.bind(s);return s.raycast=(x,_)=>{if(!o||f<0)return;let v=[];g(x,v);for(let S of v){let E=f*256+Math.min(255,Math.floor(S.uv.x*256)),w=e.actions[p].row*256+Math.min(255,Math.floor((1-S.uv.y)*256));l.data[(w*l.width+E)*4+3]>32&&_.push(S)}},{meshes:[s],get ready(){return o},get failed(){return c},pose(x,_){let v=_.sitting>.5?_.attention>.4?"wave_seated":_.reading?"read":"sit":_.attention>.4?"wave":_.speed>.04?"walk":"idle";v!==p&&(p=v,h=0),_.reduced||(h+=x);let S=e.actions[p],E=_.reduced?0:Math.floor(h*S.fps)%S.frames,w=t.rotation.y,R=m;t.rotation.y=_.gazeYaw||0,p==="walk"&&Math.abs(Math.sin(t.rotation.y))>.3&&(m=Math.sin(t.rotation.y)>0?-1:1),p!=="walk"&&(m=1),s.scale.x=m;let z=o&&(f!==E||u.offset.y!==1-(S.row+1)/e.rows);return z&&(f=E,u.offset.set(f/e.columns,1-(S.row+1)/e.rows),s.visible=!0),z||w!==t.rotation.y||R!==m},dispose(){a=!0,t.removeFromParent(),n.dispose(),i.dispose(),u.dispose(),l=null}}}function Qi(r,e,t=.25,n=[]){let{minX:i,maxX:s,minZ:a,maxZ:o}=e.bounds;return r.x-t<i||r.x+t>s||r.z-t<a||r.z+t>o?!1:!e.obstacles.some(c=>{if(n.includes(c.id))return!1;let l=r.x-c.x,h=r.z-c.z,p=Math.cos(c.angle)*l-Math.sin(c.angle)*h,f=Math.sin(c.angle)*l+Math.cos(c.angle)*h,m=Math.max(0,Math.abs(p)-c.halfX),u=Math.max(0,Math.abs(f)-c.halfZ);return m*m+u*u<=t*t})}function Ss(r,e,t,n=.25,i=[]){let s=Math.max(1,Math.ceil(Math.hypot(e.x-r.x,e.z-r.z)/.08));for(let a=0;a<=s;a++){let o=a/s;if(!Qi({x:r.x+(e.x-r.x)*o,z:r.z+(e.z-r.z)*o},t,n,i))return!1}return!0}function Yl(r,e,t=.25){let n=null,i=1/0;for(let s=e.bounds.minX+t;s<=e.bounds.maxX-t;s+=.28)for(let a=e.bounds.minZ+t;a<=e.bounds.maxZ-t;a+=.28){let o=(s-r.x)**2+(a-r.z)**2;o<i&&Qi({x:s,z:a},e,t)&&(n={x:s,z:a},i=o)}return n}function bu(r,e,t,n=.25){if(!Qi(r,t,n)||!Qi(e,t,n))return[];if(Ss(r,e,t,n))return[{...e}];let i=.28,s=t.bounds.minX+n,a=t.bounds.minZ+n,o=Math.floor((t.bounds.maxX-n-s)/i)+1,c=Math.floor((t.bounds.maxZ-n-a)/i)+1,l=S=>({x:s+S%o*i,z:a+Math.floor(S/o)*i}),h=Array.from({length:o*c},(S,E)=>Qi(l(E),t,n));function p(S){return h.map((w,R)=>({ok:w,key:R,distance:Math.hypot(l(R).x-S.x,l(R).z-S.z)})).filter(w=>w.ok).sort((w,R)=>w.distance-R.distance).find(w=>Ss(S,l(w.key),t,n))?.key}let f=p(r),m=p(e);if(f===void 0||m===void 0)return[];let u=[f],g=new Map([[f,null]]);for(let S=0;S<u.length&&!g.has(m);S++){let E=u[S],w=E%o,R=Math.floor(E/o),z=[w>0?E-1:-1,w+1<o?E+1:-1,R>0?E-o:-1,R+1<c?E+o:-1];for(let j of z)j>=0&&h[j]&&!g.has(j)&&Ss(l(E),l(j),t,n)&&(g.set(j,E),u.push(j))}if(!g.has(m))return[];let x=[e];for(let S=m;S!==null;S=g.get(S))x.unshift(l(S));let _=[],v=r;for(let S=0;S<x.length;){let E=S;for(;E+1<x.length&&Ss(v,x[E+1],t,n);)E++;_.push(x[E]),v=x[E],S=E+1}return _}function Qp(r,e,t){let n=new Kt;r.add(n),n.visible=!1;let i=null,s="",a="",o=null,c="",l={x:.8,z:2},h=[],p="idle",f="idle",m=4,u=0,g=1,x=.25,_=Math.PI,v=!1,S=0,E=null,w=0,R=0,z=0,j=null,O="";function Q(ee){let xe=g;i?.dispose(),g=ee.height||1,x=.25*g,n.scale.setScalar(g),i=o?.presentation?.mode==="paper"?$p(n,o.presentation.module):Kp(n,ee),g!==xe&&(c="")}function Y(){return{phase:f,goal:p,blocked:v,facing:n.rotation.y,position:{...l},target:h.at(-1)||null,visible:n.visible,label:o?v?E?.desk?"在空处等一会儿，书桌前暂时过不去":"书桌收起了，先在小屋里歇一会儿":f==="seated"?`在书桌旁翻看${o.work?"「"+o.work.title+"」":"手账"}`:f==="walking"?p==="desk"?"走向书桌":"在屋里走走":"在小屋里歇一会儿":"正在读取角色",ref:o?.work?.ref||null,appearance:s?JSON.parse(s):null,presentation:o?.presentation?.mode||"voxel",paperReady:i?.ready??null,paperFailed:i?.failed??!1}}function k(){let ee=Y(),xe=JSON.stringify([ee.phase,ee.goal,ee.blocked,ee.label,ee.visible]);xe!==O&&(O=xe,t?.(ee))}function X(){if(!(!o||!E)){if(v=!1,h=[],!Qi(l,E,x)&&(f==="seated"&&E.desk&&c||(l=Yl(l,E,x)),!l)){l={x:.8,z:2},n.visible=!1,v=!0;return}if(p==="desk"&&E.desk){let ee=E.desk.approach,xe=E.desk.seat;if(Ss(ee,xe,E,x,["desk"])&&(h=bu(l,ee,E,x),h.length)){h.push({x:xe.x,z:xe.z,dock:!0}),f="walking";return}v=!0}else p==="desk"&&(v=!0);f="idle",m=12,u=0}}function K(){let ee=e(),xe=JSON.stringify(ee);if(xe===c)return;let be=f==="seated";E=ee,c=xe,be&&(f="idle",l=Yl(l,E,x)||l),X()}function te(ee){let xe=o,be=ee?JSON.stringify(ee.appearance):"";if(o=ee,!ee){n.visible=!1,h=[],f="idle",p="idle",c="",R=0,z=0,j=null,u=0,k();return}let we=ee.presentation?.mode==="paper"?ee.presentation.id:"voxel";(be!==s||we!==a)&&(s=be,a=we,Q(ee.appearance)),p=ee.work?"desk":"idle";let Se=p!==(xe?.work?"desk":"idle")||JSON.stringify(xe?.work?.ref)!==JSON.stringify(ee.work?.ref);K(),Se&&(f==="seated"&&(l=E.desk?.approach||Yl(l,E,x)||l,f="idle"),X()),n.visible=!0,k()}function oe(ee,{paused:xe=!1,reduced:be=!1,viewer:we=null}={}){if(!o)return!1;let Se=n.visible;if(n.visible=!xe,xe)return Se;let se=Math.min(1,Math.max(0,ee));w-=se,we&&(j=we),R=be?0:Math.max(0,R-se);let de=0;if(w<=0&&(K(),w=.5),v&&!Qi(l,E,x)&&(n.visible=!1),!n.visible)return k(),Se;if(f==="idle"&&p!=="desk"&&!be&&(m-=se,m<=0)){let N=[{x:.8,z:2.5},{x:1.8,z:-.5},{x:-.6,z:.3},{x:2.6,z:3.6}],B=N[S++%N.length];h=bu(l,B,E,x),h.length?f="walking":m=8}if(f==="walking"){if(be)l={...h.at(-1)},h=[];else{let N=0,B=l;for(let H of h)N+=Math.hypot(H.x-B.x,H.z-B.z),B=H;let P=R>.4?0:.85*Math.min(1,.22+N/.65),V=P*se+(z-P)*(1-Math.exp(-6*se))/6;for(z=pt.damp(z,P,6,se);h.length&&V>0;){let H=h[0],F=Math.hypot(H.x-l.x,H.z-l.z);_=Math.atan2(H.x-l.x,H.z-l.z),F<=V?(l={x:H.x,z:H.z},h.shift(),V-=F,de+=F):(l.x+=(H.x-l.x)/F*V,l.z+=(H.z-l.z)/F*V,de+=V,V=0)}}h.length||(f=p==="desk"&&E.desk?"seated":"idle",m=14)}let ge=f==="seated",Te=u;(f!=="walking"||be)&&(z=0),u=be?Number(ge):pt.damp(u,Number(ge),6,se),ge&&(_=E.desk.angle);let Re=j?Math.atan2(j.x-l.x,j.z-l.z):_,ze=R>.4&&!ge?Re:_,C=Math.atan2(Math.sin(ze-n.rotation.y),Math.cos(ze-n.rotation.y))*(be?1:1-Math.exp(-5*se));n.rotation.y+=C,n.position.set(l.x,E.desk?(E.desk.seat.y-.76*g)*u:0,l.z);let J=Math.atan2(Math.sin(Re-n.rotation.y),Math.cos(Re-n.rotation.y)),G=j?-Math.atan2(j.y-(n.position.y+1.55*g),Math.hypot(j.x-l.x,j.z-l.z)):0,T=i.pose(se,{distance:de,speed:se>0?de/se:z,sitting:u,attention:R,gazeYaw:J,gazePitch:pt.clamp(G,-.3,.3),turnRate:se>0?C/se:0,reduced:be,reading:!!o.work});return k(),Se!==n.visible||de>0||T||Te!==u}return{setContext:te,tick:oe,getState:Y,get meshes(){return i?.meshes||[]},greet(ee){ee&&(j={x:ee.x,y:ee.y,z:ee.z}),R=3.2},dispose(){n.removeFromParent(),i?.dispose()}}}function ef(r){let e=new Kt;e.name="preview-courtyard",r.add(e);let t=new Nn(1,1,1),n=new Sn({roughness:1}),i=[],s=-.735,a=(P,V,H=0)=>{let F=Math.sin(P*127.1+V*311.7+H*73.9)*43758.5453;return F-Math.floor(F)},o=(P,V,H,F,$,M,ne,le=0,ye=!1)=>i.push({x:P,y:V,z:H,w:F,h:$,d:M,tint:ne,angle:le,snowCap:ye}),c=(P,V,H=0)=>P>-6.1-H&&P<6.1+H&&V>-4.7-H&&V<5.9+H,l=[[7.25,1.25],[8.6,1.25],[9.05,3.5],[8.6,6.4],[9.7,9.1],[13,12.5],[18,15]];function h(P,V){let H=1/0;for(let F=1;F<l.length;F++){let[$,M]=l[F-1],[ne,le]=l[F],ye=ne-$,Ne=le-M,Fe=Math.max(0,Math.min(1,((P-$)*ye+(V-M)*Ne)/(ye*ye+Ne*Ne)));H=Math.min(H,Math.hypot(P-$-ye*Fe,V-M-Ne*Fe))}return H}let p=document.createElement("canvas");p.width=p.height=512;let f=p.getContext("2d"),m=new He,u=new He("#687e53"),g=new He("#8fa375");for(let P=0;P<512;P+=4)for(let V=0;V<512;V+=4){let H=P/512*60,F=V/512*60,$=.45+Math.sin(H*.23+F*.17)*.19+Math.cos(F*.28-H*.11)*.15+a(H,F)*.06;m.copy(u).lerp(g,$),f.fillStyle="#"+m.getHexString(),f.fillRect(P,V,4,4)}let x=new Ii(p);x.colorSpace=Ut,x.wrapS=x.wrapT=hr,x.repeat.set(3,3);let _=document.createElement("canvas");_.width=_.height=256;let v=_.getContext("2d"),S=new He;for(let P=0;P<256;P+=4)for(let V=0;V<256;V+=4)S.set("#d8e3e8").lerp(new He("#f6f9f7"),.4+a(P,V)*.6),v.fillStyle="#"+S.getHexString(),v.fillRect(P,V,4,4);let E=new Ii(_);E.colorSpace=Ut,E.wrapS=E.wrapT=hr,E.repeat.set(3,3);let w=new Fn(180,180),R=new Sn({map:x,roughness:1}),z=new At(w,R);z.rotation.x=-Math.PI/2,z.position.y=s,z.receiveShadow=!0,e.add(z);for(let P=-6.3;P<=6.35;P+=.5)for(let V of[-4.88,6.06])o(P,s+.022,V,.48,.085,.43,a(P,V)>.5?"#c2c1a8":"#b4b6a0");for(let P=-4.4;P<=5.8;P+=.5)for(let V of[-6.32,6.32])V>0&&P>-.3&&P<2.75||o(V,s+.022,P,.43,.085,.48,"#bbbba4");o(7.32,-.632,1.25,.62,.19,2.6,"#c8c8b2",0,!0);for(let P=7.2;P<19;P+=.46)for(let V=-.2;V<17;V+=.46){if(h(P,V)>.99||c(P,V,.1))continue;let H=["#c7c3a9","#d3ceb7","#c4c2aa","#dad3b9"];o(P,s+.023,V,.445,.068,.445,H[Math.floor(a(P,V,1)*H.length)],0,a(P,V)>.4)}function j(P,V,H=1,F=!1){let $=a(P,V)>.5?"#6f8c66":"#8ca276";for(let M=0;M<3;M++){let ne=P+(M-1)*.095*H,le=(.17+a(P,V,M)*.14)*H;o(ne,s+le/2,V+M%2*.08,.055*H,le,.05*H,$,(M-1)*.27),F&&M!==1&&o(ne,s+le,V+M%2*.08,.12*H,.075*H,.12*H,a(P,V,4)>.55?"#ead1a0":"#e2bcb9")}}for(let P=0;P<175;P++){let V=a(P,1)*34-17,H=a(P,2)*32-15;c(V,H,.6)||h(V,H)<1.18||j(V,H,.65+a(P,3)*.7,P%6===0)}function O(P,V,H){for(let F=-2;F<=2;F++)for(let $=-1;$<=1;$++){if(Math.abs(F)===2&&Math.abs($)===1)continue;let M=(.27+a(F+P,$+V)*.22)*H;o(P+F*.2*H,s+M/2,V+$*.22*H,.24*H,M,.25*H,["#7c966d","#90a77d","#a5b38a"][Math.floor(a(F,$,P)*3)],0,!0)}}for(let[P,V,H]of[[-7.5,4.1,1.3],[-7.8,1.5,1.4],[2.8,7.4,1.1],[-3.8,7.2,1.15],[10.5,-.5,1.5],[6.8,-5.8,1.4],[-1.3,-6.7,1.5]])O(P,V,H);function Q(P,V,H,F){o(P,s+1.38*H,V,.24*H,2.76*H,.24*H,"#8a8168"),o(P+.3*H,s+1.93*H,V,.67*H,.18*H,.18*H,"#8a8168",-.28);let $=["#567b53","#6d8c59","#7e9a69","#4e704d","#94a777"];for(let M=-3;M<=3;M++)for(let ne=-3;ne<=3;ne++)for(let le=0;le<5;le++){if(M*M+ne*ne+(le-2)*(le-2)*1.35>11.2||a(M+F,ne,le)<.08)continue;let ye=.37*H;o(P+M*ye,s+(2.15+le*.33)*H,V+ne*ye,ye*1.02,.35*H,ye*1.02,$[Math.floor(a(M,ne+F,le)*$.length)],0,!0)}}for(let[P,V,H,F]of[[-8.8,-4.7,1.2,1],[-5.3,-9.2,1.25,2],[4.1,-9.4,1.35,3],[9.1,-5.4,1.05,4],[-13.5,2.5,1.15,5],[-15,-13,1.8,6],[0,-18,1.8,7],[12.5,-15.5,1.7,8],[-20,-2,1.5,9],[21,-7,1.8,10]])Q(P,V,H,F);for(let P=0;P<12;P++){let V=-10+P*1.48;if(o(V,s+.54,-7,.105,1.08,.105,"#bcb9a0"),P<11)for(let H of[.36,.77])o(V+.74,s+H,-7,1.47,.095,.085,"#cecab1",0,H>.5)}let Y=new ri(t,n,i.length),k=new Ke,X=new D,K=new kt,te=new D,oe=new He;i.forEach((P,V)=>{X.set(P.x,P.y,P.z),te.set(P.w,P.h,P.d),K.setFromAxisAngle(Ft.DEFAULT_UP,P.angle),Y.setMatrixAt(V,k.compose(X,K,te)),Y.setColorAt(V,oe.set(P.tint))}),Y.castShadow=!0,Y.receiveShadow=!0,Y.computeBoundingSphere(),e.add(Y);let ee=new Map;i.filter(P=>P.snowCap).forEach(P=>{let V=`${P.x.toFixed(2)}:${P.z.toFixed(2)}`;(!ee.has(V)||ee.get(V).y<P.y)&&ee.set(V,P)});let xe=new Sn({color:"#edf4f6",roughness:.96}),be=new ri(t,xe,ee.size);[...ee.values()].forEach((P,V)=>{X.set(P.x,P.y+P.h/2+.026,P.z),te.set(P.w*1.01,.064,P.d*1.01),K.identity(),be.setMatrixAt(V,k.compose(X,K,te))}),be.receiveShadow=!0,be.computeBoundingSphere(),e.add(be);let we=new Sn({color:"#9fbcc3",roughness:.18,metalness:.12,transparent:!0,opacity:.58}),Se=[[8.7,6.5,.8],[10.9,10.6,1.1],[7.7,3.2,.7],[-8.2,6.9,1.2],[3.8,8.8,.7],[-4.5,9.8,.9],[11.8,-.7,1.1],[-8.7,-.9,.8],[13,7.6,.9],[5.2,-6.2,.8]],se=new ri(t,we,Se.length*3);Se.forEach(([P,V,H],F)=>{for(let $=0;$<3;$++)X.set(P+($-1)*.23*H,s+(h(P,V)<1.1?.061:.013),V+$%2*.17),te.set(($===1?1.25:.75)*H,.01,.42*H),K.identity(),se.setMatrixAt(F*3+$,k.compose(X,K,te))}),se.computeBoundingSphere(),e.add(se);let de=new Sn({color:"#edf3ef",roughness:1,transparent:!0,opacity:.66,depthWrite:!1}),ge=new ri(t,de,15);[[-19,8,-27],[-3,11,-32],[19,10,-25]].forEach(([P,V,H],F)=>{for(let $=0;$<5;$++)X.set(P+($-2)*1.6,V+$%2*.5,H+$%3*.35),te.set(2.8,.55+a(F,$)*.55,1.5),K.identity(),ge.setMatrixAt(F*5+$,k.compose(X,K,te))}),ge.computeBoundingSphere(),e.add(ge);let Te=new Jn({color:"#d6e7f1",transparent:!0,opacity:.6,depthWrite:!1}),Re=new ri(t,Te,640);Re.instanceMatrix.setUsage($h),Re.frustumCulled=!1,e.add(Re);let ze=new D(0,0,1),L=Array.from({length:640},(P,V)=>{let H,F,$=0;do H=a(V,11,$)*40-19,F=a(V,12,$++)*40-17;while(c(H,F,.8));return{x:H,z:F,phase:a(V,13),size:.72+a(V,14)*.55}}),C="clear",J="day",G=0,T=0;function N(P){let V=C==="snow",H=V?.072:C==="storm"?.94:.66;for(let F=0;F<T;F++){let $=L[F],M=($.phase+P*H)%1;X.set($.x+(V?Math.sin(P*.8+F)*.18:0),s+.06+(1-M)*10.5,$.z),V?(te.setScalar(.066*$.size),K.setFromAxisAngle(Ft.DEFAULT_UP,P*.22+F)):(te.set(.017,(C==="storm"?.52:.35)*$.size,.017),K.setFromAxisAngle(ze,-.12)),Re.setMatrixAt(F,k.compose(X,K,te))}Re.instanceMatrix.needsUpdate=!0}function B(P,V){C=P,J=V;let H=C==="snow",F=["rain","storm"].includes(C),$=J==="night",M=["cloudy","rain","storm","snow","mist"].includes(C);R.map=H?E:x,R.needsUpdate=!0,R.color.set(F?"#a2b9bc":C==="mist"?"#d7e2db":"#ffffff"),R.roughness=F?.66:1,n.color.set(F?"#b5c5ca":"#ffffff"),n.roughness=F?.73:1,se.visible=F,be.visible=H,ge.visible=M,de.color.set($?"#748799":C==="storm"?"#8c9da7":C==="rain"?"#becdd2":"#e5eded"),de.opacity=C==="mist"?.33:.66,T=H?230:C==="storm"?640:F?430:0,Re.visible=T>0,Re.count=T,Te.color.set(H?"#ffffff":$?"#b1c5df":"#d6e7f1"),Te.opacity=H?.9:C==="storm"?.63:.5,N(G)}return B("clear","day"),{setWeather:B,tick(P){return T?(G=P,N(P),!0):!1},getState(){return{condition:C,light:J,particles:T,elapsed:G,snowCover:be.visible,wetGround:se.visible,clouds:ge.visible}},dispose(){e.removeFromParent(),[Y,be,se,ge,Re].forEach(P=>P.dispose()),[t,n,x,E,w,R,xe,we,de,Te].forEach(P=>P.dispose())}}}window.PrivateCompanionHomeRoom3D=(()=>{let r=new WeakMap,e={calendar:{label:"生活日历",target:[-5.2,2.4,-2.85],position:[3.1,5.4,5.1],fov:38},desk:{label:"日记与便签",target:[-3.7,1.35,-3.25],position:[2.3,6.4,4.5],fov:36},shelf:{label:"故事书架",target:[-4.8,1.9,-.3],position:[5.2,4.8,5.8],fov:37},wardrobe:{label:"衣柜 · 房间陈设",target:[-.25,1.9,-3.2],position:[5.9,4.6,6.3],fov:35},bed:{label:"睡眠与梦境",target:[3.8,.9,-2.1],position:[9.4,6.1,6.3],fov:36},radio:{label:"见闻电台",target:[-4.8,1,3],position:[3.5,3.7,9.1],fov:36},garden:{label:"慢慢成长",target:[4.35,.9,2.95],position:[9.9,4.3,10.5],fov:34},game:{label:"游戏伴侣"},image:{label:"生图工作室"},together:{label:"在一起"},art:{label:"相框与照片"}},t={desk:"窗边书桌",shelf:"故事书架",wardrobe:"衣柜",bed:"床与床头柜",radio:"电台边柜",garden:"阶梯花架",lounge:"阅读扶手椅",readingLamp:"落地灯",stool:"茶几",rug:"编织地毯",game:"游戏伴侣摆件",image:"生图摆件",together:"在一起电话",calendar:"生活挂历",art:"植物装饰画"},n={floor:"地面","back-wall":"后墙","left-wall":"左墙"},i=["back-wall","left-wall"],s={game:{chess:{label:"双人棋桌",surfaces:["floor"]},arcade:{label:"复古街机",surfaces:["floor"]},console:{label:"游戏挂屏",surfaces:i}},image:{camera:{label:"三脚架相机",surfaces:["floor"]},instant:{label:"拍立得展台",surfaces:["floor"]},gallery:{label:"照片挂架",surfaces:i}},together:{telephone:{label:"转盘电话柜",surfaces:["floor"]},wallPhone:{label:"壁挂电话",surfaces:i}},calendar:{calendar:{label:"便签挂历",surfaces:i}},art:{botanical:{label:"植物装饰画",surfaces:i}}},a={minX:-5.62,maxX:5.7,minZ:-4.2,maxZ:5.46,wallTop:4.65,lowWallTop:1.38,lowWallStart:1.62},o={oak:"原木日常",cream:"奶油轻居",ink:"墨蓝复古",rattan:"日式藤编",walnut:"胡桃中古",loft:"工业拼搭",blossom:"樱色软装",nordic:"北欧几何"},c=["rattan","walnut","loft","blossom","nordic"],l={oak:{note:"温润木色，保留熟悉的生活细节。",models:["窗边书桌","开放书格","竖纹双门柜","木栅床头","格栅边柜","阶梯花架","木扶手阅读椅","层叠布罩灯","编织矮茶几","椭圆织毯"]},cream:{note:"浅色饰面和饱满轮廓，让角落更轻柔。",models:["浅木围板桌","错层书格","素面分格柜","三片软包床","浅色包边柜","方柱花架","宽背软椅","方筒布罩灯","奶油方茶几","奶油条纹毯"]},ink:{note:"墨蓝与暖金搭配，点缀复古细节。",models:["金属脚书桌","宽檐书架","金线双门柜","高低栅格床","金边收音柜","细脚花架","高背阅读椅","锥形层叠灯","金脚矮茶几","墨蓝织纹毯"]},rattan:{note:"藤编格纹、细木框与竹节，带一点庭院气息。",models:["藤编抽屉桌","竹格书架","藤芯双门柜","藤编屏风床","藤编唱片柜","竹梯花架","藤背休闲椅","竹编宫灯","藤篮茶几","流苏草编毯"]},walnut:{note:"深胡桃木、收分轮廓与黄铜细节。",models:["中古抽屉桌","胡桃分区书柜","雕线胡桃柜","翼形木床头","中古唱片柜","胡桃陈列架","翼背扶手椅","琥珀蘑菇灯","椭圆双层茶几","复古菱格毯"]},loft:{note:"深色钢架、铆钉和交叉撑杆，结构清晰利落。",models:["钢架工作台","桁架书架","铆钉储物柜","钢管框架床","铆钉器材柜","钢架植物台","悬臂框架椅","折臂工作灯","框架工作茶几","拼色方格毯"]},blossom:{note:"樱粉软包和花瓣轮廓，配细腻的浅色木脚。",models:["樱色梳写桌","花瓣顶书架","花窗双门柜","花瓣软包床","樱色小边柜","花瓣托盘架","花瓣靠背椅","花苞落地灯","花瓣矮茶几","花朵簇绒毯"]},nordic:{note:"白蜡木、鼠尾草绿与几何留白，轻巧通透。",models:["A 字支架桌","几何分格架","拼色平板柜","三角拼板床","拼色几何柜","A 字花架","曲折木框椅","三脚折纸灯","三脚圆茶几","山形几何毯"]}},h={rattan:{wood:"#c6a16a",edge:"#876740",accent:"#91a17a",dark:"#596d4d",light:"#d6c59c",fabric:"#cebd92",rose:"#bb8765"},walnut:{wood:"#76503a",edge:"#48392f",accent:"#986d46",dark:"#543f34",light:"#bc996e",fabric:"#ad845f",rose:"#ba754f"},loft:{wood:"#b49a79",edge:"#38474b",accent:"#72888a",dark:"#3d4e53",light:"#b9c4bf",fabric:"#879b98",rose:"#c68a50"},blossom:{wood:"#e1c6ad",edge:"#a48a7c",accent:"#d99fac",dark:"#9c6c80",light:"#f0c6ca",fabric:"#e2b1bc",rose:"#b66f89"},nordic:{wood:"#d0b589",edge:"#786e58",accent:"#91a899",dark:"#506b63",light:"#e4eadb",fabric:"#adc2b5",rose:"#c29569"}},p={classic:{label:"原木小屋",materials:"木地板 · 绿墙裙 · 布帘窗",note:"熟悉的木色与窗边光线，保留原来的小屋。"},washitsu:{label:"日式和室",materials:"榻榻米 · 木格窗 · 纸面门",note:"草席编纹、细木格与柔和纸窗，留一间安静的和室。"},loft:{label:"红砖阁楼",materials:"红砖墙 · 水泥地 · 钢窗",note:"错缝砖墙、混凝土地面和黑色钢架，带一点旧工坊的质感。"},french:{label:"法式奶油",materials:"线板墙 · 拼花地板 · 拱窗",note:"奶油白线板与拱形窗饰，配一扇带雕线的浅色房门。"},coastal:{label:"海边白屋",materials:"白灰墙 · 蓝白砖 · 百叶窗",note:"白灰墙、蓝色窗套与门板，地面围一圈蓝白花砖。"},cabin:{label:"林间木屋",materials:"横木墙 · 宽木板 · 外露木梁",note:"横向木墙、宽板地面和粗木窗梁，像林间的小木屋。"}},f={washitsu:{wall:"#e4dfc9",lower:"#d2c9aa",wood:"#a88855",edge:"#635b3e",accent:"#788369",floor:["#b7b185","#c9c39a","#c1bb90"]},loft:{wall:"#b87961",lower:"#a96e57",wood:"#796955",edge:"#3e4b4d",accent:"#617a7b",floor:["#a7aaa1","#b5b7ad","#aeb2a7"]},french:{wall:"#f2e9da",lower:"#e4d8c2",wood:"#d9c7a9",edge:"#b59b77",accent:"#b8b89e",floor:["#bf9870","#d1b18b","#c8a67f"]},coastal:{wall:"#f0f0df",lower:"#e3e9dd",wood:"#5e8d9b",edge:"#3d6f84",accent:"#74a0ad",floor:["#e5dfc7","#f0e9d6","#dcd5bd"]},cabin:{wall:"#b28b60",lower:"#ac8056",wood:"#7e5c3f",edge:"#543f30",accent:"#799079",floor:["#b88d5f","#c6a173","#ac8257"]}},m=[{label:"01 / 越过屋檐 · 俯冲入室",points:[[0,18,2],[8,12,10],[6,5,9],[3,2.3,6]],target:[0,1,0],fovs:[46,50,58,64],bank:-.075,seconds:8},{label:"02 / 桌沿掠影 · 推拉变焦",anchor:"desk",points:[[2.5,2.1,4.1],[1.2,1.8,2.8],[-.4,2.7,2.9],[-1,4.6,4.8]],target:[0,1.4,.1],fovs:[50,67,54,36],bank:.045,seconds:8},{label:"03 / 书脊长廊 · 横移掠过",anchor:"shelf",points:[[-2,2.5,4.3],[0,1.85,3.6],[2.3,2.7,4]],target:[0,1.8,.1],fovs:[55,62,49],bank:-.035,seconds:7},{label:"04 / 床边低语 · 半环绕升起",anchor:"bed",points:[[-.7,1.8,4.5],[-1.8,2.4,4.1],[-2.8,3.5,2.8],[-1.6,6,1.4]],target:[0,.9,0],fovs:[59,57,50,43],bank:.075,seconds:8},{label:"05 / 叶间光线 · 低位环绕",anchor:"garden",points:[[2.4,1.7,3],[0,2.1,3.1],[-2.1,1.7,2.2],[-2.4,3.8,.6]],target:[0,1,0],fovs:[55,63,58,46],bank:-.06,seconds:7},{label:"06 / 一间生活 · 螺旋拉远",points:[[0,8,7],[-1,16,9],[12.9,12.2,15.1]],target:[0,1.15,0],fovs:[48,44,38],bank:.06,seconds:7}],u={wood:"#a9764f",edge:"#77553f",oak:"#d0a574",cream:"#f5ecd9",paper:"#fff6df",teal:"#507e7a",tealLight:"#7bada1",tealDark:"#365f5a",rose:"#c47465",mustard:"#d6ad55",navy:"#435369",green:"#657c45",leaf:"#91a768",dark:"#303e3d",brass:"#d7b66c"};function g(x,_={}){let v=structuredClone(e),S={...t},E=structuredClone(s),w=new Map,R={},z=new Set,j=new Set,O=null,Q=new $s,Y=new Jt(38,1,.1,110),k=new Hl({antialias:!0,powerPreference:"high-performance"});k.setPixelRatio(Math.min(window.devicePixelRatio||1,1.65)),k.shadowMap.enabled=!0,k.shadowMap.type=bl,k.shadowMap.autoUpdate=!1,k.shadowMap.needsUpdate=!0,k.outputColorSpace=Ut,k.toneMapping=Ea,k.toneMappingExposure=1.18,x.replaceChildren(k.domElement),k.domElement.setAttribute("aria-label","体素小屋。可拖动旋转、滚轮缩放，也可使用下方家具按钮浏览内容。");let X=new Xl(Y,k.domElement);X.enableDamping=!0,X.dampingFactor=.085,X.enablePan=!1,X.minDistance=1.5,X.maxDistance=36,X.minPolarAngle=.06,X.maxPolarAngle=Math.PI*.49,X.minAzimuthAngle=-.17,X.maxAzimuthAngle=Math.PI*.59;let K=new Nn(1,1,1),te=new Sn({roughness:.94,metalness:.02}),oe=new Zt(new D(0,-1,0),-1.05),ee=k.clippingPlanes.slice(),xe=k.shadowMap.enabled,be=1,we=new Map,Se=[],se={},de=[],ge={},Te={},Re={},ze={},L=new Ke,C=new kt,J=new D,G=new D,T=new He,N=0;function B(d,y=0,I=0,b=0,A=0,re=Q){let q=new Kt;return q.position.set(y,I,b),q.rotation.y=A,q.userData.station=d,re.add(q),q}function P(d){let y=d.userData.station,I=B(y,0,0,0,0,d);return(Te[y]||=[]).push(I),I}let V=B(""),H=B(""),F=B(""),$=B("");function M(d,y,I,b,A,re,q,ae=u.oak,me=0,W=0){we.has(d)||we.set(d,[]),we.get(d).push({x:y,y:I,z:b,w:A,h:re,d:q,tint:ae,ry:me,rz:W}),N++}function ne(d,y,I,b,A,re){M(d,y,I,b,A,A,A,re)}function le(d,y,I,b,A=1){for(let re=0;re<4;re++)M(d,y,I+(.08+re*.13)*A,b,(.36+re*.055)*A,.13*A,(.36+re*.055)*A,re===3?u.cream:u.rose);M(d,y,I+.48*A,b,.37*A,.055*A,.37*A,u.edge);for(let re=0;re<7;re++){let q=re*2.4,ae=.72+re%3*.22;for(let me=0;me<5;me++){let W=me/4;ne(d,y+Math.cos(q)*W*.34*A,I+(.48+ae*W*.64)*A,b+Math.sin(q)*W*.34*A,.105*A,u.tealDark)}for(let me=-1;me<=1;me++)for(let W=0;W<3;W++)ne(d,y+(Math.cos(q)*.34+me*.1)*A,I+(.48+ae*.64+W*.085)*A,b+(Math.sin(q)*.34+W*.025)*A,.13*A,(re+W)%2?u.green:u.leaf)}}function ye(d,y,I,b,A,re=.64,q=.16){M(d,y,I+re/2,b,q,re,.43,A),M(d,y,I+re/2,b+.221,q*.62,.024,.012,u.brass),M(d,y,I+re-.09,b+.221,q*.72,.022,.012,u.paper),M(d,y,I+re-.015,b,q*.7,.018,.38,u.paper)}function Ne(d,y,I,b,A=1){M(d,y,I+.06*A,b,.48*A,.12*A,.48*A,u.brass),M(d,y,I+.4*A,b,.075*A,.65*A,.075*A,u.edge);for(let re=0;re<5;re++){let q=(.68-re*.075)*A;M(d,y,I+(.6+re*.085)*A,b,q,.087*A,q,re%2?"#e8ca87":"#f9dc9f")}}M(V,0,-.43,.6,12.05,.54,10.45,u.tealDark),M(V,0,-.14,.6,12.14,.13,10.52,u.edge);for(let d=0;d<34;d++)for(let y=0;y<9;y++){let I=-5.98+y*1.51+(d%2?-.74:0),b=Math.max(-5.98,I),A=Math.min(5.98,I+1.49);if(A<=b)continue;let re=-4.43+d*.3,q=["#cda374","#d6af82","#c49b6d","#dfbb90","#d1a97a"][(d*3+y)%5];M(H,(b+A)/2,-.043,re,A-b,.065,.286,q);for(let ae=0;ae<3;ae++)M(H,(b+A)/2+(ae-1)*.07,-.008,re+(ae-1)*.063,(A-b)*.68,.003,.008,d%2?"#bb9365":"#c59e72")}for(let d=-5.7;d<5.9;d+=.3)for(let y=.16;y<4.8;y+=.3)d>-5.2&&d<-1.95&&y>1.6&&y<4.25||M(F,d,y,-4.47,.294,.294,.22,y<1.45?"#7d9b90":["#e6dfca","#eae3d0","#e2dbc7"][Math.abs(Math.round(d*10+y*10))%3]);for(let d=-4.4;d<5.7;d+=.3)for(let y=.15;y<(d>1.7?1.48:4.8);y+=.3)M($,-5.9,y,d,.22,.293,.294,y<1.5?"#76948c":"#e5dfcd");for(let d of[.18,1.48,4.8])M(F,0,d,-4.29,12,.1,.13,d===4.8?u.cream:u.tealDark);for(let d of[.18,1.48])M($,-5.72,d,.6,.13,.1,10.2,u.tealDark);M($,-5.88,4.8,-1.35,.33,.12,6.1,u.cream);for(let d=-5.5;d<5.8;d+=.55)M(F,d,.83,-4.27,.05,1.16,.08,"#adc0aa");for(let d=-4.2;d<5.7;d+=.55)M($,-5.74,.83,d,.08,1.16,.05,"#adc0aa");let Fe=B("",-3.6,2.94,-4.45);M(Fe,0,0,-.16,3.25,2.72,.04,"#9ecacc");for(let d=0;d<28;d++){let y=.23+(Math.sin(d*.41)+1)*.32;M(Fe,-1.55+d*.115,-1.22+y/2,-.1,.116,y,.05,"#709c8e"),d%2&&M(Fe,-1.55+d*.115,-1.25+y/4,-.06,.117,y/2,.04,"#547f73")}let Oe=B("",0,0,0,0,Fe);for(let d of[-1.65,0,1.65])M(Oe,d,0,.06,.11,2.83,.23,u.cream);for(let d of[-1.39,0,1.39])M(Oe,0,d,.07,3.43,.11,.24,u.cream);M(Oe,0,-1.48,.29,3.7,.14,.68,u.oak);for(let d of[-1,1])for(let y=0;y<6;y++)M(Oe,d*(1.46+y*.085),-.02,.3+y%2*.065,.095,3.1-y*.025,.12,y%2?"#ecd8b8":"#fff0d0");le(Fe,-1.05,-1.4,.33,.48);let ke=se.desk=B("desk",-3.7,0,-3.45),Pe=P(ke);M(ke,0,1.22,0,3.3,.18,1.3,u.oak);for(let d=0;d<11;d++)M(ke,-1.49+d*.298,1.318,0,.285,.017,1.27,d%3?"#d8b68b":"#c9a779");for(let d of[-1.42,1.42])for(let y of[-.46,.46])M(Pe,d,.58,y,.14,1.16,.14,u.edge);for(let d=0;d<3;d++)M(Pe,1.03,.43+d*.25,.02,.68,.235,1,u.teal),M(Pe,1.03,.43+d*.25,.55,.19,.05,.06,u.brass);for(let d of[-1,1]){M(ke,d*.3-.12,1.365,.07,.59,.055,.76,u.rose,0,d*.045);for(let y=0;y<4;y++)M(ke,d*.29-.12,1.397+y*.009,.07,.54,.008,.7,u.paper,0,d*.035);for(let y=0;y<6;y++)M(ke,d*.29-.12,1.442,-.17+y*.073,.38,.007,.012,"#acb3a0")}M(ke,.5,1.37,.28,.04,.045,.57,u.navy,-.26),Ne(ke,-1.13,1.32,-.24,.76),M(ke,.77,1.49,-.36,.26,.34,.26,u.cream);for(let d=0;d<4;d++)M(ke,.69+d*.05,1.76,-.37,.027,.41,.03,d%2?u.rose:u.navy,0,(d-1)*.1);for(let d=0;d<3;d++)M(ke,.34+d*.02,1.35+d*.028,-.42,.3,.023,.23,[u.mustard,u.rose,u.tealLight][d]);let Ze=B("desk",-.4,0,1.27,-.18,ke);M(Ze,0,.7,0,.87,.17,.82,u.teal);for(let d of[-.34,.34])for(let y of[-.29,.29])M(Ze,d,.34,y,.1,.68,.1,u.edge);for(let d=0;d<5;d++)M(Ze,-.35+d*.176,1.18,.33,.12,.86,.12,u.teal);M(Ze,0,1.59,.33,.9,.13,.16,u.tealDark);let Qe=se.calendar=B("calendar",-5.69,2.84,-2.98,Math.PI/2);M(Qe,0,0,0,1.9,1.72,.09,u.edge),M(Qe,0,0,.06,1.72,1.54,.08,"#b59265"),M(Qe,-.25,.11,.12,1,1.23,.07,u.paper),M(Qe,-.25,.63,.17,1.01,.23,.05,u.rose);for(let d=0;d<7;d++)for(let y=0;y<4;y++)M(Qe,-.65+d*.128,.34-y*.18,.17,.065,.064,.012,y===1&&d===3?u.rose:"#b6b5a2");for(let d=0;d<3;d++)M(Qe,.58,.46-d*.43,.16,.4,.32,.03,[u.mustard,u.tealLight,u.cream][d],0,(d-1)*.08),ne(Qe,.58,.56-d*.43,.19,.043,u.rose);let lt=se.shelf=B("shelf",-5.19,0,-.1,Math.PI/2),Ae=P(lt);M(Ae,0,1.74,-.32,2.68,3.45,.09,u.edge);for(let d of[-1.37,1.37])M(Ae,d,1.77,0,.16,3.54,.78,u.oak);for(let d=0;d<5;d++)if(M(lt,0,.18+d*.84,0,2.9,.12,.85,u.oak),d!==4){for(let y=0;y<(d===2?6:11);y++)ye(lt,-1.17+y*.228,.245+d*.84,.035,[u.teal,u.rose,u.navy,u.mustard,u.cream][(y+d*2)%5],.49+(y*7+d)%4*.065,.15+y%2*.025);if(d===2){for(let y=0;y<3;y++)M(lt,.7,1.99+y*.12,.1,.65,.1,.42,y%2?u.tealLight:u.cream);M(lt,.7,2.42,.1,.35,.13,.3,u.brass)}}le(lt,.87,3.6,0,.68);for(let d=0;d<3;d++)M(lt,-.67,3.67+d*.12,0,.66,.1,.47,[u.teal,u.paper,u.rose][d]);let We=se.wardrobe=B("wardrobe",-.25,0,-3.63);M(We,0,1.68,-.39,2.55,3.25,.1,u.tealDark);for(let d of[-1.32,1.32])M(We,d,1.7,0,.16,3.4,1.05,u.teal);for(let d of[.2,3.4])M(We,0,d,0,2.85,.18,1.15,u.teal);M(We,0,2.83,0,2.53,.06,.06,u.brass);for(let d=0;d<6;d++){let y=-.91+d*.36;M(We,y,2.67,0,.04,.28,.04,u.brass);for(let I=0;I<9;I++)M(We,y,2.48-I*.125,.04,.21+(I<2?.1:I*.009),.122,.51,[u.rose,u.cream,u.navy,u.mustard,u.tealLight,u.paper][d])}for(let d of[-.67,.67])M(We,d,.51,0,1.15,.5,.89,u.oak),M(We,d,.54,.48,.26,.06,.06,u.brass);for(let d of[-1,1]){let y=B("wardrobe",d*1.31,0,.56,0,We);de.push({group:y,side:d});let I=P(y);M(I,-d*.647,1.84,0,1.28,2.92,.095,u.teal);for(let b=0;b<7;b++)M(I,-d*(.1+b*.175),1.84,.052,.025,2.68,.025,"#6b9890");for(let b of[.51,3.16])M(I,-d*.65,b,.075,1.12,.055,.035,u.tealLight);M(y,-d*1.15,1.74,.11,.054,.23,.07,u.brass)}for(let d=0;d<2;d++)M(We,-.48+d*1.1,3.7,-.05,.85,.43,.73,d?u.mustard:u.cream);let Ve=se.bed=B("bed",3.9,0,-2.2);for(let d of[-1.18,1.18])for(let y of[-1.64,1.64])M(Ve,d,.21,y,.17,.43,.17,u.edge);M(Ve,0,.43,0,2.81,.24,3.78,u.oak);let qt=P(Ve);for(let d=0;d<13;d++)M(qt,-1.27+d*.212,1.05,-1.86,.18,1.44-Math.abs(d-6)*.023,.15,u.teal);for(let d=0;d<4;d++)M(Ve,0,.57+d*.07,0,2.65-(d===3?.12:0),.072,3.59,d%2?u.paper:"#e1d5b9");for(let d=0;d<22;d++)for(let y=0;y<24;y++){let I=-1.32+d*.126,b=-.87+y*.115,A=.9-Math.max(0,Math.abs(I)-1.12)*1.5+Math.sin(d*.68)*.024;ne(Ve,I,A,b,.126,y%8===0||d%8===0?"#a9c3ac":(d+y)%3?"#6e9990":"#82a89a")}for(let d of[-.68,.67])for(let y=0;y<9;y++)for(let I=0;I<5;I++)ne(Ve,d-.44+y*.11,.96+(y>0&&y<8&&I>0&&I<4?.07:0),-1.51+I*.11,.118,d<0?u.paper:"#d6bd99");for(let d=0;d<24;d++)M(Ve,-1.39+d*.12,.94,1.39,.115,.055,.48,d%4<2?u.rose:"#dc9b79");M(Ve,-1.98,.5,-1.09,.75,.94,.85,u.oak),M(Ve,-1.98,.52,-.637,.57,.65,.07,u.cream),ne(Ve,-1.98,.59,-.576,.075,u.brass),Ne(Ve,-1.98,1.01,-1.09,.79);let ln=P(se.rug=B("rug",-1.65,0,1.62));for(let d=-22;d<=22;d++)for(let y=-16;y<=16;y++){if((d/23)**2+(y/17)**2>1)continue;let I=(d/23)**2+(y/17)**2>.78;M(ln,d*.115,.025,y*.115,.112,.036,.112,I?(d+y)%3?u.rose:u.mustard:(d+y)%4?"#e5d8b8":"#dbcaab")}let yt=se.radio=B("radio",-5.12,0,3,Math.PI/2),ht=P(yt);for(let d of[-.94,.94])for(let y of[-.34,.34])M(ht,d,.17,y,.12,.34,.12,u.edge);M(ht,0,.64,0,2.34,.78,.95,u.oak);for(let d=0;d<16;d++)M(ht,-.97+d*.129,.65,.495,.06,.58,.07,u.edge);M(yt,-.35,1.37,-.02,1.3,.64,.5,u.tealDark),M(yt,-.55,1.38,.25,.69,.44,.035,u.cream);for(let d=0;d<7;d++)for(let y=0;y<4;y++)ne(yt,-.81+d*.088,1.24+y*.091,.278,.027,u.edge);M(yt,.055,1.45,.253,.24,.15,.04,u.mustard);for(let d of[-.01,.13])ne(yt,d,1.23,.29,.09,u.brass);M(yt,-.86,1.99,-.09,.027,.72,.027,u.brass,0,-.22);for(let d=0;d<4;d++)M(yt,.73,1.09+d*.075,.04,.49,.057,.51,d%2?u.paper:u.rose);le(yt,.71,1.35,-.03,.47);let ft=se.garden=B("garden",4.4,0,3.4),cn=P(ft);for(let d=0;d<3;d++){let y=.18+d*.26,I=-.62+d*.55;M(cn,I,y,-.13,.62,.09,.8,u.oak);for(let b of[-.45,.17])M(cn,I,y/2,b,.07,y,.07,u.edge);le(ft,I,y+.05,-.11,[.73,.92,1.15][d])}let Z=P(se.lounge=B("lounge",-2.85,0,1.3,Math.PI/2));for(let d of[-.57,.57])for(let y of[-.5,.5])M(Z,d,.17,y,.13,.34,.13,u.edge);M(Z,0,.46,0,1.44,.25,1.5,u.oak);for(let d=0;d<10;d++)for(let y=0;y<9;y++)ne(Z,-.58+d*.13,.69+(d>0&&d<9&&y>0&&y<8?.04:0),-.48+y*.13,.132,(d+y)%4?"#c89669":"#d4a87a");for(let d=0;d<11;d++)M(Z,-.65+d*.13,1.16,-.64,.125,1.03,.2,d%3?"#bd895d":"#c89669");for(let d of[-.76,.76])M(Z,d,.8,0,.2,.75,1.45,u.oak),M(Z,d,1.2,.02,.24,.11,1.51,u.edge);for(let d=0;d<5;d++)for(let y=0;y<5;y++)ne(Z,-.25+d*.115,.92+y*.115,-.4,.118,(d+y)%3?u.cream:u.mustard);let mt=P(se.readingLamp=B("readingLamp",-4.1,0,.16));Ne(mt,0,1.13,0,1.08),M(mt,0,.61,0,.07,1.25,.07,u.edge),M(mt,0,.065,0,.5,.13,.5,u.brass);let Mt=P(se.stool=B("stool",-.95,0,1.6));for(let d=0;d<5;d++)M(Mt,0,.16+d*.095,0,.95-Math.abs(d-2)*.09,.095,.83,d%2?"#c89963":"#d9b486");M(Mt,0,.67,0,1.25,.1,1,u.edge),M(Mt,-.14,.75,.03,.74,.045,.56,u.oak);for(let d of[-.32,.02])M(se.stool,d,.83,.02,.19,.13,.19,u.paper),M(se.stool,d,.9,.02,.13,.015,.13,u.edge);let ct=se.art=B("art",3.92,2.99,-4.25);M(ct,0,0,0,.58,.82,.08,u.edge),M(ct,0,0,.05,.46,.68,.04,u.paper);for(let d=0;d<6;d++)ne(ct,-.12+d%3*.09,-.2+d*.075,.087,.09,d%2?u.green:u.mustard);let An=se.entrance=B("entrance",5.89,0,1.25,-Math.PI/2),Cn=B("entrance",0,0,0,0,An);for(let d of[-1.25,1.25]){for(let y=.15;y<3.6;y+=.3)M(Cn,d,y,0,.3,.294,.24,y<1.5?"#7d9b90":"#eae3d0");M(Cn,d*.87,1.65,.02,.13,3.35,.33,u.cream)}M(Cn,0,3.48,0,2.8,.3,.28,u.cream),M(Cn,0,3.29,.02,2.28,.13,.33,u.oak),M(Cn,0,.025,-.16,2.2,.05,.58,u.edge);for(let d=0;d<3;d++)M(Cn,0,-.13-d*.17,-.54-d*.36,2.48,.17,.4,"#c6cab9");let kn=B("entrance",-1.04,0,.03,0,An),oi=B("entrance",0,0,0,0,kn);M(oi,1.025,1.63,0,2.03,3.2,.13,u.tealDark);for(let d of[.17,1.88])M(oi,d,1.63,.08,.095,2.94,.045,u.oak);for(let d of[.25,1.33,3.02])M(oi,1.025,d,.08,1.8,.08,.04,u.oak);for(let d=0;d<8;d++)M(oi,.32+d*.2,2.18,.075,.14,1.47,.025,"#537e73");M(kn,1.74,1.54,.15,.08,.28,.07,u.brass),M(kn,1.63,1.61,.23,.3,.055,.07,u.brass),M(An,0,.06,.63,1.76,.045,.66,u.rose);for(let d=0;d<10;d++)M(An,-.76+d*.169,.086,.63,.02,.006,.54,u.cream);for(let[d,y]of Object.entries(se))if(S[d]&&(ge[d]={},!E[d]))for(let I of["cream","ink"]){let b=B(d,0,0,0,0,y);b.visible=!1,ge[d][I]=b;let A=I==="cream",re=A?u.cream:u.navy;if(d==="bed"){for(let q=0;q<(A?3:9);q++)M(b,A?-.84+q*.84:-1.2+q*.3,1.18,-1.73,A?.8:.2,A?1.45:1.65-Math.abs(q-4)*.1,.23,re);M(b,0,.26,0,2.64,.24,3.58,A?u.paper:u.navy)}else if(d==="lounge"){M(b,0,1.17,-.49,1.23,A?1.12:1.48,.25,re);for(let q of[-.76,.76])M(b,q,.93,.05,.25,A?.62:.34,1.48,re)}else if(d==="desk")if(M(b,0,.95,-.47,2.64,.36,.12,re),A)M(b,1.04,1.17,.02,.74,.13,1.07,u.cream);else for(let q of[-1.43,1.43])M(b,q,.32,0,.16,.07,1.14,u.brass);else if(d==="shelf"){for(let q=0;q<4;q++)M(b,(q%2?1:-1)*.27,.59+q*.84,.05,.075,.72,.72,re);M(b,0,3.64,0,A?2.9:3.12,.13,A?.87:1,re)}else if(d==="wardrobe"){M(b,0,3.51,0,A?2.86:3.06,A?.1:.18,1.2,re);for(let q of de){let ae=B(d,0,0,0,0,q.group);ae.visible=!1,(b.userData.doorPanels||=[]).push(ae);for(let me=0;me<3;me++)M(ae,-q.side*.65,.98+me*.87,.077,1.08,A?.71:.025,.035,re)}}else if(d==="stool"){M(b,0,.7,0,A?1.38:1.27,.12,A?1.1:1.04,re);for(let q of[-.5,.5])M(b,q,.28,0,.09,.53,.78,A?u.cream:u.brass)}else if(d==="radio"){M(b,0,1.04,0,2.5,.12,1.06,re);for(let q of[-1.06,1.06])M(b,q,.63,.55,.07,.7,.1,A?u.cream:u.brass)}else if(d==="readingLamp")for(let q=0;q<3;q++)M(b,0,1.95+q*.1,0,A?.62:.8-q*.18,.1,A?.62:.8-q*.18,re);else if(d==="garden")for(let q=0;q<3;q++)M(b,-.62+q*.55,.1+q*.13,-.13,A?.42:.08,.18+q*.26,.56,re);else if(d==="rug")for(let q=-15;q<=15;q++)M(b,q*.14,.05,0,.06,.014,2.4*Math.sqrt(1-(q/18)**2),A?u.paper:q%3?u.navy:u.brass)}function Ct(d,y,I,b,A){let re=new D(...y),q=new D(...I),ae=re.distanceTo(q),me=Math.ceil(ae/(b*.7));for(let W=0;W<=me;W++){let pe=re.clone().lerp(q,W/me);ne(d,pe.x,pe.y,pe.z,b,A)}}function hn(d,y,I,b,A,re,q){for(let ae=0;ae<=Math.floor(A/.13);ae++)M(d,y-A/2+ae*.13,I,b,.035,re,.038,q);for(let ae=0;ae<=Math.floor(re/.13);ae++)M(d,y,I-re/2+ae*.13,b+.021,A,.035,.025,q)}function Di(d,y,I,b,A,re,q,ae,me=0){for(let W=-A;W<=A;W+=.11)for(let pe=-re;pe<=re;pe+=.11){let je=Math.hypot(W/A,pe/re),ce=me?.88+.12*Math.cos(Math.atan2(pe/re,W/A)*me):1;je<=ce&&M(d,y+W,I,b+pe,.113,q,.113,ae)}}function Da(d,y){let I=se[d],b=h[y],A=B(d,0,0,0,0,I);A.visible=!1,A.userData.variant=y,ge[d][y]=A;let re=y==="rattan",q=y==="walnut",ae=y==="loft",me=y==="blossom";if(d==="desk"){for(let W of[-1.39,1.39])if(ae){for(let pe of[-.46,.46])M(A,W,.58,pe,.1,1.16,.1,b.edge);M(A,W,.08,0,.11,.1,1.02,b.edge),Ct(A,[W,.14,-.4],[W,1.13,.4],.07,b.edge)}else if(y==="nordic"){for(let pe of[-.48,.48])Ct(A,[W,.08,pe],[W,1.17,0],.11,b.wood);M(A,W,.43,0,.09,.09,.69,b.edge)}else for(let pe of[-.43,.43])Ct(A,[W,.07,pe],[W*.95,1.17,pe*.85],me?.14:.11,b.edge);if(M(A,q||me?0:.99,1,.03,q||me?2.55:.81,.33,.98,b.wood),re)hn(A,.99,1,.54,.69,.25,b.light);else for(let W=0;W<(q||me?3:1);W++){let pe=q||me?-.85+W*.85:.99;M(A,pe,1,.535,q||me?.79:.68,.27,.05,b.accent),M(A,pe,1,.58,me?.09:.2,.045,.05,me?u.cream:u.brass)}ae&&Ct(A,[-1.28,.18,-.47],[1.28,1.12,-.47],.065,b.edge)}else if(d==="shelf"){for(let W of[-1.36,1.36])for(let pe of[-.31,.3])M(A,W,1.77,pe,ae?.085:.12,3.54,.12,b.edge);if(re)hn(A,0,1.81,-.35,2.59,3.25,b.wood);else if(ae)Ct(A,[-1.27,.26,-.35],[1.27,3.5,-.35],.06,b.edge),Ct(A,[1.27,.26,-.35],[-1.27,3.5,-.35],.06,b.edge);else{M(A,0,1.78,-.36,2.63,3.38,.075,q?b.dark:b.light);for(let W=0;W<4;W++)M(A,(W%2?1:-1)*.52,.6+W*.84,.04,.09,.73,.68,b.wood)}if(me)for(let W=-6;W<=6;W++)M(A,W*.21,3.5+.22*Math.sqrt(1-(W/7)**2),0,.205,.18,.79,b.accent);q&&(M(A,0,3.52,0,2.85,.15,.9,b.wood),M(A,0,.06,0,2.7,.12,.8,b.dark))}else if(d==="wardrobe"){for(let W of de){let pe=B(d,0,0,0,0,W.group),je=-W.side*.647;pe.visible=!1,pe.userData.variant=y,(A.userData.doorPanels||=[]).push(pe),M(pe,je,1.84,-.015,1.28,2.92,.08,re?b.dark:b.accent);for(let ce of[-.59,.59])M(pe,je+ce,1.84,.045,.075,2.92,.07,b.wood);for(let ce of[.43,3.25])M(pe,je,ce,.045,1.22,.08,.07,b.wood);if(re)hn(pe,je,1.84,.052,1.1,2.66,b.light);else if(q)for(let ce=0;ce<8;ce++)M(pe,je-.49+ce*.14,1.84,.06,.06,2.6,.04,ce%2?b.wood:b.dark);else if(ae){for(let ce of[-.53,.53])for(let De of[.62,1.4,2.22,3.06])ne(pe,je+ce,De,.087,.06,u.brass);for(let ce=0;ce<6;ce++)M(pe,je,2.36+ce*.11,.042,.72,.035,.026,b.dark)}else if(me){for(let ce=-4;ce<=4;ce++)M(pe,je+ce*.11,2.01+.12*Math.sqrt(1-(ce/5)**2),.05,.105,1.84+.24*Math.sqrt(1-(ce/5)**2),.04,b.light);for(let ce=0;ce<4;ce++)ne(pe,je+Math.cos(ce*Math.PI/2)*.1,2.66+Math.sin(ce*Math.PI/2)*.1,.09,.12,u.cream)}else M(pe,je-W.side*.23,1.84,.045,.53,2.74,.04,b.light),M(pe,je,.97,.075,1.12,.06,.03,b.wood)}(q||me)&&M(A,0,3.49,0,2.92,.12,1.16,b.wood)}else if(d==="bed"){if(re){M(A,0,1.22,-1.87,2.65,1.68,.08,b.dark),hn(A,0,1.26,-1.8,2.42,1.38,b.light);for(let W of[-1.3,1.3])M(A,W,1.14,-1.83,.11,1.94,.15,b.wood);for(let W of[.53,2.03])M(A,0,W,-1.8,2.7,.1,.13,b.wood)}else if(ae){for(let W of[-1.27,1.27])M(A,W,1.05,-1.86,.1,1.91,.1,b.edge);for(let W of[.8,1.98])M(A,0,W,-1.86,2.58,.08,.1,b.edge);for(let W=-5;W<=5;W++)M(A,W*.22,1.4,-1.86,.055,1.12,.055,b.edge)}else for(let W=-7;W<=7;W++){let pe=me?1.22+.6*Math.sqrt(1-(W/8)**2):q?1.25+.35*Math.abs(W/7):1.12+.5*(1-Math.abs(W/7));M(A,W*.175,.43+pe/2,-1.84,.17,pe,me?.26:.16,me?W%3?b.accent:b.light:q?b.wood:W<0?b.accent:b.light)}if(q)for(let W of[-1.35,1.35])M(A,W,1.18,-1.68,.12,1.5,.4,b.wood)}else if(d==="radio"){M(A,0,.98,0,2.36,.12,.98,b.wood),M(A,0,.37,0,2.2,.1,.88,b.wood);for(let W of[-1.06,1.06]){M(A,W,.68,0,.11,.56,.9,b.wood);for(let pe of[-.32,.32])Ct(A,[W,.03,pe],[W*.94,.38,pe*.9],.095,b.edge)}for(let W of[-.54,.54])if(re)M(A,W,.67,.39,.98,.47,.045,b.dark),hn(A,W,.67,.43,.93,.43,b.light);else{if(M(A,W,.67,.43,.97,.47,.05,q?b.wood:W<0?b.accent:b.light),M(A,W+.32,.7,.49,.09,.055,.04,u.brass),ae)for(let pe of[-.4,.4])for(let je of[.5,.84])ne(A,W+pe,je,.48,.05,b.edge);if(q)for(let pe=0;pe<7;pe++)M(A,W-.41+pe*.137,.67,.47,.025,.42,.025,b.light)}}else if(d==="garden"){for(let W=0;W<3;W++){let pe=-.62+W*.55,je=.18+W*.26;me?Di(A,pe,je,-.13,.4,.43,.08,W%2?b.light:b.accent,5):M(A,pe,je,-.13,.66,.08,.79,b.wood);for(let ce of[-.43,.16])y==="nordic"&&Ct(A,[pe-.24,.04,ce],[pe,je,ce],.065,b.edge),M(A,pe+(y==="nordic"?.24:0),je/2,ce,ae?.06:.09,je,.07,b.edge)}(re||ae)&&(Ct(A,[-.88,.1,-.48],[.78,.94,-.48],.065,b.edge),Ct(A,[-.88,.08,-.48],[-.88,.6,-.48],.07,b.edge))}else if(d==="lounge"){for(let W of[-.55,.55])for(let pe of[-.49,.49])Ct(A,[W,.05,pe],[W*.9,.63,pe*.83],ae?.075:.1,b.edge);if(M(A,0,.56,0,1.36,.18,1.35,b.wood),M(A,0,.71,.02,1.25,.19,1.19,b.fabric),re){hn(A,0,1.27,-.59,1.25,1.02,b.light);for(let W of[-.66,.66])M(A,W,1.26,-.6,.09,1.2,.11,b.wood);M(A,0,1.85,-.6,1.42,.08,.13,b.wood)}else if(me||q){for(let W=-4;W<=4;W++){let pe=.83+.45*Math.sqrt(1-(W/5)**2);M(A,W*.15,.65+pe/2,-.55,.145,pe,.22,me&&W%2?b.light:b.accent)}for(let W of[-.7,.7])M(A,W,1.32,-.38,.16,.88,.48,b.accent)}else{M(A,0,1.24,-.58,1.23,.98,.16,b.accent);for(let W of[-.68,.68])Ct(A,[W,.12,.6],[W,1.8,-.6],ae?.08:.12,b.edge)}for(let W of[-.75,.75])M(A,W,.98,.1,.13,.47,.12,b.edge),M(A,W,1.19,0,.2,.1,1.43,q?b.wood:b.light);M(A,.12,1.01,-.31,.57,.49,.18,me?u.cream:b.light,0,-.13)}else if(d==="readingLamp"){if(y==="nordic")for(let W=0;W<3;W++){let pe=W*Math.PI*2/3;Ct(A,[Math.cos(pe)*.36,.06,Math.sin(pe)*.36],[0,1.78,0],.07,b.wood)}else Di(A,0,.07,0,.3,.3,.12,b.edge),M(A,0,.91,0,.07,1.76,.07,b.edge);if(re){for(let W of[1.7,2.31])M(A,0,W,0,.64,.08,.64,b.wood);for(let W of[-.29,.29])for(let pe=-.27;pe<.3;pe+=.09)M(A,W,2,pe,.045,.59,.045,b.wood);for(let W of[-.29,.29])for(let pe=-.27;pe<.3;pe+=.09)M(A,pe,2,W,.045,.59,.045,b.wood);M(A,0,2,0,.42,.49,.42,"#ffdfa0")}else if(ae){Ct(A,[0,1.7,0],[.35,2.16,0],.08,b.edge),ne(A,0,1.7,0,.15,u.brass);for(let W=0;W<4;W++)M(A,.29,1.98+W*.09,0,.56-W*.1,.095,.47-W*.075,b.accent)}else for(let W=0;W<7;W++){let pe=q?.44*Math.sqrt(1-(W/8)**2):me?.16+Math.sin(W/6*Math.PI)*.19:.43-W*.039;Di(A,0,1.78+W*.077,0,pe,pe,.079,W===0?"#ffe2a6":me?W%2?b.light:b.accent:q?"#c58d49":b.light,me?5:0)}}else if(d==="stool")if(re){for(let W of[-.39,.39])hn(A,0,.35,W,.91,.48,b.light);for(let W of[-.47,.47])M(A,W,.34,0,.07,.55,.8,b.wood);M(A,0,.69,0,1.25,.12,1.02,b.wood)}else{if(ae){M(A,0,.69,0,1.29,.12,1.02,b.wood);for(let W of[-.52,.52]){for(let pe of[-.39,.39])M(A,W,.33,pe,.07,.59,.07,b.edge);M(A,W,.08,0,.075,.075,.86,b.edge)}}else{Di(A,0,.69,0,q?.76:.7,.56,.11,me?b.light:b.wood,me?5:0);for(let W=0;W<3;W++){let pe=W*Math.PI*2/3;Ct(A,[Math.cos(pe)*.49,.04,Math.sin(pe)*.4],[Math.cos(pe)*.31,.66,Math.sin(pe)*.3],.095,b.edge)}}q&&Di(A,0,.23,0,.61,.43,.07,b.wood)}else if(d==="rug"){for(let W=-22;W<=22;W++)for(let pe=-16;pe<=16;pe++){let je=W/22,ce=pe/16,De=Math.hypot(je,ce);if(!(me?De<=.87+.13*Math.cos(Math.atan2(ce,je)*6):ae?!0:De<=1))continue;let Nt=re?pe%3?b.light:b.wood:q?(Math.abs(W)+Math.abs(pe))%9<3?b.accent:b.light:ae?(Math.floor((W+22)/6)+Math.floor((pe+16)/6))%2?b.dark:b.fabric:me?De<.24?u.mustard:De>.68?b.accent:b.light:pe+16<Math.abs(W)*.8?b.light:pe%9<3?b.dark:b.fabric;M(A,W*.113,.027,pe*.113,.111,.04,.111,Nt)}if(re)for(let W=-11;W<=11;W++)for(let pe of[-1,1])M(A,W*.14,.023,pe*(1.76-Math.abs(W)*.038),.045,.028,.24,b.light)}}function yi(d){let y=f[d],I=B("");I.visible=!1,Re[d]=I;let b=B("",0,0,0,0,Fe),A=B("entrance",0,0,0,0,kn);b.visible=!1,A.visible=!1,I.userData.parts=[b,A];let re=d==="washitsu",q=d==="loft",ae=d==="french",me=d==="coastal",W=d==="cabin",pe=W?.28:q?.23:.3,je=q?.59:W?1.47:.6;for(let ce=0,De=pe/2;De<4.8;ce++,De+=pe){for(let rt=-5.98+(q&&ce%2?-je/2:0);rt<5.99;rt+=je){let Nt=Math.max(-5.98,rt),It=Math.min(5.99,rt+je),Xn=De-pe/2,Mf=De+pe/2>1.6&&Xn<4.29?[[Nt,Math.min(It,-5.25)],[Math.max(Nt,-1.93),It]]:[[Nt,It]];for(let[oc,lc]of Mf)if(lc-oc>.018){let bf=q?[y.wall,y.lower,"#c08b70","#aa725e"][Math.abs(ce+Math.round(rt*10+60))%4]:W?[y.wall,y.lower,"#bc956e"][(ce+60+Math.round(rt))%3]:De<1.48?y.lower:y.wall;M(I,(oc+lc)/2,De,-4.47,lc-oc-.012,pe-.012,W?.27:.22,bf)}}for(let rt=-4.5+(q&&ce%2?-je/2:0);rt<5.7;rt+=je){let Nt=Math.max(-4.5,rt),It=Math.min(5.7,rt+je);if(De>1.48&&(Nt+It)/2>1.7)continue;let Xn=q?[y.wall,y.lower,"#c08b70"][(ce+Math.round(rt*10+60))%3]:De<1.48?y.lower:y.wall;M(I,-5.9,De,(Nt+It)/2,W?.27:.22,pe-.012,It-Nt-.012,Xn)}}for(let ce of[.13,4.8])M(I,0,ce,-4.29,12,W?.2:.09,W?.3:.14,y.edge);if(M(I,-5.72,.13,.6,.14,.09,10.2,y.edge),M(I,-5.86,4.8,-1.35,W?.35:.2,W?.23:.1,6.1,y.edge),re||W||q){for(let ce of[-5.77,-1.73,5.79])M(I,ce,2.43,-4.25,W?.22:.13,4.8,W?.28:.14,y.edge);for(let ce of[-4.36,1.62])M(I,-5.7,2.41,ce,.16,4.7,W?.22:.14,y.edge)}if(q){for(let ce of[-5.78,-1.73,5.78])for(let De=.35;De<4.65;De+=.52)ne(I,ce,De,-4.16,.065,"#a1a69c");for(let ce of[4.44,4.65])M(I,0,ce,-4.29,11.84,.055,.18,y.edge)}if(ae){for(let ce of[.25,1.48,4.54,4.7])M(I,0,ce,-4.28,11.85,.07,.08,"#fff4df"),M(I,-5.71,Math.min(ce,1.48),.6,.08,.07,10.06,"#fff4df");for(let ce=-5.23;ce<5.6;ce+=1.32){for(let De of[-.5,.5])M(I,ce+De,.86,-4.23,.032,.97,.026,"#fff3db");for(let De of[.37,1.34])M(I,ce,De,-4.23,1.03,.03,.026,"#fff3db")}for(let ce of[2.35,4.68]){for(let De of[-.96,.96])M(I,ce+De,3.07,-4.26,.04,2.17,.05,"#fff5e3");for(let De of[1.97,4.17])M(I,ce,De,-4.26,1.96,.04,.05,"#fff5e3")}}if(me){M(I,0,1.5,-4.26,11.85,.075,.12,y.wood),M(I,-5.7,1.5,.6,.12,.075,10.09,y.wood);for(let ce=-5.7;ce<5.9;ce+=.36)M(I,ce,.78,-4.27,.026,1.3,.03,"#bccdc2")}if(re)for(let ce=0;ce<7;ce++)for(let De=0;De<4;De++){let rt=-4.47+De*2.98,Nt=-3.75+ce*1.455;M(I,rt,-.038,Nt,2.96,.065,1.435,y.edge),M(I,rt,-.006,Nt,2.81,.012,1.285,y.floor[(ce+De)%3]);for(let It=0;It<11;It++)M(I,rt,.001,Nt-.55+It*.11,2.76,.004,.018,"#a9a578")}else if(q||me){let ce=q?1.49:.596;for(let De=0;De<(q?7:17);De++)for(let rt=0;rt<(q?8:20);rt++){let Nt=-5.96+ce/2+rt*ce,It=-4.47+ce/2+De*ce,Xn=me&&(De===0||De===16||rt===0||rt===19),ac=Math.min(ce,5.68-(It-ce/2));M(I,Nt,-.032,It-(ce-ac)/2,ce-.017,.05,ac-.017,Xn?y.edge:y.floor[(De*2+rt)%3]),Xn&&M(I,Nt,-.004,It,.2,.006,.2,"#eee9d5",Math.PI/4)}}else for(let ce=0;ce<23;ce++)for(let De=0;De<8;De++){let rt=-5.96+De*1.49,Nt=-4.46+ce*.442;if(ae){let It=(ce+De)%2===0;for(let Xn=0;Xn<3;Xn++)M(I,rt+.745+(It?(Xn-1)*.49:0),-.032,Nt+.223+(It?0:(Xn-1)*.145),It?.48:1.47,.05,It?.432:.139,y.floor[Xn])}else{M(I,rt+.745,-.032,Nt+.223,1.474,.05,.432,y.floor[(ce+De)%3]);for(let It of[-.12,.12])M(I,rt+.745,-.005,Nt+.223+It,1.2,.004,.009,y.wood)}}for(let ce of[-1.65,1.65])M(b,ce,0,.1,W?.2:.12,2.9,.28,y.wood);for(let ce of[-1.4,1.4])M(b,0,ce,.1,3.5,W?.18:.12,.28,y.wood);if(M(b,0,-1.48,.24,3.7,.14,.68,y.wood),re)M(b,0,0,.014,3.19,2.67,.03,"#eee9cb"),hn(b,0,0,.11,3.15,2.62,y.wood);else if(ae){for(let ce of[-.52,.52])M(b,ce,-.22,.15,.055,2.25,.08,"#fff5df");for(let ce=-14;ce<=14;ce++){let De=ce/14,rt=.62+.72*Math.sqrt(Math.max(0,1-De*De));M(b,De*1.53,rt,.17,.117,.12,.12,"#fff6e2"),rt<1.28&&M(b,De*1.53,(rt+1.36)/2,.06,.114,1.36-rt,.1,y.wall)}M(b,0,-.24,.15,3.16,.055,.08,"#fff5df")}else{for(let ce=1;ce<(q?5:3);ce++)M(b,-1.65+ce*3.3/(q?5:3),0,.14,q?.05:.07,2.7,.09,y.edge);for(let ce of q?[-.68,0,.68]:[0])M(b,0,ce,.14,3.24,.06,.09,y.edge)}if(me)for(let ce of[-1,1]){M(b,ce*1.85,0,.25,.38,2.88,.11,y.edge);for(let De=0;De<19;De++)M(b,ce*1.85,-1.29+De*.143,.33,.34,.065,.1,y.accent)}if(W){M(b,0,1.52,.05,3.96,.21,.45,y.edge);for(let ce of[-1.74,1.74])for(let De of[-1.32,1.32])ne(b,ce,De,.27,.09,"#343f37")}M(A,1.025,1.63,0,2.03,3.2,.13,re?"#e2ddbe":q?y.edge:ae?y.wall:y.wood);for(let ce of[.08,1.97])M(A,ce,1.63,.08,.09,3.12,.06,y.edge);for(let ce of[.11,3.16])M(A,1.025,ce,.08,1.95,.09,.06,y.edge);if(re)hn(A,1.025,1.67,.087,1.77,2.83,y.wood);else if(ae)for(let[ce,De]of[[.76,.96],[2.19,1.36]]){for(let rt of[.27,1.77])M(A,rt,ce,.09,.045,De,.04,y.wood);for(let rt of[ce-De/2,ce+De/2])M(A,1.02,rt,.09,1.55,.045,.04,y.wood)}else if(q){for(let ce of[.21,1.84])for(let De=.32;De<3.1;De+=.43)ne(A,ce,De,.09,.075,"#a9b3a7");for(let ce=0;ce<5;ce++)M(A,1.025,2.28+ce*.13,.075,1.24,.038,.025,y.accent)}else{for(let ce=0;ce<8;ce++)M(A,.24+ce*.223,1.63,.079,.026,2.94,.028,y.edge);if(W){for(let ce of[.58,2.73])M(A,1.025,ce,.12,1.8,.13,.08,y.edge);Ct(A,[.27,.68,.12],[1.8,2.63,.12],.1,y.edge)}}tr()}function er(d,y){let I=se[d],b=B(d,0,0,0,0,I);(ze[d]||={})[y]=b;let A=(ae=1.15)=>{M(b,0,.76,0,ae,.12,.8,u.oak);for(let me of[-1,1])for(let W of[-1,1])M(b,me*(ae/2-.12),.37,W*.28,.12,.74,.12,u.edge)},re=(ae,me,W=1.45,pe=.9)=>{M(b,0,ae,me,W+.16,pe+.16,.16,u.dark),M(b,0,ae,me+.09,W,pe,.035,u.tealDark);for(let je=0;je<8;je++)ne(b,-.52+je*.14,ae-.25+je%3*.15,me+.115,.1,je%2?u.mustard:u.tealLight)},q=(ae,me)=>{M(b,0,ae,0,.8,me?.94:.19,me?.22:.57,u.teal);for(let W=0;W<10;W++){let pe=W*Math.PI/5;ne(b,Math.cos(pe)*.16,me?ae-.07+Math.sin(pe)*.16:ae+.13,me?.14:Math.sin(pe)*.16,.065,u.brass)}M(b,0,ae+(me?.3:.23),me?.23:-.1,.84,.13,.15,u.rose);for(let W of[-.34,.34])M(b,W,ae+(me?.25:.19),me?.25:-.1,.2,.23,.24,u.rose);for(let W=0;W<16;W++)ne(b,.44+W%2*.06,ae-.04-W*.035,.1,.06,u.dark)};if(y==="chess"){A(1.55),M(b,0,.87,0,1.5,.12,1.3,u.edge);for(let ae=0;ae<8;ae++)for(let me=0;me<8;me++)M(b,-.56+ae*.16,.94,-.56+me*.16,.155,.025,.155,(ae+me)%2?u.cream:u.tealDark);for(let ae=0;ae<8;ae++)for(let me of[-.56,.56])M(b,-.56+ae*.16,1.01,me,.09,.12,.09,me<0?u.cream:u.rose),ne(b,-.56+ae*.16,1.1+ae%3*.015,me,.08,me<0?u.cream:u.rose)}else if(y==="arcade"){M(b,0,.64,0,1.14,1.28,.95,u.teal),M(b,0,1.43,-.26,1.14,1.62,.44,u.teal),re(1.62,.005,.88,.66),M(b,0,2.25,-.06,1.2,.27,.8,u.rose),M(b,0,1.22,.31,1.2,.13,.62,u.dark),M(b,-.3,1.38,.37,.055,.22,.055,u.edge),ne(b,-.3,1.5,.37,.13,u.rose);for(let ae=0;ae<3;ae++)ne(b,.13+ae*.17,1.31,.39,.1,ae%2?u.mustard:u.tealLight);for(let ae=0;ae<6;ae++)ne(b,-.4+ae*.16,2.25,.35,.08,u.cream)}else if(y==="console"){re(.1,.03),M(b,0,-.63,.16,1.62,.1,.45,u.oak),M(b,0,-.51,.19,.7,.15,.28,u.cream);for(let ae of[-.22,.22])ne(b,ae,-.42,.3,.1,u.rose)}else if(y==="camera"||y==="instant"){let ae=y==="camera"?1.65:1.08;if(y==="instant")A();else{M(b,0,.95,0,.07,1.18,.07,u.edge);for(let[me,W]of[[-.5,.32],[.5,.32],[0,-.5]])Ct(b,[0,1.25,0],[me,.07,W],.065,u.edge)}M(b,0,ae,0,.88,.57,.37,y==="instant"?u.cream:u.teal),M(b,-.06,ae,.26,.37,.37,.23,u.dark),M(b,-.06,ae,.39,.23,.23,.045,u.tealLight),M(b,-.21,ae+.33,-.02,.28,.11,.2,u.dark),ne(b,.28,ae+.3,0,.12,u.rose),y==="instant"&&(M(b,0,ae-.36,.23,.6,.025,.45,u.paper),M(b,0,ae-.34,.23,.45,.012,.29,u.tealLight))}else if(y==="gallery"){M(b,0,.48,0,1.75,.065,.1,u.edge);for(let ae=-1;ae<=1;ae++)M(b,ae*.57,.07-ae%2*.1,.04,.49,.67,.07,u.cream),M(b,ae*.57,.12-ae%2*.1,.085,.37,.43,.02,ae===0?u.tealLight:u.rose),ne(b,ae*.57,.44,.08,.09,u.brass)}else y==="telephone"?(A(),q(1.02,!1)):y==="wallPhone"?(q(0,!0),M(b,0,0,-.15,1.08,1.44,.1,u.oak)):y==="monitor"?(A(.9),M(b,0,1.08,0,.14,.35,.15,u.navy),M(b,0,1.48,0,1.13,.73,.12,u.navy),M(b,0,1.48,.071,.97,.57,.025,u.teal),M(b,-.18,1.56,.09,.47,.04,.025,u.paper),M(b,-.25,1.44,.09,.33,.04,.025,u.tealLight),M(b,0,.955,.32,.63,.04,.2,u.cream)):y==="pedestal"&&(A(.8),M(b,0,.99,0,.52,.34,.44,u.teal),M(b,0,1.18,0,.58,.045,.5,u.paper),ne(b,0,1.28,0,.16,u.brass));tr()}for(let[d,y,I]of[["game",.6,3.5],["image",2.9,4.65],["together",-2.2,4.5]])se[d]=B(d,y,0,I),ge[d]={},er(d,Object.keys(E[d])[0]);function tr(){for(let[d,y]of we){let I=new ri(K,te,y.length);y.forEach((b,A)=>{J.set(b.x,b.y,b.z),G.set(b.w,b.h,b.d),C.setFromEuler(new Un(0,b.ry,b.rz)),L.compose(J,C,G),I.setMatrixAt(A,L),I.setColorAt(A,T.set(b.tint))}),I.castShadow=!0,I.receiveShadow=!0,I.userData.station=d.userData.station,I.userData.baseColors=y.map(b=>b.tint),I.userData.variant=d.userData.variant||"",d.add(I),Se.push(I)}we.clear(),x.dataset.voxelCount=String(N)}tr();let br=new ya("#e7f2e9","#716448",2.5),un=new hs("#fff0ce",4.1);un.position.set(-3,9,6),un.castShadow=!0,un.shadow.mapSize.set(2048,2048),Object.assign(un.shadow.camera,{left:-16,right:16,top:17,bottom:-16,near:.5,far:48}),un.shadow.normalBias=.024,un.shadow.bias=-15e-5;let Sr=new hs("#b7e2dd",1.1);Sr.position.set(7,5,-1);let Ui=new ls("#ffd094",10,7,2);Ui.position.set(-1.98,1.7,-1.09),Ve.add(Ui);let Tr=new ls("#ffcd83",7,5,2);Tr.position.set(-1.13,2,-.24),ke.add(Tr),Q.add(br,un,Sr);let li=new At(new Fn(180,180),new Sn({color:"#d8dfd2",roughness:1}));li.rotation.x=-Math.PI/2,li.position.y=-.74,li.receiveShadow=!0,Q.add(li);let Er=ef(Q);x.dataset.environment="courtyard";let vn=new Ma(new $t,"#dfb55d");vn.material.depthTest=!0,vn.material.transparent=!0,vn.material.opacity=.32,vn.visible=!1,vn.renderOrder=8,Q.add(vn);let $n=document.createElement("div");$n.className="home-room-hover-title",$n.hidden=!0,$n.setAttribute("role","tooltip"),x.appendChild($n);let U=new xa(12,48,"#547d71","#8ba698");U.position.set(0,.04,.6),U.scale.z=.85,U.visible=!1,U.material.transparent=!0,U.material.opacity=.3,Q.add(U);let ie=!1,ue=!1,fe=0,he="overview",ve="",Me=!0,Ie=!1,Ue=-1,Ee=null,at=0,$e=!1,Ge=1,ot=1,Tt=0,_t=!1,dt=0,Le=!1,it="lounge",St=[],qe=[],Be=null,Yt="classic",yn={},xn={},Wt={},Lt={},dn={},Qt={},en="",tn=!1,nr=[],wr=!!_.reducedMotion,nn=wr||!!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,Ts=window.matchMedia?.("(prefers-reduced-motion: reduce)"),tt=new us,Qn=new us,Mn=new _e,Vn={x:0,y:0},Bt=null,Gn=null,xi={},vt={photo:null,work:null},Hn=0,pn=Qp(Q,()=>({bounds:a,obstacles:[{id:"door-sweep",x:4.8,z:1.365,halfX:1.18,halfZ:1.285,angle:0},...Object.keys(S).filter(d=>d!=="rug"&&se[d]?.visible&&Wt[d]==="floor").map(d=>{let y=Ql(d);return{id:d,x:y.center.x,z:y.center.z,halfX:y.half.x,halfZ:y.half.z,angle:se[d].rotation.y}})],desk:se.desk.visible?{approach:se.desk.localToWorld(new D(-.4,0,2.28)),seat:se.desk.localToWorld(new D(-.4,.795,1.27)),angle:se.desk.rotation.y+Math.PI-.18}:null}),d=>_.onResidentChange?.(d)),bn=0,Rn=new Zt(new D(0,1,0),0);for(let d of Object.keys(S)){let y=se[d];y.updateWorldMatrix(!0,!0);let I=y.matrixWorld.clone().invert(),b=new $t;y.traverse(A=>{A.isInstancedMesh&&(A.computeBoundingBox(),b.union(A.boundingBox.clone().applyMatrix4(I.clone().multiply(A.matrixWorld))))}),dn[d]=b,Qt[d]={legacy:b.clone()},xn[d]=E[d]?Object.keys(E[d])[0]:"default",Wt[d]=d==="calendar"?"left-wall":d==="art"?"back-wall":"floor",Lt[d]={x:y.position.x,y:y.position.y,z:y.position.z,rotation:y.rotation.y*180/Math.PI,style:"oak",model:xn[d],surface:Wt[d]},yn[d]="oak"}let fn=[];function Dt(d,y,I,b,A=1){let re=new Jn({color:b,transparent:A<1,opacity:A,depthWrite:A===1});fn.push(re);let q=new At(K,re);return q.position.set(...y),q.scale.set(...I),d.add(q),q}let Zl=Dt(Fe,[0,0,-.131],[3.24,2.71,.014],"#9ecacc"),Es=Dt(Fe,[.93,.82,-.1],[.3,.3,.025],"#fff0bf"),Ua=B("",0,0,-.05,0,Fe);for(let d=0;d<3;d++)Dt(Ua,[-1.03+d*.81,.76-d%2*.44,0],[.55,.13,.025],"#e4edeb"),Dt(Ua,[-1.02+d*.81,.86-d%2*.44,0],[.27,.12,.025],"#e4edeb");let Na=B("",0,0,-.012,0,Fe),Su=Array.from({length:36},(d,y)=>Dt(Na,[y*.618%1*2.9-1.45,y*.37%1*2.46-1.23,0],[.025,.13,.022],"#d2e7eb",.78)),Tu=B("",-.32,.94,.02,0,se.stool),Eu=Array.from({length:7},(d,y)=>Dt(Tu,[0,y*.1,0],[.08,.07,.07],"#f9eee0",.35)),ws=B("",0,1.8,0,0,se.garden);Dt(ws,[0,0,0],[.07,.2,.07],"#6b533c");let tf=[-1,1].map(d=>{let y=B("",d*.04,0,0,0,ws);return Dt(y,[d*.11,.045,0],[.22,.21,.045],"#e3b15e"),Dt(y,[d*.08,-.09,0],[.15,.11,.045],"#e6d5a3"),Dt(y,[d*.16,.08,.025],[.06,.07,.025],"#825f4e"),y}),Ni=B("",.86,-1.23,.41,0,Fe);Dt(Ni,[0,0,0],[.3,.25,.23],"#8c9e9a"),Dt(Ni,[.14,.13,0],[.19,.2,.2],"#cabca0"),Dt(Ni,[.24,.11,0],[.12,.065,.1],"#cb9a4c"),Dt(Ni,[.19,.17,.105],[.035,.035,.02],"#344a47"),Dt(Ni,[-.18,-.01,0],[.18,.08,.14],"#607d78");for(let d of[-.07,.07])Dt(Ni,[d,-.15,.01],[.045,.1,.05],"#b08b52");let wu=B("",0,1.4,0,0,se.garden),nf=Array.from({length:8},(d,y)=>Dt(wu,[Math.sin(y*2.4)*.6,y%3*.24,Math.cos(y*2.4)*.6],[.06,.06,.06],"#e6f4ae")),Oa={steam:Tu,butterfly:ws,bird:Ni,fireflies:wu};Object.values(Oa).forEach(d=>{d.visible=!1});let rf={steam:"杯口升起一缕热气，慢慢散在小屋里。",butterfly:"一只小蝴蝶绕着绿植，轻轻停了一会儿。",bird:"窗沿落下一只小鸟，歪着脑袋看了看。",fireflies:"叶片间亮起几粒萤火，像藏起来的小星星。"},ei="day",mn="unknown",Ar=!0,Cr=!0,Rr=0,Jl=0,Pr=0,Fa=0,zt="",Kl="",As=40+Math.random()*35;function $l(){return!ue||Le||Ie}function sf(){return{condition:mn,light:ei,motion:Ar&&!nn,events:Cr,paused:$l(),weatherPaused:!ue||Le||!Ar||nn,event:zt||null,eventElapsed:Pr,nextIn:As,elapsed:Rr,precipitation:Na.visible,courtyard:Er.getState(),fog:{near:Q.fog?.near,far:Q.fog?.far}}}function Cs(){Object.values(Oa).forEach(d=>{d.visible=!1}),zt="",Pr=0,Fa=0,As=90+Math.random()*150,Me=!0,_.onMoment?.(null)}function Au(d=!1){if(ie||$l()||zt||d&&!Cr)return!1;let y=!["rain","snow","storm","mist"].includes(mn),I=["steam"];ei==="night"&&y&&I.push("fireflies"),ei!=="night"&&y&&I.push("bird"),ei!=="night"&&["clear","cloudy"].includes(mn)&&I.push("butterfly");let b=I.filter(A=>A!==Kl);return zt=(b.length?b:I)[Math.floor(Math.random()*(b.length||I.length))],Kl=zt,Pr=0,Fa=12,Oa[zt].visible=!0,Ba(0),Me=!0,Pt(),_.onMoment?.({id:zt,caption:rf[zt]}),!0}function Ba(d){zt==="steam"&&Eu.forEach((y,I)=>{let b=(I/Eu.length+d*.2)%1;y.position.set(Math.sin(b*7+I)*.08,b*.72,Math.cos(b*6)*.025),y.material.opacity=Math.sin(b*Math.PI)*.46}),zt==="butterfly"&&(ws.position.set(Math.sin(d*.7)*.52,1.85+Math.sin(d*.9)*.18,Math.cos(d*.7)*.42),ws.rotation.y=-d*.7,tf.forEach((y,I)=>{y.rotation.y=(I?1:-1)*(.4+Math.sin(d*9)*.55)})),zt==="bird"&&(Ni.rotation.y=Math.sin(d*.6)*.25),zt==="fireflies"&&nf.forEach((y,I)=>{y.position.set(Math.sin(I*2.4+d*.3)*.65,I%3*.24+Math.sin(d*.6+I)*.1,Math.cos(I*2.4+d*.3)*.6)})}function za(d){let y=$l();for(let[b,A]of Object.entries(Oa)){let re=b===zt&&!y;A.visible!==re&&(A.visible=re,Me=!0)}if(!ue||Le)return;let I=Math.min(d,.1);if(zt&&!y?(Fa-=I,Fa<=0&&Cs()):!y&&Cr&&!Bt&&!Ee&&(As-=I,As<=0&&Au(!0)),!(!Ar||nn)&&(Rr+=I,Jl+=I,zt&&!y&&(Pr+=I),!(Jl<1/24))){if(Jl=0,Er.tick(Rr)&&(Me=!0),Na.visible){let b=mn==="snow";Su.forEach((A,re)=>{A.position.y=1.23-(re*.37+Rr*(b?.17:.9))%1*2.46,A.position.x=re*.618%1*2.7-1.35+(b?Math.sin(Rr+re)*.09:0)}),Me=!0}zt&&!y&&(Ba(Pr),Me=!0)}}function af(d={}){let y=["clear","cloudy","rain","snow","storm","mist"].includes(d.condition)?d.condition:"unknown",I=Ar!==(d.motion!==!1),b=Cr!==(d.events!==!1);Ar=d.motion!==!1,Cr=d.events!==!1,y!==mn&&(mn=y,zt&&Cs(),qa(ei,!0)),b&&!Cr&&zt&&Cs(),I&&(Ar||Ba(0),Me=!0,Pt()),_.onAtmosphereChange?.()}function of(){Cs(),Kl="",Rr=0,Pr=0,As=40+Math.random()*35,mn="unknown",qa(ei,!0)}let ir=d=>Math.round(d*100)/100;function Wn(){return{version:1,houseStyle:Yt,items:{...structuredClone(R),...Object.fromEntries(Object.keys(S).map(d=>[d,{x:ir(se[d].position.x),y:ir(se[d].position.y),z:ir(se[d].position.z),rotation:ir(pt.radToDeg(se[d].rotation.y)),style:yn[d],model:xn[d],surface:Wt[d],...j.has(d)?{stored:!0}:{}}]))}}}function ka(d){return se[d].updateWorldMatrix(!0,!0),dn[d].clone().applyMatrix4(se[d].matrixWorld)}function lf(){return en||(j.has(it)?"已收纳。位置与外观仍保留，功能可以从清单打开。":Wt[it]!=="floor"?"沿墙拖动；方向键左右移动、上下调高低。挂件会避开窗户和家具。":it==="rug"?"地毯可铺在家具下。拖动摆放，空白处旋转视角。":"拖动摆放，重叠时保留上一个位置。方向键微调，R 旋转，Ctrl / ⌘ Z 撤销。")}function rr(){x.dataset.placementBlocked=String(tn),_.onEditorChange?.({editing:Le,houseStyle:Yt,id:it,label:S[it],item:Wn().items[it],canUndo:St.length>0,canRedo:qe.length>0,hint:lf(),blocked:tn})}function Rs(d){JSON.stringify(d)!==JSON.stringify(Wn())&&(St.push(d),St.length>60&&St.shift(),qe=[]),rr()}function Cu(d){let y=typeof d=="string"&&Object.hasOwn(p,d)?d:"classic";if(x.dataset.houseStyle=y,y===Yt)return;y!=="classic"&&!Re[y]&&yi(y),Yt=y;for(let A of[H,F,$,Oe,oi])A.visible=y==="classic";for(let[A,re]of Object.entries(Re))re.visible=A===y,re.userData.parts.forEach(q=>{q.visible=re.visible});let I=f[y],b=I?{[u.tealDark]:I.edge,[u.edge]:I.edge,[u.oak]:I.wood,[u.cream]:I.wall,"#7d9b90":I.lower,"#eae3d0":I.wall,"#c6cab9":I.floor[1]}:{};for(let A of[V,Cn])A.traverse(re=>{re.isInstancedMesh&&(re.userData.baseColors.forEach((q,ae)=>{re.setColorAt(ae,T.set(b[q]||q))}),re.instanceColor.needsUpdate=!0)});Q.updateMatrixWorld(!0),ve="",Me=!0,k.shadowMap.needsUpdate=!0}function cf(d){if(!Le)return;let y=Wn();Cu(d),Rs(y),Pt()}function Ru(d,y){if(yn[d]===y)return;let I=!E[d]&&c.includes(y),b=h[y];I&&!ge[d][y]&&(Da(d,y),tr()),yn[d]=y;let A=y==="cream"?{[u.oak]:"#e6ddc6",[u.wood]:"#c8b696",[u.edge]:"#ab987d",[u.teal]:"#d5cdb5",[u.tealDark]:"#879287",[u.tealLight]:"#e8dcc5",[u.rose]:"#cfa796"}:y==="ink"?{[u.oak]:"#78654f",[u.wood]:"#675541",[u.edge]:"#3f464b",[u.teal]:"#3f546c",[u.tealDark]:"#293b50",[u.tealLight]:"#74899b",[u.rose]:"#bc794f"}:b?{[u.oak]:b.wood,[u.wood]:b.wood,[u.edge]:b.edge,[u.teal]:b.accent,[u.tealDark]:b.dark,[u.tealLight]:b.light,[u.rose]:b.rose,"#d8b68b":b.wood,"#c9a779":b.light,"#dc9b79":b.rose}:{};y==="oak"&&w.has(d)&&(A[u.teal]=w.get(d).accent);let re=["#6e9990","#82a89a","#a9c3ac","#c89669","#d4a87a","#bd895d","#e5d8b8","#dbcaab","#6b9890"];se[d].traverse(q=>{!q.isInstancedMesh||q.userData.variant||(q.userData.baseColors.forEach((ae,me)=>{let W=y!=="oak"&&re.includes(ae)?b?.fabric||(y==="cream"?"#e1d7c4":"#546c85"):ae;q.setColorAt(me,T.set(A[ae]||W))}),q.instanceColor.needsUpdate=!0)});for(let[q,ae]of Object.entries(ge[d])){ae.visible=q===y;for(let me of ae.userData.doorPanels||[])me.visible=ae.visible}for(let q of Te[d]||[])q.visible=!I}function hf(d){let y=`${xn[d]}:${yn[d]}`;if(!Qt[d][y]){let I=de.map(q=>q.group.rotation.y);for(let q of de)q.group.rotation.y=0;let b=se[d];b.updateWorldMatrix(!0,!0);let A=b.matrixWorld.clone().invert(),re=new $t;b.traverse(q=>{if(q.isInstancedMesh){for(let ae=q;ae!==b;ae=ae.parent)if(!ae.visible)return;q.boundingBox||q.computeBoundingBox(),re.union(q.boundingBox.clone().applyMatrix4(A.clone().multiply(q.matrixWorld)))}}),Qt[d][y]=re,de.forEach((q,ae)=>{q.group.rotation.y=I[ae]})}dn[d]=Qt[d][y].clone()}function uf(d){return E[d]?.[xn[d]]?.surfaces||["floor"]}function Mi(d,y={}){let I=se[d],b=Lt[d],A=(je,ce)=>typeof je=="number"&&Number.isFinite(je)?je:ce,re=E[d]&&typeof y.model=="string"&&Object.hasOwn(E[d],y.model)?y.model:b.model;if(re!==xn[d]){(w.has(d)||["game","image","together"].includes(d))&&!ze[d]?.[re]&&er(d,re);for(let[je,ce]of Object.entries(ze[d]||{}))ce.visible=je===re;xn[d]=re,yn[d]=""}Ru(d,typeof y.style=="string"&&Object.hasOwn(o,y.style)?y.style:"oak"),hf(d);let q=uf(d);Wt[d]=q.includes(y.surface)?y.surface:q.includes(b.surface)?b.surface:q[0];let ae=Wt[d],me=ae!=="floor";I.rotation.y=me?ae==="left-wall"?Math.PI/2:0:pt.degToRad((A(y.rotation,b.rotation)%360+360)%360);let W=dn[d].clone().applyMatrix4(new Ke().makeRotationY(I.rotation.y));I.position.x=ir(pt.clamp(A(y.x,b.x),a.minX-W.min.x,a.maxX-W.max.x)),I.position.z=ir(pt.clamp(A(y.z,b.z),a.minZ-W.min.z,a.maxZ-W.max.z)),ae==="back-wall"&&(I.position.z=a.minZ-W.min.z),ae==="left-wall"&&(I.position.x=a.minX-W.min.x);let pe=ae==="left-wall"&&I.position.z+W.max.z>a.lowWallStart?a.lowWallTop:a.wallTop;I.position.y=me?ir(pt.clamp(A(y.y,b.y||2.8),.22-W.min.y,pe-W.max.y)):0,I.updateWorldMatrix(!0,!0),Me=!0,k.shadowMap.needsUpdate=!0}function Ql(d){let y=se[d],I=dn[d],b=I.getCenter(new D),A=I.getSize(new D).multiplyScalar(.5),re=y.localToWorld(b),q=y.rotation.y;return{center:re,half:A,axes:[new D(Math.cos(q),0,-Math.sin(q)),new D(Math.sin(q),0,Math.cos(q))]}}function df(d,y){let I=y.center.clone().sub(d.center);return Math.abs(I.y)>=d.half.y+y.half.y-.025?!1:[...d.axes,...y.axes].every(b=>{let A=re=>re.half.x*Math.abs(re.axes[0].dot(b))+re.half.z*Math.abs(re.axes[1].dot(b));return Math.abs(I.dot(b))<A(d)+A(y)-.025})}function Ps(d,y=Object.keys(S)){let I=ka(d),b=Wt[d];if(I.min.x<a.minX-.015||I.max.x>a.maxX+.015||I.min.z<a.minZ-.015||I.max.z>a.maxZ+.015||I.min.y<-.1||I.max.y>a.wallTop+.015)return"超出房间边界";if(b==="left-wall"&&I.max.z>a.lowWallStart&&I.max.y>a.lowWallTop+.015)return"此处是矮墙，挂件需要降低或移向里侧";if(b==="back-wall"&&I.max.x>-5.55&&I.min.x<-1.55&&I.max.y>1.38&&I.min.y<4.55)return"这里是窗户，请移到窗边的实墙";if(d!=="rug"&&I.max.x>3.62&&I.max.z>.08&&I.min.z<2.65&&I.min.y<3.48)return"请给房门留出开合空间";if(d==="rug")return"";let A=Ql(d),re=y.find(q=>q!==d&&q!=="rug"&&se[q]?.visible&&df(A,Ql(q)));return re?`与${S[re]}重叠`:""}function Va(d,y,I){if(Mi(d,y),!Ps(d,I))return!0;let b=se[d].position.clone(),A=Wt[d],re=[],q=A!=="floor";for(let ae=-48;ae<=48;ae++)for(let me=q?-19:-40;me<=(q?19:40);me++)re.push([ae,me]);re.sort((ae,me)=>ae[0]**2+ae[1]**2-me[0]**2-me[1]**2);for(let[ae,me]of re){let W=A==="left-wall"?b.x:b.x+ae*.25,pe=A==="back-wall"?b.z:b.z+(q?-ae:me)*.25;if(Mi(d,{...y,x:W,z:pe,y:q?b.y+me*.25:0}),!Ps(d,I))return!0}return!1}function ec(d,y,I=!1){let b=Wn().items[d];if(j.has(d))return Mi(d,y),!0;Mi(d,y);let A=Ps(d);return tn=!1,en="",A&&!(I&&Va(d,y))?(Mi(d,b),tn=!0,en=`${A}，已保留原位。可先移动家具再切换外观。`,!1):(A&&(en="已放到附近的空位，可继续拖动微调。"),se[d].visible=!0,z.delete(d),!0)}function Ir(d){let y=d?.version===1&&d.items&&typeof d.items=="object"?d.items:Lt;for(let b of Object.keys(R))delete R[b];for(let[b,A]of Object.entries(y))/^ext-[0-9a-f]{24}$/.test(b)&&!S[b]&&A&&typeof A=="object"&&(R[b]=structuredClone(A));Cu(d?.version===1?d.houseStyle:"classic"),en="",tn=!1,nr=[];let I=[];for(let b of Object.keys(S)){se[b].visible=!0,z.delete(b),j.delete(b);let A=y[b]&&typeof y[b]=="object"?y[b]:Lt[b];if(Mi(b,A),A.stored===!0){j.add(b),se[b].visible=!1;continue}if(Ps(b,I)&&(nr.push(b),!Va(b,A,I)&&!Va(b,Lt[b],I))){if(w.has(b)){Mi(b,A),se[b].visible=!1,z.add(b);continue}if(y!==Lt){Ir(null),en="原布局没有足够空位，已恢复默认布置；浏览器中的原记录仍保留。",rr();return}}I.push(b)}nr.length&&(en=`已为${nr.map(b=>S[b]).join("、")}避让重叠或门窗；保存后记住新位置。`),rr(),Pt()}function Pu(d){R[d]=Wn().items[d],se[d].traverse(y=>{if(!y.isInstancedMesh)return;let I=Se.indexOf(y);I>=0&&Se.splice(I,1),N-=y.count,y.dispose()}),se[d].removeFromParent();for(let y of[se,S,v,E,ge,ze,yn,xn,Wt,Lt,dn,Qt])delete y[d];w.delete(d),z.delete(d),j.delete(d)}function Iu(d){if(ie||!Array.isArray(d))return;if(Le){O=structuredClone(d);return}let y=d.filter(b=>/^ext-[0-9a-f]{24}$/.test(b?.id)),I=new Set(y.map(b=>b.id));for(let b of w.keys())I.has(b)||Pu(b);for(let b of y){let A=b.id,re=["pedestal","camera","telephone","chess","gallery","monitor"].includes(b.model)?b.model:"pedestal",q={...b,model:re,accent:/^#[0-9a-f]{6}$/i.test(b.accent)?b.accent:u.teal},ae=w.get(A);if(ae&&ae.model!==re&&Pu(A),w.set(A,q),S[A]=String(q.label||"拓展家具"),v[A]={label:S[A]},se[A]){if(ae.accent!==q.accent){let pe=yn[A];yn[A]="",Ru(A,pe)}continue}let me=re==="gallery"?i:["floor"];E[A]={[re]:{label:S[A],surfaces:me}},se[A]=B(A),ge[A]={},Qt[A]={},xn[A]=re,yn[A]="",Wt[A]=me[0],Lt[A]={x:0,y:re==="gallery"?3.4:0,z:re==="gallery"?-4.2:.5,rotation:0,style:"oak",model:re,surface:me[0]},er(A,re);let W=R[A]||Lt[A];W.stored===!0?(Mi(A,W),se[A].visible=!1,j.add(A)):Va(A,W,Object.keys(S).filter(pe=>pe!==A))||(Mi(A,W),se[A].visible=!1,z.add(A)),delete R[A]}S[it]||(it="lounge"),v[he]||(he="overview"),ve="",Gn=null,k.shadowMap.needsUpdate=!0,Me=!0,x.dataset.voxelCount=String(N),rr(),Pt()}function Is(d){let y=xi[d];y&&(y.removeFromParent(),y.geometry.dispose(),y.material.map?.dispose(),y.material.dispose(),delete xi[d])}function Lu(d,y,I){Is(d),y.colorSpace=Ut;let b=d==="photo",A=new At(new Fn(b?.47:.78,b?.69:.62),new Jn({map:y,side:En}));A.userData={station:b?"art":"desk",roomObject:structuredClone(I.ref),title:I.title},b?(A.position.set(0,0,.16),se.art.add(A)):(A.rotation.x=-Math.PI/2,A.rotation.z=-.12,A.position.set(.96,1.45,.27),se.desk.add(A)),xi[d]=A,Me=!0,Pt()}function Ga(d){let y=d?.ref;return y?[y.kind,y.id,y.revision,y.scope].join("\0"):""}function pf(d){if(!(ie||!d)){if(Object.hasOwn(d,"work")&&Ga(d.work)!==Ga(vt.work)&&(vt.work=d.work,Is("work"),d.work)){let y=document.createElement("canvas");y.width=520,y.height=410;let I=y.getContext("2d");I.fillStyle="#fff4d8",I.fillRect(0,0,520,410),I.fillStyle="#3e514a",I.font="bold 30px sans-serif",I.fillText(String(d.work.title||"原稿").slice(0,14),32,62),I.font="24px sans-serif";let b=[...String(d.work.summary||"")];for(let A=0;A<5;A++)I.fillText(b.slice(A*17,A*17+17).join(""),32,125+A*46);Lu("work",new Ii(y),d.work)}if(Object.hasOwn(d,"photo")&&(Ga(d.photo)!==Ga(vt.photo)||d.photo?.image!==vt.photo?.image)){let y=++bn;vt.photo=d.photo,Is("photo");let I=d.photo;if(I&&/^data:image\/(jpeg|png);base64,/.test(I.image||"")){let b=new Image;b.onload=()=>{if(ie||y!==bn)return;let A=document.createElement("canvas");A.width=470,A.height=690;let re=A.getContext("2d"),q=Math.min(450/b.width,670/b.height);re.fillStyle="#fff4d8",re.fillRect(0,0,470,690),re.drawImage(b,(470-b.width*q)/2,(690-b.height*q)/2,b.width*q,b.height*q),Lu("photo",new Ii(A),I)},b.src=I.image}}Me=!0,Pt()}}function ff(d){if(!Le)return;let y=Wn(),I={...y.items[it],...d};d.model&&d.model!==y.items[it].model&&(delete I.surface,I.y=2.8),ec(it,I,!!(d.model||d.surface||d.style)),Rs(y),Pt()}function mf(d){if(!Le||!S[it])return;let y=Wn(),I=it;tn=!1,en="",d?(j.add(I),z.delete(I),se[I].visible=!1):(j.delete(I),ec(I,y.items[I],!0)||(y.items[I].stored&&j.add(I),se[I].visible=!1,en="房间暂时没有合适空位，仍保留在收纳中。可先移动或收纳其他家具。")),ve="",k.shadowMap.needsUpdate=!0,Me=!0,Rs(y),Pt()}function tc(d){!Le||!S[d]||(it=d,ve="",en="",tn=!1,rr(),Pt())}function gf(d){if(Ns(),Le=!!d,U.visible=Le,St=[],qe=[],he="overview",ve="",Ls("overview"),rr(),!Le&&O){let y=O;O=null,Iu(y)}za(0),_.onAtmosphereChange?.(),Pt()}function _f(d=!1){if(!Le)return;let y=d?qe:St,I=d?St:qe;y.length&&(I.push(Wn()),Ir(y.pop()))}function Ha(){return{position:[13.5,12.8,16.2],target:[0,1.15,.5],fov:38}}let Wa=null;function vf(d){if(ie)return;let y=pt.clamp(Number(d)||0,0,1);y>=1?(k.clippingPlanes=ee,be<1&&(k.shadowMap.enabled=xe,k.shadowMap.needsUpdate=!0)):(oe.constant=pt.lerp(-1.05,5.05,y),k.clippingPlanes=[oe],k.shadowMap.enabled&&(k.shadowMap.enabled=!1)),be=y,Me=!0}function Du(d){if(ie)return;let y=pt.clamp(Number(d)||0,0,1);Ie&&Lr(),Wa=y<1?y:null,he="overview",ve="",Ee=null,nc(),$e=!0;let I=ja(Ha());Y.position.copy(I.t).lerp(I.p,.38+.62*y),X.target.copy(I.t),Y.fov=I.fov,Y.updateProjectionMatrix(),Pt()}function Uu(d){if(d==="overview")return Le?{position:[7.8,17,12.8],target:[0,0,0],fov:40}:Ha();let y=se[d];if(!y||!y.visible)return Ha();let I=dn[d]?.getCenter(new D)||new D(0,1.6,0),b=y.localToWorld(I),A=new D(2.7,3.4,7.2).applyAxisAngle(new D(0,1,0),y.rotation.y);return{position:Ds(b.clone().add(A)).toArray(),target:b.toArray(),fov:40,focusId:d}}function Nu(){return[...Se,...Object.values(xi),...Le?[]:pn.meshes].filter(d=>{for(let y=d;y;y=y.parent)if(!y.visible)return!1;return!0})}function ja(d){let y=new D(...d.position),I=new D(...d.target);if(Y.aspect<1.25&&y.sub(I).multiplyScalar(1+(1.25-Y.aspect)*.64).add(I),d.focusId){Q.updateMatrixWorld(!0);let b=Nu(),A=y.clone().sub(I),re=[[0,0],[-.5,0],[.5,0],[-.9,1],[.9,1],[0,4]],q=ka(d.focusId).getSize(new D).multiplyScalar(.37),ae=[I,I.clone().add(new D(q.x,0,0)),I.clone().add(new D(-q.x,0,0)),I.clone().add(new D(0,0,q.z)),I.clone().add(new D(0,0,-q.z)),I.clone().add(new D(0,q.y,0))],me=-1;for(let[W,pe]of re){let je=Ds(A.clone().applyAxisAngle(new D(0,1,0),W).add(I));je.y+=pe;let ce=0;for(let De of ae){Qn.set(je,De.clone().sub(je).normalize()),Qn.far=je.distanceTo(De)+.1;let rt=Qn.intersectObjects(b,!1)[0];(!rt||rt.object.userData.station===d.focusId)&&ce++}if(ce>me&&(me=ce,y.copy(je)),ce===ae.length)break}}return{p:y,t:I,fov:d.fov||38}}function nc(){$e||(X.enableDamping=!1,X.update(),X.enableDamping=!0),Y.up.set(0,1,0)}function Ou(d,y=1.45){let I=ja(d);if(nc(),$e=!0,ve="",nn||Y.position.distanceToSquared(I.p)<1e-5)Y.position.copy(I.p),X.target.copy(I.t),Y.fov=I.fov,Y.updateProjectionMatrix(),Ee=null;else{let b=Y.position.clone(),A=X.target.clone(),re=b.clone().lerp(I.p,.5),q=b.distanceTo(I.p);re.y+=Math.min(4,q*.26),re.x+=Math.min(2.8,q*.18),Ee={curve:new dr([b,re,I.p]),start:A,end:I.t,fov:Y.fov,endFov:I.fov,duration:y,time:0}}Pt()}function Lr(){Ie=!1,Me=!0,_.onTourChange?.(!1),_.onShotChange?.("自由观察"),_.onAtmosphereChange?.()}function Ls(d){Wa=null,Lr(),ve="",he=v[d]?d:"overview",_.onFocusChange?.(he),Ou(Uu(he))}function yf(d){if(d==="resident"&&!Le){pn.greet(Y.position),_.onResidentSelect?.();return}if(d==="entrance"){Hu();return}if(Le){tc(d);return}v[d]&&(Ls(d),_.onSelect?.(d==="art"?"album":d))}function Ds(d){d.x=Math.max(-5.25,d.x),d.z=Math.max(-3.85,d.z),d.y=Math.max(1.35,d.y);for(let y of Object.keys(S).filter(I=>I!=="rug"&&se[I].visible)){let I=ka(y).expandByScalar(.3);d.x>I.min.x&&d.x<I.max.x&&d.z>I.min.z&&d.z<I.max.z&&(d.y=Math.max(d.y,I.max.y+.3))}return d}function ic(){Ue=(Ue+1)%m.length;let d=m[Ue],y=se[d.anchor],I=new D(...d.target);y&&y.localToWorld(I);let b=d.points.map(q=>{let ae=new D(...q);return y&&y.localToWorld(ae),Ds(ae)});nc(),$e=!0;let A=Y.position.clone(),re=A.clone().lerp(b[0],.5);re.y=Math.max(A.y,b[0].y)+1,Ee={curve:new dr([A,re,...b],!1,"centripetal"),start:X.target.clone(),end:I,fov:Y.fov,fovs:[Y.fov,Y.fov,...d.fovs],endFov:d.fovs.at(-1),duration:d.seconds,time:0,bank:d.bank,cinematic:!0},_.onShotChange?.(d.label),za(0),_.onAtmosphereChange?.()}function xf(){return Ie?(Lr(),Ee=null,!1):Le?!1:nn?(_.onShotChange?.("已开启减少动态效果 · 可手动选择家具"),!1):(Ie=!0,ve="",he="overview",Ue=-1,_.onTourChange?.(!0),_.onFocusChange?.("overview"),ic(),!0)}function Us(){let d=ve==="resident"?{label:pn.getState().label+" · 查看角色"}:ve==="entrance"?{label:_t?"关上房门":"打开房门"}:Le&&S[ve]?{label:S[ve]}:v[ve];$n.hidden=!d||Ie||!!Bt||!!Ee,!$n.hidden&&($n.textContent=!Le&&Gn?.title?Gn.title:d.label,$n.style.left=`${Math.max(10,Math.min(Ge-138,Vn.x+14))}px`,$n.style.top=`${Math.max(10,Math.min(ot-38,Vn.y-36))}px`)}function Pt(d=!0){if(ie)return;let y=!$e&&X.enabled?X.update():!1;if(!d&&!y&&!Me)return;Me=!1;let I=Le?it:ve,b=se[I];vn.visible=!!b?.visible&&!Ie&&!Ee&&(Le||!Bt),vn.material.opacity=Le?.85:.32,vn.material.color.set(tn&&Le?"#ca6859":"#dfb55d"),b&&vn.box.copy(dn[I]?ka(I):new $t().setFromObject(b)).expandByScalar(.035),$e&&Y.lookAt(X.target),k.render(Q,Y),Us()}function Fu(d){if(!ue||ie)return;let y=Math.max(0,(d-at)/1e3);if(at=d,Ee){Me=!0,Ee.time+=y;let A=Math.min(1,Ee.time/Ee.duration),re=Ee.cinematic?A:pt.clamp(A*A*A*(A*(A*6-15)+10),0,1);if(Y.position.copy(Ee.curve.getPointAt(re)),Ee.cinematic&&Ds(Y.position),X.target.lerpVectors(Ee.start,Ee.end,Ee.cinematic?Math.min(1,A*2.6)**.7:re),Ee.fovs){let q=A*(Ee.fovs.length-1),ae=Math.min(Ee.fovs.length-2,Math.floor(q));Y.fov=pt.lerp(Ee.fovs[ae],Ee.fovs[ae+1],q-ae)}else Y.fov=pt.lerp(Ee.fov,Ee.endFov,re);Y.up.set(Math.sin(Math.PI*A)*(Ee.bank||0),1,0).normalize(),Y.updateProjectionMatrix(),A>=1&&(Ee=null,Ie&&ic())}let I=Tt;Tt=nn?he==="wardrobe"?1:0:pt.damp(Tt,he==="wardrobe"?1:0,5,y),Math.abs(I-Tt)>1e-4&&(Me=!0,k.shadowMap.needsUpdate=!0);for(let A of de)A.group.rotation.y=A.side*Tt*1.65;let b=dt;dt=nn?Number(_t):pt.damp(dt,Number(_t),4.5,y),kn.rotation.y=dt===0?0:-dt*Math.PI*.55,Math.abs(b-dt)>1e-4&&(Me=!0,k.shadowMap.needsUpdate=!0),za(y),Hn+=y,pn.tick(y,{paused:Le,reduced:nn,viewer:Y.position})&&(Me=!0,Hn>=.16&&(k.shadowMap.needsUpdate=!0,Hn=0)),Pt(!1),fe=requestAnimationFrame(Fu)}function Xa(){if(ie)return;let d=Math.max(1,x.clientWidth),y=Math.max(1,x.clientHeight);if(!(d===Ge&&y===ot)){if(Ge=d,ot=y,Y.aspect=Ge/ot,Y.updateProjectionMatrix(),k.setSize(Ge,ot,!1),Wa!==null){Du(Wa);return}if(!Ie){let I=ja(Uu(he));Y.position.copy(I.p),X.target.copy(I.t),Y.up.set(0,1,0),Y.fov=I.fov,Y.updateProjectionMatrix(),$e=!0,Ee=null}Pt()}}function rc(d){let y=!!d&&!document.hidden;ie||y===ue||(ue=y,ue?(Xa(),at=performance.now(),fe=requestAnimationFrame(Fu)):(Ns(),cancelAnimationFrame(fe),fe=0),za(0),_.onAtmosphereChange?.())}function qa(d,y=!1){let I=["night","dusk","dawn"].includes(d)?d:"day";if(!y&&I===ei&&Q.background)return;I!==ei&&zt&&Cs(),ei=I;let b=I==="night",A=I==="dusk",re=I==="dawn",q=["rain","storm","snow","mist","cloudy"].includes(mn),ae=mn==="mist",me=mn==="storm",W=mn==="snow",pe=b?q?"#293a4a":"#253a49":A?q?"#bab9c1":"#dcc8bb":re?q?"#c4ced0":"#e0dacc":ae?"#d1ded9":W?"#d2e0e5":me?"#93a8b2":q?"#bdcec9":"#cadbd2";Q.background=new He(pe),Q.fog=new Ks(Q.background,ae?22:me?25:27,ae?43:me?56:66),li.material.color.set(W?"#e6eff2":b?"#334943":A?"#a9aa86":q?"#8e9f86":"#95a886"),br.intensity=b?.95:A?1.65:re||me?1.8:q?2.25:2.5,br.color.set(b?"#b6cce6":A?"#f0d8cf":re?"#e9e2d9":"#e7f2ef"),un.intensity=b?.48:me?.7:q?1.3:A?2.3:re?2.6:4.1,un.position.set(...re?[7,6,-4]:A?[-8,6,3]:[-3,9,6]),un.color.set(b?"#a8c9ef":q?"#d4e6ef":A?"#ffbb83":re?"#ffe0af":"#fff0ce"),Sr.intensity=b?.55:q?.9:1.1,Ui.intensity=b?24:A?14:re?10:me?12:6,Tr.intensity=b?18:A?10:re?7:me?9:4,Zl.material.color.set(b?"#243c60":A&&!q?"#e8b793":re&&!q?"#efd5b5":W?"#cddddd":ae?"#c2d3d0":me?"#718c9d":q?"#8eacb7":"#9ecacc"),Es.visible=!q,Es.material.color.set(b?"#eee6c6":"#fff0bf"),Ua.visible=q,Ua.children.forEach(je=>je.material.color.set(b?"#647787":"#dbe6e5")),Na.visible=["rain","snow","storm"].includes(mn),Su.forEach(je=>{let ce=mn==="snow";je.scale.set(ce?.055:.023,ce?.055:.15,.023),je.material.color.set(ce?"#fcf7ef":"#d2e7eb")}),Er.setWeather(mn,ei),x.dataset.weather=mn,x.dataset.light=ei,k.shadowMap.needsUpdate=!0,Pt()}function Ya(d){let y=k.domElement.getBoundingClientRect();Mn.set((d.clientX-y.left)/y.width*2-1,-(d.clientY-y.top)/y.height*2+1),tt.setFromCamera(Mn,Y),Q.updateMatrixWorld(!0);let I=tt.intersectObjects(Nu(),!1)[0]?.object?.userData;Gn=!Le&&I?.roomObject?{ref:I.roomObject,title:I.title}:null;let b=I?.station||"";return v[b]||b==="entrance"||!Le&&b==="resident"||Le&&S[b]?b:""}function Bu(d,y){Ya(d);let I=Wt[y],b=se[y],A=I==="back-wall"?new Zt(new D(0,0,1),-b.position.z):I==="left-wall"?new Zt(new D(1,0,0),-b.position.x):Rn;return tt.ray.intersectPlane(A,new D)}function zu(d){if(d.button===0){if(Le){let y=Ya(d),I=S[y]?Bu(d,y):null;S[y]&&I&&(d.stopImmediatePropagation(),d.preventDefault(),Ee=null,tc(y),X.enabled=!1,Be={id:y,before:Wn(),offset:se[y].position.clone().sub(I),pointerId:d.pointerId},k.domElement.setPointerCapture(d.pointerId))}Bt={x:d.clientX,y:d.clientY,id:d.pointerId,moved:!1},ve="",Me=!0,Us()}}function ku(d){if(Bt&&Math.hypot(d.clientX-Bt.x,d.clientY-Bt.y)>7&&(Bt.moved=!0),Be&&d.pointerId===Be.pointerId){let y=Bu(d,Be.id);y&&Bt?.moved&&(y.add(Be.offset),ec(Be.id,{...Wn().items[Be.id],x:Math.round(y.x*4)/4,y:Math.round(y.y*4)/4,z:Math.round(y.z*4)/4}),rr(),Pt());return}if(!Bt&&d.pointerType!=="touch"){let y=k.domElement.getBoundingClientRect();Vn.x=d.clientX-y.left,Vn.y=d.clientY-y.top;let I=Ya(d);ve!==I&&(Me=!0),ve=I,k.domElement.style.cursor=ve?"pointer":"grab",Us()}}function Vu(d){if(Be&&d.pointerId===Be.pointerId){let y=Be.before;Be=null,Bt=null,X.enabled=!0,k.domElement.hasPointerCapture(d.pointerId)&&k.domElement.releasePointerCapture(d.pointerId),Rs(y),Pt();return}if(Bt&&Bt.id===d.pointerId&&!Bt.moved){let y=Ya(d);!Le&&Gn?_.onObjectSelect?.(structuredClone(Gn.ref)):y&&yf(y)}Bt=null}function Ns(){if(Be){let{before:d,pointerId:y}=Be;Be=null,X.enabled=!0,Ir(d),k.domElement.hasPointerCapture(y)&&k.domElement.releasePointerCapture(y)}Bt=null}function Za(d){Be&&d.type==="pointerleave"||(Ns(),ve="",Me=!0,Us())}function Gu(){Lr(),Ee=null,$e=!1,Y.up.set(0,1,0),ve="",Us()}function Hu(d,y=!0){let I=typeof d=="boolean"?d:!_t;return I===_t?_t:(_t=I,x.dataset.doorOpen=String(I),Me=!0,nn&&(dt=Number(I),kn.rotation.y=I?-Math.PI*.55:0,k.shadowMap.needsUpdate=!0,Pt()),y&&_.onDoorChange?.(I),I)}function sc(d){nn=wr||d.matches,nn&&(Lr(),Ee=null,Ls(he),Ba(0)),Me=!0,Pt(),_.onAtmosphereChange?.()}function Wu(d){d.preventDefault(),rc(!1),_.onError?.("显卡连接中断，请重试加载小屋")}let jn=k.domElement;jn.addEventListener("pointerdown",zu,!0),jn.addEventListener("pointermove",ku),jn.addEventListener("pointerup",Vu),jn.addEventListener("pointercancel",Za),jn.addEventListener("pointerleave",Za),jn.addEventListener("webglcontextlost",Wu),X.addEventListener("start",Gu),Ts?.addEventListener?.("change",sc);let ju=new ResizeObserver(Xa);ju.observe(x);let Xu=ja(Ha());return Y.position.copy(Xu.p),X.target.copy(Xu.t),qa(_.light),Ir(_.layout),Xa(),_.onTourChange?.(!1),_.onShotChange?.("自由观察"),x.dataset.doorOpen="false",{focus:Ls,resize:Xa,setActive:rc,setLight:qa,toggleTour:xf,setEntranceProgress:Du,setConstructionProgress:vf,setStationLabels(d){for(let[y,I]of Object.entries(d||{}))S[y]&&typeof I=="string"&&(v[y]={...v[y],label:I});Me=!0,Pt()},setReducedMotion(d){wr=!!d,sc({matches:!!Ts?.matches})},setAtmosphere:af,getAmbientState:sf,resetAtmosphere:of,encounter:Au,nextShot(){return Le||nn?!1:(Ie=!0,he="overview",ve="",_.onTourChange?.(!0),ic(),!0)},getLayout:Wn,setEditing:gf,selectFurniture:tc,updateFurniture:ff,setFurnitureStored:mf,updateHouseStyle:cf,undoEdit:_f,toggleDoor:Hu,setFurnitureCatalog:Iu,setRoomTraces:pf,setResident(d){pn.setContext(d),pn.tick(0,{paused:Le,reduced:nn}),Me=!0,k.shadowMap.needsUpdate=!0,Pt()},getResidentState(){return pn.getState()},focusResident(){if(Le||!pn.getState().visible)return;let d=pn.getState(),{x:y,z:I}=d.position,b=d.appearance?.height||1,A=d.phase==="seated"?d.facing-1.05:d.facing+.6,re=d.phase==="seated"?2.25:3,q=Ds(new D(y+Math.sin(A)*re,2.2*b,I+Math.cos(A)*re));Lr(),Ou({position:q.toArray(),target:[y,1.35*b,I],fov:42}),pn.greet(q)},getCatalog(){return{furniture:{...S},styles:{...o},surfaces:{...n},objectModels:structuredClone(E),houseStyles:Object.fromEntries(Object.entries(p).map(([d,y])=>[d,{...y}])),styleDetails:Object.fromEntries(Object.entries(l).map(([d,y])=>[d,{note:y.note,models:Object.fromEntries(Object.keys(S).map((I,b)=>[I,y.models[b]]))}]))}},setLayout(d){Ns(),St=[],qe=[],Ir(d)},restoreDefaults(){if(!Le)return;let d=Wn();Ir({version:1,items:Lt}),Rs(d)},reset(){Ns(),Ls("overview")},getState(){return{editing:Le,editId:it,houseStyle:Yt,placementBlocked:tn,placementMessage:en,storedFurniture:[...j,...z],roomTraces:Object.fromEntries(Object.entries(xi).map(([d,y])=>[d,structuredClone(y.userData.roomObject)])),layoutRepairs:[...nr],placementIssues:Object.fromEntries(Object.keys(S).filter(d=>se[d].visible).map(d=>[d,Ps(d)]).filter(([,d])=>d)),doorOpen:_t,doorAngle:kn.rotation.y,tourRunning:Ie,shotIndex:Ue,moving:!!Ee,constructionProgress:be,camera:{position:Y.position.toArray(),target:X.target.toArray(),fov:Y.fov,up:Y.up.toArray()}}},dispose(){ie||(rc(!1),ie=!0,ju.disconnect(),Ts?.removeEventListener?.("change",sc),bn++,Is("photo"),Is("work"),pn.dispose(),Er.dispose(),X.removeEventListener("start",Gu),X.dispose(),jn.removeEventListener("pointerdown",zu,!0),jn.removeEventListener("pointermove",ku),jn.removeEventListener("pointerup",Vu),jn.removeEventListener("pointercancel",Za),jn.removeEventListener("pointerleave",Za),jn.removeEventListener("webglcontextlost",Wu),Se.forEach(d=>d.dispose()),K.dispose(),te.dispose(),fn.forEach(d=>d.dispose()),li.geometry.dispose(),li.material.dispose(),vn.geometry.dispose(),vn.material.dispose(),U.geometry.dispose(),U.material.dispose(),k.dispose(),x.replaceChildren(),r.delete(x))}}}return{mount(x,_={}){if(r.has(x))return r.get(x);let v=g(x,_);return r.set(x,v),v}}})();})();
/**
 * @license
 * Copyright 2010-2026 Three.js Authors
 * SPDX-License-Identifier: MIT
 */
