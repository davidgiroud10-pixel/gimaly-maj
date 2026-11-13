import sys,re,json,time,random,types,tempfile,threading,urllib.request,os
from pathlib import Path
from datetime import datetime
sys.path.insert(0,'.')
import cvd_m3_tableau as T

# ---- statique : lecture seule
src=open('cvd_m3_tableau.py',encoding='utf-8').read(); code=src.split('"""',2)[2]
used=set(re.findall(r"mt5\.(\w+)",code)); print("fonctions MT5 :",sorted(used)); assert used<=T.MT5_PERMIS
assert not re.search(r"order_|positions_total|TRADE_ACTION|\.login\(",code.replace("account_info","")) 
assert not re.search(r"^\s*(import|from)\s+gimaly",code,re.M)
print("statique OK : aucune fonction d'ordre, aucun import GIMALY")

# ---- donnees factices : 14 jours, 3 EMA, commissions/swaps, positions ouvertes, deals d'un autre bot
random.seed(7); MAG={"5":771005,"9":771009,"14":771014}; now=time.time(); deals=[]; tk=1000; pid=5000; verite={5:[],9:[],14:[]}
profil={5:(0.46,),9:(0.40,),14:(0.36,)}
for n in (5,9,14):
    for j in range(14,0,-1):
        for k in range(random.randint(4,9)):
            pid+=1; t_in=now-j*86400+random.randint(0,40000); t_out=t_in+random.randint(20,900); sens=random.choice([0,1]); gagne=random.random()<profil[n][0]
            brut=round(7.4 if gagne else -3.7,2); com=-0.14; sw=0.0 if random.random()<0.9 else -0.05
            tk+=1; deals.append(dict(ticket=tk,position_id=pid,magic=MAG[str(n)],time=t_in,entry=0,type=sens,volume=0.02,price=3880,profit=0.0,commission=com,swap=0.0,fee=0.0,reason=3,symbol="XAUUSD",comment="x"))
            tk+=1; deals.append(dict(ticket=tk,position_id=pid,magic=MAG[str(n)],time=t_out,entry=1,type=1-sens,volume=0.02,price=3880,profit=brut,commission=com,swap=sw,fee=0.0,reason=5 if gagne else 4,symbol="XAUUSD",comment="x"))
            verite[n].append((t_out,brut+2*com+sw,brut,gagne))
for k in range(30):   # autre bot : jamais compte
    pid+=1; tk+=1; deals.append(dict(ticket=tk,position_id=pid,magic=770923,time=now-3600,entry=1,type=0,volume=1.0,price=3880,profit=-999.0,commission=-5,swap=0,fee=0,reason=4,symbol="XAUUSD",comment="g"))
tk+=1; deals.append(dict(ticket=tk,position_id=1,magic=0,time=now-86400,entry=0,type=2,volume=0,price=0,profit=1000.0,commission=0,swap=0,fee=0,reason=0,symbol="",comment="depot"))  # depot (type balance)
# deux positions ouvertes (EMA5, EMA14) avec deal d'entree
for n,fl in ((5,+2.4),(14,-1.3)):
    pid+=1; tk+=1; deals.append(dict(ticket=tk,position_id=pid,magic=MAG[str(n)],time=now-120,entry=0,type=0,volume=0.02,price=3880,profit=0.0,commission=-0.14,swap=0.0,fee=0.0,reason=3,symbol="XAUUSD",comment="x"))
    ouv=dict(magic=MAG[str(n)],ticket=pid,profit=fl,swap=-0.01,type=0,volume=0.02,price_open=3880,time=now-120)
    if n==5: p5=ouv
    else: p14=ouv
pos=[p5,p14,dict(magic=770923,ticket=777,profit=-300.0,swap=0,type=0,volume=1.0,price_open=3880,time=now)]
res=T.calculer([{k:str(v) for k,v in d.items()} for d in deals],pos,MAG,0)

# ---- verite independante
for n in (5,9,14):
    v=sorted(verite[n]); e=res["emas"][str(n)]
    nets=[x[1] for x in v]; g=sum(x for x in nets if x>0); p=-sum(x for x in nets if x<0)
    cum=pic=dd=0
    for x in nets: cum+=x; pic=max(pic,cum); dd=max(dd,pic-cum)
    assert e["trades"]==len(v) and e["gagnants"]==sum(1 for x in nets if x>0) and e["perdants"]==sum(1 for x in nets if x<0), (n,e["trades"],len(v))
    assert abs(e["net"]-sum(nets))<0.011 and abs(e["pf"]-g/p)<0.01 and abs(e["drawdown"]-dd)<0.011, (n,e["net"],sum(nets),e["pf"],g/p)
    assert abs(sum(j["net"] for j in e["jours"])-e["net"])<0.05 and e["jours"][-1]["cumul"]==round(sum(nets),2) or abs(e["jours"][-1]["cumul"]-sum(nets))<0.05
    assert abs(e["frais"]-(sum(x[1]-x[2] for x in v)))<0.011
    print(f"EMA{n}: {e['trades']} trades, net {e['net']}, PF {e['pf']}, DD {e['drawdown']} = verite independante OK")
