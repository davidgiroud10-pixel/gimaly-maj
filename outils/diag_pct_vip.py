# -*- coding: utf-8 -*-
r"""Diagnostic (lecture seule) : signaux du canal dont le % est incoherent avec le R."""
import sqlite3, sys
from datetime import datetime
from pathlib import Path
canal = (sys.argv[1] if len(sys.argv) > 1 else "coin trader").lower()
b = sqlite3.connect(f"file:{Path.home() / 'GIMALY' / 'trades.db'}?mode=ro", uri=True)
b.row_factory = sqlite3.Row
rows = [dict(x) for x in b.execute("""SELECT t.message_id, t.date, t.sens, t.entree, t.stop, t.objectifs,
  COALESCE(c.statut,t.statut) statut, COALESCE(c.r,t.r) r, COALESCE(c.pourcentage,t.pourcentage) pct,
  COALESCE(c.annule,t.annule) annule FROM trades t LEFT JOIN corrections c ON c.canal=t.canal AND c.message_id=t.message_id
  WHERE t.canal=? ORDER BY t.date""", (canal,))]
ok = [x for x in rows if not x["annule"] and x["r"] is not None and x["pct"] is not None and x["statut"] not in ("en cours", "non déclenché", "clos sans chiffre")]
print(f"{len(ok)} signaux avec R et % ; % par R median :", end=" ")
rat = sorted(x["pct"] / x["r"] for x in ok if abs(x["r"]) > 0.3)
print(f"{rat[len(rat)//2]:.2f}")
print("\nLes 12 plus gros %, en valeur absolue :")
for x in sorted(ok, key=lambda x: -abs(x["pct"]))[:12]:
    print(f"  id {x['message_id']:>7} {x['date'][:16]} {x['sens']:<5} {x['statut']:<7} R {x['r']:+7.2f}  % {x['pct']:+8.2f}  entree {x['entree']} stop {x['stop']}")
print("\nSignaux dont le % est tres different du R (> 3 fois le median) :")
med = rat[len(rat)//2]
n = 0
for x in ok:
    if abs(x["r"]) > 0.3 and abs(x["pct"]) > 3 * abs(med) * abs(x["r"]):
        n += 1
        print(f"  id {x['message_id']:>7} {x['date'][:16]} R {x['r']:+7.2f}  % {x['pct']:+8.2f}")
print(f"{n} signaux concernes")
