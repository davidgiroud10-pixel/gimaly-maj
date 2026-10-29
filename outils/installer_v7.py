# -*- coding: utf-8 -*-
"""Installe chez toi (l'editeur) les outils de la version 7 : signature a cle publique + mises a jour.

A lancer UNE FOIS, depuis C:\\Users\\<toi>\\gimaly, avec les fichiers telecharges dans  outils_v7\\ :
  .\\.venv\\Scripts\\python.exe outils_v7\\installer_v7.py

Ce qu'il fait (rien n'est supprime, tout est sauvegarde en  *.avant_v7 ) :
  1. copie sig25519.py et la nouvelle signaux_distants.py dans gimaly\\trading ;
  2. copie maj_auto.py, publier_maj.py et creer_installateur_v7.py dans le dossier gimaly ;
  3. cree TA paire de cles : la cle PRIVEE reste sur ton PC (jamais dans un paquet), la cle publique sera
     livree aux amis ;
  4. verifie que tout fonctionne (signature, verification, rejet d'une falsification).
Relancer ce script ne change pas tes cles existantes.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd()
OUTILS = Path(__file__).resolve().parent
DOSSIER_GIMALY = Path.home() / "GIMALY"
CLE_PRIVEE = DOSSIER_GIMALY / "trading" / "cle_signature.priv"
CLE_PUBLIQUE = DOSSIER_GIMALY / "cle_publique.txt"
ETAT = DOSSIER_GIMALY / "publication_etat.json"
COPIES = [("sig25519.py", "gimaly/trading/sig25519.py"),
          ("signaux_distants.py", "gimaly/trading/signaux_distants.py"),
          ("maj_auto.py", "maj_auto.py"),
          ("publier_maj.py", "publier_maj.py"),
          ("creer_installateur_v7.py", "creer_installateur_v7.py")]


def main():
    if not (RACINE / "gimaly" / "trading" / "trading.py").exists():
        sys.exit("Lance ce script depuis le dossier gimaly (C:\\Users\\<toi>\\gimaly).")
    if not (RACINE / "creer_installateur_v6.py").exists():
        sys.exit("creer_installateur_v6.py est introuvable dans ce dossier : il est necessaire (le v7 s'appuie dessus).")
    manque = [s for s, _ in COPIES + [("lancer.py", "")] if not (OUTILS / s).exists()]
    if manque:
        sys.exit(f"fichiers manquants dans {OUTILS} : {manque}")

    print("1/4  Copie des fichiers (sauvegarde *.avant_v7 des fichiers remplaces)")
    for src, dst in COPIES:
        cible = RACINE / dst
        if cible.exists() and cible.read_bytes() != (OUTILS / src).read_bytes():
            sauve = cible.with_name(cible.name + ".avant_v7")
            if not sauve.exists():
                shutil.copy2(cible, sauve)
        shutil.copyfile(OUTILS / src, cible)
        print(f"     {dst}")

    print("2/4  Cles de signature")
    sys.path.insert(0, str(RACINE / "gimaly" / "trading"))
    import sig25519
    (DOSSIER_GIMALY / "trading").mkdir(parents=True, exist_ok=True)
    if CLE_PRIVEE.exists():
        graine = bytes.fromhex(CLE_PRIVEE.read_text(encoding="utf-8").strip())
        print("     cle privee deja presente : conservee")
    else:
        graine = sig25519.generer_graine()
        CLE_PRIVEE.write_text(graine.hex(), encoding="utf-8")
        print(f"     cle privee creee : {CLE_PRIVEE}")
    pub = sig25519.cle_publique(graine).hex()
    CLE_PUBLIQUE.write_text(pub, encoding="utf-8")
    if not ETAT.exists():
        ETAT.write_text(json.dumps({"numero": 0}), encoding="utf-8")
    print(f"     cle publique : {pub}")

    print("3/4  Verification")
    import importlib
    sd = importlib.import_module("signaux_distants")
    importlib.reload(sd)
    msg = sd.emballer({"sens": "achat", "genre": "essai", "sl_dist": 1.0}, "secret-d-essai")
    assert sd.ouvrir_message(msg, "x", pub) is not None, "signature Ed25519 non verifiee"
    faux = json.loads(msg)
    faux["p"]["sl_dist"] = 99
    assert sd.ouvrir_message(json.dumps(faux), "x", pub) is None, "une falsification est passee"
    assert sd.ouvrir_message(msg, "secret-d-essai") is not None, "compatibilite v6 cassee"
    print("     signature OK, falsification rejetee, compatibilite v6 OK")

    print("4/4  Termine.\n")
    print("A FAIRE MAINTENANT :")
    print(f"  1. SAUVEGARDE ta cle privee (copie-la sur une cle USB ou un gestionnaire de mots de passe) :")
    print(f"       {CLE_PRIVEE}")
    print("     Sans elle, tu ne pourras plus publier de mises a jour reconnues par tes amis.")
    print("     Ne l'envoie a personne et ne la mets dans aucun paquet.")
    print("  2. Redemarre ton bot quand aucun trade n'est ouvert : il publiera alors les signaux signes.")


if __name__ == "__main__":
    main()
