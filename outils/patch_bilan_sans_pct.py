# -*- coding: utf-8 -*-
r"""Bilan Telegram « GIMALY BOT — aujourd'hui » : retire le pourcentage de la ligne du resultat (il recopiait le R
en supposant 1 % de risque par trade, ce qui est faux). La ligne devient « 🔴 -0.90 R » ; le reste du message (pips,
trades, TP/SL, winrate) ne change pas. Ne touche qu'a gimaly/skills/signals_skill.py.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_bilan_sans_pct.py   puis relancer GIMALY (fenetre principale).
Sauvegarde signals_skill.py.avant_pct. Idempotent. Rien n'est ecrit si le repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "skills" / "signals_skill.py"
ANCIEN = """f"{signe} **{stats['r_total']:+.2f} R**  ·  {stats['pourcentage']:+.2f} %","""
NOUVEAU = """f"{signe} **{stats['r_total']:+.2f} R**","""


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    a, n = ANCIEN.encode("utf-8"), NOUVEAU.encode("utf-8")
    if n in brut and a not in brut:
        print("signals_skill.py : deja corrige (rien a faire).")
        return 0
    if brut.count(a) != 1:
        print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur.")
        return 2
    nouveau = brut.replace(a, n)
    try:
        compile(nouveau.decode("utf-8").lstrip("﻿"), str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_pct"))
    F.write_bytes(nouveau)
    print("signals_skill.py : corrige (sauvegarde signals_skill.py.avant_pct). Relance GIMALY pour que ce soit pris en compte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
