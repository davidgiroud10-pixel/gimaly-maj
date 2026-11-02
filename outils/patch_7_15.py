# -*- coding: utf-8 -*-
r"""Version 7.15 : lanceur plus reactif et plus sur.
  1. Signe de vie : le premier part 45 s apres le demarrage (plus de faux « bot arrete » apres une mise a jour), puis un
     signe de vie est envoye des que l'etat du bot change ou qu'un signal est recu (max 12 par heure, 1 toutes les 30 s),
     en plus de celui toutes les 10 min.
  2. Mise a jour sans gener un trade : elle ne s'installe que si le marche est ferme ou qu'aucune position n'est ouverte
     (au plus tard apres 4 h d'attente).
  3. Ordre signe « mets-toi a jour maintenant » (forcer_maj.py, cote editeur) : canal PRIVE a part, lu par le lanceur, signe
     avec ta cle privee. (Ce n'est PAS le canal des signaux : un ancien bot y prendrait l'ordre pour une vente.)
Fichiers modifies : outils_v7/lancer.py, gimaly/trading/signaux_distants.py ; cree : forcer_maj.py. Sauvegardes *.avant_715.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_7_15.py   puis publier_maj.py. Idempotent ; rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd()
LANCEUR = RACINE / "outils_v7" / "lancer.py"
SIGNAUX = RACINE / "gimaly" / "trading" / "signaux_distants.py"
FORCER = RACINE / "forcer_maj.py"
FORCER_TEXTE = r'''# -*- coding: utf-8 -*-
r"""Editeur : envoie a tes amis l'ordre SIGNE « mets-toi a jour maintenant ».

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe forcer_maj.py
Publie d'abord ta mise a jour (publier_maj.py + zip et version.json sur GitHub), PUIS lance ce script. Le lanceur de chaque ami
qui a la version 7.15 ou plus cherche alors la mise a jour tout de suite, au lieu d'attendre jusqu'a 30 min, et l'installe des
qu'aucun trade n'est ouvert (au plus tard apres 4 h). L'ordre passe par un canal PRIVE a part, signe avec ta cle privee : un
ordre non signe est ignore. Les amis dont le lanceur est ferme ou le PC eteint ne le recoivent pas (ils se mettront a jour
a leur prochain contrôle ou demarrage). Rien n'est modifie chez toi."""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
from gimaly.trading import signaux_distants as sd  # noqa: E402


def secret_commun():
    try:
        texte = (RACINE / "config.local.yaml").read_text(encoding="utf-8-sig")
    except OSError:
        return None
    m = re.search(r"(?m)^trading_signaux_secret:[ \t]*['\"]?([^\s'\"#]+)", texte)
    return m.group(1) if m else None


