# 코딱지 효과음 + BGM 생성기 (numpy). 사용: python gen_audio.py <출력폴더>
import numpy as np, wave, sys, os
OUT=sys.argv[1] if len(sys.argv)>1 else "."
os.makedirs(OUT,exist_ok=True)
SR=44100
def wr(name,x,vol):
    x=np.clip(x/(np.max(np.abs(x))+1e-9)*vol,-1,1)
    with wave.open(os.path.join(OUT,name),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR)
        w.writeframes((x*32767).astype(np.int16).tobytes())
def env(n,a=0.005,r=0.08):
    e=np.ones(n); ai=int(a*SR); ri=int(r*SR)
    if ai: e[:ai]=np.linspace(0,1,ai)
    e[-ri:]*=np.linspace(1,0,ri); return e
def sweep(f0,f1,d,shape='sq',vib=0,curve=1.0,duty=0.5):
    n=int(d*SR); t=np.arange(n)/SR; p=(t/d)**curve; f=f0+(f1-f0)*p
    if vib: f=f*(1+0.03*np.sin(2*np.pi*vib*t))
    ph=np.cumsum(f)/SR
    if shape=='sq': w=np.where((ph%1)<duty,1.0,-1.0)
    elif shape=='tri': w=2*np.abs(2*(ph%1)-1)-1
    else: w=np.sin(2*np.pi*ph)
    return w*env(n,0.004,min(0.06,d*0.5))
def cat(*xs,gap=0.0):
    out=[]
    for x in xs:
        out.append(x)
        if gap: out.append(np.zeros(int(gap*SR)))
    return np.concatenate(out)
def sfx(name,x,vol=0.35): wr(name,np.convolve(x,np.ones(4)/4,'same'),vol)
sfx('pickup.wav', sweep(420,1250,0.13,'sq',curve=0.6,duty=0.25))
sfx('place.wav', sweep(900,380,0.12,'sq',curve=1.4,duty=0.25))
sfx('correct.wav', cat(sweep(880,880,0.07,'sq',duty=0.25),sweep(1320,1320,0.14,'sq',duty=0.25)))
sfx('wrong.wav', cat(sweep(220,180,0.11,'sq',duty=0.5),sweep(180,140,0.16,'sq',duty=0.5),gap=0.03),0.3)
sfx('clear.wav', cat(*[sweep(f,f,0.08 if i<3 else 0.3,'sq',duty=0.25) for i,f in enumerate([523,659,784,1047])]))
sfx('talk.wav', sweep(700,760,0.035,'tri'),0.25)
sfx('click.wav', sweep(1500,1100,0.03,'sq',duty=0.5),0.25)
sfx('enter.wav', sweep(300,1600,0.35,'tri',vib=18,curve=1.8),0.3)
sfx('boing.wav', cat(sweep(350,1100,0.09,'sq',curve=0.5,duty=0.25),sweep(1100,600,0.12,'sq',vib=25,duty=0.25)))
np.random.seed(7)
BPM=132; STEP=60/BPM/4
def nf(n): return 440*2**((n-69)/12)
def tone(f,d,shape,duty=0.25,vol=1.0,dec=0.0,att=0.003,rel=0.02,vib=0):
    n=int(d*SR); t=np.arange(n)/SR
    ff=f*(1+0.006*np.sin(2*np.pi*vib*t)) if vib else np.full(n,f)
    ph=np.cumsum(ff)/SR
    if shape=='sq': w=np.where((ph%1)<duty,1.,-1.)
    elif shape=='tri': w=2*np.abs(2*(ph%1)-1)-1
    else: w=np.random.uniform(-1,1,n)
    e=np.ones(n); a=int(att*SR); r=min(int(rel*SR),n)
    if a: e[:a]=np.linspace(0,1,a)
    e[-r:]*=np.linspace(1,0,r)
    if dec: e*=np.exp(-t*dec)
    return w*e*vol
bars=16; total=int(bars*16*STEP*SR)+SR; mix=np.zeros(total)
def put(step,x):
    i=int(step*STEP*SR); j=min(total,i+len(x)); mix[i:j]+=x[:j-i]
prog=[(48,[60,64,67]),(45,[57,60,64]),(41,[57,60,65]),(43,[59,62,67])]*2+[(41,[57,60,65]),(43,[59,62,67]),(48,[60,64,67]),(45,[57,60,64]),(41,[57,60,65]),(43,[59,62,67]),(48,[60,64,67]),(43,[59,62,67])]
A=[(0,2,72),(2,2,76),(4,2,79),(6,1,76),(7,1,79),(8,4,84),(12,2,83),(14,2,79)]
B=[(0,2,81),(2,2,79),(4,2,76),(6,2,72),(8,3,74),(11,1,76),(12,4,72)]
C=[(0,1,77),(1,1,79),(2,2,81),(4,2,77),(6,2,72),(8,2,74),(10,2,77),(12,4,81)]
D=[(0,2,79),(2,1,77),(3,1,76),(4,2,74),(6,2,71),(8,2,74),(10,2,79),(12,2,83),(14,2,86)]
E=[(0,1,84),(1,1,83),(2,1,81),(3,1,79),(4,4,77),(8,2,76),(10,2,77),(12,4,79)]
F=[(0,2,76),(2,2,74),(4,2,72),(6,2,74),(8,8,72)]
mel=[A,B,C,D,A,B,E,F,C,D,A,B,C,D,E,F]
for b,(root,ch) in enumerate(prog):
    s0=b*16
    for st,n in [(0,root),(4,root+7),(6,root),(8,root+12),(12,root+7),(14,root+12)]:
        put(s0+st,tone(nf(n),STEP*1.7,'tri',vol=0.55,rel=0.03))
    for st in range(16): put(s0+st,tone(nf(ch[st%3]+12),STEP*0.8,'sq',duty=0.125,vol=0.07,dec=18))
    for st,ln,n in mel[b]:
        put(s0+st,tone(nf(n),STEP*ln*0.92,'sq',duty=0.25,vol=0.24,vib=5.5,rel=0.03))
        put(s0+st+3,tone(nf(n),STEP*ln*0.6,'sq',duty=0.25,vol=0.06,rel=0.03))
    for st in range(0,16,2): put(s0+st,tone(0,0.02,'noise',vol=0.06,dec=150))
    for st in (0,8): put(s0+st,tone(nf(36),0.09,'tri',vol=0.5,dec=30))
    for st in (4,12): put(s0+st,tone(0,0.06,'noise',vol=0.14,dec=45))
    if b%2==1:
        for st in (13,14,15): put(s0+st,tone(nf(96+((st*5)%7)),0.025,'sq',duty=0.5,vol=0.05))
L=int(bars*16*STEP*SR); tail=mix[L:]; mix=mix[:L]; mix[:len(tail)]+=tail
wr('bgm_kkodakji_loop.wav',np.convolve(mix,np.ones(3)/3,'same'),0.7)
print("ok",OUT)
