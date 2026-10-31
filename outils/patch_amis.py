# -*- coding: utf-8 -*-
"""IDENTIFIANT PERSONNEL PAR AMI : un canal et un secret par ami, ton bot publie sur chacun, tu peux en couper un.

Ce patch (sur TON PC, depuis le dossier gimaly) :
  1. gimaly/trading/signaux_distants.py : publication sur le canal personnel de chaque ami actif (amis.json),
     et refus, cote ami, d'un signal destine a un autre canal. Compatible avec les bots deja installes
     (l'ancien canal commun continue de marcher tant que tu ne le coupes pas : amis.py ancien off).
  2. outils_v7/lancer.py : le lanceur d'un ami installe tout seul son fichier identifiant au demarrage.
  3. creer_installateur_v7.py : le paquet des amis ne contient PLUS de canal ni de secret des qu'un ami
     existe (amis.py ajouter NOM) ; il contient identifiant.py / identifiant.bat. Option --avec-canal : l'ancien mode.
Sauvegardes : <fichier>.avant_amis. Idempotent. Rien n'est ecrit si un repere manque (verification avant ecriture).
  .\\.venv\\Scripts\\python.exe patch_amis.py
"""
import base64
import hashlib
import shutil
import zlib
from pathlib import Path

RACINE = Path.cwd()
SD = RACINE / "gimaly" / "trading" / "signaux_distants.py"
LANCEUR = RACINE / "outils_v7" / "lancer.py"
GEN = RACINE / "creer_installateur_v7.py"
SD_ANCIEN_SHA = "56f16ebe9b617ff74b1baaeebe14e4ffd724e038c44dfab977acd59499c97d06"
SD_NOUVEAU_SHA = "17f9c52570ce03e86d84b0ae10da16004dfc01438c4bbda3005b49f783f56f61"

