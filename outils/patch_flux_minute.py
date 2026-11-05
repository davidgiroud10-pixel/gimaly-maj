# -*- coding: utf-8 -*-
r"""Patch : le bot ENREGISTRE le flux d'ordres KMM chaque minute dans un fichier (flux_minute.csv). Aucun ordre, aucune decision du bot n'est touchee.

Pourquoi : KMM n'envoie aucun historique, donc le flux (CVD, delta, VWAP, profil de volume, murs, carnet) ne peut pas etre rejoue sur des annees. Seul
moyen de pouvoir un jour le tester serieusement : le noter minute par minute, des maintenant, y compris les minutes ou KMM ne repond pas (colonne
`flux_frais` = 0), pour savoir quand les donnees sont fiables. Le bot n'enregistrait jusqu'ici le flux qu'au moment d'un signal (et 60 % des trades
n'avaient aucun flux).

Fichier : ~\GIMALY\trading\flux_minute.csv (separateur « ; »), une ligne par minute, environ 0,25 Mo par jour. Colonnes : date_heure, ts, actif,
flux_frais, age_dernier_trade_s, prix_gc, ecart_gc_xau, session, cvd, delta_1min, delta_5min, pression_1min/5min/session, vwap, sigma,
position_sigma, poc, vah, val, volume, trades, desequilibre, mur_acheteur_prix/taille, mur_vendeur_prix/taille, et la derniere bougie M1 fermee
(min_t, min_o, min_h, min_l, min_c, min_vol, min_achat, min_vente, min_delta).

Ce que fait le patch :
  1. cree gimaly/trading/flux_minute.py (reecrit a chaque mise a jour du patch) ;
  2. dans gimaly/trading/icebergs.py, ajoute un appel entoure d'un try/except juste apres la sauvegarde chaque minute du flux (methode pouls) :
     si l'ecriture echoue (fichier ouvert dans Excel par exemple), le bot continue sans rien changer et le dit une seule fois dans la console.
Retour arriere : restaurer icebergs.py.avant_flux_minute (et supprimer flux_minute.py si tu veux). Idempotent. Rien n'est ecrit si un repere manque.
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_flux_minute.py   puis relancer le bot (voir la commande de relance habituelle)."""
import shutil
import sys
from pathlib import Path

DOSSIER = Path.cwd() / "gimaly" / "trading"
F_ICE = DOSSIER / "icebergs.py"
F_MOD = DOSSIER / "flux_minute.py"
MARQUE = "gimaly.trading.flux_minute"
ANCRE = ('            self.flux.sauvegarder(FICHIER_FLUX)\n'
         '        except OSError as e:\n'
         '            print(f"Sauvegarde du flux impossible : {e!r}")\n')
AJOUT = ('        try:                                    # journal minute par minute du flux (patch_flux_minute) : ne doit jamais gener le bot\n'
         '            from gimaly.trading.flux_minute import journaliser\n'
         '            journaliser(self.flux, self.det.mid, self.ecart, actif, t)\n'
         '        except Exception as e:\n'
         '            print(f"Journal du flux (minute) : {e!r}") if not getattr(self, "_flux_minute_dit", False) else None\n'
         '            self._flux_minute_dit = True\n')

