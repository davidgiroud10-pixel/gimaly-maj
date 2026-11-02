# -*- coding: utf-8 -*-
"""Correctif des LOTS : le bot calculait la valeur d'un lot avec trade_tick_value / trade_tick_size. Sur certains serveurs
(MetaQuotes-Demo) ce chiffre est 10 fois trop faible : le bot posait des lots 10 fois trop gros (risque reel ~10 % au lieu
de 1 %). Desormais le bot demande a MetaTrader le gain REEL d'un lot pour 1 $ de mouvement (order_calc_profit) et ne garde
l'ancienne formule qu'en secours. Si les deux ne concordent pas, une ALERTE est ecrite dans trading.log.
Usage (dossier gimaly) :  .\\.venv\\Scripts\\python.exe patch_volume_reel.py   puis publier_maj.py.
Sauvegarde trading.py.avant_volume. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "def _valeur_par_dollar"

HELPER = '''_VALEUR_LOT = {"t": 0.0, "v": None, "alerte": False}


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
MODIFS = [
    ("class Bot:\n", HELPER + "class Bot:\n"),
    ("        valeur_point = info.trade_tick_value / max(info.trade_tick_size, 1e-9)   # par lot et par $\n",
     "        valeur_point = _valeur_par_dollar(mt5, info)   # par lot et par $ (valeur reelle demandee a MetaTrader)\n"),
    ("            valeur_point = info.trade_tick_value / max(info.trade_tick_size, 1e-9)\n            risque = float(trade[\"volume\"])",
     "            valeur_point = _valeur_par_dollar(self._mt5(), info)\n            risque = float(trade[\"volume\"])"),
]


def main():
    if not F.exists():
        raise SystemExit(f"{F} introuvable : lance ce script depuis le dossier gimaly")
    brut = F.read_bytes()
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), b"\r\n" in brut
    t = brut.decode("utf-8-sig").replace("\r\n", "\n")
    if MARQUE in t:
        print("trading.py : deja a jour")
        return 0
    for ancien, nouveau in MODIFS:
        if t.count(ancien) != 1:
            raise SystemExit(f"repere introuvable (une fois attendu) : RIEN ecrit. Envoie-moi trading.py.\n{ancien[:80]}")
        t = t.replace(ancien, nouveau, 1)
    compile(t, "trading.py", "exec")
    copie = F.with_name(F.name + ".avant_volume")
    if not copie.exists():
        shutil.copy2(F, copie)
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + (t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_volume). Prochaine etape : publier_maj.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
