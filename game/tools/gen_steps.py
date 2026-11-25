import numpy as np, wave, sys, os
OUT=sys.argv[1] if len(sys.argv)>1 else "."
os.makedirs(OUT,exist_ok=True)
SR=44100
def wr(name,x,vol):
    x=np.convolve(x,np.ones(3)/3,'same')
    x=np.clip(x/(np.max(np.abs(x))+1e-9)*vol,-1,1)
    with wave.open(os.path.join(OUT,name),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR)
        w.writeframes((x*32767).astype(np.int16).tobytes())
def blip(f0,f1,d,duty=0.5,dec=0.0,shape='sq',curve=1.0):
    n=int(d*SR); t=np.arange(n)/SR; f=f0+(f1-f0)*(t/d)**curve
    ph=np.cumsum(f)/SR
    w=np.where((ph%1)<duty,1.,-1.) if shape=='sq' else 2*np.abs(2*(ph%1)-1)-1
    e=np.ones(n); a=int(0.002*SR); e[:a]=np.linspace(0,1,a); r=int(min(0.015,d*0.4)*SR); e[-r:]*=np.linspace(1,0,r)
    if dec: e*=np.exp(-t*dec)
    return w*e
wr('step_a.wav', blip(980,620,0.045,duty=0.25,dec=35),0.22)
wr('step_b.wav', blip(820,520,0.045,duty=0.25,dec=35),0.22)
wr('jump.wav', blip(260,1180,0.2,duty=0.25,curve=0.55),0.3)
wr('land.wav', blip(420,200,0.06,shape='tri',dec=25),0.28)
print('ok')
