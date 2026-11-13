# -*- coding: utf-8 -*-
r"""cvd_m3_tableau.py - TABLEAU DE BORD en temps reel du bot CVD M3 (EMA 5 / 9 / 14), sur les VRAIS resultats MT5 (pas la simulation papier). Programme INDEPENDANT.

* Lecture seule de MT5 : account_info, terminal_info, positions_get, history_deals_get, symbol_info_tick (heure du serveur), initialize, shutdown, last_error. Aucune fonction d'ordre
  (verifie par test). Il tourne dans SON PROPRE processus, avec sa propre connexion au terminal configure dans cvd_m3_config.json (chemin_terminal) et REFUSE d'afficher des
  chiffres si le compte connecte n'est pas compte_attendu. Il n'ouvre rien dans le processus du bot CVD ni dans GIMALY, n'ecrit que dans son dossier.
* Identification par magic number (cvd_m3_config.json : EMA5 771005, EMA9 771009, EMA14 771014). Les positions d'autres bots (GIMALY : 770923) sont ignorees.
* Resultat net d'une position = profit + commission + swap (+ frais) de TOUS ses deals (entree et sortie), en monnaie du compte (EUR). Winrate et Profit Factor sont calcules sur ce net.
* Donnees : positions ouvertes toutes les 5 s ; historique des deals relu toutes les 30 s (recouvrement de 2 jours) et ARCHIVE dans cvd_m3_deals_cache.csv (conserve >= 30 jours,
  independamment de ce que MT5 garde). Les jours sont ceux de l'heure du PC.
* Interface : page web locale http://127.0.0.1:8765 (rafraichie toutes les 5 s). Elle n'ecoute que sur cette machine par defaut (--hote pour changer : aucune authentification, a n'utiliser
  que sur un reseau prive comme Tailscale).
Usage (dossier cvd_m3_independant) :
  python cvd_m3_tableau.py --demarrer    lance le tableau en arriere-plan (processus separe, priorite basse) ; --etat ; --arreter
  python cvd_m3_tableau.py               au premier plan (Ctrl+C pour arreter)       Options : --port 8765 --hote 127.0.0.1 --ouvrir (ouvre le navigateur)"""
from __future__ import annotations

import csv
import json
import ntpath
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RACINE = Path(__file__).resolve().parent
MAGICS_DEFAUT = {"5": 771005, "9": 771009, "14": 771014}
EMAS = (5, 9, 14)
PAS_S = 5.0
PAS_HISTORIQUE_S = 30.0
JOURS_INITIAUX = 40
MT5_PERMIS = {"initialize", "shutdown", "last_error", "account_info", "terminal_info", "positions_get", "history_deals_get", "symbol_info_tick"}
COL_CACHE = ["ticket", "position_id", "magic", "time", "entry", "type", "volume", "price", "profit", "commission", "swap", "fee", "reason", "symbol", "comment"]
RAISONS = {3: "EXPERT", 4: "SL", 5: "TP", 0: "CLIENT", 1: "MOBILE", 2: "WEB", 6: "SO"}


