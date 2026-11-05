# -*- coding: utf-8 -*-
r"""SUIVI PRE-ENREGISTRE : les chiffres ronds de 10 $ repoussent-ils le prix mieux que des niveaux au hasard ? (lecture seule, aucun ordre)

Pourquoi ce script : l'etude des niveaux (etude_niveaux.py, donnees d'aout 2022 a novembre 2026) a trouve que les multiples de 10 $ provoquent
54,6 % de rejets contre 50,0 % pour des niveaux au hasard (p = 0,0003, seuil de rigueur 0,0045). Mais cette hypothese a ete trouvee APRES avoir
regarde ces donnees : elle ne devient credible que si elle se repete sur des donnees qu'on n'avait pas vues. Ce script ne regarde donc que les
donnees POSTERIEURES au 06/11/2026 (date de depart, jamais modifiee).

REGLE FIXEE D'AVANCE (ne pas la changer apres avoir vu le resultat) :
  Test unique : sur les contacts avec un multiple de 10 $ (definition exacte d'etude_niveaux.py : « rond 10 », M15, rejet = repart de 1 ATR du bon
  cote avant de passer 1 ATR de l'autre, dans les 16 bougies suivantes), la part de rejets moins celle des niveaux au hasard (meme regle,
  memes jours) doit etre d'au moins +3 points, avec p unilateral < 0,05 (bootstrap sur les jours), sur AU MOINS 500 contacts.
  - moins de 500 contacts : PAS ASSEZ DE DONNEES, on attend (ce n'est ni une confirmation ni un echec) ;
  - ecart >= +3 points et p < 0,05 : CONFIRME (a suivre encore) ;
  - sinon : NON CONFIRME ; l'effet vu sur l'historique est alors a considerer comme du hasard.
Informations en plus, NON utilisees pour decider : sans les multiples de 50, par semaine, et le resultat en R d'un trade « vendre/acheter au
niveau, stop et objectif a 1 ATR » spread compris (R = +/-1 - spread/ATR ; les cas sans issue en 16 bougies sont ignores).

Usage (dossier gimaly, MetaTrader 5 ouvert, etude_niveaux.py dans le meme dossier) :
  .\.venv\Scripts\python.exe suivi_rond10.py
  .\.venv\Scripts\python.exe suivi_rond10.py --spread 0.25 --decalage 1
  .\.venv\Scripts\python.exe suivi_rond10.py --depuis 01/01/2026     (pour voir une autre periode : sans valeur de confirmation)"""
import os
import sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DEPART = "06/11/2026"
MIN_CONTACTS, ECART_MIN, P_MAX = 500, 0.03, 0.05


def _jour(txt):
    j, m, a = (int(x) for x in txt.split("/"))
    return (datetime(a, m, j) - datetime(1970, 1, 1)).days


def r_net(res, atr, spread):
    return (1.0 if res == 1 else -1.0) - spread / atr


def boot_moyenne(par_jour, essais=4000, rng=None):
    """par_jour : {jour: [somme R, n]} -> (moyenne, bas, haut)."""
    rng = rng or np.random.default_rng(5)
    s = np.array([v[0] for v in par_jour.values()], float)
    n = np.array([v[1] for v in par_jour.values()], float)
    idx = rng.integers(0, len(s), size=(essais, len(s)))
    b = s[idx].sum(axis=1) / np.maximum(n[idx].sum(axis=1), 1)
    return s.sum() / n.sum(), np.percentile(b, 2.5), np.percentile(b, 97.5)


