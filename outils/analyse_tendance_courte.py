# -*- coding: utf-8 -*-
r"""La tendance COURT TERME (M1, M5, M15) au moment du signal change-t-elle le resultat ? (lecture seule, aucun ordre, rien n'est modifie)

Question posee : le bot se fait « avoir » par la tendance des grosses unites de temps (H1, H4). Si on regarde aussi ce que fait le prix sur
M1 / M5 / M15 juste avant le signal, est-ce que prendre le signal DANS le sens de la tendance courte (ou refuser celui qui va contre) donne un
meilleur resultat ? On rejoue les signaux scalp_keltner_large comme rejeu_keltner.py (memes regles, meme spread, sans les filtres du bot) et on
classe chaque signal selon la tendance de chaque unite de temps, lue UNIQUEMENT sur des bougies deja fermees avant le signal.

DEFINITIONS FIXEES D'AVANCE (ne pas les changer apres avoir vu le resultat) :
  * Tendance d'une unite de temps : HAUSSIERE si la derniere cloture est au-dessus de sa moyenne mobile exponentielle 20 ET que cette moyenne
    est plus haute qu'il y a 5 bougies ; BAISSIERE dans le cas inverse ; sinon MIXTE. (M1 : bougie precedant celle du signal ; M5, M15, H1 :
    derniere bougie entierement fermee.)
  * Pour un signal : « AVEC » si la tendance va dans le sens du trade (achat + haussiere, vente + baissiere), « CONTRE » si elle va a l'oppose,
    « MIXTE » sinon.
  * Score court terme = (nb d'unites M1, M5, M15 « AVEC ») - (nb « CONTRE »), de -3 a +3 ; « court terme AVEC » = score >= +2, « CONTRE » = <= -2.
  * Le « piege » du bot : signal AVEC la tendance H1 (ce que le bot accepte) mais court terme CONTRE.
SIX TESTS, tous ecart « AVEC - CONTRE » en R par trade : M1, M5, M15, H1, score court terme, et le piege (H1 AVEC : court terme AVEC - CONTRE).
Seuil de rigueur : p < 0,0083 (0,05 / 6). Intervalle et p par bootstrap sur les JOURS (les trades d'un meme jour se ressemblent). Un ecart n'est
credible que si le seuil est passe, que les deux moities de la periode vont dans le meme sens et qu'il y a assez de jours.
Un test n'est fait que si chaque groupe compte au moins 100 trades. ATTENTION : le signal est un REBOND sur la bande de Keltner M1, donc juste apres
une poussee contre le trade : sur M1 (et souvent M5) la tendance est presque toujours « CONTRE » par construction. Ces unites-la servent surtout a
le constater ; les comparaisons utiles sont M15, H1 et le score.
Necessite MetaTrader 5 ouvert, a cote de rejeu_keltner.py et plan_du_jour.py.

Usage (dossier gimaly) :
  .\.venv\Scripts\python.exe analyse_tendance_courte.py                  depuis le 01/01/2026, spread 0,20 $
  .\.venv\Scripts\python.exe analyse_tendance_courte.py 01/06/2026 --spread 0.25"""
import bisect
import statistics
import sys
from datetime import datetime, timedelta

import numpy as np

try:
    import plan_du_jour as pj
except ImportError:
    print("Place ce script a cote de rejeu_keltner.py et plan_du_jour.py (dossier gimaly).")
    raise SystemExit(1)

rk = pj.rk
UNITES = (("M1", 60), ("M5", 300), ("M15", 900), ("H1", 3600))
N_EMA, RECUL = 20, 5
MIN_TRADES = 100          # un test n'est fait que si chaque groupe a au moins 100 trades
RNG = np.random.default_rng(23)


def tendance_unite(bars, ema, k):
    """+1 haussiere, -1 baissiere, 0 mixte, None si pas assez de recul."""
    if k is None or k < N_EMA + RECUL:
        return None
    c, e, e0 = bars[k][4], ema[k], ema[k - RECUL]
    if c > e and e > e0:
        return 1
    if c < e and e < e0:
        return -1
    return 0


