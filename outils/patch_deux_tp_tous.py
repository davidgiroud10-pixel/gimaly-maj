# -*- coding: utf-8 -*-
"""Etend les DEUX objectifs (TP1 a 1,0 R pour la moitie, stop a l'entree, TP2) a TOUS les signaux qui n'avaient qu'un seul objectif fixe (scalps, tendance...).
A installer APRES patch_deux_tp.py (qui ajoute le mecanisme). scalp_keltner_large garde ses reglages propres (trading_keltner_large_tp).
Reglage (config.local.yaml) :  trading_deux_tp_tous: [1.0, 2.0]   -> TP1 = 1,0 R ; TP2 = le plus grand de 2,0 R et de l'objectif initial du signal (un objectif a 3 R reste a 3 R).
Liste vide ou absente = comportement d'avant pour ces signaux.
Les signaux qui n'avaient pas d'objectif impose utilisent deja 2 TP par defaut (trading_tp_r [2, 4]) : ils ne changent pas.
ATTENTION : seul scalp_keltner_large a ete teste en rejeu sur 10 mois (deux TP = meme esperance, seule la forme de la courbe change). Pour les autres genres, ce n'est PAS mesure.
Sauvegardes .avant_deux_tp_tous (trading.py, config.local.yaml). Retour arriere : --annuler. Idempotent. Rien n'est ecrit si un repere manque ou si le fichier ne compile plus.
Usage (dossier gimaly) : .\\.venv\\Scripts\\python.exe patch_deux_tp_tous.py [--annuler]   puis .\\.venv\\Scripts\\python.exe redemarrer_bot.py"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path.cwd()
T = RACINE / "gimaly" / "trading" / "trading.py"
CFG = RACINE / "config.local.yaml"
NOTES = Path.home() / "GIMALY" / "trading" / "notes_reglages.txt"
CLE = "trading_deux_tp_tous"
VALEUR = "[1.0, 2.0]"


def sauv(p):
    return p.with_name(p.name + ".avant_deux_tp_tous")


REMPLACEMENTS = [
    ("reglage deux_tp_tous",
     '        "keltner_large_tp": [float(x) for x in (lire("trading_keltner_large_tp", None) or [])],   # scalp_keltner_large : TP1 (moitie) puis point mort, TP2\n',
     '        "keltner_large_tp": [float(x) for x in (lire("trading_keltner_large_tp", None) or [])],   # scalp_keltner_large : TP1 (moitie) puis point mort, TP2\n'
     '        "deux_tp_tous": [float(x) for x in (lire("trading_deux_tp_tous", None) or [])],   # autres signaux a objectif unique : TP1 puis TP2 = max(2e niveau, objectif du signal)\n'),
    ("niveaux pour tous les genres",
     '            niveaux_r = []\n'
     '            if genre == "scalp_keltner_large":\n'
     '                niveaux_r = (contexte or {}).get("tp_niveaux_r") if distant else self.reglages.get("keltner_large_tp")\n',
     '            niveaux_r = []\n'
     '            if distant:\n'
     '                niveaux_r = (contexte or {}).get("tp_niveaux_r")\n'
     '            elif genre == "scalp_keltner_large" and self.reglages.get("keltner_large_tp"):\n'
     '                niveaux_r = self.reglages.get("keltner_large_tp")\n'
     '            elif len(self.reglages.get("deux_tp_tous") or []) >= 2:\n'
     '                base_r = self.reglages["deux_tp_tous"]\n'
     '                niveaux_r = [base_r[0], max(base_r[1], tp_r)]\n'),
    ("publication des niveaux pour tous les genres",
     '                if len(trade["tp"]) > 1 and trade.get("genre") == "scalp_keltner_large":\n',
     '                if len(trade["tp"]) > 1:\n'),
]


def lire_fichier(p):
    brut = p.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    return src.replace("\r\n", "\n"), bom, "\r\n" in src


def ecrire_fichier(p, texte, bom, crlf):
    sortie = texte.replace("\n", "\r\n") if crlf else texte
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def main():
    if "--annuler" in sys.argv:
        fait = False
        for p in (T, CFG):
            if sauv(p).exists():
                shutil.copy2(sauv(p), p)
                print(f"Restaure : {p.name}")
                fait = True
        if not fait:
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        print("Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
        return 0
    if not T.exists():
        print(f"{T} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    src, bom, crlf = lire_fichier(T)
    if '"deux_tp_tous"' in src:
        print("Deja installe. (Pour changer : trading_deux_tp_tous dans config.local.yaml, puis redemarre le bot.)")
        return 0
    if '"keltner_large_tp"' not in src:
        print("Installe d'abord patch_deux_tp.py. RIEN n'est modifie.")
        return 1
    nouveau = src
    for nom, ancien, rempl in REMPLACEMENTS:
        if nouveau.count(ancien) != 1:
            print(f"Repere introuvable ou ambigu ({nom}) : ton fichier differe de celui que j'ai teste. RIEN n'est modifie.")
            return 1
        nouveau = nouveau.replace(ancien, rempl)
    try:
        compile(nouveau, str(T), "exec")
    except SyntaxError as e:
        print(f"trading.py modifie ne compile pas ({e}). RIEN n'est modifie.")
        return 1
    shutil.copy2(T, sauv(T))
    ecrire_fichier(T, nouveau, bom, crlf)
    if CFG.exists():
        cfg, bc, cc = lire_fichier(CFG)
        if re.search(rf"^\s*{CLE}\s*:", cfg, re.M):
            print(f"{CLE} deja dans config.local.yaml : je ne le modifie pas.")
        else:
            shutil.copy2(CFG, sauv(CFG))
            cfg = cfg.rstrip("\n") + f"\n{CLE}: {VALEUR}          # 12/11 : TP1 (moitie) puis point mort, TP2 pour les signaux a objectif unique ([] = comme avant)\n"
            ecrire_fichier(CFG, cfg, bc, cc)
    else:
        print(f"config.local.yaml introuvable : ajoute a la main la ligne  {CLE}: {VALEUR}")
    try:
        NOTES.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%d/%m/%Y %H:%M} : {CLE} = {VALEUR} (deux TP + point mort pour tous les signaux a objectif unique)\n")
    except OSError:
        pass
    print("Installe. Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
