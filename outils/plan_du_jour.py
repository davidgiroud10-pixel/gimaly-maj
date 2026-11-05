# -*- coding: utf-8 -*-
r"""Lecture « descendante » du marche : le contexte du matin (H4, veille, volatilite) change-t-il le resultat des signaux du jour ?
(lecture seule, aucun ordre, rien n'est modifie)

On rejoue les signaux scalp_keltner_large comme rejeu_keltner.py (memes regles, meme spread), puis on classe chaque signal selon le
CONTEXTE CONNU A 8 H (heure de ton PC) le jour meme, donc avant tout trade du jour. Trois lectures, definies a l'avance :
  1. TENDANCE H4 : ecart de la cloture H4 a sa moyenne mobile 50, en ATR H4 -> haussiere forte (> +1), baissiere forte (< -1), neutre.
     Puis chaque signal est range : AVEC la tendance, CONTRE la tendance (rebond contre une tendance forte), ou tendance neutre.
  2. VOLATILITE DE LA VEILLE : amplitude du jour precedent / moyenne des 10 jours d'avant -> calme (< 0,8), normale, agitee (> 1,2).
  3. POSITION A 8 H par rapport a l'amplitude de la veille : au-dessus, dedans, en dessous.
Pour chaque groupe : nombre de trades, nombre de jours, R par trade apres spread, intervalle a 95 % (calcule PAR JOUR, car les trades d'une
meme journee se ressemblent), et le resultat dans chaque moitie de la periode. Un groupe n'est credible que si l'intervalle exclut 0 ou
l'ecart avec les autres groupes l'exclut, que les deux moities vont dans le meme sens, et qu'il y a assez de jours (~20). Neuf groupes
regardes : un resultat isole peut etre du hasard. Pas de decision a prendre sur cette seule sortie.
Necessite MetaTrader 5 ouvert, a cote de rejeu_keltner.py.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe plan_du_jour.py            depuis le 01/01/2026 (ce qui est charge), spread 0,20 $"""
import bisect
import math
import statistics
import sys
from datetime import datetime, timedelta

try:
    import rejeu_keltner as rk
except ImportError:
    print("Place ce script a cote de rejeu_keltner.py (dossier gimaly).")
    raise SystemExit(1)

H4 = 4 * 3600


def agreger(barres, pas):
    """Bougies agregees (debut, o, h, b, c) ; pas en secondes."""
    out = {}
    for t, o, h, b, c in barres:
        k = t // pas
        if k not in out:
            out[k] = [k * pas, o, h, b, c]
        else:
            x = out[k]
            x[2] = max(x[2], h)
            x[3] = min(x[3], b)
            x[4] = c
    return [tuple(v) for _, v in sorted(out.items())]


def ema_atr(bars, n_ema=50, n_atr=14):
    a = 2 / (n_ema + 1)
    ema, e, tr, atr, a_s = [], None, [], None, []
    for i, (t, o, h, b, c) in enumerate(bars):
        e = c if e is None else a * c + (1 - a) * e
        ema.append(e)
        if i:
            tr.append(max(h - b, abs(h - bars[i - 1][4]), abs(b - bars[i - 1][4])))
            if len(tr) == n_atr:
                atr = sum(tr) / n_atr
            elif len(tr) > n_atr:
                atr = (atr * (n_atr - 1) + tr[-1]) / n_atr
        a_s.append(atr)
    return ema, a_s


def contexte_jour(cut, h4, ema4, atr4, h4_t, jours, jours_t, prix):
    """Contexte a l'instant `cut` (secondes serveur) : (tendance, volatilite_veille, position)."""
    i = bisect.bisect_right(h4_t, cut - H4) - 1          # derniere bougie H4 entierement fermee
    tendance = None
    if i >= 60 and atr4[i]:
        z = (h4[i][4] - ema4[i]) / atr4[i]
        tendance = "haussiere forte" if z > 1 else "baissiere forte" if z < -1 else "neutre"
    j = bisect.bisect_left(jours_t, cut - cut % 86400) - 1  # jour precedent (dernier jour entierement ecoule)
    vol = pos = None
    if j >= 10:
        veille = jours[j]
        amp = veille[2] - veille[3]
        moy = statistics.fmean(x[2] - x[3] for x in jours[j - 10:j])
        if moy > 0:
            r = amp / moy
            vol = "calme" if r < 0.8 else "agitee" if r > 1.2 else "normale"
        pos = "au-dessus de la veille" if prix > veille[2] else "sous la veille" if prix < veille[3] else "dans l'amplitude de la veille"
    return tendance, vol, pos


