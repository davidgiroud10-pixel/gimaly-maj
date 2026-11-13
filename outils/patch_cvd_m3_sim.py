# -*- coding: utf-8 -*-
r"""Patch : SIMULATION du bot XAUUSD "croisement CVD M3 / EMA 5, 9, 14" (lot 0.02, SL 2 $, TP 4 $, positions independantes). AUCUN ORDRE n'est envoye a MT5.
Le bot (DetecteurIcebergs) branche un observateur sur le flux GIMALY : a chaque croisement intrabougie M3 du CVD avec l'une des trois EMA, une position
FICTIVE est ouverte au prix reel MT5 (BUY a l'ask, SELL au bid, spread enregistre) puis fermee au TP/SL. Trois journaux separes (un par EMA), un journal du
CVD/bid/ask toutes les 5 s (~1 Mo/jour, sert aux backtests sur 30 jours et plus). Voir l'en-tete de gimaly/trading/cvd_m3_sim.py pour la methode et les limites.
Ce que fait le patch : cree gimaly/trading/cvd_m3_sim.py ; ajoute dans icebergs.py (apres `self.flux.sur_cycle = ...`) un appel entoure d'un try/except.
Si quoi que ce soit echoue, le bot continue sans rien changer. Pause sans desinstaller : creer le fichier ~\GIMALY\trading\cvd_m3_sim.stop.
Sauvegarde icebergs.py.avant_cvd_m3_sim. Retour arriere : --annuler. Idempotent. Rien n'est ecrit si un repere manque ou si le fichier ne compile plus.
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_cvd_m3_sim.py [--annuler]   puis redemarrer le bot (redemarrer_bot.py)."""
import shutil
import sys
from pathlib import Path

DOSSIER = Path.cwd() / "gimaly" / "trading"
F_ICE = DOSSIER / "icebergs.py"
F_MOD = DOSSIER / "cvd_m3_sim.py"
SAUV = F_ICE.with_name(F_ICE.name + ".avant_cvd_m3_sim")
MARQUE = "gimaly.trading.cvd_m3_sim"
ANCRE = "        self.flux.sur_cycle = self.nouveau_cycle\n"
AJOUT = (
    "        try:  # 13/11 : simulation CVD M3 (EMA 5/9/14), aucun ordre\n"
    "            from gimaly.trading.cvd_m3_sim import brancher as _brancher_cvd_m3\n"
    "            _brancher_cvd_m3(self.flux, lambda: self.mt5, lambda: symbole_or())\n"
    "        except Exception as _e_cvd:\n"
    "            print(f\"Simulation CVD M3 non branchee : {_e_cvd!r}\")\n")
