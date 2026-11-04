# -*- coding: utf-8 -*-
r"""Patch : un RETOUR sur le niveau casse doit TENIR le niveau (suite de patch_tendance_retest.py).
Constat du 04/11 18:50 : cassure haute a 4068,18, le prix est redescendu jusqu'a ~4064,4 (1,5 ATR SOUS le niveau, par une meche), puis il est
remonte : le bot a achete a 4069,50 en croyant a un retour valide ; stop sous le creux a 4063,95 ; le prix est reparti contre lui.
Seule la CLOTURE d'une bougie a plus d'1 ATR du niveau annulait la cassure : une meche profonde passait. Desormais la cassure est annulee
des que le prix (meche comprise) traverse le niveau de plus de trading_tendance_retest_tenue_atr (valeur initiale 0,5 ATR M5).
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_retest_tenue.py   puis redemarrer le bot (apres la fin d'un trade ouvert).
Sauvegarde trading.py.avant_tenue. Idempotent. Rien n'est ecrit si un repere manque. Necessite patch_tendance_retest.py deja applique."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "tendance_retest_tenue_atr"

A1 = '        "tendance_retest_atr": float(lire("trading_tendance_retest_atr", 0.3)),  # tolerance de « retour au niveau » (en ATR M5)\n'
B1 = A1 + '        "tendance_retest_tenue_atr": float(lire("trading_tendance_retest_tenue_atr", 0.5)),  # le retour doit tenir le niveau (meche comprise)\n'
A2 = "                    invalide, touche = c_b > niveau + atr, h_b >= niveau - marge\n"
B2 = ("                    attente['retour'] = max(attente.get('retour', h_b), h_b)     # sommet du retour, bougies APRES la cassure seulement\n"
      "                    invalide = c_b > niveau + atr or attente['retour'] > niveau + r['tendance_retest_tenue_atr'] * atr\n"
      "                    touche = h_b >= niveau - marge\n")
A3 = "                    invalide, touche = c_b < niveau - atr, l_b <= niveau + marge\n"
B3 = ("                    attente['retour'] = min(attente.get('retour', l_b), l_b)     # creux du retour, bougies APRES la cassure seulement\n"
      "                    invalide = c_b < niveau - atr or attente['retour'] < niveau - r['tendance_retest_tenue_atr'] * atr\n"
      "                    touche = l_b <= niveau + marge\n")
A4 = '''                    journal(f"tendance_m5 : le prix a rendu plus d'1 ATR au-dela de {niveau:.2f}, cassure abandonnee")
'''
B4 = '''                    journal(f"tendance_m5 : le retour n'a pas tenu le niveau {niveau:.2f} (creux/sommet du retour {attente['retour']:.2f}), cassure abandonnee")
'''
CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3), (A4, B4)]


def appliquer(txt):
    manquants = [a.strip()[:90] for a, _ in CHANGEMENTS if txt.count(a) != 1]
    if manquants:
        return None, "\n".join(manquants)
    for ancien, nouveau in CHANGEMENTS:
        txt = txt.replace(ancien, nouveau)
    return txt, None


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    crlf = brut.count(b"\r\n") > brut.count(b"\n") / 2
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    nouveau, erreur = appliquer(txt)
    if erreur:
        print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
        print(erreur)
        return 2
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_tenue"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_tenue). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