def ic_par_jour(par_jour):
    """Moyenne et intervalle a 95 % avec regroupement par jour (erreur type robuste a la correlation intra-jour)."""
    n = sum(len(v) for v in par_jour.values())
    if not n:
        return None
    m = sum(sum(v) for v in par_jour.values()) / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in par_jour.values())) / n
    return n, len(par_jour), m, m - 1.96 * se, m + 1.96 * se


def ligne(nom, items, milieu):
    par_jour = {}
    for j, r in items:
        par_jour.setdefault(j, []).append(r)
    s = ic_par_jour(par_jour)
    if not s:
        return f"  {nom:<34} -"
    n, nj, m, lo, hi = s
    h1 = [r for j, r in items if j < milieu]
    h2 = [r for j, r in items if j >= milieu]
    f = lambda z: f"{statistics.fmean(z):>+7.3f}" if len(z) >= 10 else "   (peu)"
    return f"  {nom:<34} {n:>5} trades {nj:>3} j  R/trade {m:>+7.3f}  [{lo:>+6.3f} ; {hi:>+6.3f}]   1re {f(h1)}  2e {f(h2)}"


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
    h4 = agreger(barres, H4)
    jours = agreger(barres, 86400)
    ema4, atr4 = ema_atr(h4)
    h4_t = [x[0] for x in h4]
    jours_t = [x[0] for x in jours]
    t_m1 = [x[0] for x in barres]
    cache, lignes = {}, []
    for i, sens, entree, sl in sigs:
        t_srv = barres[i][0]
        t_pc = datetime.fromtimestamp(t_srv) - timedelta(hours=h_ok)
        if t_pc < depuis:
            continue
        jour = t_pc.date()
        cut = int((datetime(jour.year, jour.month, jour.day, 8) + timedelta(hours=h_ok)).timestamp())
        if t_srv < cut:
            continue                                     # signal avant 8 h : pas de lecture du jour
        if jour not in cache:
            k = bisect.bisect_right(t_m1, cut) - 1
            cache[jour] = contexte_jour(cut, h4, ema4, atr4, h4_t, jours, jours_t, barres[k][4])
        tend, vol, pos = cache[jour]
        dist = abs(entree - sl)
        r = rk.jouer(barres, i, sens, entree, sl) - spread / dist
        lignes.append((jour, sens, r, tend, vol, pos))
    if not lignes:
        print("Aucun signal exploitable.")
        return 0
    jours_liste = sorted({x[0] for x in lignes})
    milieu = jours_liste[len(jours_liste) // 2]
    print(f"\n{len(lignes)} signaux sur {len(jours_liste)} jours, du {jours_liste[0]:%d/%m/%Y} au {jours_liste[-1]:%d/%m/%Y} | spread {spread:.2f} $ | "
          f"jours d'abord 1re moitie, puis 2e moitie a partir du {milieu:%d/%m/%Y}")
    tout = [(x[0], x[2]) for x in lignes]
    print("\nTOUS LES SIGNAUX (apres 8 h) :")
    print(ligne("tous", tout, milieu))
    print("\n1. TENDANCE H4 le matin, et sens du signal par rapport a elle :")
    for nom, test in (("AVEC la tendance forte", lambda x: (x[3] == "haussiere forte" and x[1] == "achat") or (x[3] == "baissiere forte" and x[1] == "vente")),
                      ("CONTRE la tendance forte (rebond)", lambda x: (x[3] == "haussiere forte" and x[1] == "vente") or (x[3] == "baissiere forte" and x[1] == "achat")),
                      ("tendance neutre", lambda x: x[3] == "neutre")):
        print(ligne(nom, [(x[0], x[2]) for x in lignes if test(x)], milieu))
    print("\n2. VOLATILITE DE LA VEILLE :")
    for v in ("calme", "normale", "agitee"):
        print(ligne(v, [(x[0], x[2]) for x in lignes if x[4] == v], milieu))
    print("\n3. POSITION A 8 H par rapport a la veille :")
    for p in ("au-dessus de la veille", "dans l'amplitude de la veille", "sous la veille"):
        print(ligne(p, [(x[0], x[2]) for x in lignes if x[5] == p], milieu))
    print("\nLecture : cherche un groupe dont l'intervalle exclut 0 ET qui a le meme signe dans les deux moities. Les jours sont peu nombreux :")
    print("un groupe de moins de ~20 jours ne dit presque rien. Neuf groupes regardes : un resultat isole peut etre du hasard. Si un contexte")
    print("sort nettement, on le pre-enregistre et on le teste sur les jours a venir avant d'en faire un filtre du bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
