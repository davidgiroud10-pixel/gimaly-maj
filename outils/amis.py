# -*- coding: utf-8 -*-
"""Gestion de tes amis : un canal PERSONNEL (et un secret) par ami, un petit fichier d'identifiant a lui envoyer.

Ton bot publie chaque signal sur le canal de chaque ami actif. Si tu retires un ami, il ne recoit plus rien,
sans toucher aux autres. La liste est dans  %USERPROFILE%\\GIMALY\\trading\\amis.json  (sur TON PC seulement).

Usage (depuis le dossier gimaly) :
  .\\.venv\\Scripts\\python.exe amis.py ajouter NOM        cree l'ami et son fichier identifiant-NOM.txt
  .\\.venv\\Scripts\\python.exe amis.py liste               les amis, actifs ou retires
  .\\.venv\\Scripts\\python.exe amis.py retirer NOM         coupe cet ami (il ne recoit plus rien)
  .\\.venv\\Scripts\\python.exe amis.py reactiver NOM       le remet
  .\\.venv\\Scripts\\python.exe amis.py identifiant NOM     recree le fichier identifiant de cet ami
  .\\.venv\\Scripts\\python.exe amis.py ancien off|on       coupe / remet l'ANCIEN canal commun (a couper quand
                                                            tous tes amis ont installe leur identifiant)
Le bot lit la liste a chaque signal : rien a redemarrer.
"""
import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

FICHIER = Path(os.environ.get("GIMALY_AMIS") or (Path.home() / "GIMALY" / "trading" / "amis.json"))
DOSSIER_IDENTIFIANTS = Path(os.environ.get("GIMALY_IDENTIFIANTS") or (Path.home() / "GIMALY" / "identifiants"))
NOM_OK = re.compile(r"^[A-Za-z0-9_\-]{1,30}$")


def charger():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            raise ValueError
    except OSError:
        return {"amis": {}, "ancien_canal": True}
    except ValueError:
        raise SystemExit(f"{FICHIER} est illisible : arret (rien modifie). Une copie existe peut-etre : {FICHIER}.bak")
    d.setdefault("amis", {})
    d.setdefault("ancien_canal", True)
    for a in d["amis"].values():                     # amis crees avant le signe de vie : on leur ajoute un canal retour
        a.setdefault("retour", "gimaly-r-" + secrets.token_urlsafe(18))
    return d


def enregistrer(d):
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    if FICHIER.exists():
        shutil.copy2(FICHIER, FICHIER.with_name(FICHIER.name + ".bak"))
    tmp = FICHIER.with_name(FICHIER.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FICHIER)


def ecrire_identifiant(nom, ami):
    DOSSIER_IDENTIFIANTS.mkdir(parents=True, exist_ok=True)
    f = DOSSIER_IDENTIFIANTS / f"identifiant-{nom}.txt"
    f.write_text(
        f"# GIMALY - identifiant personnel de {nom}\n"
        "# PERSONNEL : ne le partage avec personne. Il te donne acces aux signaux ; s'il est partage,\n"
        "# il pourra etre coupe sans prevenir.\n"
        f"trading_signaux_canal: {ami['canal']}\n"
        f"trading_signaux_secret: {ami['secret']}\n"
        f"trading_signaux_retour: {ami['retour']}\n"
        f"trading_ami: {nom}\n", encoding="utf-8", newline="\r\n")
    return f


def nom_valide(nom):
    if not nom or not NOM_OK.match(nom):
        raise SystemExit("nom invalide : lettres, chiffres, - et _ seulement (30 max), sans espace")
    return nom


def trouver(d, nom):
    for n in d["amis"]:
        if n.lower() == nom.lower():
            return n
    raise SystemExit(f"ami inconnu : {nom} (amis.py liste pour voir)")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0].lower(), argv[1:]
    d = charger()
    if cmd == "ajouter":
        nom = nom_valide(args[0] if args else "")
        if any(n.lower() == nom.lower() for n in d["amis"]):
            raise SystemExit(f"{nom} existe deja (amis.py identifiant {nom} pour recreer son fichier)")
        d["amis"][nom] = {"canal": "gimaly-" + secrets.token_urlsafe(18), "secret": secrets.token_hex(16),
                          "retour": "gimaly-r-" + secrets.token_urlsafe(18),
                          "actif": True, "cree": time.strftime("%Y-%m-%d %H:%M")}
        enregistrer(d)
        f = ecrire_identifiant(nom, d["amis"][nom])
        print(f"OK : {nom} ajoute.\nFichier a lui envoyer (en prive) : {f}")
        print("Il le depose dans son dossier GIMALY-Trading-v7 (il est installe tout seul au demarrage du bot),")
        print("ou il le glisse sur identifiant.bat, puis ARRETER / DEMARRER dans le panneau.")
    elif cmd == "liste":
        if not d["amis"]:
            print("Aucun ami enregistre.")
        for n, a in d["amis"].items():
            print(f"  {n:<20} {'ACTIF ' if a.get('actif', True) else 'RETIRE'}  cree {a.get('cree', '?')}  canal {a['canal'][:12]}...")
        print(f"\nAncien canal commun : {'ACTIF' if d['ancien_canal'] else 'COUPE'}")
    elif cmd in ("retirer", "reactiver"):
        n = trouver(d, args[0] if args else "")
        d["amis"][n]["actif"] = (cmd == "reactiver")
        enregistrer(d)
        print(f"OK : {n} " + ("remis : il recoit de nouveau les signaux." if cmd == "reactiver"
                              else "retire : il ne recoit plus rien (effet immediat sur le prochain signal)."))
    elif cmd == "identifiant":
        n = trouver(d, args[0] if args else "")
        enregistrer(d)                                # fige le canal retour s'il vient d'etre cree
        print(f"Fichier : {ecrire_identifiant(n, d['amis'][n])}")
    elif cmd == "ancien":
        if not args or args[0].lower() not in ("on", "off"):
            raise SystemExit("amis.py ancien on|off")
        d["ancien_canal"] = args[0].lower() == "on"
        enregistrer(d)
        print("Ancien canal commun : " + ("ACTIF" if d["ancien_canal"] else "COUPE (seuls les canaux personnels recoivent)"))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
