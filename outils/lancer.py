"""Lance le bot de trading (recepteur de signaux) et le relance s'il s'arrete (remplace le moteur GIMALY).
Mise a jour automatique : au demarrage puis toutes les 6 h, il cherche une nouvelle version signee par
l'editeur (maj_auto.py), l'installe, la teste (retour arriere si elle echoue) et se relance tout seul.
Arret propre : creer le fichier ~/GIMALY/trading/lanceur.stop (ou Ctrl+C dans cette fenetre)."""
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DOSSIER = Path.home() / "GIMALY" / "trading"
STOP_TRADES = DOSSIER / "icebergs.stop"      # arret des trades (le detecteur ne repart pas tant qu'il existe)
STOP_BOT = DOSSIER / "bot.stop"              # arret complet du bot
STOP_LANCEUR = DOSSIER / "lanceur.stop"
ATTENTE_RELANCE = 60                         # secondes minimum entre deux demarrages d'un meme processus
PROCESSUS = {
    "bot": ["-u", "-m", "gimaly.trading.trading", "--boucle"],
}
MODULE_DE_TEST = os.environ.get("GIMALY_LANCEUR_TEST") == "1"
PERIODE_MAJ = float(os.environ.get("GIMALY_MAJ_PERIODE") or 6 * 3600)    # secondes entre deux verifications


def journal(texte):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    ligne = f"{time.strftime('%d/%m/%Y %H:%M:%S')}  {texte}"
    try:
        print(ligne, flush=True)
    except Exception:
        pass
    with open(DOSSIER / "lanceur.log", "a", encoding="utf-8") as f:
        f.write(ligne + "\n")


