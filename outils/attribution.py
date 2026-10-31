# -*- coding: utf-8 -*-
"""ATTRIBUTION AUTOMATIQUE de l'identifiant personnel : l'ami n'a rien a faire.

Principe (aucune dependance, bibliotheque standard seulement) :
  1. Le bot de l'ami fabrique une cle (cle_ami.txt, restee chez lui) et en envoie la partie publique avec son
     signe de vie. Il y joint aussi le nom de son PC et de sa session Windows, CHIFFRES pour l'editeur seul.
  2. L'editeur voit « nouvelle installation » dans sa fenetre, lui donne un pseudo (un clic).
  3. L'editeur lui envoie son identifiant personnel (canal + secret) CHIFFRE avec la cle publique de cet ami
     et SIGNE avec sa cle d'editeur : seul cet ami peut le lire (pas les autres amis), et nul ne peut en forger un.
  4. Le bot de l'ami le dechiffre, l'installe dans config.local.yaml, et redemarre son bot quand c'est sans
     danger (marche ferme ou aucune position ouverte).
Cryptographie : X25519 (RFC 7748) pour l'echange de cle, flux HMAC-SHA256 + MAC pour chiffrer, Ed25519
(sig25519.py) pour la signature de l'editeur.
"""
import hashlib
import hmac
import json
import os
import re
import time
import urllib.request
import uuid
from pathlib import Path

try:
    from gimaly.trading import sig25519      # paquet des amis et PC de l'editeur
except ImportError:  # pragma: no cover
    import sig25519  # type: ignore

RACINE = Path(__file__).resolve().parent
DOSSIER = Path(os.environ.get("GIMALY_DOSSIER") or (Path.home() / "GIMALY" / "trading"))
RELAIS = "https://ntfy.sh"
AGENT = {"User-Agent": "gimaly-attribution/1"}
_P = 2 ** 255 - 19
_A24 = 121665
BASE = (9).to_bytes(32, "little")
CANAL_OK = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
SECRET_OK = re.compile(r"^[0-9a-fA-F]{16,128}$")
NOM_OK = re.compile(r"^[A-Za-z0-9_\-]{1,30}$")


# ------------------------------------------------------------------ X25519 (RFC 7748)
def _echelle(k, u):
    x1, x2, z2, x3, z3, swap = u, 1, 0, u, 1, 0
    for t in range(254, -1, -1):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = kt
        a = (x2 + z2) % _P
        aa = a * a % _P
        b = (x2 - z2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x3 + z3) % _P
        d = (x3 - z3) % _P
        da = d * a % _P
        cb = c * b % _P
        x3 = (da + cb) ** 2 % _P
        z3 = x1 * ((da - cb) ** 2) % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    return x2 * pow(z2, _P - 2, _P) % _P


def _scalaire(k):
    if isinstance(k, int):
        return k
    b = bytearray(k)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return int.from_bytes(b, "little")


def x25519(k, u):
    """k : 32 octets (ou entier deja « clampe »), u : 32 octets. Renvoie 32 octets."""
    uu = int.from_bytes(u, "little") & ((1 << 255) - 1)
    return _echelle(_scalaire(k), uu).to_bytes(32, "little")


def ed_pub_vers_x(pub):
    """Cle publique Ed25519 (32 octets) -> cle publique X25519 correspondante."""
    y = int.from_bytes(pub, "little") & ((1 << 255) - 1)
    return ((1 + y) * pow((1 - y) % _P, _P - 2, _P) % _P).to_bytes(32, "little")


def ed_graine_vers_x(graine):
    """Graine privee Ed25519 de l'editeur -> scalaire X25519 (entier)."""
    h = bytearray(hashlib.sha512(graine).digest()[:32])
    return _scalaire(bytes(h))


