# -*- coding: utf-8 -*-
"""IDENTIFIANT PERSONNEL PAR AMI : un canal et un secret par ami, ton bot publie sur chacun, tu peux en couper un.

Ce patch (sur TON PC, depuis le dossier gimaly) :
  1. gimaly/trading/signaux_distants.py : publication sur le canal personnel de chaque ami actif (amis.json),
     et refus, cote ami, d'un signal destine a un autre canal. Compatible avec les bots deja installes
     (l'ancien canal commun continue de marcher tant que tu ne le coupes pas : amis.py ancien off).
  2. outils_v7/lancer.py : le lanceur d'un ami installe tout seul son fichier identifiant au demarrage, et envoie
     toutes les 10 minutes un « signe de vie » (retour.py) que la fenetre suivi_amis.py affiche chez toi.
  3. creer_installateur_v7.py : le paquet des amis ne contient PLUS de canal ni de secret des qu'un ami
     existe (amis.py ajouter NOM) ; il contient identifiant.py / identifiant.bat. Option --avec-canal : l'ancien mode.
Sauvegardes : <fichier>.avant_amis. Idempotent. Rien n'est ecrit si un repere manque (verification avant ecriture).
  .\\.venv\\Scripts\\python.exe patch_amis.py
"""
import base64
import hashlib
import re
import shutil
import zlib
from pathlib import Path

RACINE = Path.cwd()
SD = RACINE / "gimaly" / "trading" / "signaux_distants.py"
LANCEUR = RACINE / "outils_v7" / "lancer.py"
GEN = RACINE / "creer_installateur_v7.py"
SD_ANCIENS = ("56f16ebe9b617ff74b1baaeebe14e4ffd724e038c44dfab977acd59499c97d06", "17f9c52570ce03e86d84b0ae10da16004dfc01438c4bbda3005b49f783f56f61")      # version d'origine, version intermediaire
SD_NOUVEAU_SHA = "452e6cbf8ef552278b66eec0b4d6f2e6ea5e006a75a2b6ad625efb34f0ff5ee9"

SD_NOUVEAU = """
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
"""
IDENTIFIANT = """
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
"""
RETOUR = """
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
"""


def decoder(blob):
    return zlib.decompress(base64.b64decode("".join(blob.split())))


def lire(chemin):
    brut = chemin.read_bytes().decode("utf-8")
    return brut.replace("\r\n", "\n"), "\r\n" in brut


def ecrire(chemin, texte, crlf):
    copie = chemin.with_name(chemin.name + ".avant_amis")
    if not copie.exists():
        shutil.copy2(chemin, copie)
    chemin.write_bytes((texte.replace("\n", "\r\n") if crlf else texte).encode("utf-8"))


# ------------------------------------------------------------------ 1. signaux_distants.py
def prevoir_signaux():
    if not SD.exists():
        raise SystemExit(f"{SD} introuvable : lance depuis le dossier gimaly")
    actuel = SD.read_bytes().replace(b"\r\n", b"\n")
    sha = hashlib.sha256(actuel).hexdigest()
    if sha == SD_NOUVEAU_SHA:
        return None
    if sha not in SD_ANCIENS:
        raise SystemExit("signaux_distants.py n'est pas la version attendue (modifie ?) : RIEN ecrit. Envoie-le moi.")
    return decoder(SD_NOUVEAU)


# ------------------------------------------------------------------ 2. lancer.py
L_ANCRE = '    journal("lanceur demarre (Ctrl+C ou fichier lanceur.stop pour l\'arreter)")\n'
L_AJOUT = '''    try:
        import identifiant
        message = identifiant.auto()
        if message:
            journal(message)
    except Exception as exc:  # noqa: BLE001 - l'identifiant ne doit jamais empecher le bot de demarrer
        journal(f"identifiant : erreur ignoree {exc!r}")
'''
R_IMPORT = ("import sys\nimport time\n", "import sys\nimport threading\nimport time\n")
R_COMPTE = ("def compte_demo():\n",
            "_VERROU_MT5 = threading.Lock()\n\n\ndef compte_demo():\n"
            "    with _VERROU_MT5:                                  # le signe de vie l'appelle aussi, depuis un autre fil\n"
            "        return _compte_demo()\n\n\ndef _compte_demo():\n")
