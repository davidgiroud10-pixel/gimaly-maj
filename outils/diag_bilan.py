# -*- coding: utf-8 -*-
"""Rejoue le bilan d'un canal etape par etape a partir du cache local (lecture seule).
Usage (dossier gimaly) :  $env:PYTHONIOENCODING="utf-8"; .\\.venv\\Scripts\\python.exe diag_bilan.py amely 2>$null"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    canal = sys.argv[1] if len(sys.argv) > 1 else "amely"
    from gimaly.config import Config
    from gimaly.bridges import telegram_lecture as tl
    from gimaly.skills import signals_skill as ss
    from gimaly.skills.signals_store import Historique
    config = Config.load()
    h = Historique(config.data_dir)
    msgs = h.messages(canal, datetime(2026, 11, 1, tzinfo=timezone.utc), None)
    _, valeur = tl.resoudre_alias(getattr(config, "signal_channels", None) or {}, canal)
    sujet = int(str(valeur).split("#", 1)[1])
    fils = tl.assembler_fils(msgs, sujet, False)
    print(f"{len(fils)} fil(s)")
    trades = []
    for f in fils:
        t = ss.parser_signal(f[0])
        if t is None:
            print("  NON LU :", repr(f[0][:60]))
            continue
        for r in f[1]:
            ss.appliquer_reponse(t, r)
        t.reponses = list(f[1]); t.date = f[2]; t.message_id = f[3]
        trades.append(t)
        print(f"  {f[2]:%d/%m %H:%M} {t.sens} {t.entree}->SL {t.stop} TP {t.objectifs} | touches={t.touches} stoppe={t.stoppe} eq={t.equilibre} "
              f"fermeAPlat={t.ferme_a_plat} r_annonce={t.r_annonce} | {len(f[1])} rep.")
        try:
            print("     =>", {k: v for k, v in t.resultat().items() if k in ("statut", "r", "pips", "pourcentage")})
        except Exception as exc:
            print("     => resultat() en erreur :", repr(exc))
        if "--rep" in sys.argv:
            for r in f[1]:
                print("       >", repr(r))
    print(f"{len(trades)} trade(s) lus")
    try:
        st = ss.statistiques(trades)
        print("statistiques :", st)
    except Exception as exc:
        import traceback; traceback.print_exc()
        print("statistiques en erreur :", repr(exc))


if __name__ == "__main__":
    main()