def compte_demo():
    """True si le compte MT5 connecte est un compte DEMO ; False si reel/concours ; None si on ne peut pas le savoir."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        try:
            compte = mt5.account_info()
            if compte is not None:
                try:
                    from gimaly.trading.symbole import assurer
                    assurer(mt5)
                except Exception:
                    pass
            return None if compte is None else compte.trade_mode == 0
        finally:
            mt5.shutdown()
    except Exception:
        return None


def maj_disponible():
    try:
        import maj_auto
        return maj_auto
    except Exception as exc:  # noqa: BLE001 - jamais bloquant
        journal(f"mise a jour automatique indisponible : {exc!r}")
        return None


def moment_ok(manifeste, maj):
    """Quand installer : "immediat" tout de suite ; "week-end" marche de l'or ferme ; "demarrage" au prochain
    demarrage du lanceur seulement."""
    quand = manifeste.get("quand", "demarrage")
    return quand == "immediat" or (quand == "week-end" and maj.marche_ferme())


def relancer_lanceur(procs, verrou):
    """Arrete le bot, libere le verrou et demarre un nouveau lanceur (avec le nouveau code)."""
    journal("relance du lanceur avec la nouvelle version")
    for p in procs.values():
        if p is not None and p.poll() is None:
            p.terminate()
    time.sleep(3)
    for p in procs.values():
        if p is not None and p.poll() is None:
            p.kill()
    try:
        (DOSSIER / "lanceur_vivant.txt").unlink()
    except OSError:
        pass
    verrou.close()
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen([sys.executable, str(RACINE / "lancer.py")], cwd=str(RACINE), close_fds=True,
                     env={**os.environ, "GIMALY_RELANCE": "1", "GIMALY_APRES_MAJ": "1"}, **options)
    if sys.stdout is not None and getattr(sys.stdout, "isatty", lambda: False)():
        print("Mise a jour installee : le bot continue en arriere-plan. Tu peux fermer cette fenetre.")


def demarrer(nom):
    sortie = open(DOSSIER / f"{nom}_sortie.log", "a", encoding="utf-8")
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen([sys.executable] + PROCESSUS[nom], cwd=str(RACINE), stdout=sortie,
                            stderr=subprocess.STDOUT, **options)


def autorise(nom):
    demo = compte_demo()
    if demo is None:
        return False, "compte MT5 introuvable (MT5 ouvert et connecte ?) : rien n'est lance"
    if demo is False:
        return False, "compte REEL detecte : cette version ne trade QUE sur un compte DEMO, rien n'est lance"
    if nom == "detecteur" and STOP_TRADES.exists():
        return False, "arret des trades demande (icebergs.stop) : detecteur non lance"
    if nom == "bot" and STOP_BOT.exists():
        return False, "arret du bot demande (bot.stop) : bot non lance"
    return True, ""


def main():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    import socket
    verrou = socket.socket(socket.AF_INET, socket.SOCK_STREAM)      # un seul lanceur a la fois
    for essai in range(30 if os.environ.get("GIMALY_RELANCE") == "1" else 1):    # apres une mise a jour : l'ancien lanceur se ferme
        try:
            verrou.bind(("127.0.0.1", 47824))
            break
        except OSError:
            if essai == 29 or os.environ.get("GIMALY_RELANCE") != "1":
                print("Un lanceur tourne deja : ce lancement est annule.")
                return
            time.sleep(1)
    if STOP_LANCEUR.exists():
        STOP_LANCEUR.unlink()
    procs, dernier, signale, verifie = {}, {}, {}, {}
    journal("lanceur demarre (Ctrl+C ou fichier lanceur.stop pour l'arreter)")
    try:
        import identifiant
        message = identifiant.auto()
        if message:
            journal(message)
    except Exception as exc:  # noqa: BLE001 - l'identifiant ne doit jamais empecher le bot de demarrer
        journal(f"identifiant : erreur ignoree {exc!r}")
    maj = maj_disponible()
    prochaine_maj, en_attente = 0.0, None
    if maj is not None and os.environ.get("GIMALY_APRES_MAJ") != "1":
        try:
            etat, msg = maj.verifier_et_appliquer(lambda m: True)        # au demarrage : on installe tout de suite
            journal(f"mise a jour : {msg}")
            prochaine_maj = time.time() + PERIODE_MAJ
            if etat == "installee":
                relancer_lanceur(procs, verrou)
                return
        except Exception as exc:  # noqa: BLE001
            journal(f"mise a jour : erreur ignoree {exc!r}")
    try:
        while not STOP_LANCEUR.exists():
            if maj is not None:
                try:
                    if time.time() >= prochaine_maj:
                        prochaine_maj = time.time() + PERIODE_MAJ
                        nouveau, msg = maj.chercher()            # toujours la plus recente version signee
                        if nouveau is not None:
                            if en_attente is None or nouveau.get("numero") != en_attente.get("numero"):
                                journal(f"mise a jour : {msg}")
                            en_attente = nouveau
                        else:
                            if msg.startswith("a jour"):
                                en_attente = None
                            else:
                                journal(f"mise a jour : {msg}")
                    if en_attente is not None and moment_ok(en_attente, maj):
                        ok, msg = maj.appliquer(en_attente)
                        journal(f"mise a jour : {msg}")
                        en_attente = None
                        if ok:
                            relancer_lanceur(procs, verrou)
                            return
                except Exception as exc:  # noqa: BLE001 - la mise a jour ne doit jamais arreter le bot
                    journal(f"mise a jour : erreur ignoree {exc!r}")
                    en_attente = None
            try:
                (DOSSIER / "lanceur_vivant.txt").write_text(str(time.time()), encoding="utf-8")
            except OSError:
                pass
            for nom in PROCESSUS:
                p = procs.get(nom)
                if p is not None and p.poll() is None:
                    if time.time() - verifie.get(nom, 0) > 60:
                        verifie[nom] = time.time()
                        if compte_demo() is False:
                            journal(f"compte REEL detecte : arret de {nom}")
                            p.terminate()
                    continue
                if p is not None:
                    journal(f"{nom} arrete (code {p.returncode})")
                    procs[nom] = None
                ok, motif = autorise(nom)
                if not ok:
                    if signale.get(nom) != motif:
                        journal(motif)
                        signale[nom] = motif
                    continue
                signale[nom] = None
                if time.time() - dernier.get(nom, 0) < ATTENTE_RELANCE:
                    continue
                procs[nom] = demarrer(nom)
                dernier[nom] = time.time()
                journal(f"{nom} demarre (pid {procs[nom].pid})")
            time.sleep(2 if MODULE_DE_TEST else 5)
    except KeyboardInterrupt:
        pass
    journal("arret du lanceur : arret des processus")
    try:
        (DOSSIER / "lanceur_vivant.txt").unlink()
    except OSError:
        pass
    for nom, p in procs.items():
        if p is not None and p.poll() is None:
            p.terminate()
    time.sleep(2)
    for nom, p in procs.items():
        if p is not None and p.poll() is None:
            p.kill()


if __name__ == "__main__":
    main()
