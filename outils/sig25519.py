# -*- coding: utf-8 -*-
"""Signature numerique Ed25519 (RFC 8032), sans aucune dependance : bibliotheque standard seulement.

Pourquoi : les signaux et les mises a jour envoyes aux amis doivent etre signes par une cle que SEUL
l'editeur possede. Les amis ne gardent que la cle publique : elle permet de verifier, jamais de signer.

Implementation de reference (RFC 8032, section 6) : lente (quelques ms par operation) mais suffisante
ici : une verification par signal ou par mise a jour. Testee contre les vecteurs officiels du RFC et
contre la bibliotheque `cryptography`.
"""
import hashlib
import os

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _sha512(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _P - 2, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)
_ZERO = (0, 1, 1, 0)


def _ajouter(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiplier(s, p):
    r = _ZERO
    while s > 0:
        if s & 1:
            r = _ajouter(r, p)
        p = _ajouter(p, p)
        s >>= 1
    return r


def _egal(p, q):
    if (p[0] * q[2] - q[0] * p[2]) % _P != 0:
        return False
    return (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _compresser(p):
    zi = _inv(p[2])
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompresser(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _secret_en_scalaire(graine):
    h = _sha512(graine)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _h(m):
    return int.from_bytes(_sha512(m), "little")


# ---------------------------------------------------------------- interface
def generer_graine():
    """32 octets aleatoires : c'est la CLE PRIVEE. A garder uniquement sur le PC de l'editeur."""
    return os.urandom(32)


def cle_publique(graine):
    a, _ = _secret_en_scalaire(graine)
    return _compresser(_multiplier(a, _G))


def signer(graine, message):
    a, prefixe = _secret_en_scalaire(graine)
    pub = _compresser(_multiplier(a, _G))
    r = _h(prefixe + message) % _Q
    grand_r = _compresser(_multiplier(r, _G))
    k = _h(grand_r + pub + message) % _Q
    s = (r + k * a) % _Q
    return grand_r + int.to_bytes(s, 32, "little")


def verifier(pub, message, signature):
    """True seulement si `signature` a ete produite par la cle privee associee a `pub`. Ne leve jamais."""
    try:
        if len(pub) != 32 or len(signature) != 64:
            return False
        a = _decompresser(pub)
        grand_r = _decompresser(signature[:32])
        if a is None or grand_r is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _Q:
            return False
        k = _h(signature[:32] + pub + message) % _Q
        return _egal(_multiplier(s, _G), _ajouter(grand_r, _multiplier(k, a)))
    except Exception:  # noqa: BLE001
        return False


# --- aides texte (hexadecimal) : ce que l'on stocke dans les fichiers et les messages
def signer_hex(graine_hex, message):
    return signer(bytes.fromhex(graine_hex), message).hex()


def verifier_hex(pub_hex, message, signature_hex):
    try:
        return verifier(bytes.fromhex(pub_hex.strip()), message, bytes.fromhex(signature_hex))
    except (ValueError, AttributeError):
        return False
