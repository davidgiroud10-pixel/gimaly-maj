# -*- coding: utf-8 -*-
"""Fenetre AMIS : qui est connecte, qui est a jour, et les alertes (compte reel, fichiers modifies, identifiant
utilise sur deux PC, bot arrete). Elle lit les « signes de vie » que le bot de chaque ami envoie sur son canal retour
(retour.py) : pseudo, version, etat, demo/reel, empreinte des fichiers, numero d'installation. Rien d'autre.

Lancer :   suivi_amis.bat   (ou  .\\.venv\\Scripts\\python.exe suivi_amis.py)
Sans fenetre (texte) :   .\\.venv\\Scripts\\python.exe suivi_amis.py --texte
Independant de GIMALY : tu peux la laisser ouverte ou la fermer, GIMALY n'est pas touche.
"""
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.request
import re
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import attribution
except Exception:  # noqa: BLE001 - la fenetre marche sans (pas d'attribution automatique)
    attribution = None

DOSSIER = Path.home() / "GIMALY" / "trading"
FICHIER_AMIS = Path(os.environ.get("GIMALY_AMIS") or (DOSSIER / "amis.json"))
FICHIER_ETAT = Path(os.environ.get("GIMALY_SUIVI") or (DOSSIER / "suivi_amis.json"))
FICHIER_INCONNUS = Path(os.environ.get("GIMALY_INCONNUS") or (DOSSIER / "suivi_inconnus.json"))
FICHIER_ATTR = Path(os.environ.get("GIMALY_ATTRIBUTIONS") or (DOSSIER / "attributions.json"))
CONFIG_EDITEUR = Path(os.environ.get("GIMALY_CONFIG") or (Path(__file__).resolve().parent / "config.local.yaml"))
REPUBLIER_APRES = 3 * 3600     # attribution renvoyee toutes les 3 h tant que l'ami n'a pas donne signe (le relais garde 12 h)
PUBLICATION = Path(os.environ.get("GIMALY_PUBLICATION") or (Path.home() / "GIMALY-publication"))
RELAIS = os.environ.get("GIMALY_RELAIS") or "https://ntfy.sh"
AGENT = {"User-Agent": "gimaly-suivi/1"}
EN_LIGNE = 25 * 60          # un signe de vie toutes les 10 min : 25 min sans nouvelles = hors ligne
LONG_ARRET = 24 * 3600
FENETRE_INSTALL = 72 * 3600
FICHIERS_SUIVIS = ("gimaly/trading/trading.py", "gimaly/trading/signaux_distants.py", "gimaly/trading/icebergs.py",
                   "gimaly/trading/symbole.py", "gimaly/trading/mt5_isole.py", "lancer.py", "maj_auto.py", "retour.py")


def canon(p):
    return json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ouvrir(texte, secret):
    """Le signe de vie si sa signature est valide (secret de l'ami), sinon None."""
    try:
        e = json.loads(texte)
        p, s = e["p"], e["s"]
        if not isinstance(p, dict) or not isinstance(s, str):
            return None
    except (ValueError, KeyError, TypeError):
        return None
    attendu = hmac.new(secret.encode("utf-8"), canon(p).encode("utf-8"), hashlib.sha256).hexdigest()
    return p if hmac.compare_digest(attendu, s) else None


def canal_retour(secret):
    """Canal de retour d'un ami : calcule a partir de son secret (l'editeur et l'ami arrivent au meme nom, sans rien echanger)."""
    return "gimaly-r-" + hashlib.sha256(("retour|" + secret).encode("utf-8")).hexdigest()[:32]


def secret_partage():
    """Le secret commun d'origine (ancien canal) : celui que les amis encore non nommes utilisent pour leur signe de vie."""
    try:
        m = re.search(r"(?m)^trading_signaux_secret:[ \t]*\"?([^\s\"#]+)\"?", CONFIG_EDITEUR.read_text(encoding="utf-8-sig"))
        return m.group(1) if m else None
    except OSError:
        return None


def _lire_json(chemin, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _ecrire_json(chemin, donnees):
    try:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = chemin.with_name(chemin.name + ".tmp")
        tmp.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, chemin)
    except OSError:
        pass