def preparer(barres):
    out = {}
    for nom, pas in UNITES:
        bars = barres if pas == 60 else pj.agreger(barres, pas)
        ema, _ = pj.ema_atr(bars, n_ema=N_EMA)
        out[nom] = (bars, ema, [x[0] for x in bars], pas)
    return out


def etat(unites, nom, i, t_srv):
    bars, ema, ts, pas = unites[nom]
    if nom == "M1":
        k = i - 1
    else:
        k = bisect.bisect_right(ts, t_srv - pas) - 1       # derniere bougie dont la fin est <= l'instant du signal
    return tendance_unite(bars, ema, k)


def rel(tend, sens):
    if tend is None:
        return None
    if tend == 0:
        return "mixte"
    return "avec" if (tend == 1) == (sens == "achat") else "contre"


def par_jour(items):
    d = {}
    for j, r in items:
        x = d.setdefault(j, [0.0, 0])
        x[0] += r
        x[1] += 1
    return d


def ecart(a, b, essais=4000):
    """Ecart de R/trade a - b avec bootstrap sur les jours (memes tirages pour les deux groupes). a, b : listes (jour, r)."""
    da, db = par_jour(a), par_jour(b)
    jours = sorted(set(da) | set(db))
    if not da or not db:
        return None
    sa = np.array([da.get(j, [0, 0])[0] for j in jours]); na = np.array([da.get(j, [0, 0])[1] for j in jours], float)
    sb = np.array([db.get(j, [0, 0])[0] for j in jours]); nb = np.array([db.get(j, [0, 0])[1] for j in jours], float)
    obs = sa.sum() / na.sum() - sb.sum() / nb.sum()
    idx = RNG.integers(0, len(jours), size=(essais, len(jours)))
    ok = (na[idx].sum(axis=1) > 0) & (nb[idx].sum(axis=1) > 0)
    diffs = (sa[idx].sum(axis=1)[ok] / na[idx].sum(axis=1)[ok]) - (sb[idx].sum(axis=1)[ok] / nb[idx].sum(axis=1)[ok])
    diffs = diffs - (diffs.mean() - obs)
    p = max(2 * min((diffs <= 0).mean(), (diffs >= 0).mean()), 1 / essais)
    return obs, np.percentile(diffs, 2.5), np.percentile(diffs, 97.5), p


def moyenne(items):
    return statistics.fmean(r for _, r in items) if items else float("nan")


def ligne_groupe(nom, items, milieu):
    if not items:
        return f"  {nom:<26} -"
    h1 = [r for j, r in items if j < milieu]
    h2 = [r for j, r in items if j >= milieu]
    f = lambda z: f"{statistics.fmean(z):>+7.3f}" if len(z) >= 10 else "   (peu)"
    return f"  {nom:<26} {len(items):>5} trades {len({j for j, _ in items}):>3} j  R/trade {moyenne(items):>+7.3f}   1re {f(h1)}  2e {f(h2)}"


def test_ecart(titre, avec, contre, milieu, seuil):
    e = ecart(avec, contre)
    if e is None or len(avec) < MIN_TRADES or len(contre) < MIN_TRADES:
        print(f"  {titre:<40} pas assez de trades (avec {len(avec)}, contre {len(contre)} ; il en faut {MIN_TRADES} de chaque cote)")
        return None
    obs, lo, hi, p = e
    h = []
    for moitie in (lambda j: j < milieu, lambda j: j >= milieu):
        a = [r for j, r in avec if moitie(j)]
        c = [r for j, r in contre if moitie(j)]
        h.append(f"{statistics.fmean(a) - statistics.fmean(c):>+7.3f}" if len(a) >= 10 and len(c) >= 10 else "   (peu)")
    print(f"  {titre:<40} avec {moyenne(avec):>+7.3f} ({len(avec):>4})  contre {moyenne(contre):>+7.3f} ({len(contre):>4})  ecart {obs:>+7.3f} "
          f"[{lo:>+6.3f} ; {hi:>+6.3f}]  p={p:.4f}{' *' if p < seuil else '  '}  moities {h[0]} / {h[1]}")
    return p


