# -*- coding: utf-8 -*-
"""Pourquoi « Aucun signal reconnu » pour un canal ? (lecture seule, rien n'est modifie)
Lit les derniers messages du canal/sujet DIRECTEMENT sur Telegram, puis pour chacun dit : ressemble a un signal ? lu par le parseur ?
Compare ensuite avec ce que contient le cache local de GIMALY. GIMALY doit etre FERME (la session Telegram est exclusive).
Usage (dossier gimaly) :  .\\.venv\\Scripts\\python.exe diag_canal.py amely"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main():
    canal = sys.argv[1] if len(sys.argv) > 1 else "amely"
    from gimaly.config import Config
    from gimaly.bridges import telegram_lecture as tl
    from gimaly.skills.signals_skill import parser_signal
    config = Config.load()
    _, valeur = tl.resoudre_alias(getattr(config, "signal_channels", None) or {}, canal)
    print(f"alias {canal!r} -> {valeur!r}")
    msgs = tl.moissonner(config, canal, 0, 80)
    print(f"{len(msgs)} message(s) lus sur Telegram dans ce sujet (80 max, plus recents d'abord)\n")
    ok = 0
    for m in sorted(msgs, key=lambda x: x["date"], reverse=True)[:40]:
        t = m["texte"] or ""
        r = tl.ressemble_a_un_signal(t)
        p = parser_signal(t) if r else None
        ok += bool(p)
        court = t.replace("\n", " | ")[:70]
        print(f"{m['date'][:16]} id{m['id']:>6} rep{str(m['reply_to']):>6}  ressemble={'oui' if r else 'non'}  parse={'OK' if p else '--'}  {court!r}")
    print(f"\n{ok} signal(s) reconnu(s) parmi les 40 derniers.")
    try:
        from gimaly.skills.signals_store import Historique
        h = Historique(config.data_dir)
        debut = datetime(2026, 11, 1, tzinfo=timezone.utc)
        base = h.messages(canal, debut, None)
        print(f"Cache local GIMALY depuis le 01/11 : {len(base)} message(s) ; borne de moisson : {h.borne_moisson(canal, 3)}")
    except Exception as exc:
        print(f"(cache local non lisible : {exc!r})")


if __name__ == "__main__":
    main()
