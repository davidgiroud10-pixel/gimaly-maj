# -*- coding: utf-8 -*-
"""Avis IA, version 2 de la consigne, EN PARALLELE de la v1 (observation seule, rien ne bloque ni ne retarde un trade).
Pour chaque trade ouvert, l'IA donne deja un avis (v1, ia_avis.csv). Ce patch ajoute un 2e avis avec une consigne qui explique le signal
(un rebond sur bande Keltner se prend CONTRE le mouvement : flux et tendance contraires sont normaux) et ne laisse « eviter » que pour un element
precis et chiffre. L'avis v2 va dans ia_avis_v2.csv (memes colonnes). Les deux avis sont demandes dans le meme fil d'arriere-plan : le trade n'attend rien.
Cout : un 2e appel par trade (meme modele, plafond ia_max_jour inchange car il compte les trades). Toute erreur de la v2 est avalee.
Jugement : a environ 100 avis v2, comparer les trades « eviter » et « ok » de ia_avis_v2.csv (analyse_ia.py lit ia_avis.csv ; voir analyse_ia_v2 plus bas :
  .\\.venv\\Scripts\\python.exe patch_ia_v2.py --lire  affiche le resume v2).
Retour arriere : restaurer gimaly/trading/avis_ia.py.avant_ia_v2 (ou --annuler). Idempotent. Rien n'est ecrit si un repere manque ou si le fichier ne compile plus.
Usage (dossier gimaly) : .\\.venv\\Scripts\\python.exe patch_ia_v2.py [--annuler | --lire]   puis relancer le bot."""
import csv
import shutil
import statistics
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "avis_ia.py"
SAUVEGARDE = F.with_name(F.name + ".avant_ia_v2")

CONSIGNE_V2 = '''CONSIGNE_V2 = (
    "Tu es un relecteur de trades XAUUSD (or) pour un bot de scalping M1. Le signal est un REBOND sur la bande de Keltner : on achete quand "
    "le cours touche la bande basse, on vend quand il touche la bande haute, donc TOUJOURS contre le mouvement en cours. Consequence : un flux "
    "(delta, gros ordres, carnet) ou une tendance H1 qui vont dans le sens du mouvement, donc contre le trade, sont NORMAUX pour ce signal : ne les "
    "compte PAS comme un defaut. Le bot gagne environ 40 a 45 % de ses trades pour un gain moyen de 1,1 a 1,3 fois le risque : un ratio gain/risque "
    "d'environ 1,2 est la regle, pas une anomalie. Reponds 'ok' par defaut. Reponds 'eviter' SEULEMENT si tu vois dans les donnees un element precis "
    "et chiffre qui sort de l'ordinaire, par exemple : un stop plus petit que l'amplitude normale d'une minute (bougies M1 fournies), un spread anormalement "
    "large (plus de 0,5 dollar), une bougie d'entree deja extreme par rapport aux precedentes, des donnees incoherentes. Sans raison precise et chiffree, "
    "reponds 'ok'. Reponds UNIQUEMENT par un JSON : {\\"avis\\": \\"ok\\"|\\"eviter\\", \\"confiance\\": 0-100, \\"raison\\": \\"...\\"}"
)
FICHIER_V2 = DOSSIER / "ia_avis_v2.csv"
'''

REMPLACEMENTS = [
    ("constantes v2",
     'FICHIER = DOSSIER / "ia_avis.csv"\n',
     'FICHIER = DOSSIER / "ia_avis.csv"\n#V2_CONSTANTES#'),
    ("_ecrire : fichier au choix",
     'def _ecrire(ligne):\n'
     '    with _VERROU:\n'
     '        DOSSIER.mkdir(parents=True, exist_ok=True)\n'
     '        neuf = not FICHIER.exists()\n'
     '        with open(FICHIER, "a", newline="", encoding="utf-8-sig") as f:\n',
     'def _ecrire(ligne, fichier=None):\n'
     '    fichier = fichier or FICHIER\n'
     '    with _VERROU:\n'
     '        DOSSIER.mkdir(parents=True, exist_ok=True)\n'
     '        neuf = not fichier.exists()\n'
     '        with open(fichier, "a", newline="", encoding="utf-8-sig") as f:\n'),
    ("_appeler : consigne au choix",
     'def _appeler(donnees, modele):\n',
     'def _appeler(donnees, modele, consigne=None):\n'),
    ("_appeler : system",
     '"model": modele, "max_tokens": 1500, "system": CONSIGNE,\n',
     '"model": modele, "max_tokens": 1500, "system": consigne or CONSIGNE,\n'),
    ("_tache : v1 puis v2",
     '        _ecrire({**base, "avis": avis, "confiance": conf, "raison": raison, "modele": modele, "secondes": sec})\n'
     '    except Exception as exc:\n'
     '        try:\n'
     '            log(f"avis IA indisponible : {exc!r} ({_source()})"[:240])\n'
     '        except Exception:\n'
     '            pass\n',
     '        _ecrire({**base, "avis": avis, "confiance": conf, "raison": raison, "modele": modele, "secondes": sec})\n'
     '    except Exception as exc:\n'
     '        try:\n'
     '            log(f"avis IA indisponible : {exc!r} ({_source()})"[:240])\n'
     '        except Exception:\n'
     '            pass\n'
     '    try:                                    # v2 de la consigne, en parallele, observation seule\n'
     '        avis, conf, raison, sec = _appeler(donnees, modele, CONSIGNE_V2)\n'
     '        _ecrire({**base, "avis": avis, "confiance": conf, "raison": raison, "modele": modele, "secondes": sec}, FICHIER_V2)\n'
     '    except Exception as exc:\n'
     '        try:\n'
     '            log(f"avis IA v2 indisponible : {exc!r}"[:240])\n'
     '        except Exception:\n'
     '            pass\n'),
]