# ------------------------------------------------------------------ chiffrement
def _flux(cle, n):
    sortie, i = b"", 0
    while len(sortie) < n:
        sortie += hmac.new(cle, b"k" + i.to_bytes(4, "big"), hashlib.sha256).digest()
        i += 1
    return sortie[:n]


def _cle(partage, e_pub):
    return hashlib.sha256(b"gimaly-seal|" + partage + e_pub).digest()


def sceller(pub_x, clair):
    """Chiffre `clair` (octets) pour le detenteur de la cle X25519 `pub_x`. Renvoie {"e","c","m"} (hex)."""
    esk = os.urandom(32)
    e_pub = x25519(esk, BASE)
    cle = _cle(x25519(esk, pub_x), e_pub)
    ct = bytes(a ^ b for a, b in zip(clair, _flux(cle, len(clair))))
    return {"e": e_pub.hex(), "c": ct.hex(), "m": hmac.new(cle, b"m" + ct, hashlib.sha256).hexdigest()}


def ouvrir_scelle(sk, boite):
    """Dechiffre une boite avec la cle privee `sk` (32 octets ou scalaire). Octets, ou None si invalide."""
    try:
        e_pub, ct, m = bytes.fromhex(boite["e"]), bytes.fromhex(boite["c"]), boite["m"]
        if len(e_pub) != 32:
            return None
        cle = _cle(x25519(sk, e_pub), e_pub)
        if not hmac.compare_digest(hmac.new(cle, b"m" + ct, hashlib.sha256).hexdigest(), m):
            return None
        return bytes(a ^ b for a, b in zip(ct, _flux(cle, len(ct))))
    except (KeyError, ValueError, TypeError):
        return None


def canon(p):
    return json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ------------------------------------------------------------------ cote ami
def cle_ami(dossier=None):
    """Cle privee de l'ami (32 octets), creee au premier besoin, gardee dans son dossier."""
    f = (dossier or DOSSIER) / "cle_ami.txt"
    try:
        v = bytes.fromhex(f.read_text(encoding="utf-8").strip())
        if len(v) == 32:
            return v
    except (OSError, ValueError):
        pass
    v = os.urandom(32)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(v.hex(), encoding="utf-8")
    except OSError:
        pass
    return v


def pub_ami_hex(dossier=None):
    return x25519(cle_ami(dossier), BASE).hex()


def cle_pub_editeur(racine=None):
    """Cle publique Ed25519 de l'editeur (fichier du paquet), en octets ; None si absente."""
    for chemin in ((racine or RACINE) / "gimaly" / "trading" / "cle_publique.txt", RACINE / "cle_publique.txt"):
        try:
            v = bytes.fromhex(chemin.read_text(encoding="utf-8-sig").strip())
            if len(v) == 32:
                return v
        except (OSError, ValueError):
            continue
    return None


def qui_suis_je(racine=None, dossier=None):
    """Boite chiffree pour l'editeur seul : nom du PC et de la session Windows (aide a nommer l'installation)."""
    import getpass
    import socket
    pub = cle_pub_editeur(racine)
    if pub is None:
        return None
    try:
        info = {"pc": socket.gethostname(), "user": getpass.getuser()}
    except Exception:  # noqa: BLE001
        return None
    return sceller(ed_pub_vers_x(pub), canon(info).encode("utf-8"))


def topic_attribution(secret_partage, iid):
    return "gimaly-a-" + hashlib.sha256(("attr|%s|%s" % (secret_partage, iid)).encode("utf-8")).hexdigest()[:32]