MODULE = r'''
# -*- coding: utf-8 -*-
"""gimaly/trading/cvd_m3_sim.py - SIMULATION du bot XAUUSD "croisement CVD M3 / EMA". AUCUN ORDRE n'est envoye : ce module ne lit que le CVD de GIMALY
et le tick MT5 (symbol_info_tick). Il ne contient pas d'order_send (verifie par test).

Regles (fixees par Dav, ne pas modifier sans son accord) : lot 0.02 ; SL 2 $ ; TP 4 $ (sur le prix du GOLD) ; positions independantes (un croisement = une position,
meme si d'autres sont ouvertes) ; trois lignes de signal testees en meme temps : EMA 5, EMA 9, EMA 14 du CVD, chacune avec son propre journal.

CVD : CVD de session de GIMALY (volume acheteur - vendeur des futures GC, flux KMM), remis a zero a 22:00 UTC. Ce n'est PAS celui de TradingView.
Bougies M3 alignees sur l'epoque (comme MT5/TradingView) : seau = ts // 180 s. EMA calculee sur le CVD de CLOTURE de chaque M3 (alpha = 2/(n+1)).
Croisement INTRABOUGIE : a chaque transaction, valeur de la ligne = alpha*CVD_courant + (1-alpha)*EMA_cloture_precedente ; croisement = changement de signe de
(CVD - ligne). Chaque EMA attend n bougies M3 closes apres un demarrage / changement de session / trou de flux (> 300 s) avant de signaler.
Entree : BUY a l'ASK, SELL au BID, au tick MT5 lu juste apres le croisement (spread reel enregistre). Sortie : BUY au BID, SELL a l'ASK (TP : bid >= entree+4 ;
SL : bid <= entree-2 ; inverse pour SELL). Le prix de sortie enregistre est le tick observe. 1 lot = contrat de 100 oz (lu dans MT5) : 0.02 lot = 2 oz.

APPROXIMATIONS (a lire dans les resultats) : CVD du GC (COMEX) et prix XAUUSD different (ecart ~4 $) ; MT5 interroge environ 5 fois par seconde (pas chaque tick) donc
un SL/TP peut etre constate avec un petit retard ; le flux KMM peut avoir des trous ; la ligne de signal du TradingView de Dav est inconnue (EMA supposee).
Fichiers (~\\GIMALY\\trading) : cvd_m3_ema5_trades.csv, cvd_m3_ema9_trades.csv, cvd_m3_ema14_trades.csv (une ligne par position fermee), cvd_m3_flux.csv (CVD/bid/ask toutes
les 5 s : base du backtest 30 jours), cvd_m3_etat.json (positions ouvertes, reprises apres redemarrage). Pause : creer le fichier cvd_m3_sim.stop."""
from __future__ import annotations

import csv
import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
EMAS = (5, 9, 14)
LOT = 0.02
SL_USD = 2.0
TP_USD = 4.0
SEAU_S = 180
TROU_S = 300
PAS_FLUX_S = 5
PAS_MT5_S = 0.2
CONTRAT_DEFAUT = 100.0
COLONNES = ["n", "ema", "sens", "date_signal", "ts_signal", "session", "age_session_s", "cvd", "ligne", "bid", "ask", "spread", "entree", "sl", "tp",
            "simultanees", "date_sortie", "ts_sortie", "sortie", "resultat", "duree_s", "pnl_usd", "r", "reprise", "latence_s"]
COL_FLUX = ["date_heure", "ts", "session", "cvd", "bid", "ask", "gc_prix"]


class _Ligne:
    """Etat d'une EMA du CVD sur M3."""
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

    def valeur(self, cvd):
        return self.alpha * cvd + (1 - self.alpha) * self.ema

    def maj(self, ts_s, cvd):
        """Retourne +1 / -1 si croisement (haussier / baissier), sinon 0."""
        seau = int(ts_s // SEAU_S)
        if self.seau is None:
            self.seau = seau
            self.ema = cvd
        elif seau != self.seau:
            cl = self.dernier_cvd if self.dernier_cvd is not None else cvd
            for _ in range(seau - self.seau):          # un pas par bougie M3 close (meme valeur si bougies sans transaction)
                self.ema = self.alpha * cl + (1 - self.alpha) * self.ema
                self.barres += 1
            self.seau = seau
        self.dernier_cvd = cvd
        if self.barres < self.n:
            self.signe = 0
            return 0, self.valeur(cvd)
        ligne = self.valeur(cvd)
        d = cvd - ligne
        s = 1 if d > 0 else -1 if d < 0 else self.signe
        croisement = s if (self.signe and s != self.signe) else 0
        self.signe = s
        return croisement, ligne


class SimCvdM3:
    def __init__(self, flux, get_mt5, get_symbole, dossier=None):
        self.flux = flux
        self.get_mt5 = get_mt5
        self.get_symbole = get_symbole
        self.dossier = Path(dossier) if dossier else DOSSIER
        self.lignes = {n: _Ligne(n) for n in EMAS}
        self.file = queue.Queue()
        self.ouvertes = {n: [] for n in EMAS}
        self.compteur = {n: 0 for n in EMAS}
        self.contrat = CONTRAT_DEFAUT
        self._dernier_ts = None
        self._session = None
        self._debut_session_ts = None
        self._reveil = threading.Event()
        self._fin = False
        self._verrou = threading.RLock()
        self._fichier_verrou = None
        self._erreur_dite = False
        self.actif = False

    # ---- demarrage ----
    def demarrer(self):
        try:
            self.dossier.mkdir(parents=True, exist_ok=True)
            if not self._prendre_verrou():
                return False
            for n in EMAS:
                p = self._chemin(n)
                if not p.exists():
                    with open(p, "w", newline="", encoding="utf-8-sig") as f:
                        csv.writer(f, delimiter=";").writerow(COLONNES)
            p = self.dossier / "cvd_m3_flux.csv"
            if not p.exists():
                with open(p, "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f, delimiter=";").writerow(COL_FLUX)
            self._charger_etat()
        except Exception as e:
            print(f"Simulation CVD M3 : demarrage impossible ({e!r}).")
            return False
        self.actif = True
        threading.Thread(target=self._boucle, daemon=True, name="cvd_m3_sim").start()
        print("Simulation CVD M3 (EMA 5/9/14) active : AUCUN ordre envoye.")
        return True

    def _prendre_verrou(self):
        """Un seul processus simule a la fois (GIMALY et le bot ne doivent pas doubler les journaux)."""
        f = open(self.dossier / "cvd_m3_sim.lock", "a+")
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
        self._fichier_verrou = f
        return True

    def _chemin(self, n):
        return self.dossier / f"cvd_m3_ema{n}_trades.csv"

    # ---- appele a chaque transaction du flux (thread KMM) : tres leger ----
    def sur_transaction(self):
        if not self.actif:
            return
        try:
            fl = self.flux
            ts = fl._dernier_ts
            if not ts or ts == self._dernier_ts:
                return
            ts_s = ts / 1000.0
            cvd = float(fl.cvd)
            if fl.session != self._session or (self._dernier_ts and ts - self._dernier_ts > TROU_S * 1000):
                if fl.session != self._session:
                    self._debut_session_ts = ts_s
                self._session = fl.session
                for l in self.lignes.values():
                    l.reset()
            self._dernier_ts = ts
            if (self.dossier / "cvd_m3_sim.stop").exists():
                return
            for n, l in self.lignes.items():
                c, ligne = l.maj(ts_s, cvd)
                if c:
                    self.file.put((n, c, ts_s, cvd, ligne, self._session, ts_s - (self._debut_session_ts or ts_s)))
            if not self.file.empty():
                self._reveil.set()
        except Exception as e:
            self._dire(e)

    def _dire(self, e):
        if not self._erreur_dite:
            self._erreur_dite = True
            print(f"Simulation CVD M3 : erreur ignoree ({e!r}) - le bot continue.")

    # ---- thread de simulation ----
    def _tick(self):
        mt5 = self.get_mt5()
        if mt5 is None:
            return None
        t = mt5.symbol_info_tick(self.get_symbole())
        if t is None or not t.bid or not t.ask:
            return None
        return float(t.bid), float(t.ask)

    def _boucle(self):
        dernier_flux = 0.0
        while not self._fin:
            self._reveil.wait(PAS_MT5_S)
            self._reveil.clear()
            try:
                tk = self._tick()
                if tk is not None:
                    self._ouvrir_en_attente(tk)
                    self._resoudre(tk)
                    if time.time() - dernier_flux >= PAS_FLUX_S:
                        dernier_flux = time.time()
                        self._journal_flux(tk)
            except Exception as e:
                self._dire(e)

    def _ouvrir_en_attente(self, tk):
        bid, ask = tk
        while True:
            try:
                n, c, ts_s, cvd, ligne, sess, age = self.file.get_nowait()
            except queue.Empty:
                return
            sens = "BUY" if c > 0 else "SELL"
            entree = ask if sens == "BUY" else bid
            sl = entree - SL_USD if sens == "BUY" else entree + SL_USD
            tp = entree + TP_USD if sens == "BUY" else entree - TP_USD
            with self._verrou:
                self.compteur[n] += 1
                simult = len(self.ouvertes[n]) + 1
                self.ouvertes[n].append({
                    "n": self.compteur[n], "sens": sens, "ts": ts_s, "session": sess, "age": age, "cvd": cvd, "ligne": ligne, "bid": bid, "ask": ask,
                    "entree": entree, "sl": sl, "tp": tp, "simult": simult, "ouverture": time.time(), "reprise": 0})
            self._sauver_etat()

    def _resoudre(self, tk):
        bid, ask = tk
        ferme = False
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
                    self._ecrire(n, p, px, res)
                    ferme = True
                else:
                    restantes.append(p)
            self.ouvertes[n] = restantes
        if ferme:
            self._sauver_etat()

    def _ecrire(self, n, p, px, res):
        diff = (px - p["entree"]) if p["sens"] == "BUY" else (p["entree"] - px)
        pnl = diff * self.contrat * LOT
        maintenant = time.time()
        ligne = [p["n"], f"EMA{n}", p["sens"], datetime.fromtimestamp(p["ts"]).strftime("%Y-%m-%d %H:%M:%S"), round(p["ts"], 3), p["session"],
                 round(p["age"]), round(p["cvd"], 1), round(p["ligne"], 2), p["bid"], p["ask"], round(p["ask"] - p["bid"], 2), p["entree"],
                 round(p["sl"], 2), round(p["tp"], 2), p["simult"], datetime.fromtimestamp(maintenant).strftime("%Y-%m-%d %H:%M:%S"),
                 round(maintenant, 3), px, res, round(maintenant - p["ts"], 1), round(pnl, 2), round(diff / SL_USD, 2), p["reprise"],
                 round(p["ouverture"] - p["ts"], 2)]
        with open(self._chemin(n), "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerow(ligne)

    def _journal_flux(self, tk):
        fl = self.flux
        with open(self.dossier / "cvd_m3_flux.csv", "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), round(time.time(), 1), fl.session, round(float(fl.cvd), 1),
                                                   tk[0], tk[1], getattr(fl, "dernier_prix", "")])

    # ---- etat (positions ouvertes) ----
    def _sauver_etat(self):
        try:
            with self._verrou:
                d = {"compteur": self.compteur, "ouvertes": {str(n): self.ouvertes[n] for n in EMAS}}
            tmp = self.dossier / "cvd_m3_etat.tmp"
            tmp.write_text(json.dumps(d), encoding="utf-8")
            os.replace(tmp, self.dossier / "cvd_m3_etat.json")
        except Exception as e:
            self._dire(e)

    def _charger_etat(self):
        p = self.dossier / "cvd_m3_etat.json"
        if not p.exists():
            return
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            self.compteur.update({int(k): v for k, v in d.get("compteur", {}).items()})
            for n in EMAS:
                self.ouvertes[n] = d.get("ouvertes", {}).get(str(n), [])
                for q in self.ouvertes[n]:
                    q["reprise"] = 1
        except Exception:
            pass


def brancher(flux, get_mt5, get_symbole, dossier=None):
    """Enveloppe flux._transaction : le comportement du flux est inchange, la simulation est appelee ensuite (try/except)."""
    if getattr(flux, "_cvd_m3_sim", None) is not None:
        return flux._cvd_m3_sim
    sim = SimCvdM3(flux, get_mt5, get_symbole, dossier)
    if not sim.demarrer():
        return None
    original = flux._transaction

    def _transaction(m):
        original(m)
        sim.sur_transaction()

    flux._transaction = _transaction
    flux._cvd_m3_sim = sim
    return sim
'''