SD_NOUVEAU = """
eNqtWm1T21YW/u5fcat8iNQaxSFtNnXj7lDqJMwSQgPZ6Q7DqMK6xjfIkiJdOTCM//s+59yrV9s02Q0fwLKuzvvLc454JPa+3xOz
NFLJ9ViUer73gr4ZOI5znodJkaW5FpEsRKGuk7C8FTLRuRSxFFcp3RC/hyvhykhpWeaekBq3CrpX8FPhUhXCzeVMZnSg8PzB4DRX
yUxlUozFbBF+KqWhHYtwxsdEFuY9BrLQIiuvYoWzZS7KRMxCeiLL1UqK6zzUpdLEJw7BL9HzO284ODt6fTIV4UrO6IFCznJIB9o6
vJbCffP24HDv7M3B/k/PPV8cW3aPcRIyiwRS5DKJoC6MsySpSFDSbSmLAhSgX5roQRwa6XUJq5CYqzBWkRziOFMpcAhMC6HzNBMr
JcmEGncfq1gkj0O+F8mPIQ6EMGLhizOYXbTpDgfgHeMRCEdkI7lSiaTjZKYkXYqotAYhudMy53tEWSar9E6yxebkPWNpOOGgnOE7
2O9WhFdFGpciIrZkKOOMMYnw+9HZ+cHJ4ZQYFBoKuJB9JmOwhWfixxwM/DmXcwmDzaQHD83nSg8H1rlk1zDLYkUXM7KbKnSY0KeQ
zAMhUtiaZYFgv5OFEriVxI1kywpwBNwQmj+RNdJSLiVpKeM0o5AaCPG9cAoH8rc8bKIAUvejYCXzQqUgtXqOJ3RaUshpqIVgZaXt
+cqm8zAu1FxJhPovhpUkVtNo/6efnv5s2UDEWJrYrOxk8qPN7x9k4SpD4LbrMI/A14SZoXD64bfjoz8+TIfgVP2Q/zOZLyXnBsix
NGJJcf8x5D/WaJARsaTY9Wq2oFN/gWrAeQQuvr7Vf5nMymVBrI1pW8wicphYplEZw/wxedkmspj+efR62olSNgXEwnVqKkTX2PDt
W6YkCvJdJDPkF8WBcK8UREr1QnIxQHBEMAYex+ElCfYLcWEL+9kdizyHQxLF9kZJQbEaqCWXqkVYLGJ1VV8uw1n1+SOCrfqcFtUn
sCxldaEXuQypFNZfqGV9s8xjUPZzkrLQ9beligbzHEmYhZpYC3vjFJeDgc7vxmxRPnKtlmF85yPViUl1slJuIG/JvOKIv57meZqP
xdafR6jUKlZFqBFMYpHmBbhDLNRAlBBdeMyyT37wfnp8cHQmJsJZaJ0V4ydPqFT6xcIZHLyeBm8P/sS9n0db2MGVaUIFfdwqEVlc
FlVJK2rHu6iXyElLMKAqfHBMuYRC4A3OD46OjytWz16MRl0+6UxLTVxitVSU5lTzbMXlui7cH0c/P/eqso7oDPNrOTg8np4Fh+9O
zqd/noP60Qmou47OgtwZCidCeMpgGd4GS5XQF0XMV5nKCrrUNhKDxVO6RNAivILE8cgsJ+egde98KGS+d3CNcHTGwjGO3LNN8cm+
sx4MBo/E3v/5Y/tl3d9Op+/P3p2cTI+5J+KmN3h1dPjmaPo+OHjLnqQoc9PCRwlUeZr411K7zuujtwfH/+EjjidS1B065i/SpXQ9
8UTYAw59tLHIn4m7T2nieB70ieRcyCWqg0I9dFkizwQzEu6IqhWKT4j8nMFctnkaud0X+JCHcCZKizcU4UdUVq7dnYZvuhO+tl23
E1w5LIFmz/xQNAzhpkE/5sqFFrcNNfCpEr3Jp9JAFOBTVIyqPCDkQ7QF160cCZJjR/yA4pNbRT2YFLBIug6DIljEX8jbSKHza9e7
GL+4tBaKVS4DspzbGGdq6/1YuPfoz2PED1Pl2OOq6KzXDUA6ODw/enUGMwEXySTgowGsp+Yo4a9s8UabplpIJNdDcZ6X0qu1q6sM
V22EBTnRj9MwKtx2wPhU3gItb7XL2sHxk1q/mgDLhJhPxnDNHOGTQDShEuFGJr7ogAms+7XnQ9UllB/0q4aaC1WoxDR7Nxyi8c80
MheoKrR0SEXHKtO+YYzV+cqazVvXfKxLSZgh3J7GtXgtM1bUjXi2wLrvzri6DsW/w7iU9vOB1rm6QpzytTfuM6rM/m0yfUbN37XA
weNICmyfDrhNM3xoxdThDkxBSUP9nDsloWPCVKeHwq3ggMV1tkEQ+iI1W9Fj9XuolKC+mkp+/uH99KtqCulSYwSfFGiKS8C5s6lt
J5wBUxCMW23zUDj7pGbWCktMCUDNIHV1RzCb+jES2gV5r+9pexQBHMvENVeemKBh7QsZF1KcpIlsB9SU/6AXj6mJJemncCx+O56O
Rk/FnkX4jOjGgvCuHWTILx301BeDuRhLtYFbwDkFDL4RHfaAcKGY13ha1vDXxMBQpCUTB3tbVvAMYJ40MLiL23ZUGeMWDgI3gHcg
YOD5n5VeBEmImHD6WJMq6E5/USfd4jNrCOJlnbHpvP/RMTuM/Q0yu/apiXGUoTRxs/COyrF1mOXJVToql1lR3R8ie3Md3Mi7YkK1
BtcSfgg1IN7EdYbUQMYOOqpMkOroO8VMqckrTCWySiqD/VsE2ZtdxgSL/UR+ds3Nfqsb9qXePNBtpJ3eWCOHKwrSXZLQggGBQN3f
JARVsnsnA7oyCIBaZXVB1lz74r2MSjP0Ao1qfhoRjMsKIRIm4EH7Okchq+LWCoBwpQ5UK9W+5xdSQ+iwjFHzVAQzE6736dePLmu3
+7jG6Twtk8ilacGnXy4s9IzKXKfwbJY7c4Csxdq4WavroAwz8CSLZC1jkEVrWzbdEPlhGI07jRhULlBaLkGqnqEsFXO88fV2xLOZ
ja2oBfWvi1AisyyuIY1VuO0Lm+K4vyGJ+FU0k0Oj4UzfglTlFAMdbGRU+KQ+a09dNCfIKPc3Y6JycXPJSOeGYM7mMAHJ+A5ONgR3
6mHthPs2FdJylas8sFHq8iOVC4dVbZ9QBWqS4z2BY2XmaIOIKdR3bZuAs1JTw3wmcEAFvxr3/7INoZVM9caCh/ZbZC46wOZ+JJHV
9otmvR2doNm+dHAna+n1zY8z9fkLxPZlO4ATYPcWZKwLBwPHbly3q3aLgtW4exZat9maOEGADHpotccejw1pIOhx3sW9RaTOtGo/
E1AiWdm+oLji+a9gar+35AY7tL5AAXnI2Du07TOtEHQbOP9L3tlP53fZl6LpmqIVhVsSBVuIomFbyY5W1jdQn2LPIN+kqVu0zels
+1UjF08aTUKbNfTEbFuGvEPC+Dt53iT3qYGA9bRLrc2ku5veDKt2huHvhArAStarvceyAjS8PuRpF0kapfW+l9ZQKt+eqbM0z2iy
29ma+6HYMvEnPNfdgPnvzV937twblddP7tkUazSBKNThhBkCLAD2SbQH3qaQenqRRhPn9N3ZeYsHYcc+C1ymGXoCrhtD2r8YDwuR
bw1Xd380Ei8nIgeiRL0rxEvxbDRC4Mwd+47gzfn5qbiv7q+draCRGOC7v8WO3N2IOEfGzGzlaPtWFOqKYf89yHyXg82gHUEBptR5
CuDwhZH0kbaeYTwBfEj0RjTxQHEVp7BcTp3iKi1p5jCbNyr+Zd4sUmhJh/BzdZhUbyOon5ilA61x26eZUbOLomHG7HFoE8OPCLfe
HcHKuEtvF3jqoGm0XiL54oNZ30A7YKFqi0N7xELmK1WHrRnqzSCPwGvtWBrIZN9tuEm6HBJCmrHdWnWBU4mbdJ2x1anKtF6/IqY3
3YCyJkeMX9hl36Wglc6anAria8dKhOetuLQwoXceELc1LlWbZf+cP8HwOfrQxCoBXfNrwk9t7yCLtgeGNxyIXT9RKJdpYocHmsQm
1Y7LGoHHLPR3C+x4v0MW5A0Pe9EudL5a+Dkthox1nGEHa+Nq0mwSwwu74Ln0aDdYX/Fnu+e5/FY6fpPqX7/3GMzisChQre11nYPH
di4JzV5TzOPylqcUlZT8AjRNEuCslPeS6RIl4hPtvJBoeZhcmzeL1StWA+rqzY0UNF1zatSxHwQqUToIMMDF878rG2gltO6e2JV8
r440ANQh0ZyW34m4X9PG54oBX9hKOtnOvUfEsKDDOzYZLfRGA72RxQz19usuRauUlcVqBPr19/ar7lNkSRzilz7+H/S7Nd/wiWBV
8vJz3fsaDSyhkq0IwnYwmLnPr0cnrVSZrmSiN6ib+1tJWA6SN78revsxESN/1D2Uy49SS5JwZKKBo1vM7mbmnexKyTpIIrkM8xxl
j55suRWW7ghDW9b2F74qAoTgSrpbweAWxcm/Yb5b2V0FxBwzjWr4QFrX+edsZ9Fke6U7Ka43VW+JjBG+200wngNu9p+oVlDNaC/2
dvnrpXi6P2pIQuoyk1scQLuPFGG2LekhOCzP70dLRUeE5UMv0WWMKU0VND1KCq+SXsXz4neFh5v5jFVNc60ohi4a2P95QfFPBu46
toMSuwR8YguIUqcPjU9Bkn4OFezXnaEsfjLZNcXceLdzijHE2yFMrSFPmui1YdG3Xaj59Tz02u+pxZNX418EMbv4CzS1tp5spjqa
I9AtRHPbRcdbF84WxR6GyK2aCZzclNb1E0JN/8QkNpOTeyMK9c8OaN58u/LFaPkpgO8WpPyQPds/hA+u8lITOthBolNTHrB9/+cK
qXuz84QhZ3KSBNgaan8L1ZGsmt89ztIyo8UHr+AL/lcGaskzLbe9uPqiWOpIug0oMgjguM4x2AIH2DEAqCdJSwzmggY9ZRr9vfXE
WhSbq4mWLJx49uwWgTaN2nh4qZLqSfG92B+K56NWBWzVvyG7vF83tzWoVl0c7Mwxuequhog4qHVXfIOea5sNw4NNCMaRK7PSUZHT
M8iW1i1XF3TwchsBrqmOJ74D/rAzuPMg82ap1VvxVRQrKkPUfG8biLLYpjOHVFRRkgglbFGpQgE/TMTTwc5QbEVitSA3Dwq3WQSq
xHQerxd0PU2j/p41cjoys7SUNfxeiRBFRGZsQH9T8LxvqRBapqbtuvkfAnrlbzH42P4/ysNqEYlJr7nPoaSuPUhfm10yyqjpVosU
dfaaJ2uLgce8fGn/Y5xdF7UsRKx+7WBXIkrfvhR7wA1bFxlf/POo/Q+GblrWQsbpLIRUMAxhCvrcWsoWasOvqudYs8/kTkh/VNLA
5C8AhzgFn0WXOypFvXK/uDGf0bY6LKpZlCTpeknDmM+ej0aXXSkiFNWG9c3lJvz3s7L1Dui/Vdr9sw==
"""
IDENTIFIANT = """
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
    if sha != SD_ANCIEN_SHA:
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


def prevoir_lanceur():
    if not LANCEUR.exists():
        raise SystemExit(f"{LANCEUR} introuvable : lance depuis le dossier gimaly")
    t, crlf = lire(LANCEUR)
    if "identifiant.auto()" in t:
        return None
    if t.count(L_ANCRE) != 1:
        raise SystemExit("outils_v7/lancer.py : repere introuvable : RIEN ecrit")
    return t.replace(L_ANCRE, L_ANCRE + L_AJOUT, 1), crlf


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


def prevoir_generateur():
    if not GEN.exists():
        raise SystemExit(f"{GEN} introuvable")
    t, crlf = lire(GEN)
    if "IDENTIFIANT_B64" in t:
        return None
    for nom, a in (("A1", A1), ("A2", A2), ("A3", A3), ("A4", A4), ("A5", A5), ("A6", A6)):
        if t.count(a) != 1:
            raise SystemExit(f"creer_installateur_v7.py : repere {nom} introuvable (une fois attendu) : RIEN ecrit")
    blob = base64.b64encode(zlib.compress(decoder(IDENTIFIANT), 9)).decode()
    litteral = "\n".join('    "%s"' % blob[i:i + 100] for i in range(0, len(blob), 100))
    bloc = BLOC.replace("@@IDENT_LITERAL@@", litteral)
    t = t.replace(A1, bloc + A1, 1)
    t = t.replace(A2, A2 + '    F["identifiant.py"] = identifiant_py()\n    F["identifiant.bat"] = IDENTIFIANT_BAT\n', 1)
    t = t.replace(A3, '    F["LISEZ-MOI-EN-PREMIER.txt"] = lm.replace(ancre2, PARAGRAPHE_IDENTIFIANT + PARAGRAPHE_COMPTE + ancre2)\n', 1)
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
    print("\nTermine. Etape suivante : amis.py ajouter NOM  (pour chacun de tes amis).")


if __name__ == "__main__":
    main()
