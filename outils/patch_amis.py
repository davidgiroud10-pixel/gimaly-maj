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
lMp56w==
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