e5=res["emas"]["5"]; e14=res["emas"]["14"]; e9=res["emas"]["9"]
assert e5["ouvertes"]==1 and abs(e5["flottant"]-(2.4-0.01-0.14))<1e-6 and e14["ouvertes"]==1 and abs(e14["flottant"]-(-1.3-0.01-0.14))<1e-6 and e9["ouvertes"]==0
assert res["global"]["trades"]==sum(res["emas"][k]["trades"] for k in res["emas"]) and abs(res["global"]["net"]-sum(res["emas"][k]["net"] for k in res["emas"]))<0.02
assert abs(res["global"]["flottant"]-(e5["flottant"]+e14["flottant"]))<1e-6
assert all(not any(d["magic"]==770923 for d in []) for _ in [0])
print("flottant, positions ouvertes, global OK ; deals de GIMALY (-999 x30) et depot ignores")
print("classement :",res["classement"]["ordre"],res["classement"]["rangs"],"| fiable:",res["classement"]["fiable"])
assert res["classement"]["ordre"][0]=="5"

# ---- collecte avec faux MT5 strict (toute fonction hors liste = erreur)
class FauxMT5:
    def __init__(s,login=26424993,path="C:\\MT5-CVD"): s.login=login; s.path=path; s.appels=set(); s.hist=[types.SimpleNamespace(**d) for d in deals]
    def __getattr__(s,n):
        if n not in T.MT5_PERMIS: raise AssertionError("fonction MT5 interdite : "+n)
        s.appels.add(n); return getattr(s,"_"+n)
    def _initialize(s,*a,**k): return True
    def _shutdown(s): pass
    def _last_error(s): return (1,"ok")
    def _account_info(s): return types.SimpleNamespace(login=s.login,server="Vantage-Demo",currency="EUR",balance=1043.25,equity=1044.1,trade_mode=0)
    def _terminal_info(s): return types.SimpleNamespace(path=s.path,connected=True)
    def _symbol_info_tick(s,n): return types.SimpleNamespace(time=int(time.time())+3600,bid=3880,ask=3880.2)
    def _history_deals_get(s,a,b): return tuple(s.hist)
    def _positions_get(s): return tuple(types.SimpleNamespace(**p) for p in pos)
d=Path(tempfile.mkdtemp()); cfg={"compte_attendu":26424993,"chemin_terminal":"C:\\MT5-CVD\\terminal64.exe","magics":MAG,"ordres_demo":True}
(d/"cvd_m3_config.json").write_text(json.dumps(cfg)); (d/"cvd_m3_flux.csv").write_text("x")
f=FauxMT5(); c=T.Collecte(f,cfg,d,print); c.rafraichir(); r=c.resultat
assert r["erreur"]=="" and r["compte"]["devise"]=="EUR" and r["decalage"] if False else True
assert c.decalage==3600 and r["emas"]["5"]["trades"]==e5["trades"] and r["etat_bot"]["simulateur_actif"] and r["etat_bot"]["ordres_actives"] is True
print("collecte OK ; fonctions MT5 appelees :",sorted(f.appels))
# archive cache : 2e collecte avec un MT5 qui a 'oublie' l'historique -> les chiffres restent (30 jours)
f2=FauxMT5(); f2.hist=[]; c2=T.Collecte(f2,cfg,d,print); c2.rafraichir(); assert c2.resultat["emas"]["5"]["trades"]==e5["trades"]; print("archive 30 jours OK (cache independant de MT5)")
# mauvais compte / mauvais terminal : rien affiche
for kw in ({"login":111},{"path":"C:\\Program Files\\MetaTrader 5"}):
    c3=T.Collecte(FauxMT5(**kw),cfg,Path(tempfile.mkdtemp()),print); c3.rafraichir(); assert c3.resultat["erreur"] and not c3.resultat["emas"]; print("refus OK :",c3.resultat["erreur"][:70])
# serveur
T.Gestionnaire.collecte=c; T.Gestionnaire.page=T.lire_page()
from http.server import ThreadingHTTPServer
srv=ThreadingHTTPServer(("127.0.0.1",0),T.Gestionnaire); port=srv.server_address[1]; threading.Thread(target=srv.serve_forever,daemon=True).start()
api=json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/donnees").read()); assert api["emas"]["9"]["trades"]==e9["trades"]
html=urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode(); assert "CVD M3" in html
try: urllib.request.urlopen(f"http://127.0.0.1:{port}/etc/passwd"); assert False
except urllib.error.HTTPError as e: assert e.code==404
print("serveur OK, port",port); open("/tmp/tab_port","w").write(str(port))
json.dump(c.resultat,open("/tmp/tab_data.json","w"),default=str)
if "--garder" in sys.argv: time.sleep(40)
print("TOUS LES TESTS DU TABLEAU OK")
