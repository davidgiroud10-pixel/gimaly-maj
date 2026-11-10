# -*- coding: utf-8 -*-
r"""Bilan du bot : « trop de stops » est-il un vrai changement ou la variation normale ? (lecture seule, rien n'est modifie)

Lit trades_bot.csv (trades termines, heure de ton PC) et montre :
  1. jour par jour : trades, objectifs, stops, autres sorties, R du jour, part de stops ;
  2. la periode recente (3 derniers jours par defaut) comparee a la periode de reference (depuis le 20/10, hors periode recente) :
     part de stops, R par trade, et la probabilite d'avoir AU MOINS autant de stops par hasard si le bot n'avait pas change (loi binomiale) ;
  3. les trades de la periode recente un par un (heure, sens, distance du stop, resultat, R, duree) et la plus longue serie de stops ;
  4. un rappel : avec un objectif a 1,5 R, ~40 % de reussite suffisent a l'equilibre, donc 50-55 % de stops est le fonctionnement normal.
Ne dit PAS si le bot est bon ou mauvais : sur quelques jours, une mauvaise passe est compatible avec le hasard.
Usage (dossier gimaly, a cote de diag_tp.py) :
  .\.venv\Scripts\python.exe bilan_bot.py                          3 derniers jours vs reference depuis le 20/10
  .\.venv\Scripts\python.exe bilan_bot.py --jours 1                 aujourd'hui seulement
  .\.venv\Scripts\python.exe bilan_bot.py --ref 23/09/2026 --genre tous"""
import datetime as dt
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import diag_tp
except ImportError:
    print("Place ce script a cote de diag_tp.py (dossier gimaly).")
    raise SystemExit(1)


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def classe(res):
    r = (res or "").lower()
    if "stop" in r and "point mort" not in r:
        return "stop"
    if "tp" in r or "objectif" in r:
        return "tp"
    return "autre"


def p_au_moins(k, n, p0):
    """P(X >= k) pour X ~ Binomiale(n, p0)."""
    return sum(math.comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1))


def lire(depuis, genre):
    out = []
    for tr in diag_tp.lire_trades():
        l = tr["ligne"]
        if tr["ouverture"] < depuis:
            continue
        if genre and (l.get("genre") or "").strip() != genre:
            continue
        pe, sl = nombre(l.get("pe")), nombre(l.get("sl"))
        out.append({"t0": tr["ouverture"], "t1": tr["fermeture"], "sens": (l.get("sens") or "").strip(),
                    "dist": abs(pe - sl) if pe is not None and sl is not None else None,
                    "classe": classe(l.get("resultat")), "res": (l.get("resultat") or "").strip(), "r": nombre(l.get("R"))})
    return sorted(out, key=lambda x: x["t0"])


def resume(lst):
    n = len(lst)
    s = sum(1 for x in lst if x["classe"] == "stop")
    t = sum(1 for x in lst if x["classe"] == "tp")
    rs = [x["r"] for x in lst if x["r"] is not None]
    return n, t, s, n - t - s, sum(rs), (statistics.fmean(rs) if rs else 0.0)


def main():
    args = sys.argv[1:]

    def option(nom, defaut):
        if nom in args:
            i = args.index(nom)
            val = args[i + 1]
            del args[i:i + 2]
            return val
        return defaut

    jours = int(option("--jours", "3"))
    ref = dt.datetime.strptime(option("--ref", "20/10/2026"), "%d/%m/%Y")
    genre = option("--genre", "scalp_keltner_large")
    genre = None if genre == "tous" else genre
    trades = lire(ref, genre)
    if not trades:
        sys.exit("aucun trade termine sur cette periode")
    dernier = max(x["t0"] for x in trades).date()
    debut_recent = dt.datetime.combine(dernier - dt.timedelta(days=jours - 1), dt.time())
    recent = [x for x in trades if x["t0"] >= debut_recent]
    ancien = [x for x in trades if x["t0"] < debut_recent]
    print(f"Bilan du bot ({genre or 'tous genres'}) | reference depuis le {ref:%d/%m/%Y} | periode recente : {jours} jour(s) jusqu'au {dernier:%d/%m/%Y}\n")
    print("1. JOUR PAR JOUR")
    print(f"   {'jour':<11}{'trades':>7}{'objectif':>9}{'stop':>6}{'autre':>6}{'% stop':>8}{'R du jour':>11}")
    par_jour = {}
    for x in trades:
        par_jour.setdefault(x["t0"].date(), []).append(x)
    for j in sorted(par_jour)[-14:]:
        n, t, s, a, rsum, _ = resume(par_jour[j])
        print(f"   {j:%d/%m %a}{'':<2}{n:>7}{t:>9}{s:>6}{a:>6}{100 * s / n:>7.0f}%{rsum:>+11.1f}")
    n0, t0, s0, a0, r0, m0 = resume(ancien)
    n1, t1, s1, a1, r1, m1 = resume(recent)
    print("\n2. PERIODE RECENTE COMPAREE A LA REFERENCE")
    print(f"   reference : {n0:>3} trades | {100 * s0 / max(n0, 1):.0f} % de stops | R par trade {m0:+.3f}")
    print(f"   recente   : {n1:>3} trades | {100 * s1 / max(n1, 1):.0f} % de stops | R par trade {m1:+.3f} | R total {r1:+.1f}")
    if n0 >= 30 and n1 >= 5:
        p0 = s0 / n0
        p = p_au_moins(s1, n1, p0)
        print(f"   Si le bot n'avait pas change ({100 * p0:.0f} % de stops), la probabilite d'avoir au moins {s1} stops sur {n1} trades est de {100 * p:.0f} %.")
        if p > 0.10:
            print("   -> c'est une variation COURANTE : une mauvaise passe de ce genre arrive regulierement, ce n'est pas la preuve d'un changement.")
        elif p > 0.05:
            print("   -> c'est un peu inhabituel (1 fois sur 10 a 20), a surveiller mais pas une preuve.")
        else:
            print("   -> c'est inhabituel (moins de 1 fois sur 20) : a regarder de pres (marche different ? changement recent du bot ?).")
    print("\n3. LES TRADES DE LA PERIODE RECENTE")
    print(f"   {'ouverture':<12}{'sens':<7}{'stop':>7} {'sortie':<17}{'R':>7}{'duree':>8}")
    serie = pire = 0
    for x in recent:
        duree = (x["t1"] - x["t0"]).total_seconds() / 60
        print(f"   {x['t0']:%d/%m %H:%M}  {x['sens']:<7}{(x['dist'] or 0):>6.2f}$ {x['res'][:16]:<17}{(x['r'] if x['r'] is not None else 0):>+7.2f}{duree:>6.0f} min")
        serie = serie + 1 if x["classe"] == "stop" else 0
        pire = max(pire, serie)
    print(f"   Plus longue serie de stops de suite sur la periode : {pire}")
    print("\n4. A GARDER EN TETE")
    print("   Objectif a 1,5 R : le bot est a l'equilibre avec ~40 % de trades gagnants, donc 50 a 60 % de stops est NORMAL. Le probleme n'est pas le nombre de stops")
    print("   mais le R par trade sur la duree. Quelques jours ne suffisent pas pour juger ; c'est le suivi sur des centaines de trades qui compte.")


if __name__ == "__main__":
    main()