R_INIT = ("    prochaine_maj, en_attente = 0.0, None\n", "    prochaine_maj, en_attente = 0.0, None\n    prochain_retour = 0.0\n")
R_BOUCLE = "            for nom in PROCESSUS:\n                p = procs.get(nom)\n"
R_BLOC = '''            if time.time() >= prochain_retour:                   # signe de vie vers l'editeur (voir retour.py)
                prochain_retour = time.time() + 600
                try:
                    import retour
                    vivant = procs.get("bot") is not None and procs["bot"].poll() is None
                    etat_bot = "arrete" if not vivant else ("pause" if STOP_TRADES.exists() else "actif")
                    retour.battement(etat_bot, compte_demo, journal)
                except Exception as exc:  # noqa: BLE001 - le signe de vie ne doit jamais gener le bot
                    journal(f"retour : erreur ignoree {exc!r}")
'''


def prevoir_lanceur():
    if not LANCEUR.exists():
        raise SystemExit(f"{LANCEUR} introuvable : lance depuis le dossier gimaly")
    t, crlf = lire(LANCEUR)
    avant = t
    if "identifiant.auto()" not in t:
        if t.count(L_ANCRE) != 1:
            raise SystemExit("outils_v7/lancer.py : repere introuvable : RIEN ecrit")
        t = t.replace(L_ANCRE, L_ANCRE + L_AJOUT, 1)
    if "import retour" not in t:
        for nom, a in (("import", R_IMPORT[0]), ("compte_demo", R_COMPTE[0]), ("init", R_INIT[0]), ("boucle", R_BOUCLE)):
            if t.count(a) != 1:
                raise SystemExit(f"outils_v7/lancer.py : repere {nom} introuvable : RIEN ecrit")
        t = t.replace(R_IMPORT[0], R_IMPORT[1], 1).replace(R_COMPTE[0], R_COMPTE[1], 1)
        t = t.replace(R_INIT[0], R_INIT[1], 1).replace(R_BOUCLE, R_BLOC + R_BOUCLE, 1)
    if t == avant:
        return None
    compile(t, str(LANCEUR), "exec")
    return t, crlf


# ------------------------------------------------------------------ 3. creer_installateur_v7.py
A1 = "def lire(chemin, message):\n    try:\n        return chemin.read_text(encoding=\"utf-8-sig\").strip()\n"
A2 = '    F["terminal_dedie.bat"] = TERMINAL_DEDIE_BAT\n'
A3 = '    F["LISEZ-MOI-EN-PREMIER.txt"] = lm.replace(ancre2, PARAGRAPHE_COMPTE + ancre2)\n'
A4 = "    v6.MOTIFS_SENSIBLES = _FiltreMotifs(v6.MOTIFS_SENSIBLES)\n"
A5 = "    try:\n        v6.main()\n    finally:\n        pass\n"
A6 = '    if "--nom" not in sys.argv:\n        sys.argv += ["--nom", "GIMALY-Trading-v7"]\n'

