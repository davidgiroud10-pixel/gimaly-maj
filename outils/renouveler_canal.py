# -*- coding: utf-8 -*-
"""Renouvelle le CANAL et le SECRET des signaux dans TA config.local.yaml (a lancer sur TON PC).

  .\\.venv\\Scripts\\python.exe renouveler_canal.py

A utiliser si le canal ou le secret ont ete exposes (ex. un zip contenant config.local.yaml mis sur un depot
public). Sauvegarde config.local.yaml en config.local.yaml.avant_rotation, ecrit de nouvelles valeurs
aleatoires, puis te dit quoi faire (redemarrer le bot, refaire le zip des amis). Rien n'est affiche en entier :
le secret ne s'affiche jamais.
"""
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

CONFIG = Path.cwd() / "config.local.yaml"


def remplacer(texte, cle, valeur):
    motif = re.compile(r"(?m)^(%s:[ \t]*)([^#\n]*?)([ \t]*(?:#.*)?)$" % re.escape(cle))
    if len(motif.findall(texte)) != 1:
        raise SystemExit(f"{cle} introuvable (ou en double) dans {CONFIG} : rien n'a ete change")
    return motif.sub(lambda m: m.group(1) + valeur + m.group(3), texte, count=1)


def main():
    if not CONFIG.exists():
        raise SystemExit("config.local.yaml introuvable : lance ce script depuis le dossier gimaly")
    texte = CONFIG.read_text(encoding="utf-8-sig")
    canal = "gimaly-" + secrets.token_urlsafe(18)[:24]
    secret = "s-" + secrets.token_urlsafe(32)
    nouveau = remplacer(remplacer(texte, "trading_signaux_canal", canal), "trading_signaux_secret", secret)
    sauvegarde = CONFIG.with_name("config.local.yaml.avant_rotation_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(CONFIG, sauvegarde)
    CONFIG.write_text(nouveau, encoding="utf-8", newline="")
    print(f"Sauvegarde : {sauvegarde.name}")
    print(f"Nouveau canal : {canal[:12]}...  (le secret n'est pas affiche)")
    print()
    print("A FAIRE MAINTENANT :")
    print("  1) Redemarre le bot pour qu'il publie sur le nouveau canal.")
    print("  2) Refais le zip des amis :  .\\.venv\\Scripts\\python.exe creer_installateur_v7.py --ecraser")
    print("  3) N'envoie QUE ce nouveau zip. L'ancien (ancien canal) ne recevra plus rien.")


if __name__ == "__main__":
    main()
