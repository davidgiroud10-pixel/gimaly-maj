# -*- coding: utf-8 -*-
"""IDENTIFIANT PERSONNEL PAR AMI : un canal et un secret par ami, ton bot publie sur chacun, tu peux en couper un.

Ce patch (sur TON PC, depuis le dossier gimaly) :
  1. gimaly/trading/signaux_distants.py : publication sur le canal personnel de chaque ami actif (amis.json),
     et refus, cote ami, d'un signal destine a un autre canal. Compatible avec les bots deja installes
     (l'ancien canal commun continue de marcher tant que tu ne le coupes pas : amis.py ancien off).
  2. outils_v7/lancer.py : le lanceur d'un ami envoie toutes les 10 minutes un « signe de vie » (retour.py), recoit
     tout seul son identifiant personnel (attribution.py) et redemarre son bot au bon moment ; il installe aussi
     un fichier identifiant depose dans son dossier.
  3. creer_installateur_v7.py : le paquet des amis ne contient PLUS de canal ni de secret des qu'un ami
     existe ; il contient identifiant.py / identifiant.bat / retour.py / attribution.py. Option --avec-canal : l'ancien mode.
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
ATTRIBUTION = """
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
Uuw529vZGfwbDjkQfw==
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
# redemarrage du bot apres l'installation automatique d'un identifiant (attribution.py)
F_FLAG = ('STOP_LANCEUR = DOSSIER / "lanceur.stop"\n',
          'STOP_LANCEUR = DOSSIER / "lanceur.stop"\n'
          'FLAG_REDEMARRAGE = DOSSIER / "redemarrage_bot.flag"   # pose par attribution.py : un nouvel identifiant attend un redemarrage du bot\n')