# ---------------------------------------------------------------- calcul (fonction pure, testee)
def calculer(deals, positions, magics, decalage=0):
    """deals : liste de dicts (cache) ; positions : liste de dicts {magic, ticket, profit, swap, type, volume, price_open}.
    Retourne le dictionnaire affiche par la page."""
    inv = {int(v): int(k) for k, v in magics.items()}
    par_pos = {}
    for d in deals:
        if int(d["magic"]) not in inv or int(d["type"]) not in (0, 1):
            continue
        par_pos.setdefault((inv[int(d["magic"])], int(d["position_id"])), []).append(d)
    fermees = {n: [] for n in EMAS}
    entrees_ouvertes = {}
    ouvertes_ids = {int(p["ticket"]) for p in positions}
    for (n, pid), ds in par_pos.items():
        ds.sort(key=lambda x: (float(x["time"]), int(x["ticket"])))
        ins = [d for d in ds if int(d["entry"]) == 0]
        outs = [d for d in ds if int(d["entry"]) in (1, 2, 3)]
        net = sum(float(d["profit"]) + float(d["commission"]) + float(d["swap"]) + float(d.get("fee") or 0) for d in ds)
        if outs and pid not in ouvertes_ids:
            ent = ins[0] if ins else ds[0]
            sortie = outs[-1]
            fermees[n].append({"n": n, "pid": pid, "sens": "BUY" if int(ent["type"]) == 0 else "SELL", "t_in": float(ent["time"]), "t_out": float(sortie["time"]), "net": net,
                               "brut": sum(float(d["profit"]) for d in ds), "frais": sum(float(d["commission"]) + float(d["swap"]) + float(d.get("fee") or 0) for d in ds),
                               "raison": RAISONS.get(int(sortie.get("reason") or 0), str(sortie.get("reason", "")))})
        elif ins:
            entrees_ouvertes[pid] = sum(float(d["commission"]) + float(d.get("fee") or 0) for d in ins)
    res = {"emas": {}, "global": {}}
    tous = []
    for n in EMAS:
        tr = sorted(fermees[n], key=lambda t: t["t_out"])
        tous += tr
        ouv = [p for p in positions if int(p["magic"]) == int(magics[str(n)])]
        flot = sum(float(p["profit"]) + float(p.get("swap", 0)) + entrees_ouvertes.get(int(p["ticket"]), 0.0) for p in ouv)
        res["emas"][str(n)] = _stats(n, tr, ouv, flot, decalage, [(t["t_in"], t["t_out"]) for t in tr] + [(float(p.get("time", 0) or 0), None) for p in ouv])
    res["global"] = _stats(0, sorted(tous, key=lambda t: t["t_out"]), [p for p in positions if int(p["magic"]) in inv],
                           sum(e["flottant"] for e in res["emas"].values()), decalage, [(t["t_in"], t["t_out"]) for t in tous])
    res["classement"] = _classer(res["emas"])
    return res


def _jour(ts, decalage):
    return datetime.fromtimestamp(ts - decalage).strftime("%Y-%m-%d")


