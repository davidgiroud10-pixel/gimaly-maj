import sys,re,json,time,tempfile,types,math
from pathlib import Path
sys.path.insert(0,'.')
import cvd_m3_sim as S, cvd_m3_ordres as O

# ---------- 1) controles statiques
so=open('cvd_m3_ordres.py',encoding='utf-8').read(); ss=open('cvd_m3_sim.py',encoding='utf-8').read()
code_o=so.split('"""',2)[2]; code_s=ss.split('"""',2)[2]
assert "order_send" not in code_s and "order_check" not in code_s
assert code_o.count("mt5.order_send(")==1
fn=code_o[code_o.index("def _envoyer"):code_o.index("def _entree")]
assert "mt5.order_send(" in fn and "verifier_compte()" in fn and 'assert demande["magic"]' in fn
for interdit in ("TRADE_ACTION_SLTP","TRADE_ACTION_MODIFY","TRADE_ACTION_REMOVE","CLOSE_BY","TRADE_ACTION_PENDING",'"position":',"'position':","order_close","position_close"):
    assert interdit not in code_o, interdit
assert re.findall(r"TRADE_ACTION_\w+",code_o)==["TRADE_ACTION_DEAL"]
assert not re.search(r"^\s*(import|from)\s+gimaly",code_o+code_s,re.M)
print("statique OK : un seul order_send, ouverture au marche, aucune modification/fermeture, aucun import GIMALY")

# ---------- 2) faux MT5
class F:
    ACCOUNT_TRADE_MODE_DEMO=0; ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2; SYMBOL_TRADE_MODE_FULL=4
    TRADE_ACTION_DEAL=1; ORDER_TYPE_BUY=0; ORDER_TYPE_SELL=1; ORDER_TIME_GTC=0
    ORDER_FILLING_FOK=0; ORDER_FILLING_IOC=1; ORDER_FILLING_RETURN=2; POSITION_TYPE_BUY=0
    DEAL_REASON_SL=4; DEAL_REASON_TP=5
    def __init__(s):
        s.mode=0; s.margin=2; s.login=555; s.connecte=True; s.algo=True; s.stops=0; s.vmin=0.01; s.vstep=0.01
        s.bid=3880.0; s.ask=3880.2; s.envois=[]; s.positions=[]; s.deals=[]; s.retcode=10009; s.perdu=False; s.tk_none=False; s.n=100
    def account_info(s): return types.SimpleNamespace(login=s.login,server="Demo-1",trade_mode=s.mode,margin_mode=s.margin,balance=1000.0,currency="EUR",trade_allowed=True)
    def terminal_info(s): return types.SimpleNamespace(connected=s.connecte,trade_allowed=s.algo,path=getattr(s,"chemin","C:\\MT5"))
    def symbol_info(s,n): return types.SimpleNamespace(volume_min=s.vmin,volume_max=100,volume_step=s.vstep,point=0.01,digits=2,trade_stops_level=s.stops,trade_freeze_level=0,spread=20,trade_mode=4,filling_mode=3,trade_contract_size=100.0)
    def symbol_info_tick(s,n): return None if s.tk_none else types.SimpleNamespace(bid=s.bid,ask=s.ask,time=int(time.time()))
    def positions_get(s,symbol=None): return tuple(s.positions)
    def history_deals_get(s,*a,**k):
        if "position" in k: return tuple(d for d in s.deals if d.position_id==k["position"])
        return tuple(s.deals)
    def order_send(s,req):
        s.envois.append(req)
        if s.perdu:
            if s.perdu=="cree": s._creer(req)
            return None
        if s.retcode!=10009: return types.SimpleNamespace(retcode=s.retcode,comment="refuse",order=0,price=0,position=0)
        p=s._creer(req); return types.SimpleNamespace(retcode=10009,comment="Request executed",order=p.ticket,price=req["price"]+0.03,position=p.ticket)
    def _creer(s,req):
        s.n+=1; p=types.SimpleNamespace(ticket=s.n,magic=req["magic"],comment=req["comment"],type=req["type"],price_open=req["price"],profit=0.0,sl=req["sl"],tp=req["tp"]); s.positions.append(p); return p
