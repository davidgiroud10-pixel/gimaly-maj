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


# ---------------------------------------------------------------------------------------------
# Choix du compte MT5 : le bot ne trade QUE sur le compte choisi par l'ami (numero, sans mot de passe)
# ---------------------------------------------------------------------------------------------
COMPTE_PY = r'''# -*- coding: utf-8 -*-
"""Choisir le compte MetaTrader 5 sur lequel le bot a le droit de trader (lance par compte.bat).

On ne saisit que le NUMERO du compte (jamais de mot de passe). Le bot ne trade que si MetaTrader 5 est
connecte a ce compte ; sinon il attend et l'ecrit dans le journal. Pris en compte en moins d'une minute,
sans redemarrer.
"""
import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config.local.yaml"
CLE = "trading_mt5_compte"


def lire_voulu():
    try:
        m = re.search(r"(?m)^%s:[ \t]*(\d+)" % CLE, CONFIG.read_text(encoding="utf-8-sig"))
    except OSError:
        return 0
    return int(m.group(1)) if m else 0


def ecrire(valeur):
    texte = CONFIG.read_text(encoding="utf-8-sig")
    motif = re.compile(r"(?m)^%s:[ \t]*[^#\n]*?([ \t]*#.*)?$" % CLE)
    ligne = "%s: %s" % (CLE, valeur)
    if motif.search(texte):
        texte = motif.sub(lambda m: ligne + (m.group(1) or ""), texte, count=1)
    else:
        texte = (texte.rstrip("\n") + "\n\n# compte MT5 sur lequel le bot a le droit de trader (0 = celui qui est actif)\n"
                 + ligne + "\n")
    CONFIG.write_text(texte, encoding="utf-8", newline="")


def compte_actif():
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        info = mt5.account_info()
        mt5.shutdown()
        return info
    except Exception:
        return None


def main():
    print("COMPTE MT5 DU BOT")
    print("-----------------")
    voulu = lire_voulu()
    print("Compte autorise pour le bot : " + (str(voulu) if voulu else "aucun choix (le bot prend le compte actif de MT5)"))
    actif = compte_actif()
    if actif is None:
        print("Compte actif dans MetaTrader 5 : introuvable (MT5 ferme, ou aucun compte connecte)")
    else:
        genre = "DEMO" if actif.trade_mode == 0 else "REEL (refuse par le bot)"
        print("Compte actif dans MetaTrader 5 : %s sur %s [%s]" % (actif.login, actif.server, genre))
    print()
    print("  1) Utiliser le compte actif de MetaTrader 5 (connecte-toi d'abord au bon compte dans MT5)")
    print("  2) Taper un numero de compte")
    print("  3) Ne plus restreindre (le bot prend le compte actif de MT5)")
    print("  Entree) Ne rien changer")
    choix = input("\nTon choix : ").strip()
    if choix == "1":
        if actif is None:
            print("Impossible : MetaTrader 5 n'est pas connecte. Ouvre-le, connecte-toi au compte voulu, puis recommence.")
            return 1
        if actif.trade_mode != 0:
            print("Ce compte n'est pas un compte DEMO : le bot refuse de trader dessus. Connecte MT5 a un compte demo.")
            return 1
        ecrire(actif.login)
        print("OK : le bot ne tradera que sur le compte %s." % actif.login)
    elif choix == "2":
        saisie = re.sub(r"\s", "", input("Numero du compte (chiffres seulement) : "))
        if not re.fullmatch(r"\d{4,12}", saisie):
            print("Numero invalide (4 a 12 chiffres, sans lettres). Rien n'a ete change.")
            return 1
        ecrire(int(saisie))
        print("OK : le bot ne tradera que sur le compte %s." % int(saisie))
        print("Pour qu'il trade, MetaTrader 5 doit etre connecte a CE compte (et ce doit etre un compte DEMO).")
    elif choix == "3":
        ecrire(0)
        print("OK : plus de restriction, le bot trade sur le compte actif de MetaTrader 5 (demo uniquement).")
    else:
        print("Rien n'a ete change.")
        return 0
    print("Pris en compte en moins d'une minute, sans redemarrer le bot.")
    return 0


if __name__ == "__main__":
    code = main()
    input("\nAppuie sur Entree pour fermer.")
    sys.exit(code)
'''

