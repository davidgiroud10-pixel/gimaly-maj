# -*- coding: utf-8 -*-
r"""Patch bilan des canaux : afficher les trades sortis a plat (BE touche) dans les bilans.
Avant : « 12 trades · 3 TP · 3 SL » (les 6 BE n'apparaissaient nulle part). Apres : « 12 trades · 3 TP · 3 SL · 6 BE ».
Le nombre de BE = trades clotures - TP - SL (ne change aucun calcul : R, pips et winrate sont inchanges). Rien n'est affiche s'il n'y a aucun BE.
Fichier modifie : gimaly/skills/signals_skill.py (sauvegarde signals_skill.py.avant_be). Idempotent, rien n'est ecrit si un repere manque.
Usage (dossier gimaly, GIMALY ferme) :  .\.venv\Scripts\python.exe patch_be_bilan.py"""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "skills" / "signals_skill.py"
MARQUE = "_texte_be"

HELPER = '''def _texte_be(stats: dict, long: bool = False) -> str:
    """Trades sortis a plat (BE touche) : clotures moins TP moins SL. Vide s'il n'y en a pas."""
    try:
        n = int(stats.get("trades", 0)) - int(stats.get("avec_tp", 0)) - int(stats.get("au_sl", 0))
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return f", {n} a l'equilibre (BE)" if long else f"  \\u00b7  \\u2696\\ufe0f {n} BE"


def statistiques(trades: list[Trade]) -> dict:
'''

CHANGEMENTS = [
    ("def statistiques(trades: list[Trade]) -> dict:\n", HELPER),
    ("et {stats.get('au_sl', 0)} au SL, \"", "et {stats.get('au_sl', 0)} au SL{_texte_be(stats, True)}, \""),
    ("{stats.get('au_sl', 0)} SL\",\n", "{stats.get('au_sl', 0)} SL{_texte_be(stats)}\",\n"),
]


def appliquer(txt):
    for ancien, _ in CHANGEMENTS:
        if txt.count(ancien) != 1:
            return None, ancien.strip()[:90]
    for ancien, nouveau in CHANGEMENTS:
        txt = txt.replace(ancien, nouveau)
    return txt, None


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    txt = brut.decode("utf-8-sig")
    if MARQUE in txt:
        print("signals_skill.py : deja corrige (rien a faire).")
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
    shutil.copy2(F, F.with_name(F.name + ".avant_be"))
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + nouveau.encode("utf-8"))
    print("signals_skill.py : corrige (sauvegarde signals_skill.py.avant_be). Ferme et relance GIMALY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