def mk(cfg_extra=None, fake=None):
    d=Path(tempfile.mkdtemp()); rg=Path(tempfile.mkdtemp()); (rg/"config.local.yaml").write_text("trading_mt5_compte: 999\ntrading_magic: 770923\n")
    cfg=json.loads(json.dumps(O.CONFIG_DEFAUT)); cfg["ordres_demo"]=True; cfg["compte_attendu"]=555; cfg["chemin_terminal"]="C:\\MT5\\terminal64.exe"; cfg.update(cfg_extra or {})
    f=fake or F(); logs=[]
    o=O.Ordres(f,d,"XAUUSD",cfg,logs.append,rg); return o,f,d,logs,rg
def evt(n=5,sens="BUY",ms=1,age=0.0):
    return {"n":n,"sens":sens,"event_id":f"{n}-{ms}-{sens[0]}","ts_recu":time.time()-age,"bid":3880.0,"ask":3880.2,"cvd":10}
def rows(d,n): 
    import csv; p=d/f"cvd_m3_ema{n}_ordres.csv"
    return list(csv.DictReader(open(p,encoding="utf-8-sig"),delimiter=";")) if p.exists() else []

# desactive -> rien
o,f,d,l,_=mk({"ordres_demo":False}); assert not o.traiter(evt(),0.3,0.1) and not f.envois
# demo/hedging : un ordre, bons champs
o,f,d,l,_=mk(); assert O.CONFIG_DEFAUT["max_ouvertes_par_ema"]==3 and O.CONFIG_DEFAUT["max_ouvertes_total"]==6 and O.CONFIG_DEFAUT["ordres_demo"] is False
assert o.traiter(evt(5,"BUY",1),0.3,0.1); r=f.envois[0]
assert r["action"]==1 and r["type"]==0 and r["volume"]==0.02 and r["magic"]==771005 and "position" not in r and r["price"]==3880.2 and r["sl"]==3878.2 and r["tp"]==3884.2, r
assert o.traiter(evt(9,"SELL",2),0.3,0.1); r=f.envois[1]; assert r["type"]==1 and r["magic"]==771009 and r["price"]==3880.0 and r["sl"]==3882.0 and r["tp"]==3876.0
assert o.traiter(evt(14,"BUY",3),0.3,0.1) and f.envois[2]["magic"]==771014
assert len({x["magic"] for x in f.envois})==3 and 770923 not in {x["magic"] for x in f.envois}
assert rows(d,5)[0]["evenement"]=="ENTREE" and rows(d,5)[0]["ticket"]; print("ordres normaux OK (3 EMA, 3 magics)")
# doublon : meme evenement 2 fois (et apres redemarrage) -> 1 seul ordre
n0=len(f.envois); assert not o.traiter(evt(5,"BUY",1),0.3,0.1) and len(f.envois)==n0
o2=O.Ordres(f,d,"XAUUSD",o.cfg,lambda m:None,Path(tempfile.mkdtemp())); assert not o2.traiter(evt(5,"BUY",1),0.3,0.1) and len(f.envois)==n0; print("anti-doublon OK (meme apres redemarrage)")
# compte reel -> refus absolu ; netting ; meme compte que GIMALY ; terminal/algo ; compte attendu
for champ,val,mot in (("mode",2,"NON demo"),("margin",0,"hedging"),("connecte",False,"connecte"),("algo",False,"Algo"),("login",999,"GIMALY"),("login",777,"compte attendu"),("chemin","C:\\MT5-GIMALY","terminal configure")):
    o,f,d,l,_=mk({"compte_attendu":999} if (champ,val)==("login",999) else None); setattr(f,champ,val); assert not o.traiter(evt(),0.3,0.1) and not f.envois, champ; assert mot in rows(d,5)[0]["detail"], (champ,rows(d,5)[0]["detail"])