COMPTE_BAT = "@echo off\ncd /d %~dp0\n.venv\\Scripts\\python.exe compte_mt5.py\n"

PARAGRAPHE_COMPTE = """PLUSIEURS COMPTES MT5 ?
-----------------------
Le bot ne trade QUE sur le compte MT5 choisi (a l'installation : le compte connecte a ce moment-la).
Pour changer : ouvre "GIMALY Panneau", carte "COMPTE MT5 DU BOT" : tape le numero du compte puis
"SE CONNECTER" (MetaTrader 5 se connecte tout seul, a condition que ce compte soit deja
enregistre dans MT5 avec son mot de passe : le panneau ne demande jamais de mot de passe), ou clique sur
"COMPTE ACTIF". Alternative : double-clique sur   compte.bat.
Si MT5 est connecte a un autre compte, le bot ne trade pas et attend. Impossible de changer de compte
tant qu'un trade est ouvert. Seuls les comptes DEMO sont acceptes.


"""

TRADING_METHODE_ANCIEN = "    def peut_trader(self, marche=None, filtres=True):\n"
TRADING_METHODE_NOUVEAU = r"""    def _compte_voulu(self):
        # numero du compte MT5 choisi par l'utilisateur (compte.bat), relu depuis config.local.yaml
        # (au plus toutes les 30 s) : pas de redemarrage necessaire. 0 = pas de restriction.
        try:
            return int(str(_yaml_local().get("trading_mt5_compte", 0) or 0).strip() or 0)
        except (TypeError, ValueError):
            return -1          # valeur illisible : par prudence le bot ne trade pas

"""
TRADING_CTRL_ANCIEN = ('        if compte.trade_mode != 0 and not r["autorise_reel"]:\n'
                       '            return False, "compte NON demo : refus (trading_autorise_reel est a false)"\n')
TRADING_CTRL_NOUVEAU = TRADING_CTRL_ANCIEN + (
    '        voulu = self._compte_voulu()\n'
    '        if voulu < 0:\n'
    '            return False, "trading_mt5_compte illisible dans config.local.yaml (compte.bat pour corriger)"\n'
    '        if voulu and compte.login != voulu:\n'
    '            return False, (f"MT5 est connecte au compte {compte.login}, le bot est reserve au compte "\n'
    '                           f"{voulu} (compte.bat pour changer)")\n')

ASSIST_ANCIEN = ('        print(f"\\n  [OK] Compte DEMO {compte.login} sur {compte.server}, Algo Trading actif.")\n'
                 '        return mt5, compte\n')
ASSIST_NOUVEAU = ('        print(f"\\n  [OK] Compte DEMO {compte.login} sur {compte.server}, Algo Trading actif.")\n'
                  '        regler("trading_mt5_compte", compte.login)\n'
                  '        print(f"  [OK] Le bot ne tradera QUE sur le compte {compte.login}. '
                  'Pour en choisir un autre plus tard : compte.bat.")\n'
                  '        return mt5, compte\n')


def une_fois(texte, ancien, nouveau, nom):
    if texte.count(ancien) != 1:
        raise SystemExit(f"{nom} : repere introuvable (attendu 1 fois), arret : compte MT5 NON pose")
    return texte.replace(ancien, nouveau)


def poser_compte_trading(chemin):
    """trading.py du PAQUET : refuse d'ouvrir un trade si MT5 n'est pas sur le compte choisi."""
    texte = chemin.read_text(encoding="utf-8")
    texte = une_fois(texte, TRADING_METHODE_ANCIEN, TRADING_METHODE_NOUVEAU + TRADING_METHODE_ANCIEN, "trading.py (methode)")
    texte = une_fois(texte, TRADING_CTRL_ANCIEN, TRADING_CTRL_NOUVEAU, "trading.py (controle)")
    chemin.write_text(texte, encoding="utf-8", newline="")
    print("  compte MT5 choisi : trading.py : OK")