def lire():
    d = Path.home() / "GIMALY" / "trading"
    fa, ft = d / "ia_avis_v2.csv", d / "trades_bot.csv"
    if not fa.exists():
        print("ia_avis_v2.csv absent : le patch n'a pas encore produit d'avis (relance le bot, il faut des trades).")
        return 1
    sys.path.insert(0, str(Path.cwd()))
    try:
        import analyse_ia_raisons as ar
    except ImportError:
        print("analyse_ia_raisons.py est introuvable dans le dossier gimaly.")
        return 1
    with open(fa, newline="", encoding="utf-8-sig") as f:
        avis = list(csv.DictReader(f, delimiter=";"))
    with open(ft, newline="", encoding="utf-8-sig") as f:
        trades = list(csv.DictReader(f, delimiter=";"))
    paires = ar.appariement(avis, trades)
    print(f"{len(avis)} avis v2, {len(paires)} rapproches d'un trade termine")
    for v in ("eviter", "ok"):
        rs = [r for a, r in paires if a.get("avis") == v]
        if rs:
            print(f"  avis v2 « {v} » : {len(rs)} trades termines, R moyen {statistics.fmean(rs):+.3f}, gagnants {sum(1 for r in rs if r > 0)}/{len(rs)}")
        else:
            print(f"  avis v2 « {v} » : aucun trade termine")
    ev = [r for a, r in paires if a.get("avis") == "eviter"]
    ok = [r for a, r in paires if a.get("avis") == "ok"]
    if len(ev) >= 8 and len(ok) >= 8:
        lo, hi = ar.ic(ev, ok)
        print(f"  eviter - ok : {statistics.fmean(ev) - statistics.fmean(ok):+.3f}  IC 95 % [{lo:+.3f} ; {hi:+.3f}]   (utile seulement si l'IC est nettement NEGATIF)")
    print("Lecture : sous ~100 avis, c'est un ordre de grandeur. Ne rien bloquer sur cette base tant que l'IC n'exclut pas 0.")
    return 0


def main():
    if "--lire" in sys.argv:
        return lire()
    if "--annuler" in sys.argv:
        if not SAUVEGARDE.exists():
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        shutil.copy2(SAUVEGARDE, F)
        print(f"Restaure : {F.name} remis tel qu'avant le patch. Relance le bot.")
        return 0
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    crlf = "\r\n" in src
    src = src.replace("\r\n", "\n")
    if "CONSIGNE_V2" in src:
        print("Deja installe : rien a faire.")
        return 0
    nouveau = src
    for nom, ancien, remplacant in REMPLACEMENTS:
        if nouveau.count(ancien) != 1:
            print(f"Repere introuvable ou ambigu ({nom}) : ton avis_ia.py differe de celui que j'ai teste. RIEN n'est modifie.")
            return 1
        nouveau = nouveau.replace(ancien, remplacant.replace("#V2_CONSTANTES#", ""))
    # la consigne v2 doit venir APRES la definition de DOSSIER et de CONSIGNE
    marque = ")\n\n\ndef _cle():"
    if nouveau.count(marque) != 1:
        print("Repere introuvable (apres CONSIGNE) : RIEN n'est modifie.")
        return 1
    nouveau = nouveau.replace(marque, ")\n\n" + CONSIGNE_V2 + "\n\ndef _cle():")
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as e:
        print(f"Le fichier modifie ne compile pas ({e}) : RIEN n'est modifie.")
        return 1
    shutil.copy2(F, SAUVEGARDE)
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print(f"Installe : {len(REMPLACEMENTS) + 1} modifications dans {F.name} (sauvegarde {SAUVEGARDE.name}). Relance le bot : "
          f".\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
