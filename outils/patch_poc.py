# -*- coding: utf-8 -*-
"""Installe la SIMULATION des strategies POC dans le bot (aucun ordre n'est jamais passe).

- ecrit gimaly/trading/strategie_poc.py
- accroche un appel protege dans Bot.boucle (apres suivre_fantomes), sans jamais gener le trading
- ne fait RIEN tant que config.local.yaml ne contient pas  trading_poc_simulation: true

A lancer depuis le dossier gimaly :  .\\.venv\\Scripts\\python.exe patch_poc.py
Sauvegarde : trading.py.avant_poc. Idempotent. Rien n'est ecrit si un repere manque.
Retour arriere : copie trading.py.avant_poc sur trading.py (ou mets le drapeau a false).
"""
import base64
import shutil
import sys
import zlib
from pathlib import Path

DOSSIER = Path.cwd() / "gimaly" / "trading"
TRADING = DOSSIER / "trading.py"
MODULE = DOSSIER / "strategie_poc.py"
BLOB = "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"

ANCRE = '''                try:
                    self.suivre_fantomes()
                except Exception as exc:          # le suivi des fantomes ne gene jamais le trading
                    journal(f"suivi des trades refuses : {exc!r}")
'''
AJOUT = '''                try:
                    from gimaly.trading import strategie_poc
                    strategie_poc.suivre(self)       # simulation POC : jamais d'ordre, inactive sans drapeau
                except Exception as exc:          # ne gene jamais le trading
                    journal(f"simulation POC : {exc!r}")
'''


def main():
    if not TRADING.exists():
        raise SystemExit(f"{TRADING} introuvable : lance ce script depuis le dossier gimaly")
    contenu = zlib.decompress(base64.b64decode(BLOB))
    brut = TRADING.read_bytes().decode("utf-8")
    crlf = "\r\n" in brut
    t = brut.replace("\r\n", "\n")
    if "strategie_poc.suivre" in t:
        etat_t = "deja accroche"
    else:
        if t.count(ANCRE) != 1:
            raise SystemExit("trading.py : repere de la boucle introuvable (une fois attendu) : RIEN ecrit. Envoie-moi trading.py.")
        t = t.replace(ANCRE, ANCRE + AJOUT, 1)
        compile(t.lstrip("\ufeff"), str(TRADING), "exec")
        etat_t = "accroche"
    compile(contenu.decode("utf-8"), "strategie_poc.py", "exec")
    copie = TRADING.with_name(TRADING.name + ".avant_poc")
    if etat_t == "accroche":
        if not copie.exists():
            shutil.copy2(TRADING, copie)
        TRADING.write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    MODULE.write_bytes(contenu)
    print(f"trading.py : {etat_t} ; strategie_poc.py installe.")
    print("Pour activer la simulation : ajoute la ligne  trading_poc_simulation: true  dans config.local.yaml, puis redemarre le bot.")
    print("Resultats : dossier GIMALY\\trading\\poc_resultats.csv (aucun ordre n'est passe).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