def lire_amis():
    try:
        d = json.loads(FICHIER_AMIS.read_text(encoding="utf-8"))
        return {n: dict(a, retour=canal_retour(a["secret"])) for n, a in (d.get("amis") or {}).items()
                if isinstance(a, dict) and a.get("secret")}
    except (OSError, ValueError, AttributeError):
        return {}


def derniere_publication():
    """(numero, version, {fichier: empreinte}) de la derniere mise a jour publiee (dossier GIMALY-publication)."""
    try:
        env = json.loads((PUBLICATION / "version.json").read_text(encoding="utf-8"))
        p = env["p"]
        emp = {}
        with zipfile.ZipFile(PUBLICATION / p["fichier"]) as z:
            for nom in FICHIERS_SUIVIS:
                try:
                    emp[nom] = hashlib.sha256(z.read(nom).replace(b"\r\n", b"\n")).hexdigest()[:10]
                except KeyError:
                    emp[nom] = None
        return int(p["numero"]), str(p["version"]), emp
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None, None, {}


class Suivi:
    """Ecoute les canaux retour et garde l'etat de chaque ami (fichier suivi_amis.json : survit aux redemarrages)."""

    def __init__(self, relais=RELAIS):
        self.relais = relais
        self.verrou = threading.Lock()
        try:
            self.etat = json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.etat = {}
        self.inconnus = _lire_json(FICHIER_INCONNUS, {})        # iid -> installation pas encore nommee
        self.attr = _lire_json(FICHIER_ATTR, {})                # iid -> attribution envoyee
        self._stop = threading.Event()
        self._threads = {}
        self._gen = 0                                           # change a chaque ACTUALISER : les anciens fils s'arretent

    # ---- installations pas encore nommees (signe de vie sur le canal commun)
    def enregistrer_inconnu(self, p, quand):
        iid = str(p.get("iid", ""))
        if not re.fullmatch(r"[0-9a-f]{16}", iid) or iid in self.attr:
            return
        with self.verrou:
            e = self.inconnus.setdefault(iid, {"pks": [], "premier": quand})
            if quand >= e.get("vu", 0):
                e["vu"] = quand
                e["dernier"] = {k: v for k, v in p.items() if k not in ("who", "emp")}
                if attribution is not None and isinstance(p.get("who"), dict):
                    qui = attribution.lire_qui(p["who"])
                    if qui:
                        e["pc"], e["user"] = str(qui.get("pc", ""))[:40], str(qui.get("user", ""))[:40]
            pk = p.get("pk")
            if isinstance(pk, str) and re.fullmatch(r"[0-9a-f]{64}", pk) and pk not in e["pks"]:
                e["pks"].append(pk)
            _ecrire_json(FICHIER_INCONNUS, self.inconnus)

    def lignes_inconnus(self, maintenant=None):
        maintenant = maintenant or time.time()
        with self.verrou:
            liste = json.loads(json.dumps(self.inconnus))
        sortie = []
        for iid, e in sorted(liste.items(), key=lambda kv: -kv[1].get("vu", 0)):
            if iid in self.attr:
                continue
            p = e.get("dernier", {})
            sortie.append({"iid": iid, "pc": e.get("pc", "?"), "user": e.get("user", "?"), "version": str(p.get("ver", "?")),
                           "compte": {"demo": "DEMO", "reel": "REEL"}.get(p.get("compte"), "?"), "vu": ago(maintenant - e.get("vu", 0)),
                           "en_ligne": maintenant - e.get("vu", 0) <= EN_LIGNE, "conflit": len(e.get("pks", [])) > 1,
                           "pk": (e.get("pks") or [None])[0]})
        return sortie

    def nommer(self, iid, nom, relais=None):
        """Cree l'ami `nom`, et envoie a cette installation son identifiant personnel (chiffre, signe)."""
        if attribution is None:
            raise SystemExit("attribution.py introuvable : telecharge-le dans le dossier gimaly")
        partage = secret_partage()
        with self.verrou:
            e = dict(self.inconnus.get(iid) or {})
        if not partage:
            raise SystemExit(f"secret commun introuvable dans {CONFIG_EDITEUR}")
        if not e or len(e.get("pks", [])) != 1:
            raise SystemExit("installation inconnue, ou deux cles differentes pour le meme numero (usurpation possible) : refuse")
        import amis
        ami, _ = amis.creer(nom)
        message = attribution.fabriquer_attribution(partage, iid, e["pks"][0], ami, nom)
        attribution.publier_attribution(partage, iid, message, relais or self.relais)
        with self.verrou:
            self.attr[iid] = {"nom": nom, "pk": e["pks"][0], "envoye": time.time(), "dernier_envoi": time.time()}
            _ecrire_json(FICHIER_ATTR, self.attr)
        return ami

    def republier(self, maintenant=None, relais=None):
        """Renvoie l'attribution (nouveau message) aux amis nommes qui n'ont pas encore donne signe sur leur canal personnel."""
        maintenant = maintenant or time.time()
        partage = secret_partage()
        if attribution is None or not partage:
            return 0
        amis_ = lire_amis()
        n = 0
        for iid, a in list(self.attr.items()):
            nom = a["nom"]
            if nom in amis_ and (self.etat.get(nom) or {}).get("dernier"):
                continue                                         # il est passe sur son canal : c'est fait
            if maintenant - a.get("dernier_envoi", 0) < REPUBLIER_APRES or nom not in amis_:
                continue
            try:
                msg = attribution.fabriquer_attribution(partage, iid, a["pk"], amis_[nom], nom)
                attribution.publier_attribution(partage, iid, msg, relais or self.relais)
                a["dernier_envoi"] = maintenant
                n += 1
            except Exception:  # noqa: BLE001
                pass
        if n:
            _ecrire_json(FICHIER_ATTR, self.attr)
        return n

    # ---- reception
    def enregistrer(self, nom, p, quand):
        with self.verrou:
            e = self.etat.setdefault(nom, {"iids": {}})
            if quand >= e.get("vu", 0):
                e["dernier"], e["vu"] = p, quand
            e.setdefault("premier_vu", quand)
            i = e["iids"].setdefault(str(p.get("iid", "?")), {"premier": quand, "dernier": quand})
            i["dernier"] = max(i["dernier"], quand)
            try:
                FICHIER_ETAT.parent.mkdir(parents=True, exist_ok=True)
                tmp = FICHIER_ETAT.with_name(FICHIER_ETAT.name + ".tmp")
                tmp.write_text(json.dumps(self.etat, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, FICHIER_ETAT)
            except OSError:
                pass

    def traiter_ligne(self, nom, secret, brut):
        try:
            ev = json.loads(brut.decode("utf-8") if isinstance(brut, bytes) else brut)
        except ValueError:
            return None
        if ev.get("event") != "message":
            return None
        p = ouvrir(ev.get("message", ""), secret)
        if p is None:
            return None
        self.enregistrer(nom, p, float(ev.get("time") or time.time()))
        return ev.get("id")

    def _boucle(self, nom, a):
        dernier_id, attente, gen = None, 2, self._gen
        while not self._stop.is_set() and gen == self._gen:
            try:
                depuis = dernier_id or "12h"
                req = urllib.request.Request(f"{self.relais}/{a['retour']}/json?since={depuis}", headers=AGENT)
                with urllib.request.urlopen(req, timeout=100) as r:
                    attente = 2
                    for brut in r:
                        if self._stop.is_set() or gen != self._gen:
                            break
                        i = self.traiter_ligne(nom, a["secret"], brut)
                        if i:
                            dernier_id = i
            except Exception:  # noqa: BLE001 - coupure : on se reconnecte
                pass
            if self._stop.wait(attente):
                break
            attente = min(attente * 2, 60)

    def _boucle_partage(self, secret):
        dernier_id, attente, gen = None, 2, self._gen
        topic = canal_retour(secret)
        while not self._stop.is_set() and gen == self._gen:
            try:
                req = urllib.request.Request(f"{self.relais}/{topic}/json?since={dernier_id or '12h'}", headers=AGENT)
                with urllib.request.urlopen(req, timeout=100) as r:
                    attente = 2
                    for brut in r:
                        if self._stop.is_set() or gen != self._gen:
                            break
                        try:
                            ev = json.loads(brut.decode("utf-8"))
                            if ev.get("event") != "message":
                                continue
                            p = ouvrir(ev.get("message", ""), secret)
                            if p is not None:
                                self.enregistrer_inconnu(p, float(ev.get("time") or time.time()))
                            dernier_id = ev.get("id") or dernier_id
                        except ValueError:
                            continue
            except Exception:  # noqa: BLE001
                pass
            if self._stop.wait(attente):
                break
            attente = min(attente * 2, 60)

    def demarrer(self):
        s = secret_partage()
        if s and not (self._threads.get("*partage") and self._threads["*partage"].is_alive()):
            t = threading.Thread(target=self._boucle_partage, args=(s,), daemon=True, name="suivi-partage")
            self._threads["*partage"] = t
            t.start()
        for nom, a in lire_amis().items():
            if nom not in self._threads or not self._threads[nom].is_alive():
                t = threading.Thread(target=self._boucle, args=(nom, a), daemon=True, name=f"suivi-{nom}")
                self._threads[nom] = t
                t.start()

    def actualiser(self):
        """Relit tout depuis le relais (12 h d'historique) : les anciennes ecoutes s'arretent, de nouvelles repartent."""
        self._gen += 1
        self._threads.clear()
        self.demarrer()

    def arreter(self):
        self._stop.set()

    # ---- evaluation
    def lignes(self, maintenant=None):
        maintenant = maintenant or time.time()
        num_pub, ver_pub, emp_pub = derniere_publication()
        try:
            actifs = json.loads(FICHIER_AMIS.read_text(encoding="utf-8")).get("amis", {})
        except (OSError, ValueError):
            actifs = {}
        sortie = []
        with self.verrou:
            etat = json.loads(json.dumps(self.etat))
        for nom, a in lire_amis().items():
            migr = max([x.get("envoye", 0) for x in self.attr.values() if x.get("nom") == nom] or [0]) or None
            sortie.append(evaluer(nom, etat.get(nom), actifs.get(nom, {}).get("actif", True), num_pub, emp_pub, maintenant, migr))
        return sortie, ver_pub


def ago(s):
    if s < 90:
        return "a l'instant"
    if s < 3600:
        return f"il y a {int(s // 60)} min"
    if s < 172800:
        return f"il y a {int(s // 3600)} h"
    return f"il y a {int(s // 86400)} j"


def evaluer(nom, e, actif, num_pub, emp_pub, maintenant, migration=None):
    """Une ligne de la fenetre : dict (ami, statut, version, a_jour, compte, bot, signal, alertes[(niveau, texte)])."""
    l = {"ami": nom, "actif": actif, "statut": "jamais vu", "vu": "-", "version": "-", "a_jour": None, "compte": "-",
         "bot": "-", "signal": "-", "alertes": []}
    al = l["alertes"]
    if not actif:
        al.append(("gris", "Retire : il ne recoit plus de signaux"))
    if not e or not e.get("dernier"):
        if actif and migration:
            l["statut"] = "migration"
            al.append(("gris", "Identifiant envoye " + ago(maintenant - migration) + " : en attente de son prochain signe de vie "
                       "(il s'installe tout seul, le bot redemarre quand le marche est ferme)"))
        elif actif:
            al.append(("orange", "Aucun signe de vie : identifiant pas encore installe, ou bot jamais lance"))
        return l
    p, vu = e["dernier"], e.get("vu", 0)
    age = maintenant - vu
    l["vu"] = ago(age)
    l["statut"] = "en ligne" if age <= EN_LIGNE else "hors ligne"
    l["version"] = str(p.get("ver", "?"))
    l["compte"] = {"demo": "DEMO", "reel": "REEL", "inconnu": "?"}.get(p.get("compte"), "?")
    l["bot"] = {"actif": "actif", "pause": "en pause", "arrete": "arrete"}.get(p.get("etat"), "?")
    if p.get("dernier"):
        l["signal"] = ago(maintenant - float(p["dernier"]))
    num = p.get("num")
    if num_pub:
        l["a_jour"] = (num == num_pub)
        if num != num_pub and isinstance(num, int):
            al.append(("orange", f"Pas a jour (version {p.get('ver', '?')}, derniere publiee 7.{num_pub})"))
    if p.get("compte") == "reel":
        al.append(("rouge", "MetaTrader sur un compte REEL (le bot refuse de trader, mais c'est hors cadre)"))
    if emp_pub and num == num_pub:
        modifies = [f for f, h in emp_pub.items() if h and (p.get("emp") or {}).get(f) not in (None, h)]
        manquants = [f for f, h in emp_pub.items() if h and (p.get("emp") or {}).get(f) is None]
        if modifies:
            al.append(("rouge", "Fichiers differents de la version publiee (a verifier) : " + ", ".join(m.split("/")[-1] for m in modifies)))
        if manquants:
            al.append(("rouge", "Fichiers absents : " + ", ".join(m.split("/")[-1] for m in manquants)))
    actives = [i for i, v in (e.get("iids") or {}).items() if maintenant - v["dernier"] <= FENETRE_INSTALL]
    if len(actives) >= 2:
        al.append(("rouge", f"{len(actives)} installations differentes actives en meme temps : identifiant partage ?"))
    elif len(e.get("iids") or {}) >= 2:
        al.append(("orange", "Numero d'installation different d'avant (PC change ou reinstalle ?)"))
    if l["statut"] == "hors ligne" and age > LONG_ARRET:
        al.append(("orange", f"Hors ligne depuis {ago(age).replace('il y a ', '')}"))
    if l["statut"] == "en ligne" and p.get("etat") == "arrete":
        al.append(("orange", "Bot arrete"))
    return l


def quota_relais():
    """True si le journal du bot montre des refus du relais (HTTP 429) dans les dernieres 24 h."""
    for nom in ("trading.log", "bot_sortie.log"):
        f = DOSSIER / nom
        try:
            if f.stat().st_mtime < time.time() - 86400:
                continue
            with open(f, "rb") as h:
                h.seek(max(0, f.stat().st_size - 400000))
                texte = h.read().decode("utf-8", "ignore")
        except OSError:
            continue
        if "[signaux]" in texte and "HTTP 429" in texte:
            return True
    return False


def texte(lignes, ver_pub):
    sortie = [f"Derniere version publiee : {ver_pub or '?'}", ""]
    for l in lignes:
        sortie.append(f"{l['ami']:<16} {l['statut']:<10} vu {l['vu']:<14} v{l['version']:<5} {l['compte']:<5} bot {l['bot']:<9} signal {l['signal']}")
        for niveau, t in l["alertes"]:
            sortie.append(f"    [{niveau.upper()}] {t}")
    return "\n".join(sortie)


# ------------------------------------------------------------------ fenetre
COULEURS = {"rouge": "#ff6b6b", "orange": "#f5a623", "gris": "#8a94a6", "vert": "#34d17b"}


def fenetre():
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (QApplication, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
                                   QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView)

    app = QApplication.instance() or QApplication(sys.argv)
    suivi = Suivi()
    suivi.demarrer()

    w = QWidget()
    w.setWindowTitle("GIMALY - Amis")
    w.resize(1100, 720)
    w.setStyleSheet("QWidget{background:#0b1220;color:#e6edf7;font-size:13px}"
                    "QTableWidget{background:#101a2e;gridline-color:#1b2a45;border:0}"
                    "QHeaderView::section{background:#16233d;color:#9fb0cc;border:0;padding:6px}"
                    "QPushButton{background:#2a3b5c;border:0;padding:8px 14px;font-weight:bold}"
                    "QPushButton:hover{background:#38507a}")
    v = QVBoxLayout(w)
    titre = QLabel("")
    titre.setStyleSheet("font-size:16px;font-weight:bold")
    bandeau = QLabel("")
    bandeau.setWordWrap(True)
    v.addWidget(titre)
    v.addWidget(bandeau)
    colonnes = ["Ami", "Etat", "Vu", "Version", "Compte", "Bot", "Dernier signal", "Alertes"]
    t = QTableWidget(0, len(colonnes))
    t.setHorizontalHeaderLabels(colonnes)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeToContents)
    h.setSectionResizeMode(len(colonnes) - 1, QHeaderView.Stretch)
    t.setWordWrap(True)
    v.addWidget(t, 3)
    titre2 = QLabel("")
    titre2.setStyleSheet("font-size:14px;font-weight:bold;margin-top:8px")
    v.addWidget(titre2)
    col2 = ["Installation", "Nom du PC", "Session Windows", "Version", "Compte", "Vu", "Remarque"]
    t2 = QTableWidget(0, len(col2))
    t2.setHorizontalHeaderLabels(col2)
    t2.verticalHeader().setVisible(False)
    t2.setEditTriggers(QTableWidget.NoEditTriggers)
    t2.setSelectionBehavior(QTableWidget.SelectRows)
    t2.setSelectionMode(QTableWidget.SingleSelection)
    t2.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t2.horizontalHeader().setSectionResizeMode(len(col2) - 1, QHeaderView.Stretch)
    v.addWidget(t2, 2)
    bas = QHBoxLayout()
    msg = QLabel("")
    msg.setStyleSheet("color:#9fb0cc")
    bas.addWidget(msg, 1)
    b_actualiser = QPushButton("ACTUALISER")
    b_nommer = QPushButton("NOMMER L'INSTALLATION SELECTIONNEE")
    b_retirer = QPushButton("RETIRER L'AMI SELECTIONNE")
    b_remettre = QPushButton("REMETTRE")
    bas.addWidget(b_actualiser)
    bas.addWidget(b_nommer)
    bas.addWidget(b_retirer)
    bas.addWidget(b_remettre)
    v.addLayout(bas)

    def rafraichir():
        suivi.demarrer()
        lignes, ver_pub = suivi.lignes()
        titre.setText(f"Amis ({len(lignes)}) - derniere version publiee : {ver_pub or 'inconnue'}")
        if quota_relais():
            bandeau.setText("ATTENTION : le relais de signaux a refuse des messages (HTTP 429, quota atteint). Certains amis "
                            "n'ont peut-etre pas recu tous les signaux.")
            bandeau.setStyleSheet("color:#ff6b6b;font-weight:bold")
        else:
            bandeau.setText("")
        garde = t.currentRow()
        t.setRowCount(len(lignes))
        for r, l in enumerate(lignes):
            textes = [l["ami"], l["statut"], l["vu"], l["version"] + ("  (a jour)" if l["a_jour"] else "  (ANCIENNE)" if l["a_jour"] is False else ""),
                      l["compte"], l["bot"], l["signal"], "\n".join(x for _, x in l["alertes"]) or "-"]
            niveaux = [n for n, _ in l["alertes"]]
            pire = "rouge" if "rouge" in niveaux else "orange" if "orange" in niveaux else None
            for c, s in enumerate(textes):
                it = QTableWidgetItem(s)
                if c == 1:
                    it.setForeground(QColor(COULEURS["vert"] if s == "en ligne" else COULEURS["gris"]))
                if c == 4 and s == "REEL":
                    it.setForeground(QColor(COULEURS["rouge"]))
                if c == 7 and pire:
                    it.setForeground(QColor(COULEURS[pire]))
                if not l["actif"]:
                    it.setForeground(QColor(COULEURS["gris"]))
                t.setItem(r, c, it)
            t.resizeRowToContents(r)
        if 0 <= garde < t.rowCount():
            t.selectRow(garde)
        try:
            suivi.republier()
        except Exception:  # noqa: BLE001
            pass
        inc = suivi.lignes_inconnus()
        titre2.setText(f"Nouvelles installations a nommer ({len(inc)})" if inc else
                       "Nouvelles installations : aucune (une installation qui n'a pas encore son identifiant apparait ici)")
        g2 = t2.currentRow()
        t2.setRowCount(len(inc))
        for r, x in enumerate(inc):
            rem = "DEUX CLES POUR CE NUMERO : usurpation possible, refuse" if x["conflit"] else ("en ligne" if x["en_ligne"] else "hors ligne")
            for c, s in enumerate([x["iid"][:8], x["pc"], x["user"], x["version"], x["compte"], x["vu"], rem]):
                it = QTableWidgetItem(s)
                if x["conflit"] and c == 6:
                    it.setForeground(QColor(COULEURS["rouge"]))
                t2.setItem(r, c, it)
        if 0 <= g2 < t2.rowCount():
            t2.selectRow(g2)
        inconnus_actuels[:] = inc
        msg.setText(time.strftime("Mis a jour a %H:%M:%S - un signe de vie arrive toutes les 10 minutes"))

    inconnus_actuels = []

    def nommer():
        r = t2.currentRow()
        if r < 0 or r >= len(inconnus_actuels):
            msg.setText("Selectionne d'abord une installation dans la liste du bas.")
            return
        x = inconnus_actuels[r]
        nom, ok = QInputDialog.getText(w, "Nommer", f"Qui est-ce ? (PC {x['pc']}, session {x['user']})\nPseudo (lettres, chiffres, - et _) :")
        nom = (nom or "").strip()
        if not ok or not nom:
            return
        try:
            suivi.nommer(x["iid"], nom)
            msg.setText(f"{nom} cree : son identifiant lui est envoye. Il s'installe tout seul chez lui (quelques minutes, "
                        f"puis redemarrage du bot quand le marche est ferme).")
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            msg.setText(f"Impossible : {exc}")
        rafraichir()

    def changer(actif):
        r = t.currentRow()
        if r < 0:
            msg.setText("Selectionne d'abord un ami dans la liste.")
            return
        nom = t.item(r, 0).text()
        if not actif and QMessageBox.question(w, "Retirer", f"Retirer {nom} ? Il ne recevra plus aucun signal.") != QMessageBox.Yes:
            return
        try:
            d = json.loads(FICHIER_AMIS.read_text(encoding="utf-8"))
            d["amis"][nom]["actif"] = actif
            tmp = FICHIER_AMIS.with_name(FICHIER_AMIS.name + ".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, FICHIER_AMIS)
            msg.setText(f"{nom} " + ("remis." if actif else "retire : effet au prochain signal."))
        except (OSError, ValueError, KeyError) as exc:
            msg.setText(f"Impossible de modifier amis.json : {exc}")
        rafraichir()

    def actualiser():
        suivi.actualiser()
        msg.setText("Relecture du relais en cours...")
        QTimer.singleShot(3000, lambda: (rafraichir(), msg.setText(time.strftime("Actualise a %H:%M:%S : relais relu (12 h d'historique)"))))

    b_actualiser.clicked.connect(actualiser)
    b_nommer.clicked.connect(nommer)
    b_retirer.clicked.connect(lambda: changer(False))
    b_remettre.clicked.connect(lambda: changer(True))
    minuteur = QTimer(w)
    minuteur.timeout.connect(rafraichir)
    minuteur.start(5000)
    rafraichir()
    w.show()
    if "--capture" in sys.argv:                      # test : image puis sortie
        QTimer.singleShot(1800, rafraichir)
        QTimer.singleShot(2300, lambda: (w.grab().save(sys.argv[sys.argv.index("--capture") + 1]), app.quit()))
    code = app.exec()
    suivi.arreter()
    return code


def main(argv):
    if "--texte" in argv:
        s = Suivi()
        s.demarrer()
        time.sleep(6)                                  # le temps de relire le cache du relais (12 h)
        lignes, ver_pub = s.lignes()
        print(texte(lignes, ver_pub))
        for x in s.lignes_inconnus():
            print(f"[A NOMMER] {x['iid'][:8]}  PC {x['pc']}  session {x['user']}  v{x['version']}  {x['compte']}  vu {x['vu']}"
                  + ("  CONFLIT DE CLES" if x["conflit"] else ""))
        s.arreter()
        return 0
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("PySide6 absent : lance avec  --texte  ou depuis le python du .venv de GIMALY.")
        return 1
    return fenetre()


if __name__ == "__main__":
    code = main(sys.argv[1:])
    try:
        sys.stdout.flush()                              # pythonw : pas de console (stdout vaut None)
    except Exception:  # noqa: BLE001
        pass
    os._exit(code)                                     # les fils d'ecoute ne retiennent pas la fermeture
