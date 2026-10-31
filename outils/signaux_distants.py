# -*- coding: utf-8 -*-
"""Transport des signaux entre le bot de Dav (editeur) et les bots des amis (recepteurs).

Principe : chaque signal accepte par le bot de Dav est publie sur un canal prive gratuit (relais ntfy),
SIGNE avec un secret partage (HMAC-SHA256). Le bot d'un ami ne prend en compte que les messages dont
la signature est valide, qui ne sont pas trop vieux et qu'il n'a pas deja traites. Sans la signature,
quelqu'un qui devinerait le nom du canal ne pourrait pas envoyer un faux signal.

Aucun prix absolu dans un signal : la DISTANCE du stop (et celle de l'entree de reference) suffit,
chaque bot applique ces distances a son propre prix.

Deux niveaux de signature, cote a cote dans la meme enveloppe :
  * "s" : HMAC-SHA256 avec le secret partage (versions v6 : tout detenteur du secret pourrait falsifier) ;
  * "e" : Ed25519 avec la cle privee de l'editeur (versions v7 : les amis ne gardent que la cle PUBLIQUE,
          qui permet de verifier mais jamais de signer). Si un fichier `cle_publique.txt` est present a cote
          de ce module, le recepteur EXIGE la signature "e" et ignore le secret partage.

Module sans dependance (bibliotheque standard seulement ; sig25519.py est fourni avec).
"""
import hashlib
import hmac
import json
import os
import queue
import threading
import time
import urllib.request
import uuid
from pathlib import Path

try:
    from gimaly.trading import sig25519
except ImportError:                      # utilisation hors paquet (tests)
    import sig25519

RELAIS = "https://ntfy.sh"
AGE_MAX = 90                 # secondes : un signal plus vieux est ignore (comme AGE_MAX_SIGNAL du bot)
TAILLE_MAX = 3800            # octets : limite d'un message ntfy (4096) avec une marge
CLES_CONTEXTE_MIN = ("tp_r", "duree_max_min", "sl_max_pips", "tendance_h1", "retour_n")
AGENT = {"User-Agent": "gimaly-signaux/2"}


# ---------------------------------------------------------------- amis (un canal PERSONNEL par ami)
FICHIER_AMIS = Path(os.environ.get("GIMALY_AMIS") or (Path.home() / "GIMALY" / "trading" / "amis.json"))


def empreinte(canal):
    """Identifiant court d'un canal (8 caracteres), ajoute a chaque signal envoye a un ami : un signal pris sur
    le canal d'un ami n'est pas accepte par le bot d'un autre."""
    return hashlib.sha256(("gimaly-ami:" + str(canal)).encode("utf-8")).hexdigest()[:8]


def lire_amis():
    """Editeur : ({nom: {"canal", "secret"}} des amis ACTIFS, ancien_canal_actif). Fichier absent : ({}, True)."""
    try:
        d = json.loads(FICHIER_AMIS.read_text(encoding="utf-8"))
        amis = {n: a for n, a in (d.get("amis") or {}).items()
                if isinstance(a, dict) and a.get("actif", True) and a.get("canal") and a.get("secret")}
        return amis, bool(d.get("ancien_canal", True))
    except (OSError, ValueError, AttributeError):
        return {}, True


# ---------------------------------------------------------------- cles (Ed25519)
def _fichier_cle_privee():
    """Cle privee de l'editeur : uniquement sur son PC (jamais dans un paquet distribue)."""
    return Path(os.environ.get("GIMALY_CLE_SIGNATURE") or (Path.home() / "GIMALY" / "trading" / "cle_signature.priv"))


def _lire_cle_privee():
    try:
        txt = _fichier_cle_privee().read_text(encoding="utf-8").strip()
        graine = bytes.fromhex(txt)
        return graine if len(graine) == 32 else None
    except Exception:  # noqa: BLE001 - pas de cle : on publie sans signature "e"
        return None


def cle_publique_installee():
    """Cle publique (hex) distribuee avec le paquet, ou None si absente (mode v6 : secret partage)."""
    try:
        txt = (Path(__file__).with_name("cle_publique.txt")).read_text(encoding="utf-8-sig").strip()
        return txt if len(bytes.fromhex(txt)) == 32 else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- signature
