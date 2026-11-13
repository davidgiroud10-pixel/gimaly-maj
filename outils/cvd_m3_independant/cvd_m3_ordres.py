# -*- coding: utf-8 -*-
r"""cvd_m3_ordres.py - ORDRES DEMO du simulateur CVD M3 (EMA 5 / 9 / 14). DESACTIVE PAR DEFAUT (cvd_m3_config.json : "ordres_demo": false).

Ce module est la SEULE partie du programme qui peut envoyer un ordre, et seulement dans la fonction `Ordres._envoyer`. Garanties (verifiees par test) :
  * ordre de MARCHE a l'ouverture uniquement (TRADE_ACTION_DEAL, sans champ `position`) : jamais de modification ni de fermeture ; la sortie est assuree par le SL/TP du courtier ;
  * compte DEMO verifie avant CHAQUE ordre (account_info().trade_mode) : refus absolu sur un compte reel ; compte en hedging obligatoire ;
  * trois magic numbers distincts (EMA 5 / 9 / 14), differents de celui de GIMALY ; seules les positions portant l'un de ces trois magic sont lues, comptees ou suivies :
    les positions du bot principal ne sont jamais touchees ;
  * refus si la donnee CVD est perimee, si le signal date de plus de `age_signal_max_s`, si le prix MT5 est incertain, si une limite est atteinte, si le drapeau
    cvd_m3_pause_entrees.flag existe (les positions deja ouvertes ne sont pas touchees) ;
  * un evenement (EMA + instant du croisement + sens) n'est envoye qu'UNE fois : liste persistante, aucune relance automatique d'un envoi douteux ;
  * limites configurables : positions ouvertes par EMA et au total, perte du jour (realisee + flottante des trois EMA), sans aucun filtre sur les signaux.
Si le compte MT5 est le MEME que celui du bot GIMALY (config.local.yaml : trading_mt5_compte), les ordres sont refuses sauf "autoriser_compte_gimaly": true.
Journaux : cvd_m3_ema5_ordres.csv, cvd_m3_ema9_ordres.csv, cvd_m3_ema14_ordres.csv (ENTREE / SORTIE / REFUS)."""
from __future__ import annotations

import csv
import json
import ntpath
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

EMAS = (5, 9, 14)
MAGICS_DEFAUT = {"5": 771005, "9": 771009, "14": 771014}
CONFIG_DEFAUT = {
    "ordres_demo": False,
    "lot": 0.02,
    "sl_usd": 2.0,
    "tp_usd": 4.0,
    "magics": MAGICS_DEFAUT,
    "max_ouvertes_par_ema": 3,
    "max_ouvertes_total": 6,
    "perte_jour_max": 100.0,          # monnaie du compte ; realise + flottant des trois EMA depuis minuit (heure du PC)
    "deviation_points": 20,
    "age_signal_max_s": 2.0,
    "chemin_terminal": "",            # chemin de terminal64.exe du terminal MT5 RESERVE a ce bot (obligatoire pour les ordres)
    "compte_attendu": 0,              # numero du compte demo de ce bot (obligatoire pour les ordres)
    "autoriser_compte_gimaly": False,
}
COL = ["date", "ts", "evenement", "ema", "sens", "event_id", "ticket", "volume", "prix_signal", "prix_demande", "prix_exec", "ecart_points", "sl", "tp", "retcode",
       "detail", "profit", "commission", "swap", "raison_sortie", "solde"]
RET_OK = (10009, 10008)         # TRADE_RETCODE_DONE, PLACED


