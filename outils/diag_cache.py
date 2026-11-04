# -*- coding: utf-8 -*-
"""Que contient le cache local de GIMALY pour un canal, et que devient-il dans le bilan ? (lecture seule)
Usage (dossier gimaly) :  .\\.venv\\Scripts\\python.exe diag_cache.py amely"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main():
    canal = sys.argv[1] if len(sys.argv) > 1 else "amely"
    from gimaly.config import Config
    from gimaly.bridges import telegram_lecture as tl
    from gimaly.skills.signals_store import Historique
    config = Config.load()
    h = Historique(config.data_dir)
    debut = datetime(2026, 11, 1, tzinfo=timezone.utc)
    msgs = h.messages(canal, debut, None)
    print(f"{len(msgs)} message(s) en cache depuis le 01/11")
    if msgs:
        print("cles d'un message :", sorted(msgs[0].keys()))
        for m in msgs[:3]:
            print("  exemple :", {k: (str(v)[:50] if v is not None else None) for k, v in m.items()})
        ids = [m.get("id", m.get("message_id")) for m in msgs]
        print("ids : de", min(ids), "a", max(ids))
    _, valeur = tl.resoudre_alias(getattr(config, "signal_channels", None) or {}, canal)
    sujet = int(str(valeur).split("#", 1)[1]) if "#" in str(valeur) else None
    for weekend in (False, True):
        fils = tl.assembler_fils(msgs, sujet, weekend)
        print(f"assembler_fils (ignorer weekend={weekend}) : {len(fils)} fil(s)")
    print("signal_ignorer_weekend dans la config :", getattr(config, "signal_ignorer_weekend", None))
    print("signal_fenetre_fraiche :", getattr(config, "signal_fenetre_fraiche", None))
    try:
        from gimaly.skills.signals_skill import SignalsSkill
        s = SignalsSkill(config)
        d, j, lib = s.borne("mois")
        print("periode 'mois' :", d, "->", j, "|", lib)
        t = s._collecter(canal, 5, d, j)
        print(f"_collecter : {len(t)} trade(s) lus")
    except Exception as exc:
        print("SignalsSkill/_collecter :", repr(exc))


if __name__ == "__main__":
    main()
