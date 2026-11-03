# -*- coding: utf-8 -*-
r"""Patch 7.19 : (1) COUTS REELS : a chaque entree, spread et glissement sont ecrits dans couts_trades.csv (rien d'autre ne change) ;
(2) AVIS IA en MODE OBSERVATEUR : nouveau module gimaly/trading/avis_ia.py, appele en arriere-plan apres l'ouverture d'un trade ;
l'avis va dans ia_avis.csv, il ne bloque ni ne retarde jamais rien. DESACTIVE PAR DEFAUT. Pour l'activer (config.local.yaml) :
    trading_ia_avis: true            # + cle API : variable ANTHROPIC_API_KEY ou fichier %USERPROFILE%\GIMALY\trading\ia_cle.txt
    trading_ia_max_jour: 60          # plafond d'appels par jour (cout)
puis redemarrer le bot. Les donnees envoyees a l'API : sens, type de signal, prix, stop, spread, note, 30 dernieres bougies M1.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_couts_ia.py   puis redemarrer le bot / publier_maj.py.
Sauvegarde trading.py.avant_couts_ia. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd() / "gimaly" / "trading"
F = RACINE / "trading.py"
MODULE = RACINE / "avis_ia.py"
MARQUE = "_couts_et_avis"

MODULE_TEXTE = r"""# -*- coding: utf-8 -*-
r'''Avis d'une IA sur chaque trade ouvert : MODE OBSERVATEUR. L'avis est ecrit dans ia_avis.csv, il ne bloque, ne modifie
et ne retarde JAMAIS un trade (appel dans un fil separe, toute erreur est avalee). Desactive par defaut.
Reglages (config.local.yaml) :  trading_ia_avis: true   trading_ia_modele: claude-haiku-5-5   trading_ia_max_jour: 60
Cle API : variable d'environnement ANTHROPIC_API_KEY, ou fichier  %USERPROFILE%\GIMALY\trading\ia_cle.txt  (une seule ligne).'''
import csv
import json
import os
import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
FICHIER = DOSSIER / "ia_avis.csv"
COLONNES = ["date", "heure", "position", "genre", "sens", "pe", "sl", "avis", "confiance", "raison", "modele", "secondes"]
_VERROU = threading.Lock()
_COMPTE = {"jour": "", "n": 0}

CONSIGNE = (
    "Tu es un relecteur de trades XAUUSD (or) pour un bot de scalping. Un trade vient d'etre ouvert. A partir des seules "
    "donnees fournies, dis s'il te parait BON a prendre (ok) ou A EVITER (eviter), avec une confiance de 0 a 100 et une "
    "raison en une phrase en francais. Tu ne connais pas l'avenir : ne promets rien, reste prudent, dis 'ok' si rien ne "
    "te choque. Reponds UNIQUEMENT par un JSON : {\"avis\": \"ok\"|\"eviter\", \"confiance\": 0-100, \"raison\": \"...\"}"
)


def _cle():
    c = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if c:
        return c
    try:
        return (DOSSIER / "ia_cle.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _ecrire(ligne):
    with _VERROU:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        neuf = not FICHIER.exists()
        with open(FICHIER, "a", newline="", encoding="utf-8-sig") as f:
            e = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";", extrasaction="ignore")
            if neuf:
                e.writeheader()
            e.writerow(ligne)


def _extraire(texte):
    m = re.search(r'"avis"\s*:\s*"(\w+)', texte)
    if not m:
        raise ValueError("reponse illisible : " + texte[:80].replace("\n", " "))
    avis = "eviter" if m.group(1).lower().startswith("evit") else "ok"
    c = re.search(r'"confiance"\s*:\s*"?(\d+)', texte)
    conf = max(0, min(100, int(c.group(1)))) if c else 0
    r = re.search(r'"raison"\s*:\s*"([^"]*)', texte)
    raison = (r.group(1) if r else "")[:200].replace(";", ",").replace("\n", " ")
    return avis, conf, raison


