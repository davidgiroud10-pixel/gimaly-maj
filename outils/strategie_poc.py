# -*- coding: utf-8 -*-
"""STRATEGIES POC en SIMULATION : le bot note ce que chaque logique aurait fait, sans jamais passer d'ordre.

Le POC (point de controle) est le prix ou il s'est echange le plus de volume sur la session. Trois logiques d'entree
sont evaluees a chaque bougie M1 close :
  poc_retour  : le prix s'est eloigne du POC (hors zone de valeur) puis se retourne vers lui : on vise le POC.
  poc_rebond  : en tendance (prix du bon cote du VWAP), le prix revient toucher le POC et repart : objectif 2R.
  poc_cassure : le prix passe de l'autre cote du POC et y reste (3 clotures M1) : on suit la cassure, objectif 2R.
Chaque signal est suivi comme un « trade fantome » (meme logique que trades_refuses.csv : le stop d'abord si stop et
objectif tombent dans la meme bougie, sortie a la duree max) et son resultat est ecrit dans poc_resultats.csv.
La 4e idee (le POC comme filtre des trades icebergs) se mesure avec analyse_poc.py sur icebergs.csv.

Interrupteur : trading_poc_simulation: true dans config.local.yaml (absent = rien ne tourne). Jamais d'ordre.
"""
import csv
import json
import time
from datetime import datetime
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
FICHIER_NIVEAUX = DOSSIER / "icebergs_etat.json"
FICHIER_OUVERTS = DOSSIER / "poc_ouverts.json"
FICHIER_RESULTATS = DOSSIER / "poc_resultats.csv"
SYMBOLE = "XAUUSD"
MARGE_TP = 0.15
COLONNES = ["date", "heure", "logique", "sens", "pe", "sl", "tp", "r_objectif", "issue", "R", "minutes",
            "poc", "dist_poc", "cote_vwap", "motif"]

REGLAGES = dict(
    retour_dist_min=6.0,      # $ : eloignement minimal du POC pour tenter le retour
    retour_r_min=1.2,         # gain vers le POC au moins 1,2 fois le risque
    rebond_eloignement=3.0,   # $ : le prix doit etre venu d'au moins 3 $ du POC avant de le retoucher
    rebond_contact=0.3,       # $ : contact avec le POC
    rebond_r=2.0,
    cassure_clotures=3,       # clotures M1 consecutives de l'autre cote
    cassure_marge=0.3,        # $ au-dela du POC
    cassure_max=4.0,          # $ : on ne court pas apres une cassure deja loin
    cassure_r=2.0,
    sl_min=1.5, sl_max=7.0,   # $ : memes bornes que le bot (15 et 70 pips)
    duree_max_min=60,
    attente_min=15,           # minutes entre deux signaux de la meme logique et du meme sens
    max_ouverts=3,            # fantomes ouverts en meme temps par logique
)


# ------------------------------------------------------------------ logiques (fonctions pures, testables)
def _bornes_risque(achat, pe, sl, r):
    """Applique le stop minimum, refuse au-dela du maximum. Renvoie (sl, risque) ou None."""
    risque = abs(pe - sl)
    if risque < r["sl_min"]:
        sl, risque = (pe - r["sl_min"] if achat else pe + r["sl_min"]), r["sl_min"]
    if risque > r["sl_max"]:
        return None
    return round(sl, 2), risque


def _signal(logique, achat, pe, sl, tp, motif, r):
    bornes = _bornes_risque(achat, pe, sl, r)
    if bornes is None:
        return None
    sl, risque = bornes
    gain = (tp - pe) if achat else (pe - tp)
    if gain <= 0:
        return None
    return {"logique": logique, "achat": achat, "pe": round(pe, 2), "sl": sl, "tp": round(tp, 2),
            "r_objectif": round(gain / risque, 2), "motif": motif}


