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

PARAGRAPHE_COMPTE = """BILAN EN UN CLIC
-----------------
Dans "GIMALY Panneau", ligne BILAN : clique sur AUJOURD'HUI, SEMAINE, MOIS ou TOUT. Une fenetre affiche le
bilan (trades, gagnants, resultat). Le bouton "COPIER LE BILAN" le copie : colle-le ensuite (Ctrl+V)
dans un message pour l'envoyer a l'editeur. Il ne contient aucun identifiant de compte.


PLUSIEURS COMPTES MT5 ?
-----------------------
Le bot ne trade QUE sur le compte MT5 choisi (a l'installation : le compte connecte a ce moment-la).
Pour changer : ouvre "GIMALY Panneau", carte "COMPTE MT5 DU BOT" : tape le numero du compte puis
"SE CONNECTER" (MetaTrader 5 se connecte tout seul, a condition que ce compte soit deja
enregistre dans MT5 avec son mot de passe : le panneau ne demande jamais de mot de passe), ou clique sur
"COMPTE ACTIF". Alternative : double-clique sur   compte.bat.
Si MT5 est connecte a un autre compte, le bot ne trade pas et attend. Impossible de changer de compte
tant qu'un trade est ouvert. Seuls les comptes DEMO sont acceptes.

UN COMPTE REEL ET UN COMPTE DEMO ?
----------------------------------
Un seul MetaTrader 5 ne peut etre connecte qu'a UN compte a la fois. Si tu trades a la main sur un compte reel,
installe un 2e MetaTrader 5 dans un autre dossier (ex. C:\\MT5-Bot), connecte-le au compte DEMO du bot (mot de passe
enregistre, Algo Trading actif), puis double-clique sur   terminal_dedie.bat   et suis les questions.
Ton MetaTrader habituel n'est jamais touche. Redemarre ensuite le bot.


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
     '    fen.geometry("560x820")\n    fen.minsize(520, 760)\n', "panneau (taille)"),
)


def poser_panneau(texte):
    for ancien, nouveau, nom in PANNEAU_REMPLACEMENTS:
        texte = une_fois(texte, ancien, nouveau, nom)
    ancre = '    message.pack(fill="x", padx=18)\n'
    return une_fois(texte, ancre, ancre + PANNEAU_BILAN, "panneau (bilan)")


# ---------------------------------------------------------------------------------------------
# Bilan simple : 4 boutons dans le panneau (Aujourd'hui / Semaine / Mois / Tout) + copie en un clic
# ---------------------------------------------------------------------------------------------
BILAN_SIMPLE_PY = r'''# -*- coding: utf-8 -*-
"""Bilan simple et lisible, pret a etre colle dans un message (utilise par les boutons BILAN du panneau).

  python bilan_simple.py [jour|semaine|mois|tout]

Lit seulement trades_bot.csv : ne modifie rien, aucun identifiant de compte.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent
NOMS = {"jour": "Aujourd'hui", "semaine": "Cette semaine", "mois": "Ce mois-ci", "tout": "Depuis le debut"}
JOURS = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")


def debut(periode, maintenant=None):
    n = maintenant or datetime.now()
    minuit = n.replace(hour=0, minute=0, second=0, microsecond=0)
    if periode == "jour":
        return minuit
    if periode == "semaine":
        return minuit - timedelta(days=minuit.weekday())
    if periode == "mois":
        return minuit.replace(day=1)
    return datetime(2000, 1, 1)


def version():
    try:
        return json.loads((RACINE / "VERSION.json").read_text(encoding="utf-8-sig")).get("version", "?")
    except (OSError, ValueError):
        return "?"


def _base(t):
    try:
        return t["vol"] * abs(t["pe"] - t["sl"])
    except (TypeError, KeyError):
        return None


