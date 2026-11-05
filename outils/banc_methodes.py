# -*- coding: utf-8 -*-
r"""Banc d'essai des METHODES de trading sur l'historique de l'or (lecture seule, aucun ordre, rien n'est modifie).

Methodes (definies une fois pour toutes, SANS reglage apres coup) :
  BOS+OB   cassure de structure puis retour sur l'order block (derniere bougie contraire avant la cassure) : entree au bord / au milieu
  FVG      fair value gap (ecart a trois bougies avec bougie de deplacement) : retour au bord / au milieu du gap
  IFVG     FVG inverse : un gap est traverse par une cloture, puis on joue le retour sur ce gap dans l'autre sens
  FIBO     apres une impulsion (swing a swing), retour a 50 / 61,8 / 78,6 % : stop a l'origine de l'impulsion
  SWEEP    balayage de liquidite (meche au-dela du plus haut / plus bas de 20 ou 50 bougies, cloture dedans) : retournement
  EMA      pullback sur la moyenne 20 dans une tendance (EMA50 / EMA200)
  BREAK    cassure du canal de 20 bougies, stop a 1,5 ATR
  BANDE    rebond sur la bande de Keltner (EMA20, 2 ATR) avec stop au-dela de la meche
Chaque methode : stop structurel, objectif 2 R, trade coupe apres 96 bougies, un seul trade a la fois, spread retire.
Test sur M15 et H1 (tout l'historique que MetaTrader a charge).

Controle d'honnetete pour chaque methode : pour chaque trade on rejoue AUSSI un trade « temoin » de MEME SENS, MEMES distances de stop et
d'objectif, mais pris a un autre moment tire au hasard (entre 20 et 400 bougies avant ou apres). Cela neutralise la tendance de fond de
l'or (une methode qui n'achete que dans une hausse paraitrait bonne a tort). Le p-value vient d'un test de permutation par paires (on
echange au hasard le vrai trade et son temoin, 2000 fois). Avec 26 variantes testees, le seuil de rigueur est p < 0,002 (correction de Bonferroni) ; une methode n'est credible que si
ce seuil est franchi, que les ANNEES vont dans le meme sens, et que ca tient dans les deux moities. Sinon : probablement du hasard.
Approximations : stop et objectif dans la meme bougie = stop ; ordre limite rempli des que le prix le touche ; pas de glissement.

Usage (dossier gimaly, MetaTrader 5 ouvert) :
  .\.venv\Scripts\python.exe banc_methodes.py                   M15 et H1, spread 0,30 $
  .\.venv\Scripts\python.exe banc_methodes.py --spread 0.4"""
import math
import sys
from datetime import datetime

import numpy as np

SYMBOLE = "XAUUSD"
RNG = np.random.default_rng(7)
TP_R, DUREE, ATTENTE, PIV = 2.0, 96, 20, 3


def atr_serie(h, l, c, n=14):
    out = np.full(len(c), np.nan)
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    a = None
    for i, x in enumerate(tr, start=1):
        if i == n:
            a = tr[:n].mean()
        elif i > n:
            a = (a * (n - 1) + x) / n
        if i >= n:
            out[i] = a
    return out


def ema(x, n):
    a, e, out = 2 / (n + 1), x[0], np.empty(len(x))
    for i, v in enumerate(x):
        e = a * v + (1 - a) * e
        out[i] = e
    return out


def piste(o, h, l, c, i, sens, entree, sl, dist):
    """Suit un trade rempli a la bougie i (stop/objectif des bougies suivantes). Renvoie (R, indice_sortie)."""
    achat = sens == "achat"
    tp = entree + TP_R * dist if achat else entree - TP_R * dist
    dern = entree
    for k in range(i + 1, min(len(c), i + 1 + DUREE)):
        if (l[k] <= sl) if achat else (h[k] >= sl):
            return -1.0, k
        if (h[k] >= tp) if achat else (l[k] <= tp):
            return TP_R, k
        dern = c[k]
    k = min(len(c) - 1, i + DUREE)
    return ((dern - entree) if achat else (entree - dern)) / dist, k