def main():
    if sd._lire_cle_privee() is None:
        print("Cle de signature introuvable (cle_signature.priv) : impossible de signer l'ordre. Rien n'est envoye.")
        return 1
    amis, ancien = sd.lire_amis()
    cibles = {f"ami {nom}": a["secret"] for nom, a in amis.items()}
    commun = secret_commun()
    if (ancien or not amis) and commun:
        cibles["canal commun (amis pas encore migres)"] = commun
    if not cibles:
        print("Aucun ami actif dans amis.json : rien a envoyer.")
        return 1
    echecs = 0
    for nom, secret in cibles.items():
        ok, msg = sd.publier({"cmd": "maj"}, sd.canal_commande(secret), secret)
        print(f"{'envoye' if ok else 'ECHEC '} : {nom} ({msg})")
        echecs += 0 if ok else 1
    print("L'ordre est valable 90 secondes : les lanceurs ouverts le recoivent tout de suite." if not echecs
          else "Certains envois ont echoue : relance dans un instant.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
'''

L_HELPERS = '''def pret_pour_maj(maj, procs):
    """Installer une mise a jour sans gener un trade : marche ferme, ou aucune position ouverte sur le compte.
    Si MetaTrader ne repond pas et que le bot ne tourne pas, il n'y a rien a proteger."""
    try:
        if maj is not None and maj.marche_ferme():
            return True
    except Exception:  # noqa: BLE001
        pass
    n = positions_ouvertes()
    if n == 0:
        return True
    if n is None:
        p = procs.get("bot")
        return p is None or p.poll() is not None
    return False


_ECOUTE = {"rec": None, "secret": None, "verifie": 0.0, "erreur": ""}


def ecouter_commandes():
    """Ordres de l'editeur (« mets-toi a jour maintenant ») : canal PRIVE a part, signe Ed25519, lu par le lanceur lui-meme
    (donc meme si le bot est arrete). Renvoie le recepteur, ou None."""
    if time.time() - _ECOUTE["verifie"] < 60:
        return _ECOUTE["rec"]
    _ECOUTE["verifie"] = time.time()
    try:
        import retour
        from gimaly.trading import signaux_distants as sd
        secret = retour.lire_config().get("trading_signaux_secret")
        if not secret or sd.cle_publique_installee() is None:
            return _ECOUTE["rec"]
        if secret != _ECOUTE["secret"]:
            if _ECOUTE["rec"] is not None:
                _ECOUTE["rec"].arreter()
            rec = sd.Recepteur(sd.canal_commande(secret), secret, journal=journal)
            rec.suivre_dernier = False
            rec.demarrer()
            _ECOUTE["rec"], _ECOUTE["secret"] = rec, secret
    except Exception as exc:  # noqa: BLE001 - jamais bloquant
        if _ECOUTE["erreur"] != repr(exc):
            _ECOUTE["erreur"] = repr(exc)
            journal(f"ecoute des ordres de l'editeur : erreur ignoree {exc!r}")
    return _ECOUTE["rec"]


'''

L_INIT_ANCIEN = "    prochaine_maj, en_attente = 0.0, None\n    prochain_retour = 0.0\n"
L_INIT_NOUVEAU = '''    prochaine_maj, en_attente = 0.0, None
    forcer_fin, attente_depuis, prochain_test_maj, signale_maj = 0.0, None, 0.0, False
    prochain_retour = 0.0
    debut_retour = time.time() + 45            # le bot a le temps de demarrer avant le 1er signe de vie (sinon « arrete » a tort)
    retour_etat = {"etat": None, "sig": 0.0, "envoi": 0.0, "evts": []}
'''

L_BOUCLE_ANCIEN = "        while not STOP_LANCEUR.exists():\n            if maj is not None:\n"
L_BOUCLE_NOUVEAU = '''        while not STOP_LANCEUR.exists():
            rec_cmd = ecouter_commandes()
            if rec_cmd is not None:
                for ordre in rec_cmd.recuperer():
                    if ordre.get("cmd") == "maj":
                        journal("ordre de mise a jour recu de l'editeur")
                        forcer_fin, prochaine_maj = time.time() + 600, 0.0
            if maj is not None:
'''

L_AJOUR_ANCIEN = '''                            if msg.startswith("a jour"):
                                en_attente = None
'''
L_AJOUR_NOUVEAU = '''                            if msg.startswith("a jour"):
                                en_attente = None
                                if time.time() < forcer_fin:
                                    prochaine_maj = time.time() + 120      # ordre recu : le cache de GitHub peut retarder la version
'''

L_APPLIQUER_ANCIEN = '''                    if en_attente is not None and moment_ok(en_attente, maj):
                        ok, msg = maj.appliquer(en_attente)
                        journal(f"mise a jour : {msg}")
                        en_attente = None
'''
L_APPLIQUER_NOUVEAU = '''                    pret = False
                    if en_attente is not None and (time.time() < forcer_fin or moment_ok(en_attente, maj)):
                        if attente_depuis is None:
                            attente_depuis = time.time()
                        if time.time() >= prochain_test_maj:
                            prochain_test_maj = time.time() + 30
                            pret = pret_pour_maj(maj, procs) or time.time() - attente_depuis > 4 * 3600
                            if not pret and not signale_maj:
                                signale_maj = True
                                journal("mise a jour en attente : un trade est ouvert (installation des qu'il sera ferme)")
                    if pret:
                        ok, msg = maj.appliquer(en_attente)
                        journal(f"mise a jour : {msg}")
                        en_attente, attente_depuis, signale_maj = None, None, False
'''

L_BATTEMENT_ANCIEN = '''            if time.time() >= prochain_retour:                   # signe de vie vers l'editeur (voir retour.py)
                prochain_retour = time.time() + 600
                try:
                    import retour
                    vivant = procs.get("bot") is not None and procs["bot"].poll() is None
                    etat_bot = "arrete" if not vivant else ("pause" if STOP_TRADES.exists() else "actif")
                    if vivant and not verifier_config():
                        etat_bot = "config"              # visible dans la fenetre Amis de l'editeur
                    retour.battement(etat_bot, compte_demo, journal)
'''
L_BATTEMENT_NOUVEAU = '''            maintenant = time.time()
            vivant = procs.get("bot") is not None and procs["bot"].poll() is None
            etat_cour = "arrete" if not vivant else ("pause" if STOP_TRADES.exists() else "actif")
            try:
                sig_cour = (DOSSIER / "dernier_signal.txt").stat().st_mtime
            except OSError:
                sig_cour = 0.0
            retour_etat["evts"] = [t for t in retour_etat["evts"] if maintenant - t < 3600]
            evenement = (maintenant - retour_etat["envoi"] >= 30 and len(retour_etat["evts"]) < 12
                         and (etat_cour != retour_etat["etat"] or sig_cour != retour_etat["sig"]))
            if maintenant >= debut_retour and (maintenant >= prochain_retour or evenement):   # signe de vie vers l'editeur (retour.py)
                if maintenant < prochain_retour:
                    retour_etat["evts"].append(maintenant)       # hors cadence : changement d'etat ou signal recu
                prochain_retour = maintenant + 600
                try:
                    import retour
                    etat_bot = etat_cour
                    if vivant and not verifier_config():
                        etat_bot = "config"              # visible dans la fenetre Amis de l'editeur
                    retour.battement(etat_bot, compte_demo, journal)
                    retour_etat.update(etat=etat_cour, sig=sig_cour, envoi=maintenant)
'''

L_MODIFS = [
    ("def moment_ok(manifeste, maj):\n", L_HELPERS + "def moment_ok(manifeste, maj):\n"),
    (L_INIT_ANCIEN, L_INIT_NOUVEAU),
    (L_BOUCLE_ANCIEN, L_BOUCLE_NOUVEAU),
    (L_AJOUR_ANCIEN, L_AJOUR_NOUVEAU),
    (L_APPLIQUER_ANCIEN, L_APPLIQUER_NOUVEAU),
    (L_BATTEMENT_ANCIEN, L_BATTEMENT_NOUVEAU),
]

S_COMMANDE = '''def canal_commande(secret):
    """Canal PRIVE des ordres de l'editeur vers un ami (ex. « mets-toi a jour »), derive de son secret. Distinct du canal des
    signaux : les anciens bots y lisent tout message comme un ordre de trade (un ordre y serait pris pour une VENTE)."""
    return "gimaly-cmd-" + hashlib.sha256(("gimaly-cmd:" + str(secret)).encode("utf-8")).hexdigest()[:24]


'''
S_DERNIER_ANCIEN = '''        try:                                  # pour le signe de vie envoye a l'editeur (retour.py)
            FICHIER_DERNIER_SIGNAL.write_text(str(round(time.time(), 3)), encoding="utf-8")
        except OSError:
            pass
'''
S_DERNIER_NOUVEAU = '''        if self.suivre_dernier:
            try:                              # pour le signe de vie envoye a l'editeur (retour.py)
                FICHIER_DERNIER_SIGNAL.write_text(str(round(time.time(), 3)), encoding="utf-8")
            except OSError:
                pass
'''
S_MODIFS = [
    ("def empreinte(canal):\n", S_COMMANDE + "def empreinte(canal):\n"),
    ("        self.rejetes = 0\n", "        self.rejetes = 0\n        self.suivre_dernier = True        # False : canal des ordres, pas des signaux de trade\n"),
    (S_DERNIER_ANCIEN, S_DERNIER_NOUVEAU),
]


def lire(chemin):
    brut = chemin.read_bytes()
    texte = brut.decode("utf-8-sig")
    return brut.startswith(b"\xef\xbb\xbf"), "\r\n" in texte, texte.replace("\r\n", "\n")


def appliquer(chemin, marque, modifs, nom):
    bom, crlf, t = lire(chemin)
    if marque in t:
        print(f"{nom} : deja a jour")
        return None
    for ancien, nouveau in modifs:
        if t.count(ancien) != 1:
            raise SystemExit(f"{nom} : repere introuvable (une fois attendu) : RIEN ecrit. Envoie-moi ce fichier.\n{ancien[:90]}")
        t = t.replace(ancien, nouveau, 1)
    compile(t, nom, "exec")
    return bom, crlf, t


def ecrire(chemin, bom, crlf, texte):
    copie = chemin.with_name(chemin.name + ".avant_715")
    if chemin.exists() and not copie.exists():
        shutil.copy2(chemin, copie)
    sortie = texte.replace("\n", "\r\n") if crlf else texte
    chemin.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def main():
    for f in (LANCEUR, SIGNAUX):
        if not f.exists():
            raise SystemExit(f"{f} introuvable : lance ce script depuis le dossier gimaly")
    compile(FORCER_TEXTE, "forcer_maj.py", "exec")
    travaux = [(LANCEUR, appliquer(LANCEUR, "def pret_pour_maj", L_MODIFS, "outils_v7/lancer.py")),
               (SIGNAUX, appliquer(SIGNAUX, "def canal_commande", S_MODIFS, "gimaly/trading/signaux_distants.py"))]
    for chemin, res in travaux:          # tout est verifie avant d'ecrire quoi que ce soit
        if res is not None:
            ecrire(chemin, *res)
            print(f"{chemin.name} : corrige (sauvegarde {chemin.name}.avant_715)")
    if not FORCER.exists() or FORCER.read_text(encoding="utf-8") != FORCER_TEXTE:
        ecrire(FORCER, False, False, FORCER_TEXTE)
        print("forcer_maj.py : ecrit")
    else:
        print("forcer_maj.py : deja a jour")
    print("Termine. Prochaine etape : publier_maj.py (comme d'habitude).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