def lire_config(dossier, ancienne=None, log=None):
    """Config JSON du dossier ; cree le fichier avec les valeurs par defaut s'il manque. Erreur -> ordres_demo=False par prudence."""
    p = Path(dossier) / "cvd_m3_config.json"
    if not p.exists():
        p.write_text(json.dumps(CONFIG_DEFAUT, indent=2), encoding="utf-8")
        return json.loads(json.dumps(CONFIG_DEFAUT))
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        cfg = json.loads(json.dumps(CONFIG_DEFAUT))
        cfg.update({k: v for k, v in d.items() if k in CONFIG_DEFAUT})
        cfg["magics"] = {str(k): int(v) for k, v in {**MAGICS_DEFAUT, **cfg["magics"]}.items()}
        if len(set(cfg["magics"].values())) != 3:
            raise ValueError("les trois magic numbers doivent etre differents")
        return cfg
    except (OSError, ValueError, TypeError) as e:
        if log:
            log(f"cvd_m3_config.json illisible ({e!r}) : ordres desactives par prudence")
        base = json.loads(json.dumps(ancienne or CONFIG_DEFAUT))
        base["ordres_demo"] = False
        return base


def lire_gimaly(racine_gimaly):
    """(login du compte reserve au bot GIMALY, magic du bot GIMALY) depuis config.local.yaml, en lecture seule."""
    login, magic = 0, 770923
    try:
        txt = (Path(racine_gimaly) / "config.local.yaml").read_text(encoding="utf-8")
        m = re.search(r"^trading_mt5_compte:[ \t]*(\d+)", txt, re.M)
        login = int(m.group(1)) if m else 0
        m = re.search(r"^trading_magic:[ \t]*(\d+)", txt, re.M)
        magic = int(m.group(1)) if m else 770923
    except OSError:
        pass
    return login, magic


def connecter(mt5, cfg):
    ch = (cfg.get("chemin_terminal") or "").strip()
    return mt5.initialize(path=ch) if ch else mt5.initialize()