def analyser(t_pc, o, h, l, c, atr, depuis_jour, spread, E, titre):
    jour = t_pc // 86400
    evts = E.niveaux_par_barre(t_pc, o, h, l, c, atr)
    st = {"rond 10": {}, "hasard": {}, "rond 10 sans 50": {}}
    rr = {}
    semaines = {}
    for typ, i, L, bas in evts:
        if typ not in ("rond 10", "hasard") or jour[i] < depuis_jour:
            continue
        res = E.resultat_touche(h, l, i, L, bas, atr[i - 1])
        if res is None:
            continue
        d = int(jour[i])
        noms = [typ]
        if typ == "rond 10" and abs(L / 50 - round(L / 50)) > 1e-9:
            noms.append("rond 10 sans 50")
        for nom in noms:
            x = st[nom].setdefault(d, [0, 0])
            x[0] += 1
            x[1] += res
        if typ == "rond 10":
            y = rr.setdefault(d, [0.0, 0])
            y[0] += r_net(res, atr[i - 1], spread)
            y[1] += 1
            w = semaines.setdefault((d + 3) // 7, [0, 0])
            w[0] += 1
            w[1] += res
    ref, cible = st["hasard"], st["rond 10"]
    n_c = sum(v[0] for v in cible.values())
    n_r = sum(v[0] for v in ref.values())
    print(f"\n=== {titre} ===")
    if n_c == 0 or n_r == 0:
        print("Aucun contact sur cette periode.")
        return
    p_c = sum(v[1] for v in cible.values()) / n_c
    p_r = sum(v[1] for v in ref.values()) / n_r
    diff, lo, hi, p = E.bootstrap(cible, ref)
    p_uni = p / 2 if diff > 0 else 1 - p / 2
    print(f"  multiples de 10 $ : {n_c} contacts sur {len(cible)} jours, rejets {100 * p_c:.1f} %")
    print(f"  niveaux au hasard : {n_r} contacts, rejets {100 * p_r:.1f} %")
    print(f"  ecart : {100 * diff:+.1f} points   IC 95 % [{100 * lo:+.1f} ; {100 * hi:+.1f}]   p unilateral = {p_uni:.4f}")
    sans = st["rond 10 sans 50"]
    if sum(v[0] for v in sans.values()) >= 100:
        n_s = sum(v[0] for v in sans.values())
        d_s, l_s, h_s, _ = E.bootstrap(sans, ref)
        print(f"  (info) sans les multiples de 50 : {n_s} contacts, ecart {100 * d_s:+.1f} points [{100 * l_s:+.1f} ; {100 * h_s:+.1f}]")
    if rr:
        m, a, b = boot_moyenne(rr)
        print(f"  (info) trade au niveau, stop et objectif 1 ATR, spread {spread:.2f} $ : {m:+.3f} R/contact   IC 95 % [{a:+.3f} ; {b:+.3f}]")
    sem = sorted(semaines)
    if len(sem) > 1:
        print("  (info) rejets par semaine (contacts) : " + "  ".join(f"{100 * semaines[k][1] / semaines[k][0]:.0f} % ({semaines[k][0]})" for k in sem[-8:]))
    if n_c < MIN_CONTACTS:
        verdict = f"PAS ASSEZ DE DONNEES ({n_c} contacts sur {MIN_CONTACTS} requis) : on attend, ce n'est ni une confirmation ni un echec."
    elif diff >= ECART_MIN and p_uni < P_MAX:
        verdict = "CONFIRME sur des donnees nouvelles (ecart >= +3 points, p < 0,05). A suivre encore avant toute decision : cela ne dit rien du profit."
    else:
        verdict = "NON CONFIRME : sur des donnees nouvelles l'effet n'apparait pas ; l'ecart de l'historique est a considerer comme du hasard."
    print(f"  VERDICT (regle fixee d'avance) : {verdict}")


def main(argv):
    argv = list(argv)
    spread, dec, depuis = 0.25, 1.0, DEPART
    for opt in ("--spread", "--decalage", "--depuis"):
        if opt in argv:
            i = argv.index(opt)
            v = argv[i + 1]
            del argv[i:i + 2]
            if opt == "--depuis":
                depuis = v
            elif opt == "--spread":
                spread = float(v.replace(",", "."))
            else:
                dec = float(v.replace(",", "."))
    try:
        import etude_niveaux as E
    except ImportError:
        print("etude_niveaux.py introuvable : il doit etre dans le meme dossier que ce script.")
        return 1
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    try:
        mt5.symbol_select(E.SYMBOLE, True)
        r = mt5.copy_rates_from_pos(E.SYMBOLE, mt5.TIMEFRAME_M15, 0, 200000)
    finally:
        mt5.shutdown()
    if r is None or len(r) < 5000:
        print("Historique M15 insuffisant : ouvre un graphique M15 de l'or dans MetaTrader et fais-le defiler vers la gauche.")
        return 0
    t = r["time"].astype(np.int64)
    t_pc = t - int(3600 * dec)
    o, h, l, c = (r[k].astype(float) for k in ("open", "high", "low", "close"))
    atr = E.atr_serie(h, l, c)
    print(f"M15 : {len(c)} bougies du {datetime.fromtimestamp(t[0]):%d/%m/%Y} au {datetime.fromtimestamp(t[-1]):%d/%m/%Y} | spread {spread:.2f} $ | decalage {dec:g} h")
    dj = _jour(depuis)
    if (t_pc // 86400).max() < dj:
        print(f"Aucune donnee apres le {depuis}.")
        return 0
    analyser(t_pc, o, h, l, c, atr, dj, spread, E, f"DONNEES NOUVELLES : depuis le {depuis}" + ("" if depuis == DEPART else "  (date differente de la date fixee : pas de valeur de confirmation)"))
    if depuis == DEPART:
        analyser(t_pc, o, h, l, c, atr, -10 ** 9, spread, E, "POUR MEMOIRE : tout l'historique (c'est la qu'on a trouve l'effet, donc sans valeur de preuve)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
