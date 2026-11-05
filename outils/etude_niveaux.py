# -*- coding: utf-8 -*-
r"""Les zones « cles » et le schema AMD existent-ils vraiment dans les prix de l'or ? (lecture seule, aucun ordre, rien n'est modifie)

PARTIE 1 - REACTION AUX NIVEAUX. Niveaux definis a l'avance, connus AVANT chaque bougie : plus haut / plus bas de la veille, plus haut / plus
bas de la session d'Asie (1 h-8 h, heure de ton PC), egaux hauts / egaux bas (au moins deux sommets ou creux a moins de 0,15 ATR : la
liquidite en attente), niveaux ronds (multiples de 50 $ et de 10 $), ouverture du jour, ouverture de la semaine, milieu de la veille.
Evenement : le prix touche le niveau (au plus une fois toutes les 4 h par niveau). Resultat : sur les 4 heures suivantes, le prix repart-il d'au
moins 1 ATR du bon cote (REJET) avant de passer 1 ATR de l'autre cote (CASSURE) ? Reference : des niveaux tires au hasard dans le prix, avec
exactement la meme regle. Si les niveaux « cles » n'ont aucun effet, leur part de rejets est la meme que celle des niveaux au hasard.
PARTIE 2 - AMD. Chaque jour : range d'Asie (accumulation) ; entre 8 h et 11 h, si le prix balaye le haut (ou le bas) du range puis reclot dedans
(manipulation), on joue la distribution vers l'autre bord : entree a la cloture de retour, stop au-dela de la meche du balayage, objectif = l'autre
bord du range, sortie forcee a 22 h. Resultat en R apres spread.
Pour chaque test : p-value par bootstrap sur les JOURS (les bougies d'un meme jour se ressemblent). 11 tests -> seuil de rigueur p < 0,0045.
Un effet n'est credible que s'il passe ce seuil, a le meme signe dans les deux moities et dans la plupart des annees.
Hypotheses : heure du serveur = heure du PC + 1 h (change en deux petites periodes par an) ; M15 ; pas de glissement.

Usage (dossier gimaly, MetaTrader 5 ouvert) :
  .\.venv\Scripts\python.exe etude_niveaux.py                 spread 0,30 $
  .\.venv\Scripts\python.exe etude_niveaux.py --decalage 1 --spread 0.4"""
import sys
from datetime import datetime

import numpy as np

SYMBOLE = "XAUUSD"
FENETRE, SEUIL_ATR, PAUSE = 16, 1.0, 16
RNG = np.random.default_rng(11)


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


def resultat_touche(h, l, i, niveau, depuis_bas, a):
    """+1 rejet, 0 cassure, None sinon. Rejet = repart de SEUIL_ATR du bon cote avant de passer SEUIL_ATR de l'autre."""
    haut, bas = niveau + SEUIL_ATR * a, niveau - SEUIL_ATR * a
    for k in range(i + 1, min(len(h), i + 1 + FENETRE)):
        monte, descend = h[k] >= haut, l[k] <= bas
        if monte and descend:
            return None
        if depuis_bas:
            if descend:
                return 1
            if monte:
                return 0
        else:
            if monte:
                return 1
            if descend:
                return 0
    return None


def pivots(h, l, n=3):
    hs, bs = {}, {}
    for j in range(n, len(h) - n):
        if h[j] > h[j - n:j].max() and h[j] >= h[j + 1:j + n + 1].max():
            hs[j + n] = (j, h[j])
        if l[j] < l[j - n:j].min() and l[j] <= l[j + 1:j + n + 1].min():
            bs[j + n] = (j, l[j])
    return hs, bs


