# -*- coding: utf-8 -*-
"""Installe TON identifiant personnel GIMALY (le petit fichier identifiant-TONNOM.txt recu de l'editeur).

Le plus simple : glisse le fichier sur  identifiant.bat  (ou mets-le dans ce dossier, dans Telechargements ou sur
le Bureau, puis double-clique sur identifiant.bat). Ensuite : ARRETER puis DEMARRER dans GIMALY Panneau.
Tes autres reglages ne sont pas touches (sauvegarde : config.local.avant_identifiant.yaml).
"""
import re
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
CONFIG = RACINE / "config.local.yaml"
CANAL_OK = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
SECRET_OK = re.compile(r"^[0-9a-fA-F]{16,128}$")


def candidats():
    home = Path.home()
    trouves = []
    for dossier in (RACINE, home / "Downloads", home / "Telechargements", home / "Desktop", home / "Bureau"):
        try:
            trouves += [p for p in dossier.glob("identifiant*.txt") if p.is_file()]
        except OSError:
            pass
    return sorted(trouves, key=lambda p: p.stat().st_mtime, reverse=True)


def lire_identifiant(chemin):
    texte = Path(chemin).read_text(encoding="utf-8-sig", errors="replace")
    valeurs = {}
    for ligne in texte.splitlines():
        m = re.match(r"^\s*(trading_signaux_canal|trading_signaux_secret)\s*:\s*(\S+)\s*$", ligne)
        if m:
            valeurs[m.group(1)] = m.group(2).strip("\"'")
    if not CANAL_OK.match(valeurs.get("trading_signaux_canal", "")) or not SECRET_OK.match(valeurs.get("trading_signaux_secret", "")):
        raise SystemExit(f"{chemin} n'est pas un identifiant GIMALY valide (canal ou secret manquant ou abime).")
    return valeurs


def appliquer(valeurs):
    if not CONFIG.exists():
        raise SystemExit(f"{CONFIG} introuvable : lance ce script depuis le dossier GIMALY-Trading-v7 (apres installer.bat).")
    brut = CONFIG.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    texte = brut.decode("utf-8-sig")
    crlf = "\r\n" in texte
    lignes = texte.replace("\r\n", "\n").split("\n")
    for cle, val in valeurs.items():
        nouvelle = f"{cle}: {val}"
        trouve = False
        for i, l in enumerate(lignes):
            if re.match(r"^%s\s*:" % re.escape(cle), l):
                lignes[i] = nouvelle
                trouve = True
        if not trouve:
            while lignes and lignes[-1] == "":
                lignes.pop()
            lignes += [nouvelle, ""]
    sortie = ("\r\n" if crlf else "\n").join(lignes)
    copie = CONFIG.with_name("config.local.avant_identifiant.yaml")
    if not copie.exists():
        shutil.copy2(CONFIG, copie)
    CONFIG.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def auto():
    """Appele par le lanceur a chaque demarrage : si un fichier identifiant*.txt est dans ce dossier et n'est pas encore
    installe, il est installe. Renvoie une phrase pour le journal, ou None s'il n'y a rien a faire."""
    liste = [p for p in RACINE.glob("identifiant*.txt") if p.is_file()]
    if not liste or not CONFIG.exists():
        return None
    fichier = max(liste, key=lambda p: p.stat().st_mtime)
    try:
        valeurs = lire_identifiant(fichier)
    except SystemExit:
        return f"identifiant : {fichier.name} n'est pas valide, ignore"
    lignes = CONFIG.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
    if all(f"{k}: {v}" in [l.strip() for l in lignes] for k, v in valeurs.items()):
        return None
    appliquer(valeurs)
    return f"identifiant installe depuis {fichier.name}"


def main(argv):
    if argv:
        chemin = Path(argv[0].strip('"'))
        if not chemin.is_file():
            raise SystemExit(f"fichier introuvable : {chemin}")
    else:
        liste = candidats()
        if not liste:
            raise SystemExit("Aucun fichier identifiant*.txt trouve (ce dossier, Telechargements, Bureau).\n"
                             "Glisse ton fichier identifiant-TONNOM.txt sur identifiant.bat.")
        chemin = liste[0]
    valeurs = lire_identifiant(chemin)
    appliquer(valeurs)
    print(f"OK : identifiant installe depuis {chemin.name}")
    print("Maintenant : dans GIMALY Panneau, clique sur ARRETER puis DEMARRER (ou redemarre ton PC).")
    print("Garde ce fichier pour toi : ne l'envoie a personne.")
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    sys.exit(code)
