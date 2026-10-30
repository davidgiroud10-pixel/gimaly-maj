# -*- coding: utf-8 -*-
"""Ajoute des membres de la winleague au classement par canal (bloc signal_channels de config.local.yaml).

A lancer sur TON PC, depuis le dossier gimaly (sauvegarde config.local.avant_membres.yaml, rejouable sans risque) :
  .\\.venv\\Scripts\\python.exe ajouter_canaux.py pseudo1=NUMERO1 pseudo2=NUMERO2 ...
Exemple :
  .\\.venv\\Scripts\\python.exe ajouter_canaux.py rico=10450 sam=10511

NUMERO = le numero du sujet du membre dans la winleague (ce qui vient apres WINLEAGUE#).
Un pseudo deja present n'est pas touche. Rien d'autre dans le fichier n'est modifie.
"""
import re
import shutil
import sys
from pathlib import Path

CONFIG = Path.cwd() / "config.local.yaml"


def main(args):
    if not args or any(not re.fullmatch(r"[^=:#\s][^=:#]*=\d{1,6}", a) for a in args):
        sys.exit(__doc__)
    if not CONFIG.exists():
        sys.exit(f"{CONFIG} introuvable : lance ce script depuis le dossier gimaly")
    brut = CONFIG.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    texte = brut.decode("utf-8-sig")
    crlf = "\r\n" in texte
    lignes = texte.replace("\r\n", "\n").split("\n")
    debut = next((i for i, l in enumerate(lignes) if l.strip() == "signal_channels:"), None)
    if debut is None:
        sys.exit("bloc signal_channels introuvable : rien n'a ete change")
    fin = debut + 1
    while fin < len(lignes) and re.match(r"^[ \t]+\S", lignes[fin]):
        fin += 1
    existants = {re.match(r"^[ \t]+([^:]+):", l).group(1).strip().lower()
                 for l in lignes[debut + 1:fin] if re.match(r"^[ \t]+[^:#]+:", l)}
    nouvelles, deja = [], []
    for a in args:
        nom, num = a.rsplit("=", 1)
        nom = nom.strip().lower()
        (deja if nom in existants else nouvelles).append((nom, num))
        existants.add(nom)
    for nom, _ in deja:
        print(f"  deja present : {nom}")
    if not nouvelles:
        print("Rien a ajouter.")
        return
    lignes[fin:fin] = [f"  {nom}: WINLEAGUE#{num}" for nom, num in nouvelles]
    sortie = "\n".join(lignes)
    if crlf:
        sortie = sortie.replace("\n", "\r\n")
    sauvegarde = CONFIG.with_name("config.local.avant_membres.yaml")
    if not sauvegarde.exists():
        shutil.copy2(CONFIG, sauvegarde)
    CONFIG.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    for nom, num in nouvelles:
        print(f"  ajoute : {nom} -> WINLEAGUE#{num}")
    print(f"OK (sauvegarde : {sauvegarde.name}). Relance GIMALY si le classement ne les affiche pas.")


if __name__ == "__main__":
    main(sys.argv[1:])