MODULE = r'''# -*- coding: utf-8 -*-
"""gimaly/trading/flux_minute.py - journal du flux d'ordres KMM, une ligne par minute (genere par patch_flux_minute.py)."""
import csv
import math
import time
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "flux_minute.csv"
COLONNES = ["date_heure", "ts", "actif", "flux_frais", "age_dernier_trade_s", "prix_gc", "ecart_gc_xau", "session", "cvd", "delta_1min",
            "delta_5min", "pression_1min", "pression_5min", "pression_session", "vwap", "sigma", "position_sigma", "poc", "vah", "val",
            "volume", "trades", "desequilibre", "mur_acheteur_prix", "mur_acheteur_taille", "mur_vendeur_prix", "mur_vendeur_taille",
            "min_t", "min_o", "min_h", "min_l", "min_c", "min_vol", "min_achat", "min_vente", "min_delta"]
FRAIS_S = 120          # le flux est « frais » si la derniere transaction a moins de 2 minutes
_derniere_minute = [0]


def _n(x, d=3):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return ""
        return round(float(x), d)
    except (TypeError, ValueError):
        return ""


def journaliser(flux, prix_gc, ecart, actif, t=None):
    """Ajoute une ligne (au plus une par minute). Leve OSError si le fichier est verrouille : l'appelant l'avale."""
    t = t or time.time()
    minute = int(t // 60)
    if minute == _derniere_minute[0]:
        return
    _derniere_minute[0] = minute
    i = flux.instantane()
    dernier = getattr(flux, "_dernier_ts", 0.0) or 0.0
    age = t - dernier / 1000.0 if dernier else None
    frais = 1 if (actif and age is not None and 0 <= age <= FRAIS_S) else 0
    mur_a, mur_v = i.get("mur_acheteur") or (None, None), i.get("mur_vendeur") or (None, None)
    barre = {}
    cible = (minute - 1) * 60                                  # derniere bougie M1 fermee
    for b in reversed(list(getattr(flux, "bougies", []))[-6:]):
        if b.get("t") == cible:
            barre = b
            break
    ligne = {
        "date_heure": datetime.fromtimestamp(t).strftime("%d/%m/%Y %H:%M:%S"), "ts": int(t), "actif": 1 if actif else 0, "flux_frais": frais,
        "age_dernier_trade_s": _n(age, 0), "prix_gc": _n(prix_gc, 2), "ecart_gc_xau": _n(ecart, 2), "session": getattr(flux, "session", "") or "",
        "cvd": _n(i.get("cvd"), 1), "delta_1min": _n(i.get("delta_1min"), 1), "delta_5min": _n(i.get("delta_5min"), 1),
        "pression_1min": _n(i.get("pression_1min"), 1), "pression_5min": _n(i.get("pression_5min"), 1),
        "pression_session": _n(i.get("pression_session"), 1), "vwap": _n(i.get("vwap"), 2), "sigma": _n(i.get("sigma"), 3),
        "position_sigma": _n(i.get("position_sigma"), 2), "poc": _n(i.get("poc"), 1), "vah": _n(i.get("vah"), 1), "val": _n(i.get("val"), 1),
        "volume": _n(i.get("volume"), 0), "trades": i.get("trades", ""), "desequilibre": _n(i.get("desequilibre"), 1),
        "mur_acheteur_prix": _n(mur_a[0], 2), "mur_acheteur_taille": _n(mur_a[1], 0),
        "mur_vendeur_prix": _n(mur_v[0], 2), "mur_vendeur_taille": _n(mur_v[1], 0),
        "min_t": barre.get("t", ""), "min_o": _n(barre.get("o"), 2), "min_h": _n(barre.get("h"), 2), "min_l": _n(barre.get("l"), 2),
        "min_c": _n(barre.get("c"), 2), "min_vol": _n(barre.get("v"), 0), "min_achat": _n(barre.get("achat"), 0),
        "min_vente": _n(barre.get("vente"), 0), "min_delta": _n(barre.get("delta"), 1),
    }
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not FICHIER.exists() or FICHIER.stat().st_size == 0
    with open(FICHIER, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        if nouveau:
            w.writeheader()
        w.writerow(ligne)
'''


def main():
    if not F_ICE.exists():
        print(f"{F_ICE} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F_ICE.read_bytes()
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), brut.count(b"\r\n") > brut.count(b"\n") / 2
    compile(MODULE, str(F_MOD), "exec")
    a_jour = F_MOD.exists() and F_MOD.read_text(encoding="utf-8") == MODULE
    if MARQUE in txt:
        if not a_jour:
            shutil.copy2(F_MOD, F_MOD.with_name(F_MOD.name + ".avant_flux_minute")) if F_MOD.exists() else None
            F_MOD.write_text(MODULE, encoding="utf-8")
            print("flux_minute.py : mis a jour.")
        else:
            print("Deja installe (rien a faire).")
        return 0
    if txt.count(ANCRE) != 1:
        print("REPERE INTROUVABLE (ou en double) dans icebergs.py : rien n'est modifie. Envoie-moi gimaly\\trading\\icebergs.py.")
        return 2
    nouveau = txt.replace(ANCRE, ANCRE + AJOUT)
    try:
        compile(nouveau, str(F_ICE), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F_ICE, F_ICE.with_name(F_ICE.name + ".avant_flux_minute"))
    F_MOD.write_text(MODULE, encoding="utf-8")
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F_ICE.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("Installe : flux_minute.py cree, icebergs.py modifie (sauvegarde icebergs.py.avant_flux_minute).")
    print("Relance le bot (commande de relance habituelle). Le fichier ~\\GIMALY\\trading\\flux_minute.csv se remplit ensuite, une ligne par minute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