def niveaux_par_barre(t_pc, o, h, l, c, atr):
    """Genere les evenements (type, indice, niveau, depuis_bas) ; niveaux connus avant la bougie."""
    jour = t_pc // 86400
    sec = t_pc % 86400
    semaine = (jour + 3) // 7
    n = len(c)
    # agregats par jour
    j_h, j_l, j_o, j_c = {}, {}, {}, {}
    asie_h, asie_l = {}, {}
    sem_o = {}
    for i in range(n):
        d = jour[i]
        j_h[d] = max(j_h.get(d, -1e18), h[i])
        j_l[d] = min(j_l.get(d, 1e18), l[i])
        j_o.setdefault(d, o[i])
        j_c[d] = c[i]
        if 3600 <= sec[i] < 8 * 3600:
            asie_h[d] = max(asie_h.get(d, -1e18), h[i])
            asie_l[d] = min(asie_l.get(d, 1e18), l[i])
        sem_o.setdefault(semaine[i], o[i])
    jours = sorted(j_h)
    prec = {d: jours[k - 1] for k, d in enumerate(jours) if k}
    hs, bs = pivots(h, l)
    actifs_h, actifs_b = [], []                         # (indice_pivot, prix) recents
    evts, derniere, hasard = [], {}, {}

    def toucher(typ, i, L, cle=None):
        cle = (typ, cle if cle is not None else round(L, 2))
        if i - derniere.get(cle, -10 ** 9) < PAUSE:
            return
        if h[i] >= L > h[i - 1] and c[i - 1] < L:
            derniere[cle] = i
            evts.append((typ, i, L, True))
        elif l[i] <= L < l[i - 1] and c[i - 1] > L:
            derniere[cle] = i
            evts.append((typ, i, L, False))

    for i in range(300, n - FENETRE - 1):
        a = atr[i - 1]
        if np.isnan(a):
            continue
        d = jour[i]
        if i in hs:
            j, p = hs[i]
            for (j0, p0) in actifs_h:
                if i - j0 < 300 and abs(p - p0) <= 0.15 * a:
                    actifs_h.append((j, max(p, p0)))
                    break
            else:
                actifs_h.append((j, p))
        if i in bs:
            j, p = bs[i]
            for (j0, p0) in actifs_b:
                if i - j0 < 300 and abs(p - p0) <= 0.15 * a:
                    actifs_b.append((j, min(p, p0)))
                    break
            else:
                actifs_b.append((j, p))
        actifs_h = [x for x in actifs_h if i - x[0] < 300]
        actifs_b = [x for x in actifs_b if i - x[0] < 300]
        p_d = prec.get(d)
        if p_d is not None:
            toucher("veille haut", i, j_h[p_d])
            toucher("veille bas", i, j_l[p_d])
            toucher("milieu veille", i, (j_h[p_d] + j_l[p_d]) / 2)
        if sec[i] >= 8 * 3600 and d in asie_h:
            toucher("Asie haut", i, asie_h[d])
            toucher("Asie bas", i, asie_l[d])
        # egaux hauts/bas : seulement ceux a au moins deux pivots proches (liste deja fusionnee par max/min)
        vus = set()
        for (j0, p0) in actifs_h:
            deux = sum(1 for (j1, p1) in actifs_h if abs(p1 - p0) <= 0.15 * a)
            if deux >= 2 and round(p0, 1) not in vus:
                vus.add(round(p0, 1))
                toucher("egaux hauts", i, p0)
        for (j0, p0) in actifs_b:
            deux = sum(1 for (j1, p1) in actifs_b if abs(p1 - p0) <= 0.15 * a)
            if deux >= 2 and round(p0, 1) not in vus:
                vus.add(round(p0, 1))
                toucher("egaux bas", i, p0)
        toucher("ouverture jour", i, j_o[d], cle=("o", d))
        toucher("ouverture semaine", i, sem_o[semaine[i]], cle=("s", semaine[i]))
        for pas, nom in ((50, "rond 50"), (10, "rond 10")):
            m = np.floor(h[i] / pas) * pas
            if m > h[i - 1]:
                toucher(nom, i, m)
            m2 = np.ceil(l[i] / pas) * pas
            if m2 < l[i - 1]:
                toucher(nom, i, m2)
        # niveaux aleatoires persistants (reference) : 24 niveaux par jour, tires a +-1,2 % de la cloture de la veille
        if p_d is not None:
            if d not in hasard:
                hasard[d] = j_c[p_d] * (1 + RNG.uniform(-0.012, 0.012, 24))
            for k, L in enumerate(hasard[d]):
                toucher("hasard", i, float(L), cle=("h", d, k))
    return evts


def bootstrap(par_jour_a, par_jour_b, essais=4000):
    """par_jour_x : {jour: [n, rejets]} ; renvoie (diff, bas, haut, p) de P_a - P_b ; les jours des deux echantillons sont retires separement."""
    jours = list(par_jour_a)
    na = np.array([par_jour_a[d][0] for d in jours], float)
    ra = np.array([par_jour_a[d][1] for d in jours], float)
    jb = list(par_jour_b)
    nb = np.array([par_jour_b[d][0] for d in jb], float)
    rb = np.array([par_jour_b[d][1] for d in jb], float)
    pb = rb.sum() / max(nb.sum(), 1)
    pa = ra.sum() / na.sum()
    idx = RNG.integers(0, len(jours), size=(essais, len(jours)))
    idb = RNG.integers(0, len(jb), size=(essais, len(jb)))
    diffs = ra[idx].sum(axis=1) / np.maximum(na[idx].sum(axis=1), 1) - rb[idb].sum(axis=1) / np.maximum(nb[idb].sum(axis=1), 1)
    diffs = diffs - (diffs.mean() - (pa - pb))
    p = 2 * min((diffs <= 0).mean(), (diffs >= 0).mean())
    return pa - pb, np.percentile(diffs, 2.5), np.percentile(diffs, 97.5), max(p, 1 / essais)