def coeur(o, h, l, c, atr, sig, filtre=True):
    """Un trade : (R brut, distance de stop, indice de sortie) ou None (annule / filtre)."""
    i, sens, lim, sl = sig
    achat = sens == "achat"
    if lim is None:                                  # entree au marche a l'ouverture suivante
        if i + 1 >= len(c):
            return None
        j, entree = i + 1, o[i + 1]
        if (entree <= sl) if achat else (entree >= sl):
            return None
        rempli_stop = False
    else:
        j = None
        for k in range(i + 1, min(len(c), i + 1 + ATTENTE)):
            if (l[k] <= lim) if achat else (h[k] >= lim):
                j, entree = k, lim
                break
            if (l[k] <= sl) if achat else (h[k] >= sl):
                return None                          # zone invalidee avant le retour
        if j is None:
            return None
        rempli_stop = (l[j] <= sl) if achat else (h[j] >= sl)
    dist = abs(entree - sl)
    if filtre and (dist < 0.6 or math.isnan(atr[i]) or dist > 6 * atr[i]):
        return None
    if dist <= 0:
        return None
    if lim is not None and rempli_stop:
        return -1.0, dist, j
    r, sortie = piste(o, h, l, c, j, sens, entree, sl, dist)
    return r, dist, sortie


def executer(o, h, l, c, atr, sig, spread):
    """Renvoie (R, R_temoin, indice_sortie) ou None. Le temoin rejoue la MEME consigne (meme sens, memes ecarts par rapport au prix de la
    cloture du signal, memes regles de remplissage) a un autre moment tire au hasard."""
    res = coeur(o, h, l, c, atr, sig)
    if res is None:
        return None
    r, dist, sortie = res
    i, sens, lim, sl = sig
    r_t = None
    for _ in range(12):
        dec = int(RNG.integers(20, 401)) * (1 if RNG.integers(0, 2) else -1)
        it = i + dec
        if it < 1 or it >= len(c) - 1:
            continue
        sig_t = (it, sens, None if lim is None else c[it] + (lim - c[i]), c[it] + (sl - c[i]))
        rt = coeur(o, h, l, c, atr, sig_t, filtre=False)
        if rt is not None:
            r_t = rt[0] if rt[1] > 0 else None
            if r_t is not None:
                r_t = r_t * 1.0 - 0.0
                dist_t = rt[1]
                break
    if r_t is None:
        return None
    return r - spread / dist, r_t - spread / dist_t, sortie


def pivots(h, l):
    """Listes de (indice_confirmation, prix) pour sommets et creux (fractale PIV)."""
    hauts, bas = [], []
    for j in range(PIV, len(h) - PIV):
        if h[j] > h[j - PIV:j].max() and h[j] >= h[j + 1:j + PIV + 1].max():
            hauts.append((j + PIV, j, h[j]))
        if l[j] < l[j - PIV:j].min() and l[j] <= l[j + 1:j + PIV + 1].min():
            bas.append((j + PIV, j, l[j]))
    return hauts, bas