def facteur_r():
    """Les anciennes versions calculaient le R sur 1 % du solde ACTIF (faux si le lot est plafonne ou si MT5 etait
    sur un autre compte) : un stop touche pouvait s'afficher -9 R. Si les stops du fichier ne sont pas a -1 R, le R
    est recalcule sur l'argent reellement perdu (gain / (lot x distance du stop x valeur du point)), la valeur du
    point etant deduite de tes propres stops. Renvoie ce facteur, ou None si le R du fichier est coherent."""
    try:
        import bilan_reel
        tous = [t for t in bilan_reel.charger(datetime(2000, 1, 1)) if t["R"] is not None]
    except Exception:
        return None
    stops = [t for t in tous if t["res"] == "stop loss" and t["gain"] is not None and t["gain"] < 0 and _base(t)]
    if not stops:
        return None
    r_fichier = sorted(t["R"] for t in stops)[len(stops) // 2]
    if abs(r_fichier + 1) <= 0.15:
        return None
    rapports = sorted(-t["gain"] / _base(t) for t in stops)
    return rapports[len(rapports) // 2]


def texte_bilan(periode="jour", maintenant=None):
    n = maintenant or datetime.now()
    d = debut(periode, n)
    en_tete = f"BILAN GIMALY - {NOMS.get(periode, periode)}"
    if periode != "jour" and periode != "tout":
        en_tete += f" (depuis le {d:%d/%m/%Y})"
    elif periode == "jour":
        en_tete += f" ({d:%d/%m/%Y})"
    lignes = [en_tete, f"Version {version()}", ""]
    try:
        import bilan_reel
        trades = bilan_reel.charger(d)
    except OSError:
        lignes.append("Pas encore de trade : le bot n'a pas encore pris de position.")
        return "\n".join(lignes)
    f = facteur_r()
    if f:
        for t in trades:
            if t["R"] is not None and t["gain"] is not None and _base(t):
                t["R"] = t["gain"] / (_base(t) * f)
    finis = sorted((t for t in trades if t["R"] is not None), key=lambda t: t["ouv"])
    ouverts = [t for t in trades if t["R"] is None]
    if f:
        lignes.append("(R recalcule sur le risque reellement pris)")
    if not finis:
        lignes.append("Aucun trade termine sur cette periode.")
        if ouverts:
            lignes.append(f"{len(ouverts)} trade(s) en cours.")
        return "\n".join(lignes)
    rs = [t["R"] for t in finis]
    gagnants = sum(r > 0 for r in rs)
    gains = [t["gain"] for t in finis if t["gain"] is not None]
    lignes.append(f"Trades termines : {len(finis)}  ({gagnants} gagnant(s) / {len(finis) - gagnants} perdant(s))")
    lignes.append(f"Resultat : {sum(rs):+.2f} R" + (f"   |   {sum(gains):+.2f} en argent (devise du compte)" if gains else ""))
    lignes.append(f"Moyenne par trade : {sum(rs) / len(rs):+.2f} R   |   taux de reussite : {gagnants / len(finis):.0%}")
    hors = sum(bilan_reel.manuel(t) for t in finis)
    if hors:
        lignes.append(f"Sorties a la main ou anticipees : {hors}")
    if ouverts:
        lignes.append(f"En cours : {len(ouverts)} trade(s) ouvert(s)")
    if periode in ("semaine", "mois", "tout"):
        jours = {}
        for t in finis:
            jours.setdefault(t["ouv"].date(), []).append(t["R"])
        lignes += ["", "Par jour :"]
        for j in sorted(jours)[-31:]:
            r = jours[j]
            lignes.append(f"  {j:%d/%m} {JOURS[j.weekday()]}   {len(r):>2} trade(s)   {sum(r):+6.2f} R")
    lignes += ["", "Detail des trades :" if len(finis) <= 15 else "15 derniers trades :"]
    for t in finis[-15:]:
        sens = "ACHAT" if str(t["sens"]).lower().startswith(("a", "b")) else "VENTE"
        lignes.append(f"  {t['ouv']:%d/%m %H:%M}  {sens:<6}{str(t['res']):<20}{t['R']:>+6.2f} R")
    return "\n".join(lignes)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in NOMS else "jour"
    print(texte_bilan(p))
'''

PANNEAU_BILAN = r'''    ligne_bilan = tk.Frame(fen, bg=fond)
    ligne_bilan.pack(fill="x", padx=14, pady=(2, 0))
    label(ligne_bilan, 9, couleur=doux, text="BILAN").pack(side="left", padx=(4, 8))

    def montrer_bilan(periode, titre_p):
        try:
            import bilan_simple
            contenu = bilan_simple.texte_bilan(periode)
        except Exception as exc:
            contenu = f"Bilan impossible : {exc}"
        fb = tk.Toplevel(fen)
        fb.title("Bilan GIMALY - " + titre_p)
        fb.configure(bg=fond)
        fb.geometry("560x540")
        zone = tk.Text(fb, bg=carte, fg=texte, font=("Consolas", 10), relief="flat", wrap="word", padx=12, pady=10)
        zone.insert("1.0", contenu)
        zone.config(state="disabled")
        zone.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        retour_copie = label(fb, 10, couleur=doux, text="")

        def copier():
            fb.clipboard_clear()
            fb.clipboard_append(contenu)
            fb.update()
            retour_copie.config(text="Copie ! Colle-le dans le sujet du canal (Ctrl+V).", fg="#34d27b")
        tk.Button(fb, text="COPIER LE BILAN", command=copier, bg="#34d27b", fg="#0b1118", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10, pady=8, activebackground="#34d27b",
                  cursor="hand2").pack(fill="x", padx=12, pady=(0, 4))
        retour_copie.pack(pady=(0, 10))

    for titre_p, periode in (("AUJOURD'HUI", "jour"), ("SEMAINE", "semaine"), ("MOIS", "mois"), ("TOUT", "tout")):
        tk.Button(ligne_bilan, text=titre_p, command=lambda p=periode, t=titre_p: montrer_bilan(p, t),
                  bg="#2a3b4d", fg=texte, relief="flat", font=("Segoe UI", 9, "bold"), padx=6, pady=5,
                  activebackground="#2a3b4d", activeforeground=texte, cursor="hand2").pack(
                      side="left", expand=True, fill="x", padx=3)

'''


class _FiltreMotifs:
    """Meme controle que la v6, sauf l'adresse publique du depot de mises a jour (voulue)."""

    def __init__(self, base):
        self.base = base

    def search(self, ligne):
        return None if DEPOT in ligne else self.base.search(ligne)


TERMINAL_DEDIE_B64 = (
    "eNqtWdly28gVfedXdOCZIiCT8MiJp6Y4o6g0Mj2lihZHS1USQcNqEk2qbWzTaNBSXPqifELe5stybncDBLh4SeIHiwRu377LuSuf"
    "seHekM3yWGaLEav0fPgDPel5nnc9vjw7OT86ZWfXr9jr8euTMTu6YT9fXLMRSwSb5pqVAkezTMy0YJxVGQiuL8fsTGh+rXgsFHvF"
    "fqtAJJJKmk+6wiUykaUomc7lMBWpCHu9m6x7KBOsEJVmQqvWFb9Vfc5uzvEgLcyNCWfzXJYhu5LEWdPx0j5PucxYWSmSytErIRJw"
    "JDl6TgHeeh2LNB8wmZSk1kJkItMrTbnWIovZ7/9iZZ6x3//tDg1YXrFEaiIr8yQGlwpXV0suS0cS9q7yBDrj2AhmvPlbV1OZlZon"
    "iSByoxP9CdkpDKBEKkHjg7eWIhswvhQzWK2jUMCyvig1e8dTulPn1exesB9JwVLAcvEAZKVQS/CuSBXzXbcdV7UtAGfsB+zESUXm"
    "eSm6Esc8K1e+jvOyNFIWXDHxELLjURQBMcOfcx1A41q/YUL8iwoykmjSXOeUqRT0U4MeY0zg+z1cKsuSw/4zUV8wYOZsLTWxWwn+"
    "enx2QZYnT/nw0ThTYiFLgEfRbSke47KCl/Cs8R1sFAAKdCOfaQnjGD9XJM9RssgZaYuQCHsvA3bKsxlhmJUzJQvdUqNWfiFTnjyy"
    "EfFjeFpNofAskTODQKaFSmXGk0ksYinCKdeg8mXCirykm0uCZEkQKQP2I0EKZkjkIjM2go4pz/DBsQ+jKFyKbBlFV0aeMoqKR32f"
    "Z6F4EOt3FY/Ma3kkiur33/+JyD1i6ZfkUa4WVQrMUwjAB0IRjki27okWYBFK2pIgnrUIen8M2KUAiLhC1P5ycnZ0+nf2wkUQcHUs"
    "TAqYcxcv1pq4vVqKBVcIXcLmu7ziU3pNQilZ4khgVN9jAidgOm19M0n1qwmEhHAj5v1kP/3ZYxagAMpcLsIkn/EkfORpgpggHhz8"
    "tcF1ITS4zeXsnlxoIDmrSp2n8p/GbpaPM/WpnEYRkQwLPnvPF1B6RIaKpbb5JpEIv3wtjcXCuOytcQ/zDUOXUMbXrP5acGCaVwGL"
    "+3m1VFKx43Fj9SF4W8kzUUc3B/Rn0IBXlB6dBmHvUuC9IuzAAXgCxHw9WoZDBbtQ4AAYQGJZFYWSqbA6NpAk4wYhlYmeTItcaXiu"
    "/lTeU4pvvsFozefHsjdXeQqV9X0ip8w9f4uvvd7l0fHJ+ZgdmK/h7EPsB73ji/M3J7/gmXv5gnkbnvV6Z0eXf72hk94zh7thXb2G"
    "pnJ5vd7VyfX4+Obq+uLs5B9E6s48Z/1+v4djSPiKfKG2GGXEchg00+1M+CqUmdSSJ4CLH7ClUMaZ9WGXxhDilXI+xy3+jEg28Luy"
    "aUutAGXNIDlBmaFEB0sJilCW5Qr5Juxp9WhzgjNjjigu2SQv2w+hFD2Ee8zTibXPpDGs8r4tPfsuFnM2sbnMCeYHLukwCrvH1Rf6"
    "90Hqe5YXIvO7TAeAoO0oDjzTUQxLufACI8a8y8JIlEIKyBeWgiPp+KrvH6bBr1ui/JYhf93t3XpR1L879G9/pQ/PokhFUXb3/DBw"
    "LxyZfzh6Fu4Fh9/0B7g3VIIDUEFzvXiYCaSfi6uxUrnqioUQqFTGPK95OilIyDRcqLwq/P0gRHGRBfwu56SASJDIW+SOAU7R+4Ih"
    "f5NfQsJ9KMu5TIQ/KYLmXNthLYgZk8EA7v0cntdoTTS6EeXTiwHzaocZsHoD9oaDZ8ttkxVMJ0DxQiKEDwzXFoB7DbnBQOuIYevv"
    "oTogO+/tvf9An4KuuZxg9MZo6pGannkGbNsjW/zusH+wgbkNUjKiw8DGO/pnr7i1994RR0u9zalb7LGh3soca3Yi1uvG6dJ23AHy"
    "a4Vu02FtbP6gzFstqB/pUfbp9cjqrpmYUMKs426eKxaTEelhCM/T37oCtYMTFoqROz4I5QchOtWSgtP3OhWLQhDeoezqxwFgOIml"
    "8oOt0HdE5pVCZRPs6hE1Ph0/SO17dd/TLYhowKjSQFyNKFmaKo4Geq17Mk3s7pLkBc4cVOyVmNi06C95IirlZNXiQZNtbboxkT2Z"
    "PmqySBij6Y2F30k8MI4jFQ/oVEDWCdiZSuZUO5BHMo+Mbfh3bjJ/cVGR8BmYG0rEHv63JkKHKYkHshhlagpv5e1MY78iXe19447a"
    "onrA5v2tfc1Hq/mT1yc17Bcn/Tb6yIucVqA2UtVp1ajQTudONUdUTf2Ep9MYk9PIyjSwJFR7qkwf7Ftx6epNJr4zkM2Kxi6orPgb"
    "Zc9WJbHTG3WnEuKwVnUD8sZzZ5/nLWNDM3LZphTrXrI+Uu2DazhY8Vh1oStgUQxNMp6CV6c68yVmk0ktsO1Bgt5aNlwx3HKbudG0"
    "ScBL8fjSryvn6pRlWEuCxlc4jFstTYmtce4FddSYyEMSccJVD/WtU04j9wG7NZGN0kOppSC0A6mYEN6qfKF4yt4AuyXstvmQ+Q8/"
    "fB/UryJ8gLd906vd57BREAR35qplZS66azLYlK4xAozWrTTdkYZgby2zSuzuPohxhskN+CElvL0Xa6MNfL/3YuNpsFlBiNPciBgu"
    "knzqW67B9lIDued1ZYOi24mcFUJeoDuK/fmXdR2mHrRyMDg4r+IFEATQ1WZC332W07ahNWr6m2MmDeCbM+bAjg9iy4jJmeYFZgnP"
    "JRG0/rh09yrIwd6RDXf965Kd2gnI7YGU2cF0UgOnNhwpYcuKojXpB2GX7XV3+rrnU6krkRCbT29LwiZBOE5HFN+t3cVXbEHWNyCD"
    "7RuL7n2d9UVnWSGaRQatK+pdRWdD0QhPo8VBXdM64ZLaylT3194n+mtqryPPdtf4+4yyp2mtzUNL0DTW3mAH+r+wMK/Cwsq+vb3u"
    "dte7AqgJnhoNddGBzYCCxE5Oa0UH9RWVxQxlyAGenar9LbNWUNezpmiXtuJsptu60hiSlnxWrA6G7OnSLInQIL09ZqNWHaG0JAc2"
    "M4msShEpaAwN2wHbX0tPlv3cY+yjfArYx/mTt61e1wA3im6RhVYKecq1RLIg9ddCLMoYu0aCoIH2/OZsfGlg2w0N3y57XYyaBeks"
    "T8x+lHZ7puUnCyeiVfRtcg4G3esYHaaExC7tHF2vJtpztkl25pox+k4hLCXyGk3suJBnC0poLkYwlD/AbzIrKqPPdZ65h8BCAzv3"
    "t+/1g/bkZQg3jHlJ92R9jgAV7r6w5UabzJvGhVjUjTo7QLwqb9SmJf38T5+WZYyxBbXAtPP77CfSR/vmZUDfEozkdiW3Yl1rTjXb"
    "vLttnRmy/bu25eewzEaWHrGPhvxp1U05Mx5Tc6QAUHbI/IsX50HXmLW2rmr6Xk61Oa8k/XlsV+Svt6jL0LYPcerUvVBjTXvBTE5N"
    "lunOWbRRWl/9uUzTGUC8VvNJjFajBDnBLZMI2ualyXzUqPlrqxCoLChxlQceim+uOg2JPVtlicze+51IuPgLTNqFvFPP/DxAjkLb"
    "q+gnikRsWxYF4cZqNmxGrZUVbXz+lwYzAKXzIfXMjdv/AJCvNWGUbW1AGXK0gGYjsoGEuffRkjy5uo0sT0V3bSVtXGFLttqEzu5Y"
    "3OlHh9T/xZcrBYjJk5WRmq13JFtLnbhZlX+F9FYyOxUY0brbzW9NmNsqHGys4+pc6AbVz2kZ2EbfkOGzB4vP6uLSCRFDZQHUTSYG"
    "vcl6Pmkn8drNa30R9VitXTi4NC2hg/najz87eiT2ln6wUTsDgH4s9FuLLZfvdw+LjyU9Nf61RE+f2Xrs+s1olVWa7ZlZZX13Z4rD"
    "cNi0/t0yQfNBayr4DBOXCTdZdAtOa4+3ovxcq9Py10kWU+PQ8SxNDLH74dH+RCio9nc6HXu8/3/+aSvK+hsSriWObQ1Y07u5ttP2"
    "SlsP7uqWOkPlWh/YaW+o+6SomQdfUt2cT1vNiSl1tBw1W4rJxLh7MiE4TybO2wbbBFgcX97uj1Do/wMGeudQ"
)
TERMINAL_DEDIE_BAT = ("@echo off\ncd /d %~dp0\n.venv\\Scripts\\python.exe terminal_dedie.py --assistant\n"
                      "echo.\npause\n")


def terminal_dedie_py():
    import base64
    import zlib
    return zlib.decompress(base64.b64decode(TERMINAL_DEDIE_B64)).decode("utf-8")


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
    F["bilan_simple.py"] = BILAN_SIMPLE_PY
    F["panneau.py"] = poser_panneau(F["panneau.py"])
    F["compte.bat"] = COMPTE_BAT
    F["terminal_dedie.py"] = terminal_dedie_py()
    F["terminal_dedie.bat"] = TERMINAL_DEDIE_BAT
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