def main(argv):
    argv = list(argv)
    spread, dec = 0.30, 1
    for opt in ("--spread", "--decalage"):
        if opt in argv:
            i = argv.index(opt)
            v = float(argv[i + 1].replace(",", "."))
            del argv[i:i + 2]
            if opt == "--spread":
                spread = v
            else:
                dec = v
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    try:
        mt5.symbol_select(SYMBOLE, True)
        r = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M15, 0, 200000)
    finally:
        mt5.shutdown()
    if r is None or len(r) < 5000:
        print("Historique M15 insuffisant : ouvre un graphique M15 de l'or dans MetaTrader et fais-le defiler vers la gauche.")
        return 0
    t = r["time"].astype(np.int64)
    t_pc = t - int(3600 * dec)
    o, h, l, c = (r[k].astype(float) for k in ("open", "high", "low", "close"))
    atr = atr_serie(h, l, c)
    jour = t_pc // 86400
    annee = np.array([datetime.fromtimestamp(x).year for x in t])
    print(f"M15 : {len(c)} bougies du {datetime.fromtimestamp(t[0]):%d/%m/%Y} au {datetime.fromtimestamp(t[-1]):%d/%m/%Y} ({c[0]:.0f} -> {c[-1]:.0f}) | spread {spread:.2f} $")
    # ---------------- partie 1
    evts = niveaux_par_barre(t_pc, o, h, l, c, atr)
    stats, annees_par = {}, {}
    milieu = int(np.median(np.unique(jour)))
    for typ, i, L, bas in evts:
        res = resultat_touche(h, l, i, L, bas, atr[i - 1])
        if res is None:
            continue
        d = int(jour[i])
        s = stats.setdefault(typ, {})
        x = s.setdefault(d, [0, 0])
        x[0] += 1
        x[1] += res
        annees_par.setdefault(typ, []).append((int(annee[i]), res, d))
    ref = stats.get("hasard")
    if not ref:
        print("Pas assez d'evenements de reference.")
        return 0
    n_ref = sum(v[0] for v in ref.values())
    p_ref = sum(v[1] for v in ref.values()) / n_ref
    print(f"\nPARTIE 1 - Part de REJETS apres un contact (reference = niveaux au hasard : {100 * p_ref:.1f} % sur {n_ref} contacts)")
    print(f"  {'niveau':<18} {'contacts':>8} {'jours':>6} {'rejets':>7} {'ecart':>7} {'IC 95 %':>16} {'p':>7} {'1re':>6} {'2e':>6}  annees +")
    types = [x for x in stats if x != "hasard"]
    res_p = []
    for typ in sorted(types, key=lambda k: -sum(v[0] for v in stats[k].values())):
        s = stats[typ]
        n = sum(v[0] for v in s.values())
        if n < 100:
            continue
        diff, lo, hi, p = bootstrap(s, ref)
        pa = sum(v[1] for v in s.values()) / n
        m1 = [r_ for (_, r_, d) in annees_par[typ] if d < milieu]
        m2 = [r_ for (_, r_, d) in annees_par[typ] if d >= milieu]
        ann = {}
        for an, r_, d in annees_par[typ]:
            ann.setdefault(an, []).append(r_)
        pos = sum(1 for v in ann.values() if len(v) >= 30 and np.mean(v) > p_ref)
        tot = sum(1 for v in ann.values() if len(v) >= 30)
        f = lambda z: f"{100 * np.mean(z):>5.1f}" if len(z) >= 30 else "  (-) "
        res_p.append((typ, p, diff))
        print(f"  {typ:<18} {n:>8} {len(s):>6} {100 * pa:>6.1f}% {100 * diff:>+6.1f} [{100 * lo:>+5.1f} ; {100 * hi:>+5.1f}] {p:>7.4f} {f(m1)}% {f(m2)}%  {pos}/{tot}")
    # ---------------- partie 2 : AMD
    sec = t_pc % 86400
    jours = np.unique(jour)
    res_amd = {"balayage haut": [], "balayage bas": []}
    for d in jours:
        idx = np.where(jour == d)[0]
        asie = idx[(sec[idx] >= 3600) & (sec[idx] < 8 * 3600)]
        lond = idx[(sec[idx] >= 8 * 3600) & (sec[idx] < 11 * 3600)]
        soir = idx[(sec[idx] >= 8 * 3600) & (sec[idx] < 22 * 3600)]
        if len(asie) < 20 or len(lond) < 8:
            continue
        ha, la = h[asie].max(), l[asie].min()
        a = atr[asie[-1]]
        if np.isnan(a) or ha - la < 0.5 * a:
            continue
        for nom, haut in (("balayage haut", True), ("balayage bas", False)):
            ext, balaye = None, False
            for i in lond:
                if haut:
                    if h[i] > ha:
                        balaye, ext = True, max(ext or -1e18, h[i])
                    if balaye and c[i] < ha:
                        break
                else:
                    if l[i] < la:
                        balaye, ext = True, min(ext or 1e18, l[i])
                    if balaye and c[i] > la:
                        break
            else:
                continue
            if not balaye:
                continue
            entree = c[i]
            stop = ext + 0.1 * a if haut else ext - 0.1 * a
            cible = la if haut else ha
            risque, gain = abs(stop - entree), abs(entree - cible)
            if risque < 0.5 or gain < 0.5 * risque:
                continue
            rr = None
            for k in soir[soir > i]:
                if haut:
                    if h[k] >= stop:
                        rr = -1.0
                        break
                    if l[k] <= cible:
                        rr = gain / risque
                        break
                else:
                    if l[k] <= stop:
                        rr = -1.0
                        break
                    if h[k] >= cible:
                        rr = gain / risque
                        break
            if rr is None:
                dern = c[soir[-1]]
                rr = ((entree - dern) if haut else (dern - entree)) / risque
            res_amd[nom].append((int(d), int(annee[idx[0]]), rr - spread / risque))
    print("\nPARTIE 2 - AMD : balayage du range d'Asie a Londres (8 h-11 h), entree a la cloture de retour, stop au-dela de la meche, objectif = l'autre bord")
    print(f"  {'cas':<16} {'jours':>6} {'reussite':>8} {'R/trade':>8} {'IC 95 %':>16} {'p':>7} {'1re':>7} {'2e':>7}  annees +")
    tous = []
    for nom, lst in list(res_amd.items()) + [("les deux", res_amd["balayage haut"] + res_amd["balayage bas"])]:
        if len(lst) < 30:
            continue
        rs = np.array([x[2] for x in lst])
        ds = np.array([x[0] for x in lst])
        idx = RNG.integers(0, len(rs), size=(4000, len(rs)))
        boot = rs[idx].mean(axis=1)
        p = max(2 * min((boot <= 0).mean(), (boot >= 0).mean()), 1 / 4000)
        m1, m2 = rs[ds < milieu], rs[ds >= milieu]
        ann = {}
        for d, an, r_ in lst:
            ann.setdefault(an, []).append(r_)
        pos = sum(1 for v in ann.values() if len(v) >= 15 and np.mean(v) > 0)
        tot = sum(1 for v in ann.values() if len(v) >= 15)
        g = lambda z: f"{z.mean():>+7.3f}" if len(z) >= 15 else "   (-)  "
        print(f"  {nom:<16} {len(rs):>6} {100 * (rs > 0).mean():>7.0f}% {rs.mean():>+8.3f} [{np.percentile(boot, 2.5):>+6.3f} ; {np.percentile(boot, 97.5):>+6.3f}] {p:>7.4f} {g(m1)} {g(m2)}  {pos}/{tot}")
    print("\nLecture : seuil de rigueur p < 0,0045 (11 tests). Partie 1 : 'ecart' = points de pourcentage de rejets en plus ou en moins par rapport aux")
    print("niveaux au hasard ; un niveau qui compte a un ecart nettement positif, un p petit, le meme signe dans les deux moities et dans la plupart")
    print("des annees. Si presque rien ne passe, les zones 'cles' ne se distinguent pas du hasard sur ces donnees et cette definition. Partie 2 :")
    print("R/trade > 0 avec un intervalle qui exclut 0, apres spread. Ce que ce script ne mesure pas : la lecture 'a l'oeil' et le contexte.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
