# -*- coding: utf-8 -*-
r"""INVENTAIRE EN LECTURE SEULE de ~\GIMALY\trading\icebergs_etat.json pendant 60 s (option : --duree N). N'ECRIT RIEN (affichage console uniquement), n'importe aucun module GIMALY,
ne touche ni au bot, ni a MT5, ni a un autre fichier. Le fichier est ouvert en lecture, lu d'un bloc, puis referme aussitot (quelques millisecondes), 5 fois par seconde au plus.
Il repond a : le CVD est-il present (nom exact du champ) ? a quelle frequence change-t-il ? quel age a la donnee ? y a-t-il des erreurs de lecture, et le moteur a-t-il continue
d'ecrire normalement (intervalles entre ecritures) pendant la lecture ? Y a-t-il un horodatage et un prix XAUUSD dans le fichier ?
Usage (dossier gimaly) : .\.venv\Scripts\python.exe inventaire_etat_cvd.py [--duree 60]"""
import json
import statistics
import sys
import time
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "icebergs_etat.json"
PAS = 0.2


def chercher(o, cle, chemin=""):
    """Tous les chemins dont la derniere cle contient `cle` (valeurs numeriques ou texte)."""
    trouve = []
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{chemin}.{k}" if chemin else str(k)
            if cle in str(k).lower() and not isinstance(v, (dict, list)):
                trouve.append((p, v))
            trouve += chercher(v, cle, p)
    return trouve


def valeur(o, chemin):
    for k in chemin.split("."):
        o = o[k]
    return o


def main():
    a = sys.argv[1:]
    duree = float(a[a.index("--duree") + 1]) if "--duree" in a else 60.0
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable : le moteur GIMALY ecrit-il bien ce fichier ? Rien d'autre n'a ete fait.")
        return 1
    print(f"Lecture seule de {FICHIER} pendant {duree:.0f} s ... (rien n'est ecrit)")
    lectures = erreurs_perm = erreurs_json = erreurs_autres = 0
    durees = []
    mtimes = []
    cvd_chemin = None
    cvd_vals = []          # (t, valeur)
    ages = []
    premier = None
    t_fin = time.time() + duree
    while time.time() < t_fin:
        t0 = time.perf_counter()
        try:
            with open(FICHIER, "rb") as f:
                brut = f.read()
            mt = FICHIER.stat().st_mtime
        except PermissionError:
            erreurs_perm += 1
            time.sleep(PAS)
            continue
        except OSError:
            erreurs_autres += 1
            time.sleep(PAS)
            continue
        durees.append((time.perf_counter() - t0) * 1000)
        lectures += 1
        try:
            d = json.loads(brut.decode("utf-8-sig"))
        except ValueError:
            erreurs_json += 1
            time.sleep(PAS)
            continue
        if premier is None:
            premier = d
            cands = chercher(d, "cvd")
            if cands:
                # champ du bloc flux si possible
                cvd_chemin = next((p for p, _ in cands if p.lower().startswith("flux")), cands[0][0])
        now = time.time()
        if not mtimes or mt != mtimes[-1]:
            mtimes.append(mt)
        ages.append(now - mt)
        if cvd_chemin:
            try:
                cvd_vals.append((now, float(valeur(d, cvd_chemin))))
            except (KeyError, TypeError, ValueError):
                pass
        time.sleep(PAS)

    print("\n===== RESULTAT =====")
    print(f"lectures reussies : {lectures}  | PermissionError : {erreurs_perm}  | JSON incomplet : {erreurs_json}  | autres erreurs : {erreurs_autres}")
    if durees:
        print(f"duree d'une lecture : moyenne {statistics.mean(durees):.2f} ms, maximum {max(durees):.2f} ms (fichier ouvert tres brievement)")
    if premier is None:
        print("Aucune lecture exploitable : le fichier n'a pas pu etre lu.")
        return 2
    print(f"cles principales : {', '.join(list(premier.keys())[:25])}")
    if isinstance(premier.get("flux"), dict):
        print(f"cles du bloc flux : {', '.join(list(premier['flux'].keys())[:40])}")
    print("\n-- CVD --")
    if not cvd_chemin:
        print("AUCUN champ contenant 'cvd' dans le fichier : le CVD n'y est pas. Je proposerai une autre solution independante.")
    else:
        print(f"champ retenu : {cvd_chemin}   (autres candidats : {[p for p, _ in chercher(premier, 'cvd')]})")
        chg = [t for (t, v), (_, w) in zip(cvd_vals[1:], cvd_vals[:-1]) if v != w]
        if cvd_vals:
            vs = [v for _, v in cvd_vals]
            print(f"valeur : de {vs[0]:.1f} a {vs[-1]:.1f} (min {min(vs):.1f}, max {max(vs):.1f})")
        print(f"changements de valeur vus : {len(chg)} en {duree:.0f} s  (soit {len(chg) / duree:.2f} par seconde)")
        if len(chg) > 2:
            ecarts = [b - a_ for a_, b in zip(chg[:-1], chg[1:])]
            print(f"intervalle entre deux changements : mediane {statistics.median(ecarts):.2f} s, maximum {max(ecarts):.2f} s")
    print("\n-- Ecritures du moteur (le fichier est-il bien remplace chaque seconde ?) --")
    if len(mtimes) > 2:
        iv = [b - a_ for a_, b in zip(mtimes[:-1], mtimes[1:])]
        print(f"ecritures vues : {len(mtimes)} | intervalle median {statistics.median(iv):.2f} s | maximum {max(iv):.2f} s | intervalles > 2,5 s : {sum(1 for x in iv if x > 2.5)}")
    else:
        print(f"seulement {len(mtimes)} ecriture(s) vue(s) en {duree:.0f} s : le moteur n'ecrit pas chaque seconde ?")
    if ages:
        print(f"age de la donnee a la lecture : median {statistics.median(ages):.2f} s, maximum {max(ages):.2f} s")
    print("\n-- Horodatage / prix dans le fichier --")
    for nom in ("ts", "heure", "time", "date", "maj", "horodatage"):
        c = chercher(premier, nom)
        if c:
            print(f"  {nom} : {c[:4]}")
    for nom in ("xau", "bid", "ask", "prix"):
        c = chercher(premier, nom)
        if c:
            print(f"  {nom} : {c[:4]}")
    print("\nAucun fichier ecrit, aucune modification. Envoie-moi ce texte en entier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
