# -*- coding: utf-8 -*-
"""RESTAURATION de gimaly/bridges/telegram_lecture.py et gimaly/trading/flux_kmm.py (remplaces par des versions
allegees apres l'extraction accidentelle d'une mise a jour dans le dossier de developpement).

Les deux fichiers ont ete reconstruits a partir de leurs .pyc (dossiers __pycache__, compiles avant l'accident)
et de tes sauvegardes. Ce script les ecrit SEULEMENT si leur code compile est strictement identique a celui du
.pyc present chez toi (a l'identique : instructions, numeros de ligne, constantes). Sinon : rien n'est ecrit.

Usage, depuis le dossier gimaly, avec le python de ton .venv (celui de GIMALY, Python 3.14) :
  .\\.venv\\Scripts\\python.exe restaurer_telegram_kmm.py              (verification seule)
  .\\.venv\\Scripts\\python.exe restaurer_telegram_kmm.py --appliquer  (ecrit ; sauvegarde <fichier>.avant_restauration)
"""
import base64
import importlib.util
import marshal
import shutil
import sys
import types
import zlib
from pathlib import Path

RACINE = Path.cwd()

TELEGRAM_LECTURE = """
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
fwH2O2IL
"""
FLUX_KMM = """
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
Vga7cjgSq8rR92Wf8iRwzIPAfy6sWDg=
"""

CIBLES = [
    ("gimaly/bridges/telegram_lecture.py", TELEGRAM_LECTURE, 26183),
    ("gimaly/trading/flux_kmm.py", FLUX_KMM, 3690),
]


def decoder(blob):
    return zlib.decompress(base64.b64decode("".join(blob.split())))


def normaliser(code, nom):
    """Meme code, avec un nom de fichier uniforme (le .pyc peut avoir ete compile avec un chemin relatif)."""
    constantes = tuple(normaliser(c, nom) if isinstance(c, types.CodeType) else c for c in code.co_consts)
    return code.replace(co_filename=nom, co_consts=constantes)


def pyc_de(chemin):
    marque = Path(importlib.util.cache_from_source(str(chemin)))
    return marque if marque.exists() else None


def main():
    appliquer = "--appliquer" in sys.argv
    if sys.version_info[:2] != (3, 14):
        raise SystemExit("Utilise le python du .venv de GIMALY (Python 3.14) : .\\.venv\\Scripts\\python.exe restaurer_telegram_kmm.py")
    print("Restauration de telegram_lecture.py et flux_kmm.py" + ("" if appliquer else " (VERIFICATION SEULE)") + " :")
    ok = True
    for relatif, blob, taille in CIBLES:
        chemin = RACINE / relatif
        contenu = decoder(blob)
        if len(contenu) != taille:
            raise SystemExit("contenu interne corrompu : arret")
        pyc = pyc_de(chemin)
        if pyc is None:
            print(f"  {relatif}: .pyc d'origine introuvable, RIEN ecrit")
            ok = False
            continue
        brut = pyc.read_bytes()
        attendu = marshal.loads(brut[16:])
        # le .pyc garde la taille du source qu'il a compile : doit etre celle du fichier reconstruit
        taille_pyc = int.from_bytes(brut[12:16], "little")
        code = compile(contenu.decode("utf-8"), "x", "exec")
        pareil = (marshal.dumps(normaliser(attendu, "x")) == marshal.dumps(normaliser(code, "x"))) and taille_pyc == taille
        if not pareil:
            print(f"  {relatif}: la reconstruction ne correspond PAS au .pyc (taille source {taille_pyc}), RIEN ecrit")
            ok = False
            continue
        actuel = chemin.read_bytes() if chemin.exists() else b""
        if actuel == contenu:
            print(f"  {relatif}: deja restaure")
            continue
        print(f"  {relatif}: reconstruction IDENTIQUE au .pyc d'origine ({taille} octets)")
        if appliquer:
            if chemin.exists():
                copie = chemin.with_name(chemin.name + ".avant_restauration")
                if not copie.exists():
                    shutil.copy2(chemin, copie)
            chemin.write_bytes(contenu)
    print()
    if not ok:
        raise SystemExit("au moins un fichier n'a pas pu etre verifie : rien d'incertain n'a ete ecrit")
    print("Termine." if appliquer else "Verification OK. Pour restaurer vraiment : relance avec --appliquer")


if __name__ == "__main__":
    main()