BLOC = r'''IDENTIFIANT_B64 = (
@@IDENT_LITERAL@@
)
RETOUR_B64 = (
@@RETOUR_LITERAL@@
)
IDENTIFIANT_BAT = ("@echo off\ncd /d %~dp0\n.venv\\Scripts\\python.exe identifiant.py %1\n"
                   "echo.\npause\n")
CANAL_ABSENT = "IDENTIFIANT-A-INSTALLER"
PARAGRAPHE_IDENTIFIANT = """TON IDENTIFIANT PERSONNEL
-------------------------
Pour recevoir les signaux, il te faut un petit fichier personnel, "identifiant-TONNOM.txt", envoye par
l'editeur. Depose-le dans ce dossier (ou glisse-le sur   identifiant.bat  ) : il est installe tout seul au
prochain demarrage. Ensuite, dans "GIMALY Panneau", clique sur ARRETER puis DEMARRER.
Ce fichier est strictement personnel : ne le partage avec personne, il peut etre coupe a tout moment.
Tant qu'il n'est pas installe, le bot ne recoit aucun signal.


"""
PARAGRAPHE_SIGNE = """SIGNE DE VIE
------------
Toutes les 10 minutes, le bot envoie a l'editeur un petit message : ton pseudo, la version du programme,
l'etat du bot (actif / pause / arrete), demo ou reel, une empreinte de quelques fichiers du programme et un
numero d'installation aleatoire. JAMAIS ton numero de compte, ton solde, tes trades ni tes mots de passe.
Cela sert a savoir qui est connecte et a jour, et a voir si une installation sort du cadre prevu (compte reel,
fichiers modifies, identifiant partage). Le message est signe avec ton identifiant ; le code est lisible dans
retour.py. Sans identifiant installe, rien n'est envoye.


"""


def identifiant_py():
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(IDENTIFIANT_B64)).decode("utf-8")


def retour_py():
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(RETOUR_B64)).decode("utf-8")


def sans_canal():
    """Des qu'un ami existe (amis.py ajouter), le paquet ne contient plus ni canal ni secret."""
    if AVEC_CANAL:
        return False
    try:
        d = json.loads((Path.home() / "GIMALY" / "trading" / "amis.json").read_text(encoding="utf-8"))
        return bool(d.get("amis"))
    except (OSError, ValueError, AttributeError):
        return False


def retirer_canal_du_paquet(sortie):
    """Remplace le canal/secret de config.local.yaml du paquet par du vide et refait le zip."""
    import re
    f = sortie / "config.local.yaml"
    t = f.read_text(encoding="utf-8")
    t2 = re.sub(r"(?m)^(trading_signaux_(?:canal|secret):)[ \t]*%s[ \t]*$" % CANAL_ABSENT, r'\1 ""', t)
    if CANAL_ABSENT in t2 or t2 == t:
        raise SystemExit("paquet : canal/secret introuvables dans config.local.yaml, arret (zip a refaire)")
    f.write_text(t2, encoding="utf-8", newline="")
    shutil.make_archive(str(sortie), "zip", root_dir=str(sortie))
    print("  identifiant : le paquet ne contient AUCUN canal ni secret (chaque ami installe le sien)")


AVEC_CANAL = False


'''
PARA_ANCIEN = 'lm.replace(ancre2, PARAGRAPHE_IDENTIFIANT + PARAGRAPHE_COMPTE + ancre2)'
PARA_NOUVEAU_EXPR = 'PARAGRAPHE_IDENTIFIANT + PARAGRAPHE_SIGNE + PARAGRAPHE_COMPTE + ancre2'
PARA_NOUVEAU = 'lm.replace(ancre2, ' + PARA_NOUVEAU_EXPR + ')'


def litteral(donnees):
    blob = base64.b64encode(zlib.compress(donnees, 9)).decode()
    return "\n".join('    "%s"' % blob[i:i + 100] for i in range(0, len(blob), 100))