def lire_marqueur(dossier=None):
    try:
        return (( dossier or DOSSIER) / "attribution_ok.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def recevoir(secret_partage, iid, relais=RELAIS, racine=None, dossier=None, appliquer=None, timeout=10):
    """Cote ami : cherche une attribution qui m'est destinee, la verifie, l'installe.
    Renvoie une phrase pour le journal, ou None s'il n'y a rien de nouveau. Ne leve jamais d'exception."""
    dossier = dossier or DOSSIER
    try:
        pub = cle_pub_editeur(racine)
        if pub is None or not secret_partage:
            return None
        req = urllib.request.Request(f"{relais}/{topic_attribution(secret_partage, iid)}/json?poll=1&since=all", headers=AGENT)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            lignes = r.read().decode("utf-8", "replace").splitlines()
        deja = lire_marqueur(dossier)
        for brut in reversed(lignes):
            try:
                ev = json.loads(brut)
                if ev.get("event") != "message":
                    continue
                e = json.loads(ev["message"])
                p, sig = e["p"], e["e"]
                if p.get("t") != "attr" or p.get("iid") != iid or p.get("id") == deja:
                    continue
                if not sig25519.verifier_hex(pub.hex(), canon(p).encode("utf-8"), sig):
                    continue
                clair = ouvrir_scelle(cle_ami(dossier), p["box"])
                if clair is None:
                    continue
                v = json.loads(clair.decode("utf-8"))
                if not (CANAL_OK.match(v.get("canal", "")) and SECRET_OK.match(v.get("secret", "")) and NOM_OK.match(v.get("ami", ""))):
                    continue
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            (appliquer or _appliquer_par_defaut)({"trading_signaux_canal": v["canal"], "trading_signaux_secret": v["secret"],
                                                   "trading_ami": v["ami"]})
            dossier.mkdir(parents=True, exist_ok=True)
            (dossier / "attribution_ok.txt").write_text(p["id"], encoding="utf-8")
            (dossier / "redemarrage_bot.flag").write_text(str(time.time()), encoding="utf-8")
            return f"identifiant personnel recu et installe (ami {v['ami']}) : le bot redemarrera au bon moment"
    except Exception as exc:  # noqa: BLE001
        return f"attribution : erreur ignoree {exc!r}"
    return None


def _appliquer_par_defaut(valeurs):
    import identifiant
    identifiant.appliquer(valeurs)


# ------------------------------------------------------------------ cote editeur
def graine_editeur():
    f = Path(os.environ.get("GIMALY_CLE_SIGNATURE") or (Path.home() / "GIMALY" / "trading" / "cle_signature.priv"))
    try:
        g = bytes.fromhex(f.read_text(encoding="utf-8").strip())
        return g if len(g) == 32 else None
    except (OSError, ValueError):
        return None


def lire_qui(boite, graine=None):
    """{"pc","user"} si la boite est lisible par l'editeur, sinon None."""
    graine = graine or graine_editeur()
    if graine is None or not isinstance(boite, dict):
        return None
    clair = ouvrir_scelle(ed_graine_vers_x(graine), boite)
    try:
        d = json.loads(clair.decode("utf-8")) if clair else None
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


def fabriquer_attribution(secret_partage, iid, pub_ami_hex_, ami, nom, graine=None):
    """Le message signe a publier sur topic_attribution(...). ami = {"canal","secret"}."""
    graine = graine or graine_editeur()
    if graine is None:
        raise SystemExit("cle de signature introuvable (cle_signature.priv) : impossible de signer l'attribution")
    pub = bytes.fromhex(pub_ami_hex_)
    if len(pub) != 32:
        raise ValueError("cle publique de l'ami invalide")
    clair = canon({"canal": ami["canal"], "secret": ami["secret"], "ami": nom}).encode("utf-8")
    p = {"t": "attr", "iid": iid, "box": sceller(pub, clair), "id": uuid.uuid4().hex, "date": int(time.time())}
    return json.dumps({"p": p, "e": sig25519.signer_hex(graine.hex(), canon(p).encode("utf-8"))},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def publier_attribution(secret_partage, iid, message, relais=RELAIS, timeout=10):
    req = urllib.request.Request(f"{relais}/{topic_attribution(secret_partage, iid)}", data=message.encode("utf-8"),
                                 headers=AGENT, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return 200 <= r.status < 300
