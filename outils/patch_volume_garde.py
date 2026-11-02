# -*- coding: utf-8 -*-
r"""Garde-fou des LOTS (suite de patch_volume_reel.py) : un stop a -10 R a montre qu'une reponse manquee de MetaTrader
faisait retomber le bot sur l'ancienne formule (valeur d'un lot 10 fois trop faible sur certains serveurs = lot 10 fois trop gros).
Desormais la valeur d'un lot vient de : 1. order_calc_profit ; 2. sa derniere valeur reussie ; 3. la taille du contrat
(si le profit est dans la devise du compte) ; on garde toujours la PLUS GRANDE (lots plus petits). L'ancienne formule ne sert
qu'en tout dernier recours, et n'est jamais memorisee. Une ALERTE est ecrite dans trading.log si elle diverge.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_volume_garde.py   puis redemarrer le bot / publier_maj.py.
Sauvegarde trading.py.avant_garde. Idempotent. Rien n'est ecrit si un repere manque (il faut d'abord patch_volume_reel.py)."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = '"exact": None'

ANCIEN = '''_VALEUR_LOT = {"t": 0.0, "v": None, "alerte": False}


def _valeur_par_dollar(mt5, info):
    """Gain (ou perte) d'UN lot pour 1 $ de mouvement de l'or, dans la devise du compte. On le demande a MetaTrader
    (order_calc_profit) car trade_tick_value / trade_tick_size est faux sur certains serveurs (10 fois trop faible sur
    MetaQuotes-Demo : lots 10 fois trop gros). Ancienne formule gardee en secours."""
    ancienne = info.trade_tick_value / max(info.trade_tick_size, 1e-9)
    if _VALEUR_LOT["v"] and time.time() - _VALEUR_LOT["t"] < 60:
        return _VALEUR_LOT["v"]
    exact = None
    try:
        tick = mt5.symbol_info_tick(SYMBOLE)
        prix = float(getattr(tick, "ask", 0) or getattr(tick, "bid", 0) or 0)
        if prix > 0:
            gain = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, SYMBOLE, 1.0, prix, prix + 1.0)
            if gain is not None and gain > 0:
                exact = float(gain)
    except Exception:  # noqa: BLE001
        exact = None
    valeur = exact or ancienne
    if exact and ancienne > 0 and abs(exact / ancienne - 1) > 0.05 and not _VALEUR_LOT["alerte"]:
        _VALEUR_LOT["alerte"] = True
        journal(f"ALERTE valeur d'un lot : MetaTrader donne {ancienne:.2f} (tick) mais le calcul reel donne {exact:.2f} "
                f"par $ : le calcul reel est utilise pour les lots")
    _VALEUR_LOT["t"], _VALEUR_LOT["v"] = time.time(), valeur
    return valeur


'''

NOUVEAU = '''_VALEUR_LOT = {"t": 0.0, "v": None, "exact": None, "alerte": ""}


def _valeur_par_dollar(mt5, info):
    """Gain (ou perte) d'UN lot pour 1 $ de mouvement de l'or, dans la devise du compte. Sources, de la plus sure a la
    moins sure : 1. order_calc_profit (MetaTrader calcule lui-meme) ; 2. la derniere valeur reussie de ce calcul ; 3. la
    taille du contrat (100 $ par lot pour 1 $ d'or) si le profit est dans la devise du compte. On garde la PLUS GRANDE
    (lots plus petits = plus prudent). trade_tick_value / trade_tick_size est FAUX sur certains serveurs (10 fois trop faible
    sur MetaQuotes-Demo : lots 10 fois trop gros, stop a -10 R) : on ne s'en sert JAMAIS. Sans valeur sure : None (pas de trade)."""
    if _VALEUR_LOT["v"] and time.time() - _VALEUR_LOT["t"] < 60:
        return _VALEUR_LOT["v"]
    tick_formule = info.trade_tick_value / max(info.trade_tick_size, 1e-9)
    exact = None
    try:
        tick = mt5.symbol_info_tick(SYMBOLE)
        prix = float(getattr(tick, "ask", 0) or getattr(tick, "bid", 0) or 0)
        if prix > 0:
            gain = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, SYMBOLE, 1.0, prix, prix + 1.0)
            if gain is not None and gain > 0:
                exact = float(gain)
                _VALEUR_LOT["exact"] = exact
    except Exception:  # noqa: BLE001
        exact = None
    if exact is None:
        exact = _VALEUR_LOT["exact"]                      # derniere valeur reussie
    contrat = None
    try:
        compte = mt5.account_info()
        if compte is not None and getattr(info, "currency_profit", None) == getattr(compte, "currency", None):
            contrat = float(info.trade_contract_size)
    except Exception:  # noqa: BLE001
        contrat = None
    sures = [v for v in (exact, contrat) if v and v > 0]
    if not sures:                                         # aucune valeur sure : PAS de trade (None), on reessaie au prochain
        message = "ALERTE valeur d'un lot introuvable (MetaTrader ne repond pas) : trade refuse par prudence"
        if _VALEUR_LOT["alerte"] != message:
            _VALEUR_LOT["alerte"] = message
            journal(message)
        return None
    valeur = max(sures)
    if tick_formule > 0 and abs(valeur / tick_formule - 1) > 0.05:
        message = (f"ALERTE valeur d'un lot : MetaTrader donne {tick_formule:.2f} (tick) mais la valeur sure est "
                   f"{valeur:.2f} par $ : la valeur sure est utilisee pour les lots")
        if _VALEUR_LOT["alerte"] != message:
            _VALEUR_LOT["alerte"] = message
            journal(message)
    _VALEUR_LOT["t"], _VALEUR_LOT["v"] = time.time(), valeur
    return valeur


'''

VOL_ANCIEN = "        valeur_point = _valeur_par_dollar(mt5, info)   # par lot et par $ (valeur reelle demandee a MetaTrader)\n"
VOL_NOUVEAU = VOL_ANCIEN + "        if not valeur_point:\n            return 0.0                                   # valeur d'un lot introuvable : pas de trade (voir ALERTE)\n"


def main():
    if not F.exists():
        raise SystemExit(f"{F} introuvable : lance ce script depuis le dossier gimaly")
    brut = F.read_bytes()
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), b"\r\n" in brut
    t = brut.decode("utf-8-sig").replace("\r\n", "\n")
    if MARQUE in t:
        print("trading.py : deja a jour")
        return 0
    if t.count(ANCIEN) != 1:
        raise SystemExit("repere introuvable : RIEN ecrit. Lance d'abord patch_volume_reel.py, ou envoie-moi trading.py.")
    if t.count(VOL_ANCIEN) != 1:
        raise SystemExit("volume() : repere introuvable : RIEN ecrit. Lance d'abord patch_volume_reel.py, ou envoie-moi trading.py.")
    t = t.replace(ANCIEN, NOUVEAU, 1).replace(VOL_ANCIEN, VOL_NOUVEAU, 1)
    compile(t, "trading.py", "exec")
    copie = F.with_name(F.name + ".avant_garde")
    if not copie.exists():
        shutil.copy2(F, copie)
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + (t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_garde). Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
