# -*- coding: utf-8 -*-
"""SIGNE DE VIE du bot vers l'editeur (toutes les 10 minutes), pour que l'editeur sache qui est connecte, qui est
a jour, et si une installation sort du cadre prevu (compte reel, fichiers modifies, identifiant partage).

Ce que contient le message (et RIEN d'autre) :
  - ton pseudo, la version du programme, l'etat du bot (actif / pause / arrete) ;
  - demo ou reel (le programme refuse le reel : l'editeur le sait simplement) ;
  - une empreinte courte de quelques fichiers du programme (pour voir s'ils ont ete modifies) ;
  - un numero d'installation (aleatoire, propre a ce PC) et une cle publique (pour recevoir ton identifiant) ;
  - le nom de ton PC et de ta session Windows, CHIFFRES : seul l'editeur peut les lire ;
  - la date du dernier signal recu.
JAMAIS : ton numero de compte, ton solde, tes trades, tes mots de passe.
Le message est signe avec ton identifiant (personne d'autre ne peut parler a ta place) et part sur un canal
« retour » qui t'est propre (calcule a partir de ton identifiant). Sans identifiant installe, rien n'est envoye.
"""
import hashlib
import hmac
import json
import re
import threading
import time
import urllib.request
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DOSSIER = Path.home() / "GIMALY" / "trading"
RELAIS = "https://ntfy.sh"
AGENT = {"User-Agent": "gimaly-retour/1"}
PERIODE = 600                       # secondes entre deux signes de vie
FICHIERS_SUIVIS = ("gimaly/trading/trading.py", "gimaly/trading/signaux_distants.py", "gimaly/trading/icebergs.py",
                   "gimaly/trading/symbole.py", "gimaly/trading/mt5_isole.py", "lancer.py", "maj_auto.py", "retour.py")
_derniere_erreur = {"texte": ""}


def lire_config(racine=None):
    """trading_ami (facultatif) et trading_signaux_secret lus dans config.local.yaml."""
    try:
        texte = ((racine or RACINE) / "config.local.yaml").read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    valeurs = {}
    for cle in ("trading_ami", "trading_signaux_secret"):
        m = re.search(r"(?m)^%s:[ \t]*\"?([^\s\"#]+)\"?" % cle, texte)
        if m:
            valeurs[cle] = m.group(1)
    return valeurs


def canal_retour(secret):
    """Canal de retour d'un ami : calcule a partir de son secret (l'editeur et l'ami arrivent au meme nom, sans rien echanger)."""
    return "gimaly-r-" + hashlib.sha256(("retour|" + secret).encode("utf-8")).hexdigest()[:32]


def empreinte_fichier(chemin):
    try:
        brut = Path(chemin).read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return None
    return hashlib.sha256(brut).hexdigest()[:10]


def empreintes(racine=None):
    base = racine or RACINE
    return {nom: empreinte_fichier(base / nom) for nom in FICHIERS_SUIVIS}


def numero_installation():
    f = DOSSIER / "install_id.txt"
    try:
        v = f.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-f]{16}", v):
            return v
    except OSError:
        pass
    v = uuid.uuid4().hex[:16]
    try:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        f.write_text(v, encoding="utf-8")
    except OSError:
        pass
    return v


def version_installee(racine=None):
    try:
        d = json.loads(((racine or RACINE) / "VERSION.json").read_text(encoding="utf-8-sig"))
        return str(d.get("version", "?")), int(d.get("numero", 0))
    except (OSError, ValueError):
        return "?", 0


def dernier_signal():
    try:
        return float((DOSSIER / "dernier_signal.txt").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def canon(p):
    return json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def construire(etat, demo, config=None, racine=None):
    """Le message (dictionnaire) ; None si l'identifiant n'est pas installe."""
    c = config if config is not None else lire_config(racine)
    if not c.get("trading_signaux_secret"):
        return None
    version, numero = version_installee(racine)
    extra = {}
    try:
        import attribution
        extra = {"pk": attribution.pub_ami_hex(DOSSIER), "who": attribution.qui_suis_je(racine or RACINE)}
    except Exception:  # noqa: BLE001 - jamais bloquant
        pass
    return {**extra, "v": 1, "ami": c.get("trading_ami", "?"), "ver": version, "num": numero, "etat": etat,
            "compte": "demo" if demo is True else "reel" if demo is False else "inconnu",
            "iid": numero_installation(), "emp": empreintes(racine), "dernier": dernier_signal(),
            "t": round(time.time(), 3), "id": uuid.uuid4().hex}


def emballer(p, secret):
    return json.dumps({"p": p, "s": hmac.new(secret.encode("utf-8"), canon(p).encode("utf-8"), hashlib.sha256).hexdigest()},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ouvrir(texte, secret):
    """Editeur : le message si la signature est valide, sinon None."""
    try:
        e = json.loads(texte)
        p, s = e["p"], e["s"]
        if not isinstance(p, dict) or not isinstance(s, str):
            return None
    except (ValueError, KeyError, TypeError):
        return None
    attendu = hmac.new(secret.encode("utf-8"), canon(p).encode("utf-8"), hashlib.sha256).hexdigest()
    return p if hmac.compare_digest(attendu, s) else None


def envoyer(etat, demo, relais=RELAIS, racine=None, timeout=8):
    """Publie un signe de vie. Renvoie (ok, message). Ne leve jamais d'exception."""
    try:
        c = lire_config(racine)
        p = construire(etat, demo, c, racine)
        if p is None:
            return False, "identifiant non installe : rien envoye"
        corps = emballer(p, c["trading_signaux_secret"]).encode("utf-8")
        req = urllib.request.Request(f"{relais}/{canal_retour(c['trading_signaux_secret'])}", data=corps, headers=AGENT, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (200 <= r.status < 300), f"relais HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"signe de vie impossible : {exc!r}"


def chercher_attribution(journal=None, relais=None, racine=None):
    """L'editeur m'a-t-il envoye mon identifiant personnel ? Si oui il est installe (voir attribution.py)."""
    try:
        import attribution
        c = lire_config(racine)
        if c.get("trading_signaux_secret") and not attribution.lire_marqueur(DOSSIER):
            recu = attribution.recevoir(c["trading_signaux_secret"], numero_installation(), relais or RELAIS,
                                        racine or RACINE, DOSSIER)
            if recu and journal is not None:
                journal(recu)
            return recu
    except Exception:  # noqa: BLE001
        pass
    return None


def battement(etat, demo, journal=None):
    """Envoie en fond (ne bloque jamais le lanceur). Ne journalise qu'un changement d'erreur."""
    def travail():
        d = demo
        if callable(d):
            try:
                d = d()
            except Exception:  # noqa: BLE001
                d = None
        ok, msg = envoyer(etat, d)
        chercher_attribution(journal)
        if journal is not None and not ok and msg != _derniere_erreur["texte"]:
            journal(f"signe de vie : {msg}")
        _derniere_erreur["texte"] = "" if ok else msg
    threading.Thread(target=travail, daemon=True, name="gimaly-retour").start()