# ---------------------------------------------------------------------------------------------
# Panneau : carte « COMPTE MT5 DU BOT » (saisir un numero, se connecter, ou prendre le compte actif)
# ---------------------------------------------------------------------------------------------
PANNEAU_FONCTIONS = r'''VERROU_MT5 = threading.Lock()      # un seul acces MT5 a la fois (lecture periodique / changement de compte)


def compte_voulu():
    """Numero du compte reserve au bot (config.local.yaml), 0 = aucun choix."""
    try:
        m = re.search(r"(?m)^trading_mt5_compte:[ \t]*(\d+)", CONFIG.read_text(encoding="utf-8-sig"))
    except OSError:
        return 0
    return int(m.group(1)) if m else 0


def ecrire_compte(valeur):
    texte = CONFIG.read_text(encoding="utf-8-sig")
    motif = re.compile(r"(?m)^trading_mt5_compte:[ \t]*[^#\n]*?([ \t]*#.*)?$")
    ligne = "trading_mt5_compte: %s" % valeur
    if motif.search(texte):
        texte = motif.sub(lambda m: ligne + (m.group(1) or ""), texte, count=1)
    else:
        texte = (texte.rstrip("\n") + "\n\n# compte MT5 sur lequel le bot a le droit de trader (0 = celui qui est actif)\n"
                 + ligne + "\n")
    CONFIG.write_text(texte, encoding="utf-8", newline="")


def choisir_compte(numero=None):
    """numero=None : le bot est reserve au compte actif de MT5. Sinon MetaTrader 5 se connecte a ce compte
    (mot de passe deja enregistre dans MT5 : il n'est JAMAIS demande ici) puis le bot lui est reserve.
    Seuls les comptes DEMO sont acceptes. Renvoie le message a afficher."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return "MetaTrader5 n'est pas installe."
    with VERROU_MT5:
        if not mt5.initialize():
            return "MetaTrader 5 est injoignable : ouvre-le d'abord."
        try:
            avant = mt5.account_info()
            if numero is None:
                if avant is None:
                    return "Aucun compte n'est connecte dans MetaTrader 5."
                numero = avant.login
            if avant is None or avant.login != numero:
                if (mt5.positions_total() or 0) > 0:
                    return ("Un trade est encore ouvert sur le compte actuel : attends qu'il soit termine "
                            "avant de changer de compte.")
                if not mt5.login(numero):
                    return (f"MetaTrader 5 n'a pas pu se connecter au compte {numero}. Il faut qu'il soit deja "
                            "enregistre dans MetaTrader 5 (Fichier > Se connecter au compte de trading, "
                            "avec 'Enregistrer le mot de passe'). Rien n'a ete change.")
            info = mt5.account_info()
            if info is None or info.login != numero:
                return "MetaTrader 5 n'est pas sur ce compte. Rien n'a ete change."
            if info.trade_mode != 0:
                if avant is not None and avant.login != numero:
                    mt5.login(avant.login)          # on remet le compte d'avant
                return f"Le compte {numero} n'est pas un compte DEMO : refuse. Rien n'a ete change."
            ecrire_compte(numero)
            return f"Le bot est reserve au compte {numero} ({info.server}). MetaTrader 5 y est connecte."
        except Exception as exc:
            return f"Changement de compte impossible : {exc}"
        finally:
            mt5.shutdown()


'''

