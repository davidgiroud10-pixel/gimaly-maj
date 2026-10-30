# -*- coding: utf-8 -*-
"""Liste les sujets de la winleague (pseudo et numero) qui ne sont PAS encore dans ton classement par canal.

A lancer sur TON PC, depuis le dossier gimaly (lecture seule : rien n'est modifie) :
  .\\.venv\\Scripts\\python.exe lister_sujets_winleague.py            tous les sujets absents du classement
  .\\.venv\\Scripts\\python.exe lister_sujets_winleague.py --tout      tous les sujets, y compris ceux deja presents
Ferme GIMALY avant (il garde la session Telegram ouverte) si le programme parle d'une base verrouillee.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main():
    tout = "--tout" in sys.argv
    try:
        from gimaly.config import Config
        from gimaly.bridges import telegram_lecture as tl
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Lance ce script depuis le dossier gimaly ({exc!r})")
    config = Config.load()
    present = set()
    for valeur in (getattr(config, "signal_channels", None) or {}).values():
        m = re.search(r"#(\d+)\s*$", str(valeur))
        if m:
            present.add(m.group(1))
    try:
        sujets = tl.lister_sujets(config, "WINLEAGUE", 300)
    except Exception as exc:  # noqa: BLE001
        texte = repr(exc)
        if "lock" in texte.lower():
            sys.exit("La session Telegram est utilisee par GIMALY : ferme GIMALY puis relance cette commande.")
        sys.exit(f"Lecture des sujets impossible : {texte}")
    if not sujets:
        sys.exit("Aucun sujet renvoye par Telegram pour WINLEAGUE.")
    print(f"{len(sujets)} sujet(s) dans la winleague ; {len(present)} deja dans ton classement.\n")
    montres = 0
    for ligne in sujets:
        ligne = str(ligne)
        nums = set(re.findall(r"\d+", ligne))
        connu = bool(nums & present)
        if connu and not tout:
            continue
        montres += 1
        print(("  [deja] " if connu else "  ") + ligne)
    if not montres:
        print("Tous les sujets sont deja dans ton classement.")


if __name__ == "__main__":
    main()