class Ordres:
    def __init__(self, mt5, dossier, symbole, cfg, log, racine_gimaly):
        self.mt5 = mt5
        self.dossier = Path(dossier)
        self.symbole = symbole
        self.cfg = cfg
        self.log = log
        self.racine_gimaly = racine_gimaly
        self.envoyes = []              # event_id deja traites (persistant)
        self.ouverts = {}              # ticket(str) -> infos
        self.bloque_jusqua = 0.0
        self.perte_dite = False
        self.pause_dite = False
        self.refus_vus = {}
        self._charger()

    # ---- etat persistant ----
    def _charger(self):
        try:
            d = json.loads((self.dossier / "cvd_m3_ordres_etat.json").read_text(encoding="utf-8"))
            self.envoyes = d.get("envoyes", [])[-500:]
            self.ouverts = d.get("ouverts", {})
        except (OSError, ValueError):
            pass

    def _sauver(self):
        try:
            tmp = self.dossier / "cvd_m3_ordres_etat.tmp"
            tmp.write_text(json.dumps({"envoyes": self.envoyes[-500:], "ouverts": self.ouverts}), encoding="utf-8")
            os.replace(tmp, self.dossier / "cvd_m3_ordres_etat.json")
        except OSError as e:
            self.log(f"etat des ordres non sauvegarde : {e!r}")

    def _ecrire(self, ema, **kw):
        p = self.dossier / f"cvd_m3_ema{ema}_ordres.csv"
        nouveau = not p.exists()
        ligne = {c: "" for c in COL}
        ligne.update(kw)
        ligne.update({"date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ts": round(time.time(), 3), "ema": f"EMA{ema}"})
        with open(p, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            if nouveau:
                w.writerow(COL)
            w.writerow([ligne[c] for c in COL])

    # ---- identification ----
    def magics(self):
        return {int(k): int(v) for k, v in self.cfg["magics"].items()}

    def ema_du_magic(self, magic):
        for n, m in self.magics().items():
            if m == magic:
                return n
        return None

    def mes_positions(self):
        """UNIQUEMENT les positions portant l'un des trois magic numbers du simulateur."""
        ms = set(self.magics().values())
        return [p for p in (self.mt5.positions_get(symbol=self.symbole) or ()) if p.magic in ms]

    # ---- verifications compte / symbole ----
    def verifier_compte(self):
        """(ok, raison, infos). Appele avant chaque ordre."""
        mt5 = self.mt5
        compte = mt5.account_info()
        term = mt5.terminal_info()
        if compte is None or term is None:
            return False, "compte ou terminal MT5 illisible", {}
        demo = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        hedge = getattr(mt5, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", 2)
        infos = {"login": compte.login, "serveur": getattr(compte, "server", ""), "demo": compte.trade_mode == demo, "hedging": compte.margin_mode == hedge,
                 "solde": compte.balance, "devise": compte.currency, "terminal_connecte": bool(term.connected), "algo_terminal": bool(getattr(term, "trade_allowed", False)),
                 "algo_compte": bool(getattr(compte, "trade_allowed", True)), "chemin": getattr(term, "path", "")}
        if compte.trade_mode != demo:
            return False, "compte NON demo : refus absolu", infos
        if compte.margin_mode != hedge:
            return False, "compte sans hedging (netting) : refus", infos
        if not term.connected:
            return False, "terminal MT5 non connecte au serveur", infos
        if not getattr(term, "trade_allowed", True):
            return False, "Algo Trading desactive dans le terminal MT5", infos
        if not getattr(compte, "trade_allowed", True):
            return False, "trading non autorise sur ce compte", infos
        attendu = int(self.cfg.get("compte_attendu") or 0)
        if not attendu:
            return False, "compte_attendu non renseigne dans cvd_m3_config.json (obligatoire pour les ordres)", infos
        if compte.login != attendu:
            return False, f"compte {compte.login} different du compte attendu {attendu} : refus", infos
        ch = (self.cfg.get("chemin_terminal") or "").strip()
        if not ch:
            return False, "chemin_terminal non renseigne dans cvd_m3_config.json (obligatoire pour les ordres)", infos
        voulu = ntpath.normcase(ntpath.normpath(ntpath.dirname(ch) if ch.lower().endswith(".exe") else ch))
        reel = ntpath.normcase(ntpath.normpath(getattr(term, "path", "") or ""))
        infos["terminal_attendu"] = voulu
        if reel != voulu:
            return False, f"terminal MT5 utilise ({getattr(term, 'path', '')}) different du terminal configure ({ch}) : refus", infos
        login_g, magic_g = lire_gimaly(self.racine_gimaly)
        if magic_g in self.magics().values():
            return False, f"un magic number du simulateur est celui de GIMALY ({magic_g})", infos
        if login_g and compte.login == login_g and not self.cfg.get("autoriser_compte_gimaly"):
            return False, f"meme compte ({login_g}) que le bot GIMALY : refuse (voir autoriser_compte_gimaly)", infos
        return True, "ok", infos

    def verifier_symbole(self):
        """(ok, raisons, infos) : volume, SL/TP et mode d'execution acceptes par le courtier."""
        mt5 = self.mt5
        info = mt5.symbol_info(self.symbole)
        if info is None:
            return False, ["symbole introuvable"], {}
        raisons = []
        lot = float(self.cfg["lot"])
        pas = float(getattr(info, "volume_step", 0.01) or 0.01)
        if lot < info.volume_min - 1e-9 or lot > info.volume_max + 1e-9:
            raisons.append(f"volume {lot} hors limites ({info.volume_min} - {info.volume_max})")
        if abs(round(lot / pas) * pas - lot) > 1e-9:
            raisons.append(f"volume {lot} pas multiple du pas {pas}")
        point = float(info.point)
        mini = max(int(getattr(info, "trade_stops_level", 0) or 0), int(getattr(info, "trade_freeze_level", 0) or 0)) * point
        spread = float(getattr(info, "spread", 0)) * point
        if mini > 0 and float(self.cfg["sl_usd"]) < mini + spread:
            raisons.append(f"SL {self.cfg['sl_usd']} $ plus proche que la distance minimale du courtier ({mini + spread:.2f} $)")
        if mini > 0 and float(self.cfg["tp_usd"]) < mini:
            raisons.append(f"TP {self.cfg['tp_usd']} $ plus proche que la distance minimale du courtier ({mini:.2f} $)")
        if getattr(info, "trade_mode", 4) != getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4):
            raisons.append("trading du symbole non complet (fermeture seule ou desactive)")
        modes = int(getattr(info, "filling_mode", 3) or 0)
        fill = (getattr(mt5, "ORDER_FILLING_IOC", 1) if modes & 2 else getattr(mt5, "ORDER_FILLING_FOK", 0) if modes & 1 else getattr(mt5, "ORDER_FILLING_RETURN", 2))
        return (not raisons), raisons, {"volume_min": info.volume_min, "volume_max": info.volume_max, "volume_step": pas, "stops_level": getattr(info, "trade_stops_level", 0),
                                         "freeze_level": getattr(info, "trade_freeze_level", 0), "digits": info.digits, "point": point, "contrat": getattr(info, "trade_contract_size", 100),
                                         "filling": fill, "spread_points": getattr(info, "spread", 0)}

    # ---- limites ----
    def perte_du_jour(self):
        """Realise (profit + commission + swap des sorties des trois magic) + flottant des positions des trois magic, depuis minuit (heure du PC)."""
        mt5 = self.mt5
        tk = mt5.symbol_info_tick(self.symbole)
        decalage = 0
        if tk is not None and getattr(tk, "time", 0):
            decalage = round((tk.time - time.time()) / 1800) * 1800
        minuit = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + decalage
        ms = set(self.magics().values())
        deals = mt5.history_deals_get(datetime.now() - timedelta(days=3), datetime.now() + timedelta(days=2)) or ()
        realise = sum(d.profit + getattr(d, "commission", 0) + getattr(d, "swap", 0) for d in deals if d.magic in ms and d.entry != 0 and d.time >= minuit)
        flottant = sum(p.profit for p in self.mes_positions())
        return realise + flottant

    # ---- point d'entree : un croisement ----
    def traiter(self, evt, age_donnee, age_tick):
        """evt : dict n, sens, event_id, ts_recu, bid, ask, cvd. Retourne True si un ordre a ete envoye."""
        n = evt["n"]
        if not self.cfg.get("ordres_demo"):
            return False
        if evt["event_id"] in self.envoyes:
            return False
        self.envoyes.append(evt["event_id"])        # marque AVANT l'envoi : jamais deux fois le meme evenement
        self._sauver()
        raison = self._autoriser(evt, age_donnee, age_tick)
        if raison:
            self._refus(evt, raison)
            return False
        return self._envoyer(evt)

    def _refus(self, evt, raison):
        self._ecrire(evt["n"], evenement="REFUS", sens=evt["sens"], event_id=evt["event_id"], detail=raison)
        cle = (evt["n"], raison)
        if self.refus_vus.get(cle, 0) < time.time() - 300:
            self.refus_vus[cle] = time.time()
            self.log(f"ordre EMA{evt['n']} {evt['sens']} REFUSE : {raison}")

    def _autoriser(self, evt, age_donnee, age_tick):
        if (self.dossier / "cvd_m3_pause_entrees.flag").exists():
            return "entrees en pause (cvd_m3_pause_entrees.flag)"
        if time.time() < self.bloque_jusqua:
            return "entrees bloquees apres un envoi incertain"
        if age_donnee is None or age_donnee > 5.0:
            return f"donnee CVD perimee ({age_donnee})"
        if age_tick is None or age_tick > 5.0:
            return "prix MT5 incertain (tick trop ancien)"
        if time.time() - evt["ts_recu"] > float(self.cfg["age_signal_max_s"]):
            return "signal trop ancien au moment de l'envoi"
        ok, why, _ = self.verifier_compte()
        if not ok:
            return why
        ok, raisons, _ = self.verifier_symbole()
        if not ok:
            return "; ".join(raisons)
        mes = self.mes_positions()
        if len(mes) >= int(self.cfg["max_ouvertes_total"]):
            return f"limite totale atteinte ({len(mes)} positions)"
        if sum(1 for p in mes if p.magic == self.magics()[evt["n"]]) >= int(self.cfg["max_ouvertes_par_ema"]):
            return f"limite EMA{evt['n']} atteinte"
        if self.perte_du_jour() <= -abs(float(self.cfg["perte_jour_max"])):
            return f"perte du jour maximale atteinte ({self.perte_du_jour():.2f})"
        return None

    def _envoyer(self, evt):
        """SEUL endroit du programme qui envoie un ordre. Ouverture au marche uniquement, magic du simulateur uniquement."""
        mt5 = self.mt5
        n, sens = evt["n"], evt["sens"]
        ok, why, _ = self.verifier_compte()
        if not ok:                                   # controle demo REFAIT juste avant l'envoi
            self._refus(evt, why)
            return False
        _, _, sym = self.verifier_symbole()
        self._point = sym.get('point', 0.01) or 0.01
        tk = mt5.symbol_info_tick(self.symbole)
        if tk is None or not tk.bid or not tk.ask:
            self._refus(evt, "prix MT5 indisponible")
            return False
        achat = sens == "BUY"
        prix = float(tk.ask if achat else tk.bid)
        d = int(sym["digits"])
        sl = round(prix - self.cfg["sl_usd"] if achat else prix + self.cfg["sl_usd"], d)
        tp = round(prix + self.cfg["tp_usd"] if achat else prix - self.cfg["tp_usd"], d)
        magic = self.magics()[n]
        commentaire = f"E{n}-{evt['event_id'].split('-')[1][-9:]}-{sens[0]}"[:31]
        demande = {"action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbole, "volume": float(self.cfg["lot"]),
                   "type": mt5.ORDER_TYPE_BUY if achat else mt5.ORDER_TYPE_SELL, "price": prix, "sl": sl, "tp": tp,
                   "deviation": int(self.cfg["deviation_points"]), "magic": magic, "comment": commentaire,
                   "type_time": mt5.ORDER_TIME_GTC, "type_filling": sym["filling"]}
        assert demande["magic"] in self.magics().values() and "position" not in demande
        try:
            r = mt5.order_send(demande)
        except Exception as e:
            r = None
            self.log(f"order_send EMA{n} : exception {e!r}")
        if r is None:
            self.bloque_jusqua = time.time() + 30
            time.sleep(1.0)
            trouve = [p for p in self.mes_positions() if p.magic == magic and getattr(p, "comment", "") == commentaire]
            if trouve:
                p = trouve[0]
                self._entree(evt, n, sens, p.ticket, p.price_open, prix, sl, tp, 0, "reponse perdue, position retrouvee")
                return True
            self._ecrire(n, evenement="REFUS", sens=sens, event_id=evt["event_id"], detail="envoi incertain : aucune position retrouvee, aucune relance")
            self.log(f"EMA{n} : envoi incertain, aucune relance ; entrees bloquees 30 s")
            return False
        if r.retcode not in RET_OK:
            self._ecrire(n, evenement="REFUS", sens=sens, event_id=evt["event_id"], prix_demande=prix, sl=sl, tp=tp, retcode=r.retcode, detail=getattr(r, "comment", ""))
            self.log(f"EMA{n} {sens} refuse par le courtier : {r.retcode} {getattr(r, 'comment', '')}")
            return False
        ticket = getattr(r, "position", 0) or r.order
        self._entree(evt, n, sens, ticket, r.price, prix, sl, tp, r.retcode, getattr(r, "comment", ""))
        return True

    def _entree(self, evt, n, sens, ticket, exec_, demande, sl, tp, retcode, detail):
        pt = getattr(self, '_point', 0.01)
        self.ouverts[str(ticket)] = {"ema": n, "sens": sens, "event_id": evt["event_id"], "ts": time.time()}
        self._sauver()
        self._ecrire(n, evenement="ENTREE", sens=sens, event_id=evt["event_id"], ticket=ticket, volume=self.cfg["lot"], prix_signal=evt["ask"] if sens == "BUY" else evt["bid"],
                     prix_demande=demande, prix_exec=exec_, ecart_points=round((exec_ - demande) / pt * (1 if sens == "BUY" else -1)), sl=sl, tp=tp, retcode=retcode, detail=detail)
        self.log(f"ORDRE DEMO EMA{n} {sens} {self.cfg['lot']} lot a {exec_} (SL {sl} / TP {tp}) ticket {ticket}")

    # ---- suivi : sorties et reprise apres redemarrage ----
    def suivre(self):
        mt5 = self.mt5
        mes = {str(p.ticket): p for p in self.mes_positions()}
        for t, p in mes.items():
            if t not in self.ouverts:
                n = self.ema_du_magic(p.magic)
                self.ouverts[t] = {"ema": n, "sens": "BUY" if p.type == getattr(mt5, "POSITION_TYPE_BUY", 0) else "SELL", "event_id": "reprise", "ts": time.time()}
                self.log(f"position EMA{n} retrouvee par son magic number : ticket {t}")
        changement = False
        for t in list(self.ouverts):
            if t in mes:
                continue
            deals = [d for d in (mt5.history_deals_get(position=int(t)) or ()) if d.entry != 0]
            if not deals:
                if time.time() - self.ouverts[t].get("ts", 0) > 600:
                    self.log(f"position {t} disparue sans deal de sortie visible : abandon du suivi")
                    del self.ouverts[t]
                    changement = True
                continue
            d = deals[-1]
            raison = {getattr(mt5, "DEAL_REASON_SL", 4): "SL", getattr(mt5, "DEAL_REASON_TP", 5): "TP"}.get(getattr(d, "reason", None), str(getattr(d, "reason", "")))
            o = self.ouverts.pop(t)
            self._ecrire(o["ema"], evenement="SORTIE", sens=o["sens"], event_id=o["event_id"], ticket=t, volume=d.volume, prix_exec=d.price, profit=d.profit,
                         commission=getattr(d, "commission", 0), swap=getattr(d, "swap", 0), raison_sortie=raison)
            self.log(f"sortie EMA{o['ema']} {o['sens']} ticket {t} : {raison} {d.profit:+.2f}")
            changement = True
        if changement:
            self._sauver()

    def rapport(self):
        """Pour --verifier : ligne par controle, sans envoyer aucun ordre."""
        out = []
        ok, why, infos = self.verifier_compte()
        out.append(("compte MT5", f"{infos.get('login')} @ {infos.get('serveur')} | {'DEMO' if infos.get('demo') else 'REEL !'} | {'hedging' if infos.get('hedging') else 'NETTING'} | "
                    f"solde {infos.get('solde')} {infos.get('devise')}", infos.get("demo") and infos.get("hedging")))
        out.append(("terminal MT5", f"{infos.get('chemin')} | connecte={infos.get('terminal_connecte')} | Algo Trading terminal={infos.get('algo_terminal')} compte={infos.get('algo_compte')}",
                    infos.get("terminal_connecte") and infos.get("algo_terminal")))
        okc = ok
        out.append(("verdict compte", why, okc))
        oks, raisons, s = self.verifier_symbole()
        out.append(("symbole " + self.symbole, f"volume {s.get('volume_min')}-{s.get('volume_max')} pas {s.get('volume_step')} | stops_level {s.get('stops_level')} freeze {s.get('freeze_level')} | "
                    f"digits {s.get('digits')} | spread {s.get('spread_points')} pts | contrat {s.get('contrat')} | remplissage {s.get('filling')}", oks))
        if raisons:
            out.append(("  problemes", "; ".join(raisons), False))
        try:
            lg, mg = lire_gimaly(self.racine_gimaly)
            out.append(("bot GIMALY", f"compte reserve {lg or 'non precise'} | magic {mg} | magic du simulateur {sorted(self.magics().values())}", mg not in self.magics().values()))
            if lg and infos.get("login") == lg:
                out.append(("MEME COMPTE QUE GIMALY", "les ordres seront refuses tant que autoriser_compte_gimaly est false (voir procedure)", False))
        except Exception:
            pass
        autres = [p for p in (self.mt5.positions_get(symbol=self.symbole) or ()) if p.magic not in self.magics().values()]
        out.append(("positions d'autres bots", f"{len(autres)} position(s) non touchees (magic {sorted({p.magic for p in autres})})", True))
        out.append(("positions du simulateur", f"{len(self.mes_positions())}", True))
        return out