def _canon(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def signer(payload, secret):
    return hmac.new(secret.encode("utf-8"), _canon(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def emballer(payload, secret):
    """Texte a publier : {"p": signal, "s": signature}. Reduit le contexte si le message est trop gros."""
    payload = dict(payload)
    payload.setdefault("id", uuid.uuid4().hex)
    payload.setdefault("t", round(time.time(), 3))

    graine = _lire_cle_privee()

    def texte(p):
        env = {"p": p, "s": signer(p, secret)}
        if graine:
            env["e"] = sig25519.signer(graine, _canon(p).encode("utf-8")).hex()
        return json.dumps(env, separators=(",", ":"), ensure_ascii=False)

    msg = texte(payload)
    if len(msg.encode("utf-8")) > TAILLE_MAX:
        ctx = payload.get("contexte") or {}
        payload["contexte"] = {k: ctx[k] for k in CLES_CONTEXTE_MIN if k in ctx}
        msg = texte(payload)
    return msg


def ouvrir_message(texte, secret, cle_pub=None):
    """Renvoie le signal si la signature est valide, sinon None.
    Avec `cle_pub` (hex) : signature Ed25519 "e" exigee (le secret partage ne compte plus)."""
    try:
        enveloppe = json.loads(texte)
        payload = enveloppe["p"]
        if not isinstance(payload, dict):
            return None
        if cle_pub:
            sig = enveloppe.get("e")
            if not isinstance(sig, str):
                return None
            if not sig25519.verifier_hex(cle_pub, _canon(payload).encode("utf-8"), sig):
                return None
            return payload
        sig = enveloppe["s"]
        if not isinstance(sig, str):
            return None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not hmac.compare_digest(signer(payload, secret), sig):
        return None
    return payload


# ---------------------------------------------------------------- editeur
def publier(payload, canal, secret, relais=RELAIS, timeout=6):
    """Publie un signal. Renvoie (ok, message). Ne leve jamais d'exception : le bot ne doit pas en patir."""
    try:
        corps = emballer(payload, secret).encode("utf-8")
        req = urllib.request.Request(f"{relais}/{canal}", data=corps, headers=AGENT, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (200 <= r.status < 300), f"relais HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"publication impossible : {exc!r}"


def publier_en_fond(payload, canal, secret, relais=RELAIS, journal=print):
    """Publie sans bloquer la boucle du bot : sur le canal commun (tant qu'il est actif) et sur le canal
    PERSONNEL de chaque ami actif (amis.json), chacun avec son empreinte. Un ami retire n'est plus servi."""
    amis, ancien = lire_amis()

    def envoyer(nom, p, c, sec):
        ok, msg = publier(p, c, sec, relais)
        if not ok:
            journal(f"[signaux] {nom} : {msg}")

    if ancien or not amis:
        threading.Thread(target=envoyer, args=("canal commun", payload, canal, secret),
                         daemon=True, name="gimaly-publier").start()
    for nom, a in amis.items():
        threading.Thread(target=envoyer, args=(f"ami {nom}", dict(payload, d=empreinte(a["canal"])), a["canal"], a["secret"]),
                         daemon=True, name="gimaly-publier").start()


# ---------------------------------------------------------------- recepteur
class Recepteur:
    """Lit le canal en flux continu (reconnexion automatique) et range les signaux valides dans une file."""

    def __init__(self, canal, secret, relais=RELAIS, age_max=AGE_MAX, journal=print, cle_pub="auto"):
        self.canal, self.secret, self.relais = canal, secret, relais
        self.cle_pub = cle_publique_installee() if cle_pub == "auto" else cle_pub
        self.age_max, self.journal = age_max, journal
        self.file = queue.Queue()
        self._vus = {}
        self._dernier_id = None
        self._stop = threading.Event()
        self._thread = None
        self.derniere_activite = 0.0
        self.rejetes = 0

    # --- cycle de vie
    def demarrer(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._boucle, daemon=True, name="gimaly-recepteur")
        self._thread.start()

    def arreter(self):
        self._stop.set()

    def en_ligne(self):
        return time.time() - self.derniere_activite < 120

    def recuperer(self):
        """Tous les signaux valides arrives depuis le dernier appel (liste, eventuellement vide)."""
        sortie = []
        while True:
            try:
                sortie.append(self.file.get_nowait())
            except queue.Empty:
                return sortie

    # --- interne
    def _boucle(self):
        attente = 2
        while not self._stop.is_set():
            try:
                depuis = self._dernier_id or f"{int(self.age_max)}s"
                req = urllib.request.Request(f"{self.relais}/{self.canal}/json?since={depuis}", headers=AGENT)
                with urllib.request.urlopen(req, timeout=100) as r:
                    attente = 2
                    for brut in r:
                        if self._stop.is_set():
                            break
                        self._ligne(brut)
            except Exception as exc:  # noqa: BLE001 - toute coupure : on se reconnecte
                if not self._stop.is_set():
                    self.journal(f"[signaux] flux interrompu ({exc!r}), nouvel essai dans {attente} s")
            if self._stop.wait(attente):
                break
            attente = min(attente * 2, 60)

    def _ligne(self, brut):
        self.derniere_activite = time.time()
        try:
            ev = json.loads(brut.decode("utf-8"))
        except ValueError:
            return
        if ev.get("id"):
            self._dernier_id = ev["id"]
        if ev.get("event") != "message":
            return
        payload = ouvrir_message(ev.get("message", ""), self.secret, self.cle_pub)
        if payload is None:
            self.rejetes += 1
            self.journal("[signaux] message rejete (signature invalide)")
            return
        d = payload.get("d")
        if d is not None and d != empreinte(self.canal):
            self.rejetes += 1
            self.journal("[signaux] message destine a un autre canal : ignore")
            return
        age = time.time() - float(ev.get("time") or 0)     # horloge du relais : pas celle de l'editeur
        if age > self.age_max or age < -120:
            return                                          # trop vieux (ou horloge locale tres decalee)
        sid = payload.get("id")
        if not sid or sid in self._vus:
            return
        self._vus[sid] = time.time()
        for k in [k for k, t in self._vus.items() if time.time() - t > 3600]:
            del self._vus[k]
        self.file.put(payload)
