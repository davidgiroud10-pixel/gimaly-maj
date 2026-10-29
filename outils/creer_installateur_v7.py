# -*- coding: utf-8 -*-
"""VERSION 7 : le paquet v6 (recepteur automatique) + signatures a cle publique + mise a jour automatique.

S'appuie sur creer_installateur_v6.py (meme dossier) : il en reprend toute la logique, y ajoute
  * sig25519.py (signature Ed25519) et la CLE PUBLIQUE de l'editeur (gimaly/trading/cle_publique.txt) ;
  * maj_auto.py + un lanceur qui cherche, installe et teste les mises a jour signees, puis se relance ;
  * VERSION.json (numero de version installee) et maj.bat (voir l'etat des mises a jour).
La cle PRIVEE ne sort jamais de ton PC : le script verifie qu'elle n'est pas dans le paquet.

Usage (depuis C:\\Users\\<toi>\\gimaly) :
  .\\.venv\\Scripts\\python.exe creer_installateur_v7.py --nom "GIMALY-Trading-v7"
"""
import json
import os
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
try:
    import creer_installateur_v6 as v6
except ImportError:
    raise SystemExit("creer_installateur_v6.py introuvable : lance ce script depuis le dossier gimaly")

OUTILS = RACINE / "outils_v7"
DOSSIER_GIMALY = Path.home() / "GIMALY"
CLE_PRIVEE = DOSSIER_GIMALY / "trading" / "cle_signature.priv"
CLE_PUBLIQUE = DOSSIER_GIMALY / "cle_publique.txt"
ETAT_PUBLICATION = DOSSIER_GIMALY / "publication_etat.json"
DEPOT = "davidgiroud10-pixel/gimaly-maj"

PARAGRAPHE_MAJ = """MISES A JOUR AUTOMATIQUES
-------------------------
Le programme se met a jour tout seul : au demarrage puis toutes les 6 heures, il regarde si l'editeur a
publie une nouvelle version. Chaque version est SIGNEE : une version qui n'est pas signee par l'editeur est
refusee. Avant de l'installer, le programme la teste ; si quelque chose ne va pas, il remet l'ancienne
version tout seul. Tes reglages (config.local.yaml) ne sont jamais touches.
Tu n'as rien a faire. Pour voir l'etat : double-clique sur   maj.bat
(le journal est dans le dossier  %USERPROFILE%\\GIMALY\\trading  : fichier maj.log).


"""


class _FiltreMotifs:
    """Meme controle que la v6, sauf l'adresse publique du depot de mises a jour (voulue)."""

    def __init__(self, base):
        self.base = base

    def search(self, ligne):
        return None if DEPOT in ligne else self.base.search(ligne)


def lire(chemin, message):
    try:
        return chemin.read_text(encoding="utf-8-sig").strip()
    except OSError:
        raise SystemExit(message)


def preparer():
    cle_pub = lire(CLE_PUBLIQUE, f"{CLE_PUBLIQUE} introuvable : lance d'abord outils_v7\\installer_v7.py")
    try:
        assert len(bytes.fromhex(cle_pub)) == 32
    except (ValueError, AssertionError):
        raise SystemExit("cle_publique.txt invalide")
    try:
        numero = int(json.loads(ETAT_PUBLICATION.read_text(encoding="utf-8")).get("numero", 0))
    except (OSError, ValueError):
        numero = 0
    for chemin, texte in ((RACINE / "gimaly/trading/sig25519.py", "sig25519.py"),
                          (RACINE / "maj_auto.py", "maj_auto.py"),
                          (OUTILS / "lancer.py", "outils_v7\\lancer.py")):
        if not chemin.exists():
            raise SystemExit(f"{texte} introuvable : lance d'abord outils_v7\\installer_v7.py")
    sd = (RACINE / "gimaly/trading/signaux_distants.py").read_text(encoding="utf-8")
    if "cle_publique_installee" not in sd:
        raise SystemExit("gimaly/trading/signaux_distants.py est l'ancienne version : lance outils_v7\\installer_v7.py")

    if "sig25519" not in v6.MODULES:
        v6.MODULES.append("sig25519")
    v6.MOTIFS_SENSIBLES = _FiltreMotifs(v6.MOTIFS_SENSIBLES)
    F = v6.FICHIERS
    F["lancer.py"] = (OUTILS / "lancer.py").read_text(encoding="utf-8")
    F["maj_auto.py"] = (RACINE / "maj_auto.py").read_text(encoding="utf-8")
    F["gimaly/trading/cle_publique.txt"] = cle_pub + "\n"
    F["VERSION.json"] = json.dumps({"numero": numero, "version": f"7.{numero}"})
    F["maj.bat"] = ("@echo off\ncd /d %~dp0\n.venv\\Scripts\\python.exe maj_auto.py --etat\n"
                    "echo.\necho (journal complet : %USERPROFILE%\\GIMALY\\trading\\maj.log)\npause\n")
    lm = F["LISEZ-MOI-EN-PREMIER.txt"]
    ancre = "CHAQUE JOUR\n-----------"
    if lm.count(ancre) != 1:
        raise SystemExit("LISEZ-MOI : repere introuvable, arret")
    F["LISEZ-MOI-EN-PREMIER.txt"] = lm.replace(ancre, PARAGRAPHE_MAJ + ancre)
    return numero


def verifier_sortie(sortie):
    """La cle privee ne doit JAMAIS se trouver dans le paquet."""
    graine = lire(CLE_PRIVEE, "cle privee introuvable : lance outils_v7\\installer_v7.py")
    for f in sortie.rglob("*"):
        if f.is_file():
            if "cle_signature" in f.name or graine.encode() in f.read_bytes():
                Path(str(sortie) + ".zip").unlink(missing_ok=True)
                raise SystemExit(f"ALERTE : la cle privee est dans {f} : paquet supprime")
    print("  cle privee : absente du paquet (voulu)")
    pub = (sortie / "gimaly/trading/cle_publique.txt").read_text(encoding="utf-8-sig").strip()
    print(f"  cle publique du paquet : {pub[:16]}...")


def main():
    if "--nom" not in sys.argv:
        sys.argv += ["--nom", "GIMALY-Trading-v7"]
    numero = preparer()
    print(f"Paquet v7 (version installee au depart : 7.{numero})")
    nom = sys.argv[sys.argv.index("--nom") + 1]
    if "--sortie" in sys.argv:
        sortie = Path(sys.argv[sys.argv.index("--sortie") + 1])
    else:
        sortie = Path.home() / nom
    try:
        v6.main()
    finally:
        pass
    verifier_sortie(sortie)


if __name__ == "__main__":
    main()