def _stats(n, tr, ouv, flot, decalage, intervalles):
    nets = [t["net"] for t in tr]
    gagn = [x for x in nets if x > 0]
    perd = [x for x in nets if x < 0]
    pf = (sum(gagn) / -sum(perd)) if perd else (None if not gagn else float("inf"))
    cum, pic, dd, serie = 0.0, 0.0, 0.0, []
    for t in tr:
        cum += t["net"]
        pic = max(pic, cum)
        dd = max(dd, pic - cum)
        serie.append([t["t_out"] - decalage, round(cum, 2)])
    jours = {}
    for t in tr:
        j = jours.setdefault(_jour(t["t_out"], decalage), {"n": 0, "w": 0, "l": 0, "net": 0.0})
        j["n"] += 1
        j["w"] += t["net"] > 0
        j["l"] += t["net"] < 0
        j["net"] += t["net"]
    lj, c = [], 0.0
    for d in sorted(jours):
        c += jours[d]["net"]
        lj.append({"jour": d, "n": jours[d]["n"], "gagnants": jours[d]["w"], "perdants": jours[d]["l"], "net": round(jours[d]["net"], 2), "cumul": round(c, 2)})
    ev = []
    for a, b in intervalles:
        if a:
            ev.append((a, 1))
            if b:
                ev.append((b, -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = mx = 0
    for _, dlt in ev:
        cur += dlt
        mx = max(mx, cur)
    buy = sum(1 for t in tr if t["sens"] == "BUY")
    return {"ema": n, "trades": len(tr), "gagnants": len(gagn), "perdants": len(perd), "winrate": round(100 * len(gagn) / len(tr), 1) if tr else None,
            "net": round(sum(nets), 2), "brut": round(sum(t["brut"] for t in tr), 2), "frais": round(sum(t["frais"] for t in tr), 2),
            "pf": None if pf is None else ("inf" if pf == float("inf") else round(pf, 2)), "drawdown": round(dd, 2), "ouvertes": len(ouv), "flottant": round(flot, 2),
            "simultanees_max": mx, "buy": buy, "sell": len(tr) - buy, "moyenne": round(sum(nets) / len(nets), 2) if nets else None,
            "tp": sum(1 for t in tr if t["raison"] == "TP"), "sl": sum(1 for t in tr if t["raison"] == "SL"), "jours": lj, "serie": serie[-400:], "n_jours": len(lj)}


def _classer(emas):
    lignes = [(n, e) for n, e in emas.items()]
    par_net = sorted(lignes, key=lambda x: (-x[1]["net"], -(x[1]["pf"] if isinstance(x[1]["pf"], (int, float)) else 99 if x[1]["pf"] == "inf" else 0)))
    rangs = {}
    for crit, cle, sens in (("net", lambda e: e["net"], -1), ("pf", lambda e: (99 if e["pf"] == "inf" else e["pf"] or 0), -1), ("winrate", lambda e: e["winrate"] or 0, -1),
                            ("drawdown", lambda e: e["drawdown"], 1)):
        ordre = sorted(lignes, key=lambda x: sens * cle(x[1]))
        for i, (n, _) in enumerate(ordre):
            rangs.setdefault(n, {})[crit] = i + 1
    total_tr = sum(e["trades"] for _, e in lignes)
    jours = max([e["n_jours"] for _, e in lignes] + [0])
    return {"ordre": [n for n, _ in par_net], "rangs": rangs, "fiable": total_tr >= 300 and jours >= 30,
            "avertissement": ("Classement INDICATIF : " + (f"{total_tr} trades sur {jours} jour(s). " if True else "") +
                              "Il faut au moins ~100 trades par EMA et 30 jours pour qu'une difference ne soit pas due au hasard.") if not (total_tr >= 300 and jours >= 30) else ""}


# ---------------------------------------------------------------- cache des deals
def lire_cache(chemin):
    out = {}
    try:
        with open(chemin, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f, delimiter=";"):
                out[int(r["ticket"])] = r
    except (OSError, ValueError, KeyError):
        pass
    return out


def ecrire_cache(chemin, nouveaux):
    if not nouveaux:
        return
    nouveau = not Path(chemin).exists()
    with open(chemin, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if nouveau:
            w.writerow(COL_CACHE)
        for d in nouveaux:
            w.writerow([d[c] for c in COL_CACHE])


def deal_en_dict(d):
    return {"ticket": d.ticket, "position_id": d.position_id, "magic": d.magic, "time": d.time, "entry": d.entry, "type": d.type, "volume": d.volume, "price": d.price,
            "profit": d.profit, "commission": getattr(d, "commission", 0.0), "swap": getattr(d, "swap", 0.0), "fee": getattr(d, "fee", 0.0), "reason": getattr(d, "reason", 0),
            "symbol": getattr(d, "symbol", ""), "comment": getattr(d, "comment", "")}


# ---------------------------------------------------------------- collecte MT5 (lecture seule)
class Collecte:
    def __init__(self, mt5, cfg, dossier, log=print):
        self.mt5 = mt5
        self.cfg = cfg
        self.dossier = Path(dossier)
        self.log = log
        self.magics = {str(k): int(v) for k, v in {**MAGICS_DEFAUT, **cfg.get("magics", {})}.items()}
        self.cache_chemin = self.dossier / "cvd_m3_deals_cache.csv"
        self.cache = lire_cache(self.cache_chemin)
        self.dernier_historique = 0.0
        self.decalage = 0
        self.resultat = {"erreur": "demarrage...", "maj": 0}

    def verifier_compte(self):
        c = self.mt5.account_info()
        t = self.mt5.terminal_info()
        if c is None or t is None:
            return None, "compte ou terminal MT5 illisible (terminal ferme ou deconnecte ?)"
        att = int(self.cfg.get("compte_attendu") or 0)
        if not att:
            return None, "compte_attendu non renseigne dans cvd_m3_config.json"
        if c.login != att:
            return None, f"le terminal est connecte au compte {c.login}, pas au compte attendu {att} : rien n'est affiche"
        ch = (self.cfg.get("chemin_terminal") or "").strip()
        if ch:
            voulu = ntpath.normcase(ntpath.normpath(ntpath.dirname(ch) if ch.lower().endswith(".exe") else ch))
            if ntpath.normcase(ntpath.normpath(getattr(t, "path", "") or "")) != voulu:
                return None, f"terminal utilise ({getattr(t, 'path', '')}) different du terminal configure ({ch})"
        return c, ""

    def _decalage(self, symbole):
        try:
            tk = self.mt5.symbol_info_tick(symbole)
            if tk is not None and getattr(tk, "time", 0):
                self.decalage = round((tk.time - time.time()) / 1800) * 1800
        except Exception:
            pass

    def rafraichir(self, symbole="XAUUSD"):
        compte, err = self.verifier_compte()
        if compte is None:
            self.resultat = {"erreur": err, "maj": time.time(), "emas": {}, "global": {}, "classement": {}}
            return
        self._decalage(symbole)
        now = time.time()
        if now - self.dernier_historique >= PAS_HISTORIQUE_S:
            depuis = datetime.now() - timedelta(days=JOURS_INITIAUX if not self.cache else 2)
            deals = self.mt5.history_deals_get(depuis, datetime.now() + timedelta(days=2))
            if deals is None:
                self.log(f"historique MT5 illisible ({self.mt5.last_error()})")
            else:
                ms = set(self.magics.values())
                nouveaux = [deal_en_dict(d) for d in deals if d.magic in ms and d.ticket not in self.cache]
                for d in nouveaux:
                    self.cache[int(d["ticket"])] = {k: str(v) for k, v in d.items()}
                ecrire_cache(self.cache_chemin, nouveaux)
                self.dernier_historique = now
        ms = set(self.magics.values())
        pos = [{"magic": p.magic, "ticket": p.ticket, "profit": p.profit, "swap": getattr(p, "swap", 0.0), "type": p.type, "volume": p.volume,
                "price_open": p.price_open, "time": getattr(p, "time", 0)} for p in (self.mt5.positions_get() or ()) if p.magic in ms]
        res = calculer(list(self.cache.values()), pos, self.magics, self.decalage)
        res.update({"erreur": "", "maj": now, "compte": {"login": compte.login, "serveur": getattr(compte, "server", ""), "devise": compte.currency, "solde": compte.balance,
                                                          "equite": compte.equity, "demo": compte.trade_mode == 0},
                    "magics": self.magics, "jours_cache": len({_jour(float(d["time"]), self.decalage) for d in self.cache.values()}),
                    "etat_bot": etat_bot(self.dossier)})
        self.resultat = res


def etat_bot(dossier):
    """Etat du bot CVD sans toucher a son verrou : age de ses fichiers + ordres actives dans la config (lecture seule)."""
    d = Path(dossier)
    out = {"simulateur_actif": False, "ordres_actives": None, "pause": (d / "cvd_m3_pause_entrees.flag").exists()}
    try:
        out["simulateur_actif"] = time.time() - (d / "cvd_m3_flux.csv").stat().st_mtime < 20
    except OSError:
        pass
    try:
        out["ordres_actives"] = bool(json.loads((d / "cvd_m3_config.json").read_text(encoding="utf-8")).get("ordres_demo"))
    except (OSError, ValueError):
        pass
    return out


# ---------------------------------------------------------------- serveur web
class Gestionnaire(BaseHTTPRequestHandler):
    collecte = None
    page = b""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.split("?")[0] == "/api/donnees":
            corps = json.dumps(self.collecte.resultat, ensure_ascii=False, default=str).encode("utf-8")
            type_ = "application/json; charset=utf-8"
        elif self.path.split("?")[0] in ("/", "/index.html"):
            corps, type_ = self.page, "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)


def lire_page():
    return (RACINE / "cvd_m3_tableau.html").read_bytes()


class Verrou:
    def __init__(self, nom="cvd_m3_tableau.lock"):
        self.chemin = RACINE / nom
        self.f = None

    def prendre(self):
        f = open(self.chemin, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self.f = f
        return True

    def libre(self):
        if not self.prendre():
            return False
        self.liberer()
        return True

    def liberer(self):
        if self.f:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f, fcntl.LOCK_UN)
            except OSError:
                pass
            self.f.close()
            self.f = None


def log_fichier(msg):
    ligne = f"{datetime.now():%d/%m %H:%M:%S}  {msg}"
    try:
        p = RACINE / "cvd_m3_tableau.log"
        if p.exists() and p.stat().st_size > 2_000_000:
            os.replace(p, p.with_name("cvd_m3_tableau.log.1"))
        with open(p, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except OSError:
        pass
    if getattr(sys, "stdout", None):
        try:
            print(ligne, flush=True)
        except Exception:
            pass


def lire_config():
    try:
        return json.loads((RACINE / "cvd_m3_config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def serveur(args):
    verrou = Verrou()
    if not verrou.prendre():
        log_fichier("un tableau tourne deja : arret de cette instance")
        return 3
    flag = RACINE / "cvd_m3_tableau_arret.flag"
    try:
        flag.unlink()
    except OSError:
        pass
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log_fichier("module MetaTrader5 absent")
        return 4
    cfg = lire_config()
    ch = (cfg.get("chemin_terminal") or "").strip()
    ok = mt5.initialize(path=ch) if ch else mt5.initialize()
    if not ok:
        log_fichier(f"MT5 injoignable ({mt5.last_error()}) : arret (rien n'est touche)")
        return 5
    sys.path.insert(0, str(RACINE))
    try:
        from cvd_m3_sim import symbole_or
        symbole = symbole_or(mt5, RACINE.parent)
    except Exception:
        symbole = "XAUUSD"
    coll = Collecte(mt5, cfg, RACINE, log_fichier)
    Gestionnaire.collecte = coll
    Gestionnaire.page = lire_page()
    port = int(args.get("port", 8765))
    hote = args.get("hote", "127.0.0.1")
    try:
        srv = ThreadingHTTPServer((hote, port), Gestionnaire)
    except OSError as e:
        log_fichier(f"port {port} indisponible ({e!r}) : essaie --port autre")
        mt5.shutdown()
        return 6
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log_fichier(f"TABLEAU CVD M3 demarre : http://{hote}:{port}  (lecture seule MT5, compte attendu {cfg.get('compte_attendu')}, symbole {symbole})")
    if args.get("ouvrir"):
        import webbrowser
        webbrowser.open(f"http://{hote}:{port}")
    try:
        while not flag.exists():
            t0 = time.time()
            try:
                coll.rafraichir(symbole)
            except Exception as e:
                coll.resultat = {"erreur": f"lecture MT5 impossible : {e!r}", "maj": time.time(), "emas": {}, "global": {}, "classement": {}}
                log_fichier(f"erreur de lecture : {e!r}")
            time.sleep(max(0.5, PAS_S - (time.time() - t0)))
        log_fichier("demande d'arret recue")
    except KeyboardInterrupt:
        log_fichier("arret demande (Ctrl+C)")
    finally:
        try:
            srv.shutdown()
        except Exception:
            pass
        try:
            mt5.shutdown()
        except Exception:
            pass
        try:
            flag.unlink()
        except OSError:
            pass
        verrou.liberer()
        log_fichier("tableau arrete")
    return 0


def demarrer(args):
    if not Verrou().libre():
        print("Le tableau tourne deja.")
        return 0
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    interp = str(pyw if (os.name == "nt" and pyw.exists()) else exe)
    cmd = [interp, str(Path(__file__).resolve()), "--serveur"] + (["--port", str(args["port"])] if "port" in args else []) + (["--hote", args["hote"]] if "hote" in args else [])
    kw = {"cwd": str(RACINE), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x00004000
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    for _ in range(40):
        time.sleep(0.25)
        if not Verrou().libre():
            print(f"Tableau demarre en arriere-plan : http://{args.get('hote', '127.0.0.1')}:{args.get('port', 8765)}  (ouvre cette adresse dans le navigateur)")
            return 0
    print("Le tableau ne s'est pas lance : lis cvd_m3_tableau.log. Rien d'autre n'est touche.")
    return 1


def arreter():
    if Verrou().libre():
        print("Aucun tableau en cours.")
        return 0
    (RACINE / "cvd_m3_tableau_arret.flag").write_text("arret", encoding="utf-8")
    for _ in range(40):
        time.sleep(0.5)
        if Verrou().libre():
            print("Tableau arrete. Le bot CVD et GIMALY n'ont pas ete touches.")
            return 0
    print("Le tableau s'arretera des qu'il lira le drapeau.")
    return 1


def main():
    a = sys.argv[1:]
    args = {}
    if "--port" in a:
        args["port"] = int(a[a.index("--port") + 1])
    if "--hote" in a:
        args["hote"] = a[a.index("--hote") + 1]
    if "--ouvrir" in a:
        args["ouvrir"] = True
    if "--demarrer" in a:
        return demarrer(args)
    if "--arreter" in a:
        return arreter()
    if "--etat" in a:
        print("Tableau : " + ("EN COURS" if not Verrou().libre() else "arrete"))
        return 0
    return serveur(args)


if __name__ == "__main__":
    sys.exit(main())
