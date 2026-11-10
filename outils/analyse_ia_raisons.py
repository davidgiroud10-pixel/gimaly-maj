# -*- coding: utf-8 -*-
r"""POURQUOI l'IA dit « eviter », et ces raisons predisent-elles la perte ? (lecture seule, rien n'est modifie)
Lit la colonne « raison » de ia_avis.csv (texte libre, tronque a 200 caracteres : l'extraction est donc partielle), la rapproche du resultat reel
du trade (comme analyse_ia.py) et compare le R moyen quand une raison est citee et quand elle ne l'est pas :
  - flux contre le trade (mots : « flux », « delta », « carnet », « gros ordres » + « contre »)
  - tendance H1 contre / contre-tendance / contre-courant
  - ratio gain/risque faible
  - donnees manquantes (« non renseign », « pas renseign »)
  - delta 5 min FORT contre le sens du trade (valeur extraite du texte, |delta| >= 200)
Si une raison est vraie, les trades concernes doivent perdre NETTEMENT plus que les autres. Avec moins de ~100 avis : aucune conclusion, juste un ordre de grandeur.
Usage (dossier gimaly) :  $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe analyse_ia_raisons.py"""
import csv
import random
import re
import statistics
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
import analyse_ia as ai

D = ai.D
RE_DELTA = re.compile(r"delta(?:\s*5\s*min(?:utes)?)?[^0-9]{0,25}?([+\-\u2212]?)\s?(\d{1,5})", re.I)


def appariement(avis, trades):
    out = []
    for a in avis:
        ta = ai.instant(a.get("date", ""), a.get("heure", ""))
        pe = ai.nombre(a.get("pe"))
        res = None
        for t in trades:
            if (t.get("resultat") or "").strip() in ("", "ouvert"):
                continue
            tt = ai.instant(t.get("date", ""), t.get("heure", ""))
            if ta and tt and -300 <= (tt - ta).total_seconds() <= 2 * 86400 and (t.get("genre") or "").strip() == a.get("genre", "").strip() \
                    and (t.get("sens") or "").strip() == a.get("sens", "").strip() and None not in (pe, ai.nombre(t.get("pe"))) \
                    and abs(ai.nombre(t.get("pe")) - pe) <= 0.5:
                res = ai.nombre(t.get("R"))
                break
        if res is not None:
            out.append((a, res))
    return out


def etiquettes(a):
    txt = (a.get("raison") or "").lower()
    sens = (a.get("sens") or "").strip()
    e = {}
    e["flux contre le trade"] = bool(re.search(r"(flux|delta|carnet|gros ordres)[^.]{0,80}contre|contre[^.]{0,30}(flux|vendeur|acheteur)|d[eé]s[eé]quilibre[^.]{0,30}(contraire|d[eé]favorable|oppos)", txt))
    e["tendance H1 contre / contre-tendance"] = bool(re.search(r"contre-?\s?tendance|contre-?\s?courant|tendance h1 (baissi|haussi)", txt))
    e["ratio gain/risque faible"] = bool(re.search(r"(ratio|gain/risque|risque/gain)[^.]{0,40}(faible|proche de 1|insuffisant)|ne couvre|[aà] peine sup", txt))
    e["donnees manquantes"] = bool(re.search(r"(non|pas) renseign", txt))
    m = RE_DELTA.search(txt)
    fort = None
    if m:
        v = int(m.group(2)) * (-1 if m.group(1) in ("-", "−") else 1)
        contre = (sens == "achat" and v < 0) or (sens == "vente" and v > 0)
        fort = contre and abs(v) >= 200
    e["delta 5 min fort contre (|delta|>=200)"] = fort
    return e


def ic(a, b, n=3000):
    random.seed(5)
    out = sorted(statistics.fmean(random.choices(a, k=len(a))) - statistics.fmean(random.choices(b, k=len(b))) for _ in range(n))
    return out[int(0.025 * n)], out[int(0.975 * n)]


def main():
    fa, ft = D / "ia_avis.csv", D / "trades_bot.csv"
    if not fa.exists() or not ft.exists():
        print("ia_avis.csv ou trades_bot.csv introuvable.")
        return 1
    with open(fa, newline="", encoding="utf-8-sig") as f:
        avis = list(csv.DictReader(f, delimiter=";"))
    with open(ft, newline="", encoding="utf-8-sig") as f:
        trades = list(csv.DictReader(f, delimiter=";"))
    paires = appariement(avis, trades)
    print(f"{len(avis)} avis, {len(paires)} rapproches d'un trade termine | R moyen de ces trades {statistics.fmean(r for _, r in paires):+.3f}\n")
    if len(paires) < 20:
        print("trop peu pour comparer.")
        return 0
    lab = [(etiquettes(a), r) for a, r in paires]
    print(f"{'raison citee':<42}{'cites':>6}{'R moy':>8}{'  autres':>8}{'R moy':>8}   difference [IC 95 %]")
    for nom in lab[0][0]:
        oui = [r for e, r in lab if e[nom] is True]
        non = [r for e, r in lab if e[nom] is False]
        if len(oui) < 8 or len(non) < 8:
            print(f"{nom:<42}{len(oui):>6}{'':>8}{len(non):>8}   trop peu pour comparer")
            continue
        lo, hi = ic(oui, non)
        print(f"{nom:<42}{len(oui):>6}{statistics.fmean(oui):>+8.2f}{len(non):>8}{statistics.fmean(non):>+8.2f}   {statistics.fmean(oui) - statistics.fmean(non):>+.2f} [{lo:+.2f} ; {hi:+.2f}]"
              + ("" if lo <= 0 <= hi else "  <- net"))
    print("\nLecture : si une raison PREDIT la perte, ses trades ont un R moyen nettement plus bas que les autres (difference negative, IC sans 0). Sinon l'IA")
    print("refuse pour des raisons qui ne se verifient pas : il faut changer sa consigne, pas lui faire confiance. Peu d'avis = ordre de grandeur seulement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
