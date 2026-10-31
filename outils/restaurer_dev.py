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
COMPTE_ANCRE_METHODE = '    def peut_trader(self, marche=None, filtres=True):\n'
COMPTE_METHODE = '    def _compte_voulu(self):\n        # numero du compte MT5 choisi par l\'utilisateur (compte.bat), relu depuis config.local.yaml\n        # (au plus toutes les 30 s) : pas de redemarrage necessaire. 0 = pas de restriction.\n        try:\n            return int(str(_yaml_local().get("trading_mt5_compte", 0) or 0).strip() or 0)\n        except (TypeError, ValueError):\n            return -1          # valeur illisible : par prudence le bot ne trade pas\n\n'
COMPTE_CTRL_ANCIEN = '        if compte.trade_mode != 0 and not r["autorise_reel"]:\n            return False, "compte NON demo : refus (trading_autorise_reel est a false)"\n'
COMPTE_CTRL_NOUVEAU = '        if compte.trade_mode != 0 and not r["autorise_reel"]:\n            return False, "compte NON demo : refus (trading_autorise_reel est a false)"\n        voulu = self._compte_voulu()\n        if voulu < 0:\n            return False, "trading_mt5_compte illisible dans config.local.yaml (compte.bat pour corriger)"\n        if voulu and compte.login != voulu:\n            return False, (f"MT5 est connecte au compte {compte.login}, le bot est reserve au compte "\n                           f"{voulu} (compte.bat pour changer)")\n'
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
        texte = retirer_compte(texte)
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
        texte = poser_compte(texte)
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


def poser_compte(texte):
    """Ce que fait creer_installateur_v7.poser_compte_trading sur le trading.py du paquet."""
    if texte.count(COMPTE_ANCRE_METHODE) != 1 or texte.count(COMPTE_CTRL_ANCIEN) != 1:
        raise ValueError("reperes du patch compte introuvables")
    texte = texte.replace(COMPTE_ANCRE_METHODE, COMPTE_METHODE + COMPTE_ANCRE_METHODE)
    return texte.replace(COMPTE_CTRL_ANCIEN, COMPTE_CTRL_NOUVEAU)


def retirer_compte(texte):
    """Inverse de poser_compte (le patch ne doit exister qu'UNE fois dans le fichier du paquet)."""
    if texte.count(COMPTE_METHODE + COMPTE_ANCRE_METHODE) != 1 or texte.count(COMPTE_CTRL_NOUVEAU) != 1:
        raise ValueError("patch compte du paquet introuvable (ou en double)")
    texte = texte.replace(COMPTE_METHODE + COMPTE_ANCRE_METHODE, COMPTE_ANCRE_METHODE)
    return texte.replace(COMPTE_CTRL_NOUVEAU, COMPTE_CTRL_ANCIEN)


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


def corriger_compte_dev(chemin, appliquer):
    """Correction d'une restauration faite AVEC la v1 de ce script : elle laissait dans trading.py le patch
    « compte MT5 choisi » (ajoute seulement dans le paquet des amis). On le retire, puis on verifie en
    re-fabriquant le trading.py du paquet : il doit etre identique a celui de maj-7.N.zip (dans le dossier gimaly)."""
    import zipfile
    texte = lire_texte(chemin)
    if "def _compte_voulu" not in texte:
        print("  trading.py (patch compte) : rien a corriger")
        return True
    if texte.count(COMPTE_METHODE + COMPTE_ANCRE_METHODE) != 1:
        print("  trading.py (patch compte) : forme inattendue, RIEN ecrit")
        return False
    corrige = retirer_compte(texte)
    zips = sorted(RACINE.glob("maj-7.*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    refs = []
    for z in zips:
        try:
            with zipfile.ZipFile(z) as f:
                refs.append((z.name, f.read("gimaly/trading/trading.py").decode("utf-8").replace("\r\n", "\n")))
        except (OSError, KeyError, zipfile.BadZipFile):
            continue
    fabrique = appliquer_module("trading", corrige)
    trouve = [nom for nom, t in refs if t == fabrique]
    if not trouve:
        print("  trading.py (patch compte) : la verification contre maj-7.N.zip echoue (ou aucun zip present), RIEN ecrit")
        return False
    fdl = fin_de_ligne_habituelle(chemin)
    sortie = corrige.replace("\n", fdl).encode("utf-8")
    print(f"  trading.py (patch compte) : retire et verifie contre {trouve[0]} ({len(sortie)} octets)")
    if appliquer:
        copie = chemin.with_name(chemin.name + ".avant_correction_compte")
        if not copie.exists():
            shutil.copy2(chemin, copie)
        chemin.write_bytes(sortie)
    return True


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
    ok &= corriger_compte_dev(trading / "trading.py", appliquer)
    print()
    if not ok:
        raise SystemExit("au moins une verification a echoue : rien d'incertain n'a ete ecrit pour ces fichiers")
    if appliquer:
        print("Termine. Sauvegardes : <fichier>.avant_restauration. Reste a traiter : bridges\\telegram_lecture.py et trading\\flux_kmm.py.")
    else:
        print("Verification OK. Pour restaurer vraiment : relance avec --appliquer")


if __name__ == "__main__":
    main()