def _appeler(donnees, modele):
    t0 = time.time()
    corps = json.dumps({
        "model": modele, "max_tokens": 1500, "system": CONSIGNE,
        "messages": [{"role": "user", "content": json.dumps(donnees, ensure_ascii=False)}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=corps, method="POST",
        headers={"x-api-key": _cle(), "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rep = json.loads(r.read().decode("utf-8"))
    texte = "".join(b.get("text", "") for b in rep.get("content", []) if b.get("type") == "text")
    return (*_extraire(texte), round(time.time() - t0, 1))


def _tache(donnees, modele, base, log):
    try:
        avis, conf, raison, sec = _appeler(donnees, modele)
        _ecrire({**base, "avis": avis, "confiance": conf, "raison": raison, "modele": modele, "secondes": sec})
    except Exception as exc:
        try:
            log(f"avis IA indisponible : {exc!r}"[:200])
        except Exception:
            pass


def demander(donnees, base, reglages, log):
    '''Lance l'appel en arriere-plan et rend la main tout de suite. Ne leve jamais d'exception.'''
    try:
        if not reglages.get("ia_avis") or not _cle():
            return False
        jour = datetime.now().strftime("%Y%m%d")
        if _COMPTE["jour"] != jour:
            _COMPTE["jour"], _COMPTE["n"] = jour, 0
        if _COMPTE["n"] >= int(reglages.get("ia_max_jour", 60)):
            return False
        _COMPTE["n"] += 1
        base = {"date": datetime.now().strftime("%d/%m/%Y"), "heure": datetime.now().strftime("%H:%M:%S"), **base}
        threading.Thread(target=_tache, args=(donnees, reglages.get("ia_modele") or "claude-haiku-5-5", base, log),
                         daemon=True).start()
        return True
    except Exception:
        return False
"""

REGLAGE_A = '        "sl_min_pips": float('
REGLAGE_B = ('        "ia_avis": bool(lire("trading_ia_avis", False)),   # avis IA en observation (jamais bloquant)\n'
             '        "ia_modele": str(lire("trading_ia_modele", "claude-haiku-5-5")),\n'
             '        "ia_max_jour": int(lire("trading_ia_max_jour", 60)),\n'
             '        "sl_min_pips": float(')

APPEL_A = '''        self._journal(trade, "ouvert")
        details = ", ".join('''
APPEL_B = '''        self._journal(trade, "ouvert")
        self._couts_et_avis(trade, tick, pe, achat, contexte)
        details = ", ".join('''

METHODE_A = "    def niveaux_marche(self):\n"
METHODE_B = '''    def _couts_et_avis(self, trade, tick, pe_demande, achat, contexte):
        """Spread et glissement de l'entree -> couts_trades.csv ; avis IA (observateur, en arriere-plan). Ne leve jamais."""
        try:
            spread = round(max(0.0, float(tick.ask) - float(tick.bid)), 2)
            reel = float(trade["pe"])
            glissement = round((reel - pe_demande) if achat else (pe_demande - reel), 2)   # > 0 = defavorable
            distance = abs(reel - trade["sl"])
            DOSSIER.mkdir(parents=True, exist_ok=True)
            neuf = not (DOSSIER / "couts_trades.csv").exists()
            with open(DOSSIER / "couts_trades.csv", "a", newline="", encoding="utf-8-sig") as f:
                e = csv.writer(f, delimiter=";")
                if neuf:
                    e.writerow(["date", "heure", "position", "sens", "genre", "volume", "spread", "pe_demande", "pe_reel",
                                "glissement", "distance"])
                maintenant = datetime.now()
                e.writerow([maintenant.strftime("%d/%m/%Y"), maintenant.strftime("%H:%M:%S"), trade["position"],
                            trade["sens"], trade["genre"], trade["volume"], spread, round(pe_demande, 2),
                            round(reel, 2), glissement, round(distance, 2)])
        except Exception as exc:
            journal(f"couts du trade non enregistres : {exc!r}")
            spread, distance = None, None
        try:
            if not self.reglages.get("ia_avis"):
                return
            from gimaly.trading import avis_ia
            bougies = []
            try:
                mt5 = self._mt5()
                for b in (mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M1, 0, 30) or [])[-30:]:
                    bougies.append([round(float(b["open"]), 2), round(float(b["high"]), 2),
                                    round(float(b["low"]), 2), round(float(b["close"]), 2)])
            except Exception:
                pass
            donnees = {"sens": trade["sens"], "signal": trade["genre"], "prix_entree": round(float(trade["pe"]), 2),
                       "stop": round(float(trade["sl"]), 2), "distance_stop_dollars": distance, "spread": spread,
                       "objectifs": [round(float(t), 2) for t in trade["tp"]], "note_bot": trade.get("note"),
                       "points": trade.get("points"), "raison_bot": trade.get("raison", "")[:200],
                       "heure": datetime.now().strftime("%H:%M"),
                       "observations": trade.get("observations") or {}, "bougies_M1_open_high_low_close": bougies}
            base = {"position": trade["position"], "genre": trade["genre"], "sens": trade["sens"],
                    "pe": round(float(trade["pe"]), 2), "sl": round(float(trade["sl"]), 2)}
            avis_ia.demander(donnees, base, self.reglages, journal)
        except Exception as exc:
            journal(f"avis IA non lance : {exc!r}")

    def niveaux_marche(self):
'''


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt = F.read_text(encoding="utf-8")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    for a in (REGLAGE_A, APPEL_A, METHODE_A):
        if txt.count(a) != 1:
            print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
            print(a.strip()[:80])
            return 2
    nouveau = txt.replace(REGLAGE_A, REGLAGE_B).replace(APPEL_A, APPEL_B).replace(METHODE_A, METHODE_B)
    try:
        compile(nouveau.lstrip("\ufeff"), str(F), "exec")
        compile(MODULE_TEXTE, "avis_ia.py", "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_couts_ia"))
    F.write_text(nouveau, encoding="utf-8")
    MODULE.write_text(MODULE_TEXTE, encoding="utf-8")
    print("trading.py : corrige (sauvegarde trading.py.avant_couts_ia) + avis_ia.py cree. Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
