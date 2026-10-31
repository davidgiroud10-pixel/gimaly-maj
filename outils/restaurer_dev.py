# -*- coding: utf-8 -*-
"""RESTAURATION de tes fichiers de DEVELOPPEMENT apres une extraction accidentelle d'une mise a jour (maj-7.N.zip)
dans le dossier gimaly.

Le paquet des amis est fabrique par creer_installateur_v6/v7 avec quelques remplacements de texte simples
(symbole de l'or, verrou demo, pause du panneau, nom d'utilisateur). Ce script les INVERSE, puis verifie
son travail : il re-applique les remplacements au fichier restaure et compare avec ce qui est en place.
Si c'est identique, la restauration est exacte (aux fins de ligne ppres, retablies d'apres tes anciennes sauvegardes).

Fichiers traites : gimaly/trading/{trading,icebergs,contexte_marche,liquidite,respiration}.py et bilan_reel.py.
NE traite PAS (a restaurer autrement, voir les explications) : gimaly/bridges/telegram_lecture.py, gimaly/trading/flux_kmm.py.

Usage, depuis le dossier gimaly (rien n'est ecrit sans --appliquer) :
  .\\.venv\\Scripts\\python.exe restaurer_dev.py              (verification seule)
  .\\.venv\\Scripts\\python.exe restaurer_dev.py --appliquer  (restaure ; sauvegarde  <fichier>.avant_restauration)
"""
import re
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd()
IMPORT_SYMBOLE = "from gimaly.trading.symbole import symbole_or  # symbole de l'or du courtier\n"
LITTERAL = re.compile(r'(?<=[(\s,])"XAUUSD"(?=\s*[,)])')
ATTENDUS = {"trading": 1, "icebergs": 11, "contexte_marche": 1, "liquidite": 1, "respiration": 1}
PAUSE_ANCIEN = "        for p in rec.recuperer():\n"
PAUSE_NOUVEAU = ("        signaux = rec.recuperer()\n"
                 "        if (DOSSIER / \"icebergs.stop\").exists():\n"
                 "            return          # PAUSE du panneau : les signaux recus pendant la pause sont ignores\n"
                 "        for p in signaux:\n")
REEL_ANCIEN = '"autorise_reel": bool(lire("trading_autorise_reel", False)),'
REEL_NOUVEAU = '"autorise_reel": False,   # paquet : demo uniquement'
UTIL_DEV = b"C:\\Users\\Alycia"
UTIL_PAQUET = b"C:\\Users\\<toi>"


def lire_texte(chemin):
    """Texte avec fins de ligne normalisees en \\n (comme read_text du generateur)."""
    return chemin.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------- sens PAQUET -> DEV (inverse)
def inverser_module(module, texte):
    n = texte.count("symbole_or()")
    if module == "trading":
        a = IMPORT_SYMBOLE + "SYMBOLE = symbole_or()"
        if texte.count(a) != 1:
            raise ValueError("ligne SYMBOLE du paquet introuvable")
        texte = texte.replace(a, 'SYMBOLE = "XAUUSD"')
        if texte.count(REEL_NOUVEAU) != 1:
            raise ValueError("verrou demo du paquet introuvable")
        texte = texte.replace(REEL_NOUVEAU, REEL_ANCIEN)
        if texte.count(PAUSE_NOUVEAU) != 1:
            raise ValueError("pause distante du paquet introuvable")
        texte = texte.replace(PAUSE_NOUVEAU, PAUSE_ANCIEN)
        n_restants = texte.count("symbole_or")
        if n_restants:
            raise ValueError("trading.py : 'symbole_or' encore present apres inversion")
    else:
        if n != ATTENDUS[module]:
            raise ValueError(f"{module}.py : {n} occurrence(s) de symbole_or() au lieu de {ATTENDUS[module]}")
        # import ajoute avant le bloc  if __name__ == "__main__":  ou en toute fin de fichier
        if texte.count("\n" + IMPORT_SYMBOLE) != 1:
            raise ValueError(f"{module}.py : ligne d'import du paquet introuvable (ou en double)")
        if texte.endswith("\n\n" + IMPORT_SYMBOLE):
            texte = texte[: -len("\n\n" + IMPORT_SYMBOLE)] + "\n"
        else:
            texte = texte.replace("\n" + IMPORT_SYMBOLE, "", 1)
        texte = texte.replace("symbole_or()", '"XAUUSD"')
        if "symbole_or" in texte:
            raise ValueError(f"{module}.py : 'symbole_or' encore present apres inversion")
    return texte.replace(UTIL_PAQUET.decode(), UTIL_DEV.decode())