F_FONCTIONS = ("def maj_disponible():\n", '''def positions_ouvertes():
    """Nombre de positions ouvertes sur le compte MT5, ou None si on ne peut pas le savoir."""
    with _VERROU_MT5:
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return None
            try:
                return mt5.positions_total()
            finally:
                mt5.shutdown()
        except Exception:
            return None


def redemarrage_possible(maj):
    """Redemarrer le bot sans risque : marche de l'or ferme, ou aucune position ouverte."""
    try:
        if maj is not None and maj.marche_ferme():
            return True
    except Exception:  # noqa: BLE001
        pass
    return positions_ouvertes() == 0


def maj_disponible():
''')
F_DEMARRAGE = ("    maj = maj_disponible()\n", '''    try:
        FLAG_REDEMARRAGE.unlink()                      # le bot demarre maintenant : il lira le nouvel identifiant
    except OSError:
        pass
    maj = maj_disponible()
''')
F_BLOC = '''            if FLAG_REDEMARRAGE.exists():                        # nouvel identifiant installe (attribution.py)
                p = procs.get("bot")
                if p is None or p.poll() is not None:
                    FLAG_REDEMARRAGE.unlink()                   # le bot ne tourne pas : il lira le nouvel identifiant
                elif redemarrage_possible(maj):
                    journal("nouvel identifiant installe : redemarrage du bot")
                    FLAG_REDEMARRAGE.unlink()
                    p.terminate()
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
    if "FLAG_REDEMARRAGE" not in t:
        for nom, a in (("stop", F_FLAG[0]), ("maj_disponible", F_FONCTIONS[0]), ("demarrage", F_DEMARRAGE[0]), ("boucle", R_BOUCLE)):
            if t.count(a) != 1:
                raise SystemExit(f"outils_v7/lancer.py : repere {nom} introuvable : RIEN ecrit")
        t = t.replace(F_FLAG[0], F_FLAG[1], 1).replace(F_FONCTIONS[0], F_FONCTIONS[1], 1)
        t = t.replace(F_DEMARRAGE[0], F_DEMARRAGE[1], 1).replace(R_BOUCLE, F_BLOC + R_BOUCLE, 1)
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
    ""
)
IDENTIFIANT_BAT = ("@echo off\ncd /d %~dp0\n.venv\\Scripts\\python.exe identifiant.py %1\n"
                   "echo.\npause\n")
CANAL_ABSENT = "IDENTIFIANT-A-INSTALLER"


def identifiant_py():
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(IDENTIFIANT_B64)).decode("utf-8")


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

# textes (remplaces a chaque mise a niveau du patch)
TEXTE_IDENTIFIANT = '''PARAGRAPHE_IDENTIFIANT = """TON IDENTIFIANT PERSONNEL
-------------------------
Pour recevoir les signaux, il te faut un identifiant personnel. Il t'est envoye AUTOMATIQUEMENT par l'editeur
(par le canal de « signe de vie » decrit plus bas) : tu n'as rien a faire, ton bot l'installe tout seul puis
redemarre quand le marche est ferme ou qu'aucune position n'est ouverte.
Si l'editeur te donne a la place un fichier "identifiant-TONNOM.txt", depose-le dans ce dossier (ou glisse-le
sur   identifiant.bat  ) puis, dans "GIMALY Panneau", clique sur ARRETER puis DEMARRER.
Cet identifiant est strictement personnel : ne le partage avec personne, il peut etre coupe a tout moment.


"""
'''
TEXTE_SIGNE = '''PARAGRAPHE_SIGNE = """SIGNE DE VIE
------------
Toutes les 10 minutes, le bot envoie a l'editeur un petit message : ton pseudo, la version du programme,
l'etat du bot (actif / pause / arrete), demo ou reel, une empreinte de quelques fichiers du programme, un
numero d'installation aleatoire, et le nom de ton PC et de ta session Windows (CHIFFRES : seul l'editeur peut
les lire). JAMAIS ton numero de compte, ton solde, tes trades ni tes mots de passe.
Cela sert a savoir qui est connecte et a jour, a te transmettre ton identifiant personnel, et a voir si une
installation sort du cadre prevu (compte reel, fichiers modifies, identifiant partage). Le message est signe ;
le code est lisible dans retour.py et attribution.py.


"""
'''
FONC_RETOUR = '''def retour_py():
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(RETOUR_B64)).decode("utf-8")
'''
FONC_ATTRIBUTION = '''def attribution_py():
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(ATTRIBUTION_B64)).decode("utf-8")
'''
PARA_ANCIEN = 'lm.replace(ancre2, PARAGRAPHE_IDENTIFIANT + PARAGRAPHE_COMPTE + ancre2)'
PARA_NOUVEAU_EXPR = 'PARAGRAPHE_IDENTIFIANT + PARAGRAPHE_SIGNE + PARAGRAPHE_COMPTE + ancre2'
PARA_NOUVEAU = 'lm.replace(ancre2, ' + PARA_NOUVEAU_EXPR + ')'
F_APRES = '    F["identifiant.bat"] = IDENTIFIANT_BAT\n'
AVANT_BAT = "IDENTIFIANT_BAT = ("
AVANT_FONC = "\n\ndef identifiant_py():"


def litteral(donnees):
    blob = base64.b64encode(zlib.compress(donnees, 9)).decode()
    return "\n".join('    "%s"' % blob[i:i + 100] for i in range(0, len(blob), 100))


def poser_blob(t, nom, donnees):
    """Pose (ou met a jour) le litteral NOM = ( ... ) du generateur."""
    bloc = "%s = (\n%s\n)\n" % (nom, litteral(donnees))
    m = re.search(r'%s = \(\n(?:    "[^"\n]*"\n)+\)\n' % nom, t)
    if m:
        return t[:m.start()] + bloc + t[m.end():]
    if t.count(AVANT_BAT) != 1:
        raise SystemExit("creer_installateur_v7.py : repere IDENTIFIANT_BAT introuvable : RIEN ecrit")
    return t.replace(AVANT_BAT, bloc + AVANT_BAT, 1)


def poser_texte(t, nom, definition):
    """Pose (ou met a jour) une constante texte PARAGRAPHE_xxx = \"\"\"...\"\"\"."""
    m = re.search(r'%s = """.*?"""\n' % nom, t, re.S)
    if m:
        return t[:m.start()] + definition + t[m.end():]
    if t.count(AVANT_FONC) != 1:
        raise SystemExit("creer_installateur_v7.py : repere identifiant_py introuvable : RIEN ecrit")
    return t.replace(AVANT_FONC, "\n\n" + definition.rstrip("\n") + "\n" + AVANT_FONC, 1)


def poser_fonction(t, nom, definition):
    if ("def %s()" % nom) in t:
        return t
    if t.count(AVANT_FONC) != 1:
        raise SystemExit("creer_installateur_v7.py : repere identifiant_py introuvable : RIEN ecrit")
    return t.replace(AVANT_FONC, "\n\n" + definition.rstrip("\n") + "\n" + AVANT_FONC, 1)


def poser_ligne_f(t, ligne):
    if ligne in t:
        return t
    if t.count(F_APRES) != 1:
        raise SystemExit("creer_installateur_v7.py : repere F[identifiant.bat] introuvable : RIEN ecrit")
    return t.replace(F_APRES, F_APRES + ligne, 1)


def prevoir_generateur():
    if not GEN.exists():
        raise SystemExit(f"{GEN} introuvable")
    t, crlf = lire(GEN)
    original = t
    if "IDENTIFIANT_B64" not in t:                  # generateur d'origine : on pose d'abord la base
        for nom, a in (("A1", A1), ("A2", A2), ("A3", A3), ("A4", A4), ("A5", A5), ("A6", A6)):
            if t.count(a) != 1:
                raise SystemExit(f"creer_installateur_v7.py : repere {nom} introuvable (une fois attendu) : RIEN ecrit")
        t = t.replace(A1, BLOC + A1, 1)
        t = t.replace(A2, A2 + '    F["identifiant.py"] = identifiant_py()\n    F["identifiant.bat"] = IDENTIFIANT_BAT\n', 1)
        t = t.replace(A3, '    F["LISEZ-MOI-EN-PREMIER.txt"] = ' + PARA_NOUVEAU + '\n', 1)
        t = t.replace(A4, A4 + "    if sans_canal():\n        v6.lire_canal = lambda: (CANAL_ABSENT, CANAL_ABSENT)\n", 1)
        t = t.replace(A5, "    try:\n        v6.main()\n    finally:\n        pass\n    if sans_canal():\n        retirer_canal_du_paquet(sortie)\n", 1)
        t = t.replace(A6, '    global AVEC_CANAL\n    if "--avec-canal" in sys.argv:\n        sys.argv.remove("--avec-canal")\n        AVEC_CANAL = True\n' + A6, 1)
    # mise a niveau (aussi apres un patch precedent)
    if "PARAGRAPHE_SIGNE" not in t and t.count(PARA_ANCIEN) == 1:
        t = t.replace(PARA_ANCIEN, PARA_NOUVEAU, 1)
    for nom, data in (("IDENTIFIANT_B64", decoder(IDENTIFIANT)), ("RETOUR_B64", decoder(RETOUR)),
                      ("ATTRIBUTION_B64", decoder(ATTRIBUTION))):
        t = poser_blob(t, nom, data)
    t = poser_texte(t, "PARAGRAPHE_IDENTIFIANT", TEXTE_IDENTIFIANT)
    t = poser_texte(t, "PARAGRAPHE_SIGNE", TEXTE_SIGNE)
    t = poser_fonction(t, "retour_py", FONC_RETOUR)
    t = poser_fonction(t, "attribution_py", FONC_ATTRIBUTION)
    t = poser_ligne_f(t, '    F["retour.py"] = retour_py()\n')
    t = poser_ligne_f(t, '    F["attribution.py"] = attribution_py()\n')
    if "PARAGRAPHE_SIGNE + PARAGRAPHE_COMPTE" not in t:
        raise SystemExit("creer_installateur_v7.py : ligne LISEZ-MOI non reconnue : RIEN ecrit. Envoie-le moi.")
    if t == original:
        return None
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
    print("\nTermine. Etape suivante : publier_maj.py, puis suivi_amis.bat (nommer les installations de tes amis).")


if __name__ == "__main__":
    main()