def generer(o, h, l, c, atr):
    """Renvoie {nom_variante: [signaux]}."""
    n = len(c)
    hauts, bas = pivots(h, l)
    out = {k: [] for k in ("BOS+OB bord", "BOS+OB milieu", "FVG bord", "FVG milieu", "IFVG", "FIBO 50", "FIBO 61.8", "FIBO 78.6",
                          "SWEEP 20", "SWEEP 50", "EMA", "BREAK", "BANDE")}
    # derniers pivots connus a chaque bougie
    ih = ib = 0
    sh = sb = None
    sh_i = sb_i = None
    cass_h = cass_b = None
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    kel_haut, kel_bas = e20 + 2 * np.nan_to_num(atr, nan=0), e20 - 2 * np.nan_to_num(atr, nan=0)
    gaps = []                                       # FVG pour IFVG : (indice, 'haussier'/'baissier', bas, haut)
    jambe_vue = set()
    for i in range(210, n - 1):
        while ih < len(hauts) and hauts[ih][0] <= i:
            sh, sh_i = hauts[ih][2], hauts[ih][1]
            ih += 1
        while ib < len(bas) and bas[ib][0] <= i:
            sb, sb_i = bas[ib][2], bas[ib][1]
            ib += 1
        a = atr[i]
        if math.isnan(a):
            continue
        # BOS + OB
        if sh is not None and c[i] > sh and c[i - 1] <= sh and cass_h != sh_i:
            cass_h = sh_i
            for k in range(i - 1, max(i - 16, sh_i), -1):
                if c[k] < o[k]:
                    out["BOS+OB bord"].append((i, "achat", h[k], l[k] - 0.2 * a))
                    out["BOS+OB milieu"].append((i, "achat", (h[k] + l[k]) / 2, l[k] - 0.2 * a))
                    break
        if sb is not None and c[i] < sb and c[i - 1] >= sb and cass_b != sb_i:
            cass_b = sb_i
            for k in range(i - 1, max(i - 16, sb_i), -1):
                if c[k] > o[k]:
                    out["BOS+OB bord"].append((i, "vente", l[k], h[k] + 0.2 * a))
                    out["BOS+OB milieu"].append((i, "vente", (h[k] + l[k]) / 2, h[k] + 0.2 * a))
                    break
        # FVG (ecart a trois bougies, bougie centrale de deplacement)
        if l[i] > h[i - 2] and abs(c[i - 1] - o[i - 1]) > a:
            if c[i - 1] > o[i - 1]:
                out["FVG bord"].append((i, "achat", l[i], l[i - 2] - 0.1 * a))
                out["FVG milieu"].append((i, "achat", (l[i] + h[i - 2]) / 2, l[i - 2] - 0.1 * a))
                gaps.append((i, "haussier", h[i - 2], l[i]))
        if h[i] < l[i - 2] and abs(c[i - 1] - o[i - 1]) > a:
            if c[i - 1] < o[i - 1]:
                out["FVG bord"].append((i, "vente", h[i], h[i - 2] + 0.1 * a))
                out["FVG milieu"].append((i, "vente", (h[i] + l[i - 2]) / 2, h[i - 2] + 0.1 * a))
                gaps.append((i, "baissier", h[i], l[i - 2]))
        # IFVG : gap traverse par une cloture, puis retour dans l'autre sens
        restants = []
        for g in gaps:
            gi, typ, gb, gh = g
            if i - gi > 40:
                continue
            if typ == "haussier" and c[i] < gb and i > gi + 2:
                out["IFVG"].append((i, "vente", gb, gh + 0.1 * a))
                continue
            if typ == "baissier" and c[i] > gh and i > gi + 2:
                out["IFVG"].append((i, "achat", gh, gb - 0.1 * a))
                continue
            restants.append(g)
        gaps = restants
        # FIBO : impulsion du dernier creux au dernier sommet (et inversement), retour a 50 / 61,8 / 78,6 %
        if sh is not None and sb is not None and sh_i is not None and sb_i is not None and i == hauts[ih - 1][0] and sb_i < sh_i and sh - sb > 2 * a:
            for nom, f in (("FIBO 50", .5), ("FIBO 61.8", .618), ("FIBO 78.6", .786)):
                out[nom].append((i, "achat", sh - f * (sh - sb), sb - 0.1 * a))
        if sh is not None and sb is not None and i == bas[ib - 1][0] and sh_i < sb_i and sh - sb > 2 * a:
            for nom, f in (("FIBO 50", .5), ("FIBO 61.8", .618), ("FIBO 78.6", .786)):
                out[nom].append((i, "vente", sb + f * (sh - sb), sh + 0.1 * a))
        # SWEEP
        for nom, w in (("SWEEP 20", 20), ("SWEEP 50", 50)):
            mx, mn = h[i - w:i].max(), l[i - w:i].min()
            if h[i] > mx and c[i] < mx and c[i] < o[i]:
                out[nom].append((i, "vente", None, h[i] + 0.1 * a))
            if l[i] < mn and c[i] > mn and c[i] > o[i]:
                out[nom].append((i, "achat", None, l[i] - 0.1 * a))
        # EMA pullback
        if e50[i] > e200[i] and c[i] > e50[i] and l[i] <= e20[i] < c[i]:
            out["EMA"].append((i, "achat", None, l[i] - 0.2 * a))
        if e50[i] < e200[i] and c[i] < e50[i] and h[i] >= e20[i] > c[i]:
            out["EMA"].append((i, "vente", None, h[i] + 0.2 * a))
        # BREAK (canal de 20)
        if c[i] > h[i - 20:i].max():
            out["BREAK"].append((i, "achat", None, c[i] - 1.5 * a))
        if c[i] < l[i - 20:i].min():
            out["BREAK"].append((i, "vente", None, c[i] + 1.5 * a))
        # BANDE (Keltner)
        if l[i] <= kel_bas[i] < c[i]:
            out["BANDE"].append((i, "achat", None, l[i] - 0.2 * a))
        if h[i] >= kel_haut[i] > c[i]:
            out["BANDE"].append((i, "vente", None, h[i] + 0.2 * a))
    return out


def jouer_variante(o, h, l, c, atr, signaux, spread):
    """Un trade a la fois. Renvoie (indices, R, R_temoin)."""
    idx, rs, ri = [], [], []
    libre = 0
    for sig in sorted(signaux, key=lambda s: s[0]):
        if sig[0] < libre:
            continue
        res = executer(o, h, l, c, atr, sig, spread)
        if res is None:
            continue
        r, r_inv, sortie = res
        idx.append(sig[0])
        rs.append(r)
        ri.append(r_inv)
        libre = sortie + 1
    return np.array(idx), np.array(rs), np.array(ri)


