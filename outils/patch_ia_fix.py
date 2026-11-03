# -*- coding: utf-8 -*-
r"""Correctif avis IA (v2 : le fichier ia_cle.txt prime sur la variable ANTHROPIC_API_KEY ; l'erreur du journal indique l'origine de la cle). Les modeles recents « reflechissent » avant de repondre, ce qui consommait les 200 jetons autorises et
coupait la reponse (erreur JSONDecodeError). Le module avis_ia.py est remplace par une version qui autorise 1500 jetons et lit la
reponse meme si elle est tronquee. Sauvegarde avis_ia.py.avant_fix. Idempotent. Usage (dossier gimaly) :
  .\.venv\Scripts\python.exe patch_ia_fix.py"""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "avis_ia.py"
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
    # le fichier ia_cle.txt a la priorite (une variable ANTHROPIC_API_KEY heritee du lanceur peut etre une ancienne cle)
    try:
        c = (DOSSIER / "ia_cle.txt").read_text(encoding="utf-8-sig").strip()
        if c:
            return c
    except OSError:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def _source():
    # pour le journal : d'ou vient la cle utilisee (4 derniers caracteres seulement)
    c = _cle()
    try:
        du_fichier = c == (DOSSIER / "ia_cle.txt").read_text(encoding="utf-8-sig").strip()
    except OSError:
        du_fichier = False
    return f"cle {'du fichier' if du_fichier else 'de la variable ANTHROPIC_API_KEY'} ...{c[-4:]}"


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
            log(f"avis IA indisponible : {exc!r} ({_source()})"[:240])
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


def main():
    if not F.parent.exists():
        print(f"{F.parent} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    if F.exists() and F.read_text(encoding="utf-8") == MODULE_TEXTE:
        print("avis_ia.py : deja a jour (rien a faire).")
        return 0
    try:
        compile(MODULE_TEXTE, "avis_ia.py", "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe : {exc}. Rien n'est ecrit.")
        return 3
    if F.exists():
        shutil.copy2(F, F.with_name(F.name + ".avant_fix"))
    F.write_text(MODULE_TEXTE, encoding="utf-8")
    print("avis_ia.py : mis a jour. Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