PANNEAU_CARTE = r'''    cadre = tk.Frame(fen, bg=carte, padx=16, pady=10)
    cadre.pack(fill="x", padx=14, pady=4)
    label(cadre, 9, couleur=doux, text="COMPTE MT5 DU BOT").pack(anchor="w")
    reserve = label(cadre, 10, text="", justify="left", wraplength=500)
    reserve.pack(anchor="w", pady=(4, 6))
    ligne_compte = tk.Frame(cadre, bg=carte)
    ligne_compte.pack(fill="x")
    saisie = tk.Entry(ligne_compte, font=("Segoe UI", 11), width=13, bg=fond, fg=texte, insertbackground=texte,
                      relief="flat")
    saisie.pack(side="left", padx=(0, 6), ipady=5)

    def lancer_choix(numero):
        message.config(text="Changement de compte en cours...")
        resultat = []                                   # le fil secondaire n'appelle jamais Tk

        def tache():
            resultat.append(choisir_compte(numero))

        def attendre():
            if resultat:
                message.config(text=resultat[0])
                rafraichir(False)
            else:
                fen.after(200, attendre)
        threading.Thread(target=tache, daemon=True).start()
        fen.after(200, attendre)

    def se_connecter():
        numero = re.sub(r"\s", "", saisie.get())
        if not re.fullmatch(r"\d{4,12}", numero):
            message.config(text="Tape le numero du compte MT5 (chiffres seulement).")
            return
        lancer_choix(int(numero))

    for texte_b, commande, couleur_b in (("SE CONNECTER", se_connecter, "#4aa8ff"),
                                         ("COMPTE ACTIF", lambda: lancer_choix(None), "#8a96a3")):
        tk.Button(ligne_compte, text=texte_b, command=commande, bg=couleur_b, fg="#0b1118", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8, pady=5, activebackground=couleur_b,
                  cursor="hand2").pack(side="left", padx=3)

'''

PANNEAU_RAFRAICHIR = r'''        voulu = compte_voulu()
        if not voulu:
            reserve.config(text="Aucun compte choisi : le bot prend le compte actif de MetaTrader 5.", fg=doux)
        elif m.get("erreur"):
            reserve.config(text=f"Compte reserve au bot : {voulu} (MetaTrader 5 n'est pas joignable).", fg="#f0a030")
        elif m["login"] == voulu:
            reserve.config(text=f"Le bot trade sur le compte {voulu}.", fg="#34d27b")
        else:
            reserve.config(text=f"MetaTrader 5 est sur le compte {m['login']} : le bot ATTEND le compte {voulu} "
                                "(clique sur SE CONNECTER).", fg="#f0a030")
'''

PANNEAU_REMPLACEMENTS = (
    ("def boucle_mt5():\n", PANNEAU_FONCTIONS + "def boucle_mt5():\n", "panneau (fonctions)"),
    ("        mt5_etat = lire_mt5()\n        time.sleep(6)\n",
     "        with VERROU_MT5:\n            mt5_etat = lire_mt5()\n        time.sleep(6)\n", "panneau (verrou)"),
    ("    barre = tk.Frame(fen, bg=fond)\n", PANNEAU_CARTE + "    barre = tk.Frame(fen, bg=fond)\n", "panneau (carte)"),
    ("        finis, ouverts, derniers = trades_du_jour()\n",
     PANNEAU_RAFRAICHIR + "        finis, ouverts, derniers = trades_du_jour()\n", "panneau (etat)"),
    ('    fen.geometry("560x620")\n    fen.minsize(520, 560)\n',
     '    fen.geometry("560x760")\n    fen.minsize(520, 700)\n', "panneau (taille)"),
)


def poser_panneau(texte):
    for ancien, nouveau, nom in PANNEAU_REMPLACEMENTS:
        texte = une_fois(texte, ancien, nouveau, nom)
    return texte


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
    _remplacer = v6.remplacer_symbole

    def _remplacer_et_compte(chemin, module):
        _remplacer(chemin, module)
        if module == "trading":
            poser_compte_trading(chemin)
    v6.remplacer_symbole = _remplacer_et_compte
    F["assistant_installation.py"] = une_fois(F["assistant_installation.py"], ASSIST_ANCIEN, ASSIST_NOUVEAU,
                                              "assistant_installation.py")
    F["compte_mt5.py"] = COMPTE_PY
    F["panneau.py"] = poser_panneau(F["panneau.py"])
    F["compte.bat"] = COMPTE_BAT
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
    lm = lm.replace(ancre, PARAGRAPHE_MAJ + ancre)
    ancre2 = "EN CAS DE PROBLEME\n------------------"
    if lm.count(ancre2) != 1:
        raise SystemExit("LISEZ-MOI : repere 'EN CAS DE PROBLEME' introuvable, arret")
    F["LISEZ-MOI-EN-PREMIER.txt"] = lm.replace(ancre2, PARAGRAPHE_COMPTE + ancre2)
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