def permutation(rs, ri, essais=2000):
    """p-value : le total reel depasse-t-il le total obtenu en echangeant au hasard chaque trade et son temoin ?"""
    rng = np.random.default_rng(1)
    obs = rs.sum()
    masque = rng.integers(0, 2, size=(essais, len(rs)), dtype=np.int8).astype(bool)
    tot = np.where(masque, rs, ri).sum(axis=1)
    return (1 + (tot >= obs).sum()) / (essais + 1)


def main(argv):
    argv = list(argv)
    spread = 0.30
    if "--spread" in argv:
        i = argv.index("--spread")
        spread = float(argv[i + 1].replace(",", "."))
        del argv[i:i + 2]
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    donnees = {}
    try:
        mt5.symbol_select(SYMBOLE, True)
        for nom, tf in (("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1)):
            r = mt5.copy_rates_from_pos(SYMBOLE, tf, 0, 200000)
            if r is not None and len(r) > 1500:
                donnees[nom] = r
    finally:
        mt5.shutdown()
    if not donnees:
        print("Historique insuffisant : ouvre un graphique M15 et H1 de l'or dans MetaTrader et fais-le defiler vers la gauche.")
        return 0
    tests = []
    for nom_tf, r in donnees.items():
        t = r["time"].astype(np.int64)
        o, h, l, c = (r[k].astype(float) for k in ("open", "high", "low", "close"))
        annees = np.array([datetime.fromtimestamp(x).year for x in t])
        d0, d1 = datetime.fromtimestamp(t[0]), datetime.fromtimestamp(t[-1])
        print(f"{nom_tf} : {len(c)} bougies du {d0:%d/%m/%Y} au {d1:%d/%m/%Y} ({c[0]:.0f} -> {c[-1]:.0f}) | spread {spread:.2f} $")
        atr = atr_serie(h, l, c)
        sigs = generer(o, h, l, c, atr)
        for nom, s in sigs.items():
            idx, rs, ri = jouer_variante(o, h, l, c, atr, s, spread)
            if len(rs) < 30:
                continue
            moitie = len(rs) // 2
            par_an = {an: rs[annees[idx] == an] for an in sorted(set(annees[idx]))}
            tests.append((nom_tf, nom, len(rs), (rs > 0).mean(), rs.mean(), rs.sum(), ri.mean(), permutation(rs, ri),
                          rs[:moitie].mean(), rs[moitie:].mean(), par_an))
    k = len(tests)
    seuil = 0.05 / max(k, 1)
    print(f"\n{k} variantes testees -> seuil de rigueur p < {seuil:.4f} (0,05 / {k}).")
    print(f"\n{'periode':>5} {'methode':<14} {'trades':>6} {'reussite':>8} {'R/trade':>8} {'R total':>8} {'temoin':>8} {'p':>7} {'1re':>7} {'2e':>7}  annees positives")
    for nom_tf, nom, n, g, m, tot, minv, p, m1, m2, par_an in sorted(tests, key=lambda x: -x[4]):
        pos = sum(1 for v in par_an.values() if len(v) >= 5 and v.mean() > 0)
        tot_an = sum(1 for v in par_an.values() if len(v) >= 5)
        marque = "  <-- passe le seuil" if p < seuil and m > 0 and m1 > 0 and m2 > 0 else ""
        print(f"{nom_tf:>5} {nom:<14} {n:>6} {100 * g:>7.0f}% {m:>+8.3f} {tot:>+8.1f} {minv:>+8.3f} {p:>7.3f} {m1:>+7.3f} {m2:>+7.3f}  {pos}/{tot_an}{marque}")
    gagnants = [t for t in tests if t[4] > 0]
    print(f"\n{len(gagnants)} variantes sur {k} ont un R/trade positif apres spread ; {sum(1 for t in tests if t[7] < 0.05)} ont p < 0,05 ; "
          f"{sum(1 for t in tests if t[7] < seuil and t[4] > 0 and t[8] > 0 and t[9] > 0)} passent le seuil de rigueur (p, R positif, deux moities positives).")
    print("Lecture : par hasard on attend environ 5 % de p < 0,05 parmi les variantes (donc 1 a 2 sur 26). 'temoin' = R/trade du meme sens pris a un autre moment")
    print("au hasard : si les deux sont proches, la methode ne choisit pas mieux le moment qu'un tirage. Une methode ne vaut le coup que si elle")
    print("passe le seuil, que la plupart des annees sont positives et que les deux moities le sont. A confirmer ensuite sur des donnees nouvelles.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