o,f,d,l,_=mk({"compte_attendu":123}); assert not o.traiter(evt(),0.3,0.1) and not f.envois
o,f,d,l,_=mk({"compte_attendu":0}); assert not o.traiter(evt(),0.3,0.1) and not f.envois and "obligatoire" in rows(d,5)[0]["detail"]
o,f,d,l,_=mk({"chemin_terminal":""}); assert not o.traiter(evt(),0.3,0.1) and not f.envois and "obligatoire" in rows(d,5)[0]["detail"]
o,f,d,l,_=mk({"chemin_terminal":"c:\\mt5\\"}); assert o.traiter(evt(),0.3,0.1)   # casse / separateur final sans importance
o,f,d,l,_=mk({"autoriser_compte_gimaly":True,"compte_attendu":999}); f.login=999; assert o.traiter(evt(),0.3,0.1)
# le compte devient reel ENTRE l'autorisation et l'envoi : refus quand meme
o,f,d,l,_=mk(); orig=o._autoriser
def piege(e,a,b):
    r=orig(e,a,b); f.mode=2; return r
o._autoriser=piege; assert not o.traiter(evt(),0.3,0.1) and not f.envois; print("compte reel refuse (controle avant chaque ordre + juste avant l'envoi) OK")
# donnees / prix / signal perimes, pause
o,f,d,l,_=mk(); assert not o.traiter(evt(ms=1),9.0,0.1) and not o.traiter(evt(ms=2),0.3,9.0) and not o.traiter(evt(ms=3,age=5),0.3,0.1) and not o.traiter(evt(ms=4),None,0.1) and not f.envois
f.tk_none=True; assert not o.traiter(evt(ms=5),0.3,0.1) and not f.envois; f.tk_none=False
(d/"cvd_m3_pause_entrees.flag").write_text("x"); assert not o.traiter(evt(ms=6),0.3,0.1) and not f.envois
(d/"cvd_m3_pause_entrees.flag").unlink(); assert o.traiter(evt(ms=7),0.3,0.1); print("perime/pause/reprise OK")
# limites + positions d'un autre bot ignorees
o,f,d,l,_=mk({"max_ouvertes_par_ema":2,"max_ouvertes_total":3})
for k in range(30): f.positions.append(types.SimpleNamespace(ticket=900+k,magic=770923,comment="GIMALY",type=0,price_open=3880,profit=-50.0,sl=0,tp=0))
assert o.traiter(evt(5,ms=1),.3,.1) and o.traiter(evt(5,ms=2),.3,.1) and not o.traiter(evt(5,ms=3),.3,.1)
assert o.traiter(evt(9,ms=4),.3,.1) and not o.traiter(evt(14,ms=5),.3,.1)   # total 3 atteint (les 30 positions GIMALY ne comptent pas)
assert len([p for p in f.positions if p.magic==770923])==30; print("limites OK ; positions GIMALY ignorees")
# perte du jour
o,f,d,l,_=mk({"perte_jour_max":50}); f.deals=[types.SimpleNamespace(magic=771005,entry=1,profit=-60.0,commission=0,swap=0,time=int(time.time()),position_id=1)]
assert not o.traiter(evt(),.3,.1) and "perte du jour" in rows(d,5)[0]["detail"]
o,f,d,l,_=mk({"perte_jour_max":50}); f.deals=[types.SimpleNamespace(magic=770923,entry=1,profit=-600.0,commission=0,swap=0,time=int(time.time()),position_id=1)]
assert o.traiter(evt(),.3,.1); print("perte du jour OK (perte de GIMALY non comptee)")
# broker : SL trop proche, volume
o,f,d,l,_=mk(); f.stops=300; assert not o.traiter(evt(),.3,.1) and "distance minimale" in rows(d,5)[0]["detail"]
o,f,d,l,_=mk(); f.vmin=0.1; assert not o.traiter(evt(),.3,.1)
# retcode refuse / envoi douteux
o,f,d,l,_=mk(); f.retcode=10006; assert not o.traiter(evt(),.3,.1) and rows(d,5)[-1]["evenement"]=="REFUS" and len(f.envois)==1
o,f,d,l,_=mk(); f.perdu=True; import cvd_m3_ordres as OO
time_sleep=time.sleep; time.sleep=lambda x:None
assert not o.traiter(evt(ms=1),.3,.1) and len(f.envois)==1 and not o.traiter(evt(ms=2),.3,.1) and len(f.envois)==1, "pas de relance, entrees bloquees"
o,f,d,l,_=mk(); f.perdu="cree"; assert o.traiter(evt(ms=1),.3,.1) and len(f.envois)==1 and rows(d,5)[0]["evenement"]=="ENTREE"; time.sleep=time_sleep; print("echecs / envoi douteux OK (aucune relance)")
# suivi, sortie, reprise apres redemarrage
o,f,d,l,_=mk(); o.traiter(evt(9,"BUY",1),.3,.1); tk=f.positions[-1].ticket
f.positions.append(types.SimpleNamespace(ticket=1,magic=770923,comment="GIMALY",type=0,price_open=3880,profit=0,sl=0,tp=0))
o3=O.Ordres(f,d,"XAUUSD",o.cfg,lambda m:None,Path(tempfile.mkdtemp())); o3.ouverts={}; o3.suivre(); assert str(tk) in o3.ouverts and "1" not in o3.ouverts; print("reprise par magic OK, position GIMALY non adoptee")
f.positions=[p for p in f.positions if p.ticket!=tk]; f.deals.append(types.SimpleNamespace(magic=771009,entry=1,profit=7.4,commission=-0.1,swap=0,time=int(time.time()),position_id=tk,volume=0.02,price=3884.2,reason=5))
o3.suivre(); r=rows(d,9)[-1]; assert r["evenement"]=="SORTIE" and r["raison_sortie"]=="TP" and float(r["profit"])==7.4; print("sortie suivie OK")
# config invalide -> ordres coupes
dd=Path(tempfile.mkdtemp()); (dd/"cvd_m3_config.json").write_text("{pas du json"); c=O.lire_config(dd,{"ordres_demo":True},lambda m:None); assert c["ordres_demo"] is False
(dd/"cvd_m3_config.json").write_text(json.dumps({"ordres_demo":True,"magics":{"5":1,"9":1,"14":2}})); assert O.lire_config(dd,None,lambda m:None)["ordres_demo"] is False
dd=Path(tempfile.mkdtemp()); assert O.lire_config(dd)["ordres_demo"] is False and (dd/"cvd_m3_config.json").exists(); print("config OK (defaut = ordres desactives)")