def logique_retour(niv, barres, bid, ask, r):
    poc, vah, val = niv.get("poc"), niv.get("vah"), niv.get("val")
    if poc is None or len(barres) < 6:
        return None
    dernier, avant = barres[-1], barres[-2]
    prix = (bid + ask) / 2
    dist = prix - poc
    if abs(dist) < r["retour_dist_min"]:
        return None
    dernieres = barres[-5:]
    if dist > 0:                                       # au-dessus : on vend le retour vers le POC
        if vah is not None and prix < vah:
            return None
        if not (dernier["close"] < dernier["open"] and dernier["close"] < avant["close"]):
            return None
        sl = max(b["high"] for b in dernieres) + 0.3
        s = _signal("poc_retour", False, bid, sl, poc + MARGE_TP, f"prix {dist:+.1f} $ du POC, retournement M1", r)
    else:
        if val is not None and prix > val:
            return None
        if not (dernier["close"] > dernier["open"] and dernier["close"] > avant["close"]):
            return None
        sl = min(b["low"] for b in dernieres) - 0.3
        s = _signal("poc_retour", True, ask, sl, poc - MARGE_TP, f"prix {dist:+.1f} $ du POC, retournement M1", r)
    return s if s and s["r_objectif"] >= r["retour_r_min"] else None


def logique_rebond(niv, barres, bid, ask, r):
    poc, vwap = niv.get("poc"), niv.get("vwap")
    if poc is None or vwap is None or len(barres) < 20:
        return None
    fermetures = [b["close"] for b in barres[-20:]]
    au_dessus = sum(1 for c in fermetures if c > vwap) / len(fermetures)
    recentes, avant = barres[-3:], barres[-18:-3]
    dernier = barres[-1]
    if au_dessus >= 0.7:                               # tendance haussiere : on achete le retour sur le POC
        if min(b["low"] for b in recentes) <= poc + r["rebond_contact"] and dernier["close"] > poc + 0.2 \
                and max(b["high"] for b in avant) >= poc + r["rebond_eloignement"]:
            sl = min(poc, min(b["low"] for b in recentes)) - 0.3
            risque = abs(ask - sl)
            s = _signal("poc_rebond", True, ask, sl, ask + r["rebond_r"] * max(risque, r["sl_min"]),
                        "tendance haussiere, retour sur le POC", r)
            return s
    elif au_dessus <= 0.3:                             # tendance baissiere : on vend
        if max(b["high"] for b in recentes) >= poc - r["rebond_contact"] and dernier["close"] < poc - 0.2 \
                and min(b["low"] for b in avant) <= poc - r["rebond_eloignement"]:
            sl = max(poc, max(b["high"] for b in recentes)) + 0.3
            risque = abs(bid - sl)
            return _signal("poc_rebond", False, bid, sl, bid - r["rebond_r"] * max(risque, r["sl_min"]),
                           "tendance baissiere, retour sur le POC", r)
    return None


def logique_cassure(niv, barres, bid, ask, r):
    poc = niv.get("poc")
    n = r["cassure_clotures"]
    if poc is None or len(barres) < n + 8:
        return None
    dernieres, avant = barres[-n:], barres[-(n + 7):-n]
    prix = (bid + ask) / 2
    if all(b["close"] > poc + r["cassure_marge"] for b in dernieres) and \
            sum(1 for b in avant if b["close"] < poc) >= 3 and prix - poc <= r["cassure_max"]:
        sl = poc - 0.8
        risque = abs(ask - sl)
        return _signal("poc_cassure", True, ask, sl, ask + r["cassure_r"] * max(risque, r["sl_min"]),
                       f"{n} clotures M1 au-dessus du POC", r)
    if all(b["close"] < poc - r["cassure_marge"] for b in dernieres) and \
            sum(1 for b in avant if b["close"] > poc) >= 3 and poc - prix <= r["cassure_max"]:
        sl = poc + 0.8
        risque = abs(bid - sl)
        return _signal("poc_cassure", False, bid, sl, bid - r["cassure_r"] * max(risque, r["sl_min"]),
                       f"{n} clotures M1 sous le POC", r)
    return None


