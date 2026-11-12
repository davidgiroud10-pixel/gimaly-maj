# -*- coding: utf-8 -*-
"""Signal scalp_keltner_large : DEUX objectifs. La moitie de la position est prise au TP1 (1,0 R), le stop du reste passe a l'ENTREE (point mort), le reste vise le TP2 (2,0 R).
Le bot sait deja faire le partiel et le point mort (config par defaut trading_tp_r [2, 4]) : ce patch lui donne ces deux niveaux pour ce signal.
Reglage (config.local.yaml) :  trading_keltner_large_tp: [1.0, 2.0]   (liste vide ou absente = un seul objectif, comme avant)
Mesure (test_deux_tp.py, 12/11/2026, 12 350 signaux sur 10 mois) : meme esperance qu'un seul objectif a 1,5 R (-0,071 R contre -0,074 R par trade, ecart dans le bruit) ;
l'interet est la FORME de la courbe : plus de trades qui « passent », des sorties a zero au lieu de pertes entieres apres un 1er gain.
AMIS : les distances publiees portent maintenant aussi la liste des objectifs (tp_niveaux_r). Un bot d'ami qui n'a pas ce patch ignore cette liste et prend un seul objectif a 2,0 R
(sans partiel ni point mort) : sa sortie differe alors de la tienne. Pour la meme sortie chez tous, l'ami applique ce meme patch puis redemarre son bot.
Modifie trading.py, signaux_distants.py et config.local.yaml (sauvegardes .avant_deux_tp). Retour arriere : --annuler. Idempotent.
Rien n'est ecrit si un repere manque ou si un fichier ne compile plus.
Usage (dossier gimaly) : .\\.venv\\Scripts\\python.exe patch_deux_tp.py [--annuler]   puis .\\.venv\\Scripts\\python.exe redemarrer_bot.py"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path.cwd()
T = RACINE / "gimaly" / "trading" / "trading.py"
S = RACINE / "gimaly" / "trading" / "signaux_distants.py"
CFG = RACINE / "config.local.yaml"
NOTES = Path.home() / "GIMALY" / "trading" / "notes_reglages.txt"
CLE = "trading_keltner_large_tp"
VALEUR = "[1.0, 2.0]"


def sauv(p):
    return p.with_name(p.name + ".avant_deux_tp")


REMPLACEMENTS_T = [
    ("reglage keltner_large_tp",
     '        "lots_max": float(lire("trading_lots_max", 1.5)),          # garde-fou sur le volume\n',
     '        "lots_max": float(lire("trading_lots_max", 1.5)),          # garde-fou sur le volume\n'
     '        "keltner_large_tp": [float(x) for x in (lire("trading_keltner_large_tp", None) or [])],   # scalp_keltner_large : TP1 (moitie) puis point mort, TP2\n'),
    ("deux objectifs dans ouvrir",
     '            raisons_tp = [f"{tp_r:g}R"]\n'
     '            if self.reglages.get("tp_niveau", True) and not (contexte or {}).get("tp_fixe"):\n',
     '            raisons_tp = [f"{tp_r:g}R"]\n'
     '            niveaux_r = []\n'
     '            if genre == "scalp_keltner_large":\n'
     '                niveaux_r = (contexte or {}).get("tp_niveaux_r") if distant else self.reglages.get("keltner_large_tp")\n'
     '            if niveaux_r and len(niveaux_r) >= 2:\n'
     '                # 12/11 : TP1 (moitie) -> stop a l\'entree -> TP2 ; le partiel et le point mort sont geres par le suivi\n'
     '                tp = [round(pe_reel + float(r) * distance_reelle if achat else pe_reel - float(r) * distance_reelle, 2) for r in niveaux_r]\n'
     '                raisons_tp = [f"{float(r):g}R" for r in niveaux_r]\n'
     '                contexte = {**contexte, "tp_fixe": True}\n'
     '            if self.reglages.get("tp_niveau", True) and not (contexte or {}).get("tp_fixe"):\n'),
    ("liste des objectifs publiee aux amis",
     '            if risque > 0 and gain > 0:\n'
     '                return {**contexte, "tp_r": round(gain / risque, 2)}\n',
     '            if risque > 0 and gain > 0:\n'
     '                sortie = {**contexte, "tp_r": round(gain / risque, 2)}\n'
     '                if len(trade["tp"]) > 1 and trade.get("genre") == "scalp_keltner_large":\n'
     '                    sortie["tp_niveaux_r"] = [round(abs(float(t) - float(trade["pe"])) / risque, 2) for t in trade["tp"]]\n'
     '                return sortie\n'),
]
REMPLACEMENTS_S = [
    ("tp_niveaux_r dans le contexte minimal",
     'CLES_CONTEXTE_MIN = ("tp_r", "duree_max_min", "sl_max_pips", "tendance_h1", "retour_n")',
     'CLES_CONTEXTE_MIN = ("tp_r", "tp_niveaux_r", "duree_max_min", "sl_max_pips", "tendance_h1", "retour_n")'),
]


def lire_fichier(p):
    brut = p.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    crlf = "\r\n" in src
    return src.replace("\r\n", "\n"), bom, crlf


def ecrire_fichier(p, texte, bom, crlf):
    sortie = texte.replace("\n", "\r\n") if crlf else texte
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def preparer(p, remplacements, marque):
    src, bom, crlf = lire_fichier(p)
    if marque in src:
        return None, bom, crlf, "deja"
    nouveau = src
    for nom, ancien, rempl in remplacements:
        if nouveau.count(ancien) != 1:
            return None, bom, crlf, f"Repere introuvable ou ambigu ({nom}) dans {p.name}"
        nouveau = nouveau.replace(ancien, rempl)
    try:
        compile(nouveau, str(p), "exec")
    except SyntaxError as e:
        return None, bom, crlf, f"{p.name} modifie ne compile pas ({e})"
    return nouveau, bom, crlf, "ok"


def main():
    if "--annuler" in sys.argv:
        fait = False
        for p in (T, S, CFG):
            if sauv(p).exists():
                shutil.copy2(sauv(p), p)
                print(f"Restaure : {p.name}")
                fait = True
        if not fait:
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        print("Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
        return 0
    for p in (T, S):
        if not p.exists():
            print(f"{p} introuvable : lance ce script depuis le dossier gimaly.")
            return 1
    nt, bt, ct, et = preparer(T, REMPLACEMENTS_T, '"keltner_large_tp"')
    ns, bs, cs, es = preparer(S, REMPLACEMENTS_S, '"tp_niveaux_r"')
    if et not in ("ok", "deja") or es not in ("ok", "deja"):
        print((et if et not in ("ok", "deja") else es) + " : ton fichier differe de celui que j'ai teste. RIEN n'est modifie.")
        return 1
    if et == "deja" and es == "deja":
        print("Deja installe. (Pour changer les objectifs : modifie trading_keltner_large_tp dans config.local.yaml puis redemarre le bot.)")
        return 0
    if nt is not None:
        shutil.copy2(T, sauv(T))
        ecrire_fichier(T, nt, bt, ct)
    if ns is not None:
        shutil.copy2(S, sauv(S))
        ecrire_fichier(S, ns, bs, cs)
    if CFG.exists():
        cfg, bc, cc = lire_fichier(CFG)
        if re.search(rf"^\s*{CLE}\s*:", cfg, re.M):
            print(f"{CLE} deja dans config.local.yaml : je ne le modifie pas.")
        else:
            shutil.copy2(CFG, sauv(CFG))
            cfg = cfg.rstrip("\n") + f"\n{CLE}: {VALEUR}          # 12/11 : TP1 (moitie) puis point mort, TP2 pour scalp_keltner_large ([] = un seul objectif)\n"
            ecrire_fichier(CFG, cfg, bc, cc)
    else:
        print(f"config.local.yaml introuvable : ajoute a la main la ligne  {CLE}: {VALEUR}")
    try:
        NOTES.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%d/%m/%Y %H:%M} : {CLE} = {VALEUR} (moitie au TP1, point mort, TP2)\n")
    except OSError:
        pass
    print("Installe (trading.py, signaux_distants.py, config.local.yaml). Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
