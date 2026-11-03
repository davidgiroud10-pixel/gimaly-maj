# -*- coding: utf-8 -*-
r"""Reglage « refuser les stops trop courts » (7.19) : trading_sl_refus_sous_pips. Si le stop final d'un trade (apres le plancher
trading_sl_min_pips) est SOUS cette valeur en pips (10 pips = 1 $), le trade est refuse et suivi en « fantome » (trades_refuses.csv),
comme les autres refus : on pourra donc mesurer plus tard ce que ce refus a fait gagner ou perdre. Motif ecrit : « stop trop court ».
DESACTIVE PAR DEFAUT (0). Pour l'activer, dans config.local.yaml :
    trading_sl_refus_sous_pips: 20     # refuse les trades dont le stop fait moins de 20 pips ; 0 = desactive
puis redemarrer le bot. Ne change rien aux trades deja ouverts.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_stop_court.py   puis redemarrer le bot / publier_maj.py.
Sauvegarde trading.py.avant_stopcourt. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "sl_refus_sous_pips"

REGLAGE_A = '''        "sl_min_pips": float('''
REGLAGE_B = '''        "sl_refus_sous_pips": float(lire("trading_sl_refus_sous_pips", 0)),   # 0 = desactive : refuse les stops plus courts
        "sl_min_pips": float('''

CODE_A = '''            distance = minimum
        maximum = self.reglages["sl_max_pips"] / PIPS_PAR_DOLLAR
'''
CODE_B = '''            distance = minimum
        refus_sous = self.reglages.get("sl_refus_sous_pips", 0) or 0
        if refus_sous and distance * PIPS_PAR_DOLLAR < refus_sous - 1e-6:
            fantome(f"stop trop court ({distance * PIPS_PAR_DOLLAR:.0f} pips < {refus_sous:.0f})")
            return None, (f"pas de trade : stop trop court ({distance * PIPS_PAR_DOLLAR:.0f} pips, "
                          f"minimum voulu {refus_sous:.0f})")
        maximum = self.reglages["sl_max_pips"] / PIPS_PAR_DOLLAR
'''


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt = F.read_text(encoding="utf-8")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    for a in (REGLAGE_A, CODE_A):
        if txt.count(a) != 1:
            print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
            print(a.strip()[:80])
            return 2
    nouveau = txt.replace(REGLAGE_A, REGLAGE_B).replace(CODE_A, CODE_B)
    try:
        compile(nouveau.lstrip("﻿"), str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_stopcourt"))
    F.write_text(nouveau, encoding="utf-8")
    print("trading.py : corrige (sauvegarde trading.py.avant_stopcourt). Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