def main():
    if not F_ICE.exists():
        print(f"{F_ICE} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    if "--annuler" in sys.argv:
        if SAUV.exists():
            shutil.copy2(SAUV, F_ICE)
            print("icebergs.py restaure (simulation retiree). Redemarre le bot. Les journaux cvd_m3_*.csv sont conserves.")
        else:
            print("Aucune sauvegarde : rien a annuler.")
        return 0
    brut = F_ICE.read_bytes()
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), brut.count(b"\r\n") > brut.count(b"\n") / 2
    compile(MODULE, str(F_MOD), "exec")
    a_jour = F_MOD.exists() and F_MOD.read_text(encoding="utf-8") == MODULE
    if MARQUE in txt:
        if not a_jour:
            F_MOD.write_text(MODULE, encoding="utf-8")
            print("cvd_m3_sim.py : mis a jour. Redemarre le bot.")
        else:
            print("Deja installe (rien a faire).")
        return 0
    if txt.count(ANCRE) != 1:
        print("REPERE INTROUVABLE (ou en double) dans icebergs.py : rien n'est modifie. Envoie-moi gimaly\\trading\\icebergs.py.")
        return 2
    nouveau = txt.replace(ANCRE, ANCRE + AJOUT)
    try:
        compile(nouveau, str(F_ICE), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F_ICE, SAUV)
    F_MOD.write_text(MODULE, encoding="utf-8")
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F_ICE.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("Installe : cvd_m3_sim.py cree, icebergs.py modifie (sauvegarde icebergs.py.avant_cvd_m3_sim).")
    print("Redemarre le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py. Journaux dans ~\\GIMALY\\trading\\cvd_m3_*.csv. Bilan : cvd_m3_bilan.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
