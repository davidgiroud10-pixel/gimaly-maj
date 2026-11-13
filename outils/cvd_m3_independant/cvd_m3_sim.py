# -*- coding: utf-8 -*-
r"""cvd_m3_sim.py - SIMULATEUR INDEPENDANT du bot XAUUSD "croisement CVD M3 / EMA 5, 9, 14". Processus Windows separe de GIMALY. AUCUN ORDRE (ni reel ni demo).

Ce programme :
  * LIT (lecture seule, ouverture de quelques ms) ~\GIMALY\trading\icebergs_etat.json -> champ flux.cvd (CVD de session des futures GC, ecrit par le moteur chaque seconde)
    et, UNIQUEMENT pour l'amorcage au demarrage, les dernieres lignes de ~\GIMALY\trading\flux_minute.csv ;
  * LIT le bid/ask XAUUSD dans MT5 avec sa propre connexion (symbol_info_tick, symbol_info, symbols_get : lectures uniquement ; aucune fonction d'ordre, controle par test) ;
  * n'ECRIT que dans son propre dossier (celui de ce fichier) : journaux CSV, log, etat. Il n'importe aucun module GIMALY, ne modifie aucun fichier du moteur, ne redemarre
    rien, ne ferme aucun processus autre que lui-meme.

Strategie (fixee par Dav, inchangee) : lot fictif 0.02 ; SL 2 $ ; TP 4 $ (prix XAUUSD) ; positions independantes (chaque croisement ouvre une position, meme si d'autres sont
ouvertes) ; aucun filtre ; trois simulations separees : EMA 5, EMA 9, EMA 14.
Calcul : bougies M3 alignees sur l'heure UTC (seau = ts // 180 s, comme MT5/TradingView). Chaque EMA (alpha = 2/(n+1)) est calculee sur le CVD de CLOTURE des bougies M3 PRECEDENTES.
Croisement INTRABOUGIE : a chaque nouvelle valeur du CVD (~1 par seconde), ligne = alpha*CVD_courant + (1-alpha)*EMA_derniere_cloture ; croisement = changement de signe de (CVD - ligne).
Remise a zero du CVD de session : GIMALY remet le CVD a zero a 22:00 UTC (au premier echange apres). A chaque changement de session (horloge UTC) : toutes les EMA sont effacees,
le simulateur attend le PREMIER mouvement du CVD (le moteur a alors remis a zero), repart de cette valeur et n'emet aucun signal avant n bougies M3 closes (5 / 9 / 14 -> 15 / 27 / 42 min).
Meme regle apres un trou de donnees > 300 s (moteur arrete, flux coupe) : on repart de zero, aucun faux croisement n'est fabrique.
Amorcage : au demarrage, si la session est la meme, les EMA sont reconstruites depuis les clotures M3 des dernieres heures (flux_minute.csv, une valeur par minute, + le journal du simulateur) :
approximatif mais evite 42 min d'attente. Option --sans-amorcage pour desactiver.
Entree : BUY a l'ASK, SELL au BID au tick MT5 lu a l'instant du croisement ; spread reel enregistre. Sortie : BUY au BID (TP bid >= entree+4, SL bid <= entree-2), SELL a l'ASK ; prix de sortie = tick observe.
1 lot = trade_contract_size oz lu dans MT5 (100 par defaut) ; 0.02 lot = 2 oz -> pnl $ = ecart de prix x 2.

APPROXIMATIONS : CVD du GC (COMEX) != XAUUSD (ecart ~4 $) ; CVD echantillonne ~1 fois par seconde (pas a chaque transaction) : un croisement tres bref peut etre manque ou vu avec 1 s de retard ;
MT5 lu au plus 2 fois par seconde : un SL/TP peut etre constate avec un leger retard ; trous possibles du flux ; la ligne de signal de l'indicateur TradingView de Dav est inconnue (EMA supposee).

Usage (dossier gimaly\cvd_m3_independant) :
  python cvd_m3_sim.py --demarrer     lance le simulateur en arriere-plan (processus separe, priorite basse)
  python cvd_m3_sim.py --etat         dit s'il tourne et affiche ses derniers chiffres
  python cvd_m3_sim.py --arreter      l'arrete proprement (positions fictives ouvertes conservees pour la reprise)
  python cvd_m3_sim.py --bilan        bilan quotidien (voir cvd_m3_bilan.py)
  python cvd_m3_sim.py                (sans option) tourne au premier plan, Ctrl+C pour arreter
Autres options : --sans-amorcage ; --donnees DOSSIER (dossier des donnees GIMALY, defaut ~\GIMALY\trading)."""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DONNEES_DEFAUT = Path.home() / "GIMALY" / "trading"
EMAS = (5, 9, 14)
LOT = 0.02
SL_USD = 2.0
TP_USD = 4.0
SEAU_S = 180
TROU_S = 300            # trou de donnees au-dela duquel on repart de zero
PERIME_S = 5.0          # donnee plus vieille que ca : le moteur n'ecrit plus -> attente
PAS_S = 0.25            # lecture du fichier (le moteur ecrit ~1 fois/s)
PAS_TICK_S = 0.5        # lecture MT5 quand des positions sont ouvertes
PAS_FLUX_S = 5.0        # journal CVD/bid/ask
AMORCAGE_H = 4
CONTRAT_DEFAUT = 100.0
COLONNES = ["n", "ema", "sens", "date_signal", "ts_signal", "session", "age_session_s", "cvd", "ligne", "age_cvd_s", "bid", "ask", "spread", "entree", "sl", "tp",
            "simultanees", "date_sortie", "ts_sortie", "sortie", "resultat", "duree_s", "pnl_usd", "r", "reprise"]