LOGIQUES = (logique_retour, logique_rebond, logique_cassure)


def signaux(niveaux, barres, bid, ask, reglages=None):
    """Tous les signaux du moment (fonction pure)."""
    r = {**REGLAGES, **(reglages or {})}
    sortie = []
    for logique in LOGIQUES:
        s = logique(niveaux, barres, bid, ask, r)
        if s:
            sortie.append(s)
    return sortie


# ------------------------------------------------------------------ niveaux lus dans l'etat du detecteur
def lire_niveaux(chemin=None, maintenant=None):
    """{"poc","vah","val","vwap"} en prix XAUUSD, ou None si l'etat du detecteur est trop vieux."""
    try:
        etat = json.loads((chemin or FICHIER_NIVEAUX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (maintenant or time.time()) - etat.get("maj_ts", 0) > 120:
        return None
    noms = {"POC": "poc", "haut zone de valeur": "vah", "bas zone de valeur": "val", "VWAP": "vwap"}
    niv = {}
    for n in etat.get("niveaux_xau") or []:
        cle = noms.get(n.get("nom"))
        if cle:
            try:
                niv[cle] = float(n["prix"])
            except (KeyError, TypeError, ValueError):
                pass
    return niv if "poc" in niv else None


# ------------------------------------------------------------------ fantomes
def _charger(chemin=None):
    try:
        return json.loads((chemin or FICHIER_OUVERTS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _sauver(liste, chemin=None):
    chemin = chemin or FICHIER_OUVERTS
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(liste), encoding="utf-8")
    tmp.replace(chemin)


_DERNIER = {}      # (logique, sens) -> heure du dernier signal note (meme si le fantome est deja termine)


def ouvrir_fantomes(sigs, niv, maintenant, r=None, chemin=None):
    """Enregistre les nouveaux signaux (avec temps d'attente et plafond par logique). Renvoie le nombre ajoute."""
    r = {**REGLAGES, **(r or {})}
    ouverts = _charger(chemin)
    ajoutes = 0
    for s in sigs:
        meme = [f for f in ouverts if f["logique"] == s["logique"]]
        if len(meme) >= r["max_ouverts"]:
            continue
        cle = (s["logique"], s["achat"])
        if any(f["achat"] == s["achat"] and maintenant - f["t"] < r["attente_min"] * 60 for f in meme) \
                or maintenant - _DERNIER.get(cle, 0) < r["attente_min"] * 60:
            continue                                   # meme logique, meme sens : pas deux fois dans l'attente
        _DERNIER[cle] = maintenant
        vwap = niv.get("vwap")
        ouverts.append({**s, "t": maintenant, "expire": maintenant + r["duree_max_min"] * 60, "poc": niv["poc"],
                        "cote_vwap": "" if vwap is None else ("dessus" if s["pe"] > vwap else "dessous")})
        ajoutes += 1
    if ajoutes:
        _sauver(ouverts, chemin)
    return ajoutes


def rejouer(ouverts, barres, maintenant, prix_sortie, decalage=0):
    """Rejoue chaque fantome sur les bougies M1 depuis son entree. Renvoie (restants, termines[(f, issue, R)])."""
    restants, termines = [], []
    for f in ouverts:
        risque = abs(f["pe"] - f["sl"]) or 1e-9
        issue = r_val = None
        for b in barres:
            if int(b["time"]) - decalage + 60 <= f["t"]:
                continue
            haut, bas = float(b["high"]), float(b["low"])
            stop = bas <= f["sl"] if f["achat"] else haut >= f["sl"]
            objectif = haut >= f["tp"] if f["achat"] else bas <= f["tp"]
            if stop:                                   # stop d'abord si les deux tombent dans la meme bougie
                issue, r_val = "stop", -1.0
                break
            if objectif:
                issue, r_val = "objectif", f["r_objectif"]
                break
        if issue is None and maintenant >= f["expire"] and prix_sortie is not None:
            bid, ask = prix_sortie
            prix = bid if f["achat"] else ask
            issue = "duree max"
            r_val = round(((prix - f["pe"]) if f["achat"] else (f["pe"] - prix)) / risque, 2)
        if issue is None:
            restants.append(f)
        else:
            termines.append((f, issue, r_val))
    return restants, termines


def ecrire_resultats(termines, maintenant, chemin=None):
    chemin = chemin or FICHIER_RESULTATS
    nouveau = not chemin.exists()
    with open(chemin, "a", newline="", encoding="utf-8-sig") as sortie:
        w = csv.DictWriter(sortie, fieldnames=COLONNES, delimiter=";")
        if nouveau:
            w.writeheader()
        for f, issue, r_val in termines:
            debut = datetime.fromtimestamp(f["t"])
            milieu = f["pe"]
            w.writerow({"date": debut.strftime("%d/%m/%Y"), "heure": debut.strftime("%H:%M:%S"), "logique": f["logique"],
                        "sens": "achat" if f["achat"] else "vente", "pe": f["pe"], "sl": f["sl"], "tp": f["tp"],
                        "r_objectif": f["r_objectif"], "issue": issue, "R": r_val,
                        "minutes": round((maintenant - f["t"]) / 60), "poc": round(f["poc"], 2),
                        "dist_poc": round(milieu - f["poc"], 2), "cote_vwap": f.get("cote_vwap", ""), "motif": f["motif"]})


# ------------------------------------------------------------------ appel depuis la boucle du bot
_ETAT = {"t": 0.0, "derniere_barre": 0}


def actif():
    try:
        from gimaly.trading import trading
        return bool(trading._yaml_local().get("trading_poc_simulation"))
    except Exception:  # noqa: BLE001
        return False


def suivre(bot, maintenant=None):
    """Appelee a chaque tour du bot : evalue (une fois par bougie M1 close) et rejoue les fantomes ouverts.
    Aucune erreur ne doit remonter jusqu'au bot. Jamais d'ordre."""
    maintenant = maintenant or time.time()
    if maintenant - _ETAT["t"] < 20 or not actif():
        return
    _ETAT["t"] = maintenant
    mt5 = bot._mt5()
    decalage = bot._decalage_serveur()
    barres = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(maintenant - 5400 + decalage),
                                  datetime.fromtimestamp(maintenant + decalage + 120))
    if barres is None or len(barres) == 0:
        return
    liste = [{"time": int(b["time"]), "open": float(b["open"]), "high": float(b["high"]),
              "low": float(b["low"]), "close": float(b["close"])} for b in barres]
    fermees = [b for b in liste if b["time"] - decalage + 60 <= maintenant]
    tick = mt5.symbol_info_tick(SYMBOLE)
    if tick is None or not fermees:
        return
    ouverts = _charger()
    if ouverts:
        restants, termines = rejouer(ouverts, liste, maintenant, (tick.bid, tick.ask), decalage)
        if termines:
            _sauver(restants)
            ecrire_resultats(termines, maintenant)
            for f, issue, r_val in termines:
                from gimaly.trading.trading import journal
                journal(f"POC simulation {f['logique']} {'achat' if f['achat'] else 'vente'} : {issue}, {r_val:+.2f} R")
    if fermees[-1]["time"] == _ETAT["derniere_barre"]:
        return                                       # pas de nouvelle bougie close : rien a evaluer
    _ETAT["derniere_barre"] = fermees[-1]["time"]
    niv = lire_niveaux()
    if niv is None:
        return
    nouveaux = signaux(niv, fermees, tick.bid, tick.ask)
    if nouveaux and ouvrir_fantomes(nouveaux, niv, maintenant):
        from gimaly.trading.trading import journal
        journal("POC simulation : " + ", ".join(f"{s['logique']} {'achat' if s['achat'] else 'vente'} "
                                                f"PE {s['pe']} SL {s['sl']} TP {s['tp']}" for s in nouveaux))