def main(argv):
    argv = list(argv)
    spread = 0.20
    if "--spread" in argv:
        i = argv.index("--spread")
        spread = float(argv[i + 1].replace(",", "."))
        del argv[i:i + 2]
    depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 1, 1)
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    try:
        mt5.symbol_select(rk.SYMBOLE, True)
        barres = rk.charger(mt5, depuis - timedelta(days=30))
        if len(barres) < 20000:
            print("Historique M1 insuffisant : charge plus d'historique M1 de l'or dans MetaTrader puis relance.")
            return 0
        sigs = rk.signaux(barres)
        h_ok, _ = rk.controle(mt5, barres, sigs, depuis)
    finally:
        mt5.shutdown()
    unites = preparer(barres)
    lignes = []
    for i, sens, entree, sl in sigs:
        t_srv = barres[i][0]
        t_pc = datetime.fromtimestamp(t_srv) - timedelta(hours=h_ok)
        if t_pc < depuis:
            continue
        rels = {nom: rel(etat(unites, nom, i, t_srv), sens) for nom, _ in UNITES}
        if None in rels.values():
            continue
        r = rk.jouer(barres, i, sens, entree, sl) - spread / abs(entree - sl)
        score = sum(1 if rels[n] == "avec" else -1 if rels[n] == "contre" else 0 for n in ("M1", "M5", "M15"))
        lignes.append((t_pc.date(), sens, r, rels, score))
    if not lignes:
        print("Aucun signal exploitable.")
        return 0
    jours = sorted({x[0] for x in lignes})
    milieu = jours[len(jours) // 2]
    seuil = 0.05 / 6
    print(f"\n{len(lignes)} signaux sur {len(jours)} jours, du {jours[0]:%d/%m/%Y} au {jours[-1]:%d/%m/%Y} | spread {spread:.2f} $ | 2e moitie a partir du {milieu:%d/%m/%Y}")
    print(ligne_groupe("tous les signaux", [(x[0], x[2]) for x in lignes], milieu))
    print("\nPAR UNITE DE TEMPS (tendance lue sur des bougies fermees avant le signal) :")
    for nom, _ in UNITES:
        for g in ("avec", "mixte", "contre"):
            print(ligne_groupe(f"{nom} {g.upper()}", [(x[0], x[2]) for x in lignes if x[3][nom] == g], milieu))
    print("\nSCORE COURT TERME (M1+M5+M15 ; +3 = tout dans le sens du trade, -3 = tout a l'oppose) :")
    for s in range(3, -4, -1):
        print(ligne_groupe(f"score {s:+d}", [(x[0], x[2]) for x in lignes if x[4] == s], milieu))
    print(f"\nLES SIX TESTS (seuil p < {seuil:.4f}, marque d'une * s'il est passe ; ecart = R/trade « avec » - « contre ») :")
    ps = []
    for nom, _ in UNITES:
        ps.append(test_ecart(f"{nom} : avec - contre", [(x[0], x[2]) for x in lignes if x[3][nom] == "avec"],
                             [(x[0], x[2]) for x in lignes if x[3][nom] == "contre"], milieu, seuil))
    ps.append(test_ecart("score court terme >= +2 / <= -2", [(x[0], x[2]) for x in lignes if x[4] >= 2],
                         [(x[0], x[2]) for x in lignes if x[4] <= -2], milieu, seuil))
    ps.append(test_ecart("piege : H1 AVEC, court terme +/-",
                         [(x[0], x[2]) for x in lignes if x[3]["H1"] == "avec" and x[4] >= 2],
                         [(x[0], x[2]) for x in lignes if x[3]["H1"] == "avec" and x[4] <= -2], milieu, seuil))
    n_pass = sum(1 for p in ps if p is not None and p < seuil)
    print(f"\n{n_pass} test(s) sur 6 passe(nt) le seuil de rigueur.")
    print("Lecture : un ecart n'est credible que s'il passe le seuil ET va dans le meme sens dans les deux moities. Sinon, la tendance court terme")
    print("ne change pas le resultat de facon mesurable : on ne l'ajoute pas comme filtre. Si quelque chose passe, on le pre-enregistre et on le")
    print("teste sur les jours a venir (a partir du 06/11/2026) avant de toucher au bot. Le rejeu ne contient pas les autres filtres du bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