# ---------------------------------------------------------------- sens DEV -> PAQUET (verification)
def appliquer_module(module, texte):
    texte = texte.replace(UTIL_DEV.decode(), UTIL_PAQUET.decode())
    if module == "trading":
        texte = texte.replace('SYMBOLE = "XAUUSD"', IMPORT_SYMBOLE + "SYMBOLE = symbole_or()")
        texte = texte.replace(REEL_ANCIEN, REEL_NOUVEAU)
        texte = texte.replace(PAUSE_ANCIEN, PAUSE_NOUVEAU)
        return texte
    lignes = []
    n = 0
    for l in texte.split("\n"):
        s = l.strip()
        if not s.startswith(("print", "#", '"""')) and 'f"' not in l:
            l, k = LITTERAL.subn("symbole_or()", l)
            n += k
        lignes.append(l)
    texte = "\n".join(lignes)
    if n:
        marque = "\nif __name__ == \"__main__\":"
        i = texte.rfind(marque)
        if i >= 0:
            texte = texte[:i] + "\n" + IMPORT_SYMBOLE + texte[i:]
        else:
            texte = texte.rstrip("\n") + "\n\n" + IMPORT_SYMBOLE
    return texte


def fin_de_ligne_habituelle(chemin):
    """CRLF si tes anciennes sauvegardes du meme fichier sont en CRLF."""
    sauvegardes = sorted(chemin.parent.glob(chemin.name + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for s in sauvegardes[:5]:
        try:
            brut = s.read_bytes()
        except OSError:
            continue
        if b"\r\n" in brut:
            return "\r\n"
        if b"\n" in brut:
            return "\n"
    return "\n"


def traiter(chemin, inverser, appliquer_direct, appliquer, etiquette):
    if not chemin.exists():
        print(f"  {etiquette}: fichier absent, ignore")
        return True
    actuel = lire_texte(chemin)
    try:
        restaure = inverser(actuel)
    except ValueError as e:
        print(f"  {etiquette}: deja en version dev (ou version inattendue) : {e}")
        return True
    if appliquer_direct(restaure) != actuel:
        print(f"  {etiquette}: ECHEC de la verification (la restauration ne redonne pas le fichier en place), RIEN ecrit")
        return False
    fdl = fin_de_ligne_habituelle(chemin)
    sortie = restaure.replace("\n", fdl).encode("utf-8")
    print(f"  {etiquette}: restaure et verifie ({len(sortie)} octets, fins de ligne {'CRLF' if fdl == chr(13)+chr(10) else 'LF'})")
    if appliquer:
        copie = chemin.with_name(chemin.name + ".avant_restauration")
        if not copie.exists():
            shutil.copy2(chemin, copie)
        chemin.write_bytes(sortie)
    return True


BILAN_PAQUET_1 = 'Path.home() / "GIMALY" / "trading"'
BILAN_DEV_1 = 'Path(r"C:\\Users\\Alycia\\GIMALY\\trading")'
BILAN_PAQUET_2 = "Usage (depuis le dossier du paquet) :"
BILAN_DEV_2 = "Usage (depuis C:\\\\Users\\\\Alycia\\\\gimaly) :"


def inverser_bilan(t):
    if BILAN_PAQUET_1 not in t:
        raise ValueError("chemin du paquet introuvable")
    return t.replace(BILAN_PAQUET_1, BILAN_DEV_1).replace(BILAN_PAQUET_2, BILAN_DEV_2)


def appliquer_bilan(t):
    return t.replace(BILAN_DEV_1, BILAN_PAQUET_1).replace(BILAN_DEV_2, BILAN_PAQUET_2)


def main():
    appliquer = "--appliquer" in sys.argv
    trading = RACINE / "gimaly" / "trading"
    if not trading.is_dir():
        raise SystemExit("lance ce script depuis le dossier gimaly (celui qui contient le dossier gimaly\\trading)")
    print("Restauration des fichiers de developpement" + ("" if appliquer else " (VERIFICATION SEULE, rien n'est ecrit)") + " :")
    ok = True
    for module in ATTENDUS:
        ok &= traiter(trading / (module + ".py"),
                      lambda t, m=module: inverser_module(m, t),
                      lambda t, m=module: appliquer_module(m, t),
                      appliquer, module + ".py")
    ok &= traiter(RACINE / "bilan_reel.py", inverser_bilan, appliquer_bilan, appliquer, "bilan_reel.py")
    print()
    if not ok:
        raise SystemExit("au moins une verification a echoue : rien d'incertain n'a ete ecrit pour ces fichiers")
    if appliquer:
        print("Termine. Sauvegardes : <fichier>.avant_restauration. Reste a traiter : bridges\\telegram_lecture.py et trading\\flux_kmm.py.")
    else:
        print("Verification OK. Pour restaurer vraiment : relance avec --appliquer")


if __name__ == "__main__":
    main()