def prevoir_generateur():
    if not GEN.exists():
        raise SystemExit(f"{GEN} introuvable")
    t, crlf = lire(GEN)
    id_lit, re_lit = litteral(decoder(IDENTIFIANT)), litteral(decoder(RETOUR))
    if "RETOUR_B64" in t and id_lit in t and re_lit in t:
        return None
    if "IDENTIFIANT_B64" in t:                      # patch precedent (sans signe de vie) : mise a niveau
        if "RETOUR_B64" in t:
            raise SystemExit("creer_installateur_v7.py : etat inattendu (RETOUR_B64 sans les bons blocs) : RIEN ecrit")
        m = re.search(r'IDENTIFIANT_B64 = \(\n(?:    "[^"\n]*"\n)+\)\n', t)
        if m is None or t.count(PARA_ANCIEN) != 1 or t.count('    F["identifiant.bat"] = IDENTIFIANT_BAT\n') != 1 \
                or t.count("\n\ndef identifiant_py():") != 1:
            raise SystemExit("creer_installateur_v7.py : version precedente non reconnue : RIEN ecrit. Envoie-le moi.")
        sig = BLOC.index("PARAGRAPHE_SIGNE = ")
        fonc = BLOC.index("def retour_py")
        t = t[:m.start()] + "IDENTIFIANT_B64 = (\n" + id_lit + "\n)\nRETOUR_B64 = (\n" + re_lit + "\n)\n" + t[m.end():]
        t = t.replace("\n\ndef identifiant_py():",
                      "\n\n" + BLOC[sig:BLOC.index("def identifiant_py")].rstrip("\n") + "\n\n\n"
                      + BLOC[fonc:BLOC.index("def sans_canal")].rstrip("\n") + "\n\n\ndef identifiant_py():", 1)
        t = t.replace('    F["identifiant.bat"] = IDENTIFIANT_BAT\n', '    F["identifiant.bat"] = IDENTIFIANT_BAT\n    F["retour.py"] = retour_py()\n', 1)
        t = t.replace(PARA_ANCIEN, PARA_NOUVEAU, 1)
        compile(t, str(GEN), "exec")
        return t, crlf
    for nom, a in (("A1", A1), ("A2", A2), ("A3", A3), ("A4", A4), ("A5", A5), ("A6", A6)):
        if t.count(a) != 1:
            raise SystemExit(f"creer_installateur_v7.py : repere {nom} introuvable (une fois attendu) : RIEN ecrit")
    bloc = BLOC.replace("@@IDENT_LITERAL@@", id_lit).replace("@@RETOUR_LITERAL@@", re_lit)
    t = t.replace(A1, bloc + A1, 1)
    t = t.replace(A2, A2 + '    F["identifiant.py"] = identifiant_py()\n    F["identifiant.bat"] = IDENTIFIANT_BAT\n    F["retour.py"] = retour_py()\n', 1)
    t = t.replace(A3, '    F["LISEZ-MOI-EN-PREMIER.txt"] = ' + PARA_NOUVEAU + '\n', 1)
    t = t.replace(A4, A4 + "    if sans_canal():\n        v6.lire_canal = lambda: (CANAL_ABSENT, CANAL_ABSENT)\n", 1)
    t = t.replace(A5, "    try:\n        v6.main()\n    finally:\n        pass\n    if sans_canal():\n        retirer_canal_du_paquet(sortie)\n", 1)
    t = t.replace(A6, '    global AVEC_CANAL\n    if "--avec-canal" in sys.argv:\n        sys.argv.remove("--avec-canal")\n        AVEC_CANAL = True\n' + A6, 1)
    compile(t, str(GEN), "exec")
    return t, crlf


def main():
    print("Identifiant personnel par ami :")
    sd = prevoir_signaux()
    lanceur = prevoir_lanceur()
    gen = prevoir_generateur()
    if sd is not None:
        copie = SD.with_name(SD.name + ".avant_amis")
        if not copie.exists():
            shutil.copy2(SD, copie)
        SD.write_bytes(sd)
        print("  signaux_distants.py : mis a jour (canal personnel par ami)")
    else:
        print("  signaux_distants.py : deja a jour")
    for chemin, res, nom in ((LANCEUR, lanceur, "outils_v7/lancer.py"), (GEN, gen, "creer_installateur_v7.py")):
        if res is None:
            print(f"  {nom} : deja a jour")
        else:
            ecrire(chemin, res[0], res[1])
            print(f"  {nom} : mis a jour")
    print("\nTermine. Etape suivante : amis.py ajouter NOM  (pour chacun de tes amis), puis suivi_amis.bat.")


if __name__ == "__main__":
    main()