COL_FLUX = ["date_heure", "ts", "session", "cvd", "bid", "ask"]
MT5_PERMIS = {"initialize", "shutdown", "symbol_info_tick", "symbol_info", "symbols_get", "last_error"}   # lectures uniquement (verifie par test)


def session_horloge(t):
    return int((t + 2 * 3600) // 86400)


class Journal:
    """Log texte du simulateur (cvd_m3_simulation.log), 5 Mo max puis rotation."""
    def __init__(self, dossier):
        self.chemin = Path(dossier) / "cvd_m3_simulation.log"

    def __call__(self, msg):
        ligne = f"{datetime.now():%d/%m %H:%M:%S}  {msg}"
        try:
            if self.chemin.exists() and self.chemin.stat().st_size > 5_000_000:
                os.replace(self.chemin, self.chemin.with_name("cvd_m3_simulation.log.1"))
            with open(self.chemin, "a", encoding="utf-8") as f:
                f.write(ligne + "\n")
        except OSError:
            pass
        if getattr(sys, "stdout", None):
            try:
                print(ligne, flush=True)
            except Exception:
                pass


class Ligne:
    """EMA du CVD sur M3 (une par n)."""
    def __init__(self, n):
        self.n = n
        self.alpha = 2.0 / (n + 1)
        self.reset()

    def reset(self):
        self.ema = None
        self.seau = None
        self.dernier_cvd = None
        self.barres = 0
        self.signe = 0

    def amorcer(self, clotures, seau_courant):
        """clotures : liste ordonnee de (seau, cvd de cloture), seaux < seau_courant. Les seaux manquants repetent la derniere cloture."""
        self.reset()
        prec = None
        for seau, cvd in clotures:
            if self.ema is None:
                self.ema = cvd
                self.barres = 1
            else:
                for _ in range(seau - prec - 1):
                    self.ema = self.alpha * self.dernier_cvd + (1 - self.alpha) * self.ema
                    self.barres += 1
                self.ema = self.alpha * cvd + (1 - self.alpha) * self.ema
                self.barres += 1
            self.dernier_cvd = cvd
            prec = seau
        if self.ema is not None:
            for _ in range(seau_courant - prec - 1):
                self.ema = self.alpha * self.dernier_cvd + (1 - self.alpha) * self.ema
                self.barres += 1
            self.seau = seau_courant
            self.dernier_cvd = None

    def maj(self, t, cvd):
        """(croisement +1/-1/0, valeur de la ligne)."""
        seau = int(t // SEAU_S)
        if self.seau is None:
            self.seau, self.ema = seau, cvd
        elif seau != self.seau:
            cl = self.dernier_cvd if self.dernier_cvd is not None else cvd
            for _ in range(seau - self.seau):
                self.ema = self.alpha * cl + (1 - self.alpha) * self.ema
                self.barres += 1
            self.seau = seau
        self.dernier_cvd = cvd
        ligne = self.alpha * cvd + (1 - self.alpha) * self.ema
        if self.barres < self.n:
            return 0, ligne
        d = cvd - ligne
        s = 1 if d > 0 else -1 if d < 0 else self.signe
        c = s if (self.signe and s != self.signe) else 0
        self.signe = s
        return c, ligne


class Sim:
    def __init__(self, dossier, contrat=CONTRAT_DEFAUT, log=None):
        self.dossier = Path(dossier)
        self.log = log or Journal(dossier)
        self.contrat = contrat
        self.lignes = {n: Ligne(n) for n in EMAS}
        self.ouvertes = {n: [] for n in EMAS}
        self.compteur = {n: 0 for n in EMAS}
        self.session = None
        self.debut_session = None
        self.attente_raz = None          # CVD au moment du changement de session : on attend son premier mouvement
        self.dernier_t = None
        self.dernier_cvd = None
        self.nb_signaux = {n: 0 for n in EMAS}

    # ---- fichiers de sortie ----
    def chemin(self, n):
        return self.dossier / f"cvd_m3_ema{n}_trades.csv"

    def preparer_fichiers(self):
        self.dossier.mkdir(parents=True, exist_ok=True)
        for n in EMAS:
            if not self.chemin(n).exists():
                with open(self.chemin(n), "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f, delimiter=";").writerow(COLONNES)
        p = self.dossier / "cvd_m3_flux.csv"
        if not p.exists():
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f, delimiter=";").writerow(COL_FLUX)
        self.charger_etat()

    def charger_etat(self):
        p = self.dossier / "cvd_m3_etat.json"
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.compteur.update({int(k): v for k, v in d.get("compteur", {}).items()})
        for n in EMAS:
            self.ouvertes[n] = d.get("ouvertes", {}).get(str(n), [])
            for q in self.ouvertes[n]:
                q["reprise"] = 1
        if any(self.ouvertes.values()):
            self.log("positions fictives reprises : " + ", ".join(f"EMA{n}={len(v)}" for n, v in self.ouvertes.items()))

    def sauver_etat(self):
        try:
            tmp = self.dossier / "cvd_m3_etat.tmp"
            tmp.write_text(json.dumps({"compteur": self.compteur, "ouvertes": {str(n): self.ouvertes[n] for n in EMAS}, "maj": time.time()}), encoding="utf-8")
            os.replace(tmp, self.dossier / "cvd_m3_etat.json")
        except OSError as e:
            self.log(f"etat non sauvegarde : {e!r}")

    # ---- amorcage ----
    def amorcer(self, t, donnees):
        """Reconstruit les EMA depuis les clotures M3 de la session en cours (valeurs ~1/min : approximatif)."""
        sess = session_horloge(t)
        seau_courant = int(t // SEAU_S)
        par_seau = {}
        for ts, cvd, s in lire_historique(donnees, self.dossier, t - AMORCAGE_H * 3600):
            if s != sess:
                continue
            b = int(ts // SEAU_S)
            if b >= seau_courant:
                continue
            if b not in par_seau or ts >= par_seau[b][0]:
                par_seau[b] = (ts, cvd)
        # on garde la fin continue d'au plus 2 h sans trou de plus de 10 min
        seaux = sorted(par_seau)
        bloc = []
        for b in seaux:
            if bloc and (b - bloc[-1]) * SEAU_S > 600:
                bloc = []
            bloc.append(b)
        if not bloc or (seau_courant - bloc[-1]) * SEAU_S > 900:
            self.log("amorcage impossible (pas de donnees recentes de la session) : attente de n bougies M3")
            return False
        clotures = [(b, par_seau[b][1]) for b in bloc]
        for l in self.lignes.values():
            l.amorcer(clotures, seau_courant)
        self.session = sess
        self.debut_session = clotures and par_seau[bloc[0]][0]
        self.log(f"amorcage APPROXIMATIF : {len(clotures)} clotures M3 ({datetime.fromtimestamp(par_seau[bloc[0]][0]):%H:%M} -> {datetime.fromtimestamp(par_seau[bloc[-1]][0]):%H:%M}) ; "
                 + " ; ".join(f"EMA{n} {min(l.barres, 999)} barres" for n, l in self.lignes.items()))
        return True

    # ---- traitement d'une nouvelle valeur de CVD ----
    def nouvelle_valeur(self, t, cvd, bid, ask, age):
        sess = session_horloge(t)
        if self.dernier_t is not None and t - self.dernier_t > TROU_S:
            self.log(f"trou de donnees de {t - self.dernier_t:.0f} s : EMA remises a zero, attente de n bougies M3")
            for l in self.lignes.values():
                l.reset()
            self.attente_raz = None
        if sess != self.session:
            if self.session is not None:
                self.log(f"changement de session ({self.session} -> {sess}) : EMA effacees, attente du premier mouvement du CVD (remise a zero du moteur)")
                for l in self.lignes.values():
                    l.reset()
                self.attente_raz = cvd
            self.session = sess
            self.debut_session = t
        self.dernier_t = t
        if self.attente_raz is not None:
            if cvd == self.attente_raz:
                self.dernier_cvd = cvd
                return
            self.attente_raz = None
            self.debut_session = t
            self.log(f"CVD reparti ({cvd:.0f}) : nouvelle session suivie depuis ce point")
        self.dernier_cvd = cvd
        for n, l in self.lignes.items():
            c, ligne = l.maj(t, cvd)
            if c:
                self.nb_signaux[n] += 1
                if bid is None or ask is None:
                    self.log(f"croisement EMA{n} sans prix MT5 : ignore")
                    continue
                self.ouvrir(n, c, t, cvd, ligne, bid, ask, age)

    def ouvrir(self, n, c, t, cvd, ligne, bid, ask, age):
        sens = "BUY" if c > 0 else "SELL"
        entree = ask if sens == "BUY" else bid
        self.compteur[n] += 1
        self.ouvertes[n].append({
            "n": self.compteur[n], "sens": sens, "ts": t, "session": self.session, "age": t - (self.debut_session or t), "cvd": cvd, "ligne": ligne, "age_cvd": age,
            "bid": bid, "ask": ask, "entree": entree, "sl": entree - SL_USD if sens == "BUY" else entree + SL_USD,
            "tp": entree + TP_USD if sens == "BUY" else entree - TP_USD, "simult": len(self.ouvertes[n]) + 1, "reprise": 0})
        self.sauver_etat()

    def resoudre(self, bid, ask, maintenant=None):
        maintenant = maintenant or time.time()
        change = False
        for n in EMAS:
            restantes = []
            for p in self.ouvertes[n]:
                if p["sens"] == "BUY":
                    px = bid
                    res = "TP" if px >= p["tp"] else "SL" if px <= p["sl"] else None
                else:
                    px = ask
                    res = "TP" if px <= p["tp"] else "SL" if px >= p["sl"] else None
                if res:
                    self.ecrire(n, p, px, res, maintenant)
                    change = True
                else:
                    restantes.append(p)
            self.ouvertes[n] = restantes
        if change:
            self.sauver_etat()

    def ecrire(self, n, p, px, res, maintenant):
        diff = (px - p["entree"]) if p["sens"] == "BUY" else (p["entree"] - px)
        pnl = diff * self.contrat * LOT
        ligne = [p["n"], f"EMA{n}", p["sens"], datetime.fromtimestamp(p["ts"]).strftime("%Y-%m-%d %H:%M:%S"), round(p["ts"], 3), p["session"], round(p["age"]),
                 round(p["cvd"], 1), round(p["ligne"], 2), round(p.get("age_cvd", 0), 2), p["bid"], p["ask"], round(p["ask"] - p["bid"], 2), p["entree"], round(p["sl"], 2),
                 round(p["tp"], 2), p["simult"], datetime.fromtimestamp(maintenant).strftime("%Y-%m-%d %H:%M:%S"), round(maintenant, 3), px, res,
                 round(maintenant - p["ts"], 1), round(pnl, 2), round(diff / SL_USD, 2), p["reprise"]]
        with open(self.chemin(n), "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerow(ligne)

    def noter_flux(self, t, cvd, bid, ask):
        with open(self.dossier / "cvd_m3_flux.csv", "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerow([datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S"), round(t, 1), session_horloge(t), round(cvd, 1),
                                                   "" if bid is None else bid, "" if ask is None else ask])


# ---------------------------------------------------------------- lectures (seule partie qui touche aux donnees de GIMALY : lecture seule)
def lire_etat(donnees):
    """(cvd, mtime) depuis icebergs_etat.json ; None si illisible. Ouverture en lecture, lecture d'un bloc, fermeture immediate."""
    p = Path(donnees) / "icebergs_etat.json"
    try:
        with open(p, "rb") as f:
            brut = f.read()
        mt = p.stat().st_mtime
        d = json.loads(brut.decode("utf-8-sig"))
        return float(d["flux"]["cvd"]), mt
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _fin_de_fichier(chemin, octets=400_000):
    try:
        with open(chemin, "rb") as f:
            f.seek(0, os.SEEK_END)
            taille = f.tell()
            f.seek(max(0, taille - octets))
            brut = f.read()
    except OSError:
        return []
    lignes = brut.decode("utf-8-sig", errors="ignore").splitlines()
    return lignes[1:] if taille > octets else lignes


def lire_historique(donnees, dossier, depuis):
    """(ts, cvd, session_horloge) depuis flux_minute.csv (lecture seule) puis le flux du simulateur, a partir de `depuis`."""
    sortie = []
    chemin = Path(donnees) / "flux_minute.csv"
    lignes = _fin_de_fichier(chemin)
    entete = None
    try:
        with open(chemin, "r", encoding="utf-8-sig") as f:
            entete = f.readline().strip().split(";")
    except OSError:
        pass
    if entete and "ts" in entete and "cvd" in entete:
        i_ts, i_cvd = entete.index("ts"), entete.index("cvd")
        for l in lignes:
            c = l.split(";")
            try:
                ts, cvd = float(c[i_ts]), float(c[i_cvd])
            except (ValueError, IndexError):
                continue
            if ts >= depuis:
                sortie.append((ts, cvd, session_horloge(ts)))
    for l in _fin_de_fichier(Path(dossier) / "cvd_m3_flux.csv"):
        c = l.split(";")
        try:
            ts, cvd = float(c[1]), float(c[3])
        except (ValueError, IndexError):
            continue
        if ts >= depuis:
            sortie.append((ts, cvd, session_horloge(ts)))
    return sortie


def symbole_or(mt5, racine_gimaly):
    """Nom du symbole de l'or : config.local.yaml de GIMALY (lecture seule) puis recherche dans MT5."""
    try:
        txt = (Path(racine_gimaly) / "config.local.yaml").read_text(encoding="utf-8")
        m = re.search(r"^trading_symbole:[ \t]*([^#\n]*?)[ \t]*(?:#.*)?$", txt, re.M)
        v = m.group(1).strip().strip("'\"") if m else ""
        if v and v.lower() != "auto":
            return v
    except OSError:
        pass
    noms = [s.name for s in (mt5.symbols_get() or [])]
    for pref in ("XAUUSD",):
        if pref in noms:
            return pref
    cand = sorted(n for n in noms if n.upper().startswith("XAUUSD"))
    return cand[0] if cand else "XAUUSD"


# ---------------------------------------------------------------- verrou / processus
class Verrou:
    def __init__(self, dossier):
        self.chemin = Path(dossier) / "cvd_m3_sim.lock"
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
        """True si aucun simulateur ne tient le verrou."""
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


def boucle(args):
    dossier = RACINE
    donnees = Path(args.get("donnees") or DONNEES_DEFAUT)
    log = Journal(dossier)
    verrou = Verrou(dossier)
    if not verrou.prendre():
        log("un simulateur tourne deja : arret de cette instance")
        return 3
    flag = dossier / "cvd_m3_arret.flag"
    try:
        flag.unlink()
    except OSError:
        pass
    (dossier / "cvd_m3_sim.pid").write_text(str(os.getpid()), encoding="utf-8")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log("module MetaTrader5 absent : arret (le simulateur a besoin du prix MT5)")
        return 4
    sim = None
    try:
        if not mt5.initialize():
            log(f"MT5 injoignable ({mt5.last_error()}) : arret (GIMALY n'est pas touche)")
            return 5
        symbole = symbole_or(mt5, RACINE.parent)
        info = mt5.symbol_info(symbole)
        contrat = float(getattr(info, "trade_contract_size", 0) or CONTRAT_DEFAUT)
        sim = Sim(dossier, contrat, log)
        sim.preparer_fichiers()
        log(f"SIMULATEUR CVD M3 demarre (pid {os.getpid()}) : symbole {symbole}, contrat {contrat:g} oz, lot {LOT} ; EMA {EMAS} ; AUCUN ORDRE ; donnees lues dans {donnees}")
        if not args.get("sans_amorcage"):
            try:
                sim.amorcer(time.time(), donnees)
            except Exception as e:
                log(f"amorcage impossible : {e!r}")
        derniere_mtime = None
        t_tick = t_flux = t_etat_log = 0.0
        bid = ask = None
        attente_dite = False
        while True:
            if flag.exists():
                log("demande d'arret recue : arret propre")
                break
            now = time.time()
            lu = lire_etat(donnees)
            nouveau = False
            if lu is None:
                if not attente_dite:
                    log("icebergs_etat.json illisible ou sans flux.cvd : attente")
                    attente_dite = True
            else:
                cvd, mt = lu
                age = now - mt
                if age > PERIME_S:
                    if not attente_dite:
                        log(f"donnee CVD perimee ({age:.0f} s) : le moteur n'ecrit plus ? attente (rien n'est touche)")
                        attente_dite = True
                else:
                    if attente_dite:
                        log("donnees CVD de nouveau disponibles")
                        attente_dite = False
                    if mt != derniere_mtime:
                        derniere_mtime = mt
                        nouveau = True
            besoin_tick = nouveau or (any(sim.ouvertes.values()) and now - t_tick >= PAS_TICK_S) or now - t_flux >= PAS_FLUX_S
            if besoin_tick:
                try:
                    tk = mt5.symbol_info_tick(symbole)
                    if tk is not None and tk.bid and tk.ask:
                        bid, ask = float(tk.bid), float(tk.ask)
                        t_tick = now
                except Exception as e:
                    log(f"lecture tick MT5 : {e!r}")
            if nouveau and not attente_dite:
                sim.nouvelle_valeur(mt, cvd, bid, ask, age)
            if bid is not None and (nouveau or any(sim.ouvertes.values())) and now - t_tick < 5:
                sim.resoudre(bid, ask, now)
            if lu is not None and not attente_dite and now - t_flux >= PAS_FLUX_S:
                t_flux = now
                sim.noter_flux(now, cvd, bid, ask)
            if now - t_etat_log >= 3600:
                t_etat_log = now
                log("en marche : " + " | ".join(f"EMA{n}: signaux {sim.nb_signaux[n]}, ouvertes {len(sim.ouvertes[n])}, barres {sim.lignes[n].barres}" for n in EMAS))
            time.sleep(PAS_S)
    except KeyboardInterrupt:
        log("arret demande (Ctrl+C)")
    except Exception as e:
        log(f"ERREUR du simulateur (seul lui s'arrete, GIMALY n'est pas touche) : {e!r}")
        return 6
    finally:
        try:
            if sim:
                sim.sauver_etat()
        except Exception:
            pass
        try:
            mt5.shutdown()
        except Exception:
            pass
        for nom in ("cvd_m3_arret.flag", "cvd_m3_sim.pid"):
            try:
                (dossier / nom).unlink()
            except OSError:
                pass
        verrou.liberer()
        log("simulateur arrete")
    return 0


# ---------------------------------------------------------------- commandes
def demarrer(args):
    if not Verrou(RACINE).libre():
        print("Le simulateur tourne deja (rien a faire).")
        return 0
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    interp = str(pyw if (os.name == "nt" and pyw.exists()) else exe)
    cmd = [interp, str(Path(__file__).resolve()), "--worker"] + (["--sans-amorcage"] if args.get("sans_amorcage") else []) \
        + (["--donnees", str(args["donnees"])] if args.get("donnees") else [])
    kw = {"cwd": str(RACINE), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x00004000       # DETACHED | NEW_PROCESS_GROUP | BELOW_NORMAL
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    for _ in range(40):
        time.sleep(0.25)
        if not Verrou(RACINE).libre():
            print("Simulateur demarre en arriere-plan (processus separe, priorite basse). Suivi : python cvd_m3_sim.py --etat ; journal : cvd_m3_simulation.log")
            return 0
    print("Le simulateur ne s'est pas lance : lis cvd_m3_simulation.log. GIMALY n'est pas touche.")
    return 1


def arreter():
    if Verrou(RACINE).libre():
        print("Aucun simulateur en cours.")
        return 0
    (RACINE / "cvd_m3_arret.flag").write_text("arret", encoding="utf-8")
    for _ in range(60):
        time.sleep(0.5)
        if Verrou(RACINE).libre():
            print("Simulateur arrete proprement. GIMALY n'a pas ete touche.")
            return 0
    print("Le simulateur ne s'arrete pas : il se terminera des qu'il lira le drapeau (cvd_m3_arret.flag). Rien d'autre n'a ete fait.")
    return 1


def etat():
    tourne = not Verrou(RACINE).libre()
    print("Simulateur : " + ("EN COURS" if tourne else "arrete"))
    for l in _fin_de_fichier(RACINE / "cvd_m3_simulation.log", 6000)[-6:]:
        print("  " + l)
    for n in EMAS:
        p = RACINE / f"cvd_m3_ema{n}_trades.csv"
        k = max(0, sum(1 for _ in open(p, encoding="utf-8-sig")) - 1) if p.exists() else 0
        print(f"  EMA {n} : {k} positions fermees")
    try:
        d = json.loads((RACINE / "cvd_m3_etat.json").read_text(encoding="utf-8"))
        print("  ouvertes : " + ", ".join(f"EMA{n}={len(d['ouvertes'].get(str(n), []))}" for n in EMAS))
    except (OSError, ValueError):
        pass
    return 0


def lire_args(a):
    r = {"sans_amorcage": "--sans-amorcage" in a}
    if "--donnees" in a:
        r["donnees"] = a[a.index("--donnees") + 1]
    return r


def main():
    a = sys.argv[1:]
    args = lire_args(a)
    if "--demarrer" in a:
        return demarrer(args)
    if "--arreter" in a:
        return arreter()
    if "--etat" in a:
        return etat()
    if "--bilan" in a:
        sys.path.insert(0, str(RACINE))
        import cvd_m3_bilan
        sys.argv = [sys.argv[0]] + [x for x in a if x != "--bilan"]
        return cvd_m3_bilan.main() or 0
    return boucle(args)


if __name__ == "__main__":
    sys.exit(main())