# ---------- 3) plusieurs croisements dans UNE meme bougie M3, sans doublon
d=Path(tempfile.mkdtemp()); sim=S.Sim(d,100.0,lambda m:None); sim.preparer_fichiers()
B=(1794600000//180)*180
base=[(B-180*k, 0.0) for k in range(30,0,-1)]
for l in sim.lignes.values(): l.amorcer([(int(t//180),c) for t,c in base], int(B//180))
sim.session=S.session_horloge(B); sim.debut_session=B-3000
seq=[+5,-5,+6,-6,+7,-7,+8,-8]       # 7 inversions dans la meme bougie (sans compter l'initialisation)
t=B+1.0
for v in seq:
    sim.nouvelle_valeur(t,v,3880.0,3880.2,0.4); t+=1.0
ev=[e for e in sim.evenements if e["n"]==5]
print("croisements EMA5 dans la bougie :",len(ev),[e["sens"] for e in ev]); assert len(ev)==7
assert len({e["event_id"] for e in sim.evenements})==len(sim.evenements)
o,f,dd2,l,_=mk({"max_ouvertes_par_ema":100,"max_ouvertes_total":100})
for e in sim.evenements+sim.evenements: o.traiter(e,.3,.1)       # envoi double volontaire
assert len(f.envois)==len(sim.evenements); print("pas de doublon : ",len(f.envois),"ordres pour",len(sim.evenements),"evenements (envoi double teste)")
assert sim.nb_signaux[5]==7
print("TOUS LES TESTS D'ORDRES OK")
