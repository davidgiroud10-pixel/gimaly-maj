# -*- coding: utf-8 -*-
"""Mise a jour automatique et SURE du bot GIMALY Trading (cote amis).

Principe :
  1. l'editeur publie deux fichiers dans un depot GitHub public : `version.json` (SIGNE) et `maj-X.zip` ;
  2. ici, on telecharge version.json, on verifie sa signature Ed25519 avec la cle PUBLIQUE livree dans le
     paquet (gimaly/trading/cle_publique.txt, que la mise a jour ne peut pas remplacer) ;
  3. si le numero est plus recent, on telecharge le zip, on verifie son empreinte SHA-256 (elle est dans le
     manifeste signe), on le decompresse dans un dossier temporaire en refusant tout chemin douteux ;
  4. on sauvegarde les fichiers remplaces, on remplace, on teste (compilation + import) ;
     au moindre probleme : retour automatique a l'ancienne version ;
  5. le lanceur se relance tout seul avec le nouveau code.

Jamais touches par une mise a jour : config.local.yaml (reglages et canal), cle_publique.txt, VERSION.json.
Aucune dependance : bibliotheque standard + sig25519.py.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DOSSIER = Path.home() / "GIMALY" / "trading"
DOSSIER_MAJ = DOSSIER / "maj"
SOURCE = os.environ.get("GIMALY_MAJ_SOURCE") or "https://raw.githubusercontent.com/davidgiroud10-pixel/gimaly-maj/main"
FICHIER_VERSION_LOCALE = RACINE / "VERSION.json"
FICHIER_CLE_PUBLIQUE = RACINE / "gimaly" / "trading" / "cle_publique.txt"
JOURNAL = DOSSIER / "maj.log"
ETAT = DOSSIER_MAJ / "etat.json"
TAILLE_MAX_ZIP = 30 * 1024 * 1024
FICHIERS_MAX = 1500
AGENT = {"User-Agent": "gimaly-maj/1", "Cache-Control": "no-cache"}

# chemins qu'une mise a jour a le droit de poser (relatifs a la racine du paquet)
AUTORISES = re.compile(r"^(?:[A-Za-z0-9_\-]+\.(?:py|bat|txt|html|md)|gimaly/(?:[A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-]+\.(?:py|txt|yaml))$")
JAMAIS = {"config.local.yaml", "VERSION.json", "gimaly/trading/cle_publique.txt"}
NOM_ZIP = re.compile(r"^[A-Za-z0-9._\-]{1,80}\.zip$")


def journal(texte):
    ligne = f"{time.strftime('%d/%m/%Y %H:%M:%S')}  {texte}"
    try:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except OSError:
        pass
    try:
        print(ligne, flush=True)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- outils
def _sig():
    try:
        from gimaly.trading import sig25519
    except ImportError:
        sys.path.insert(0, str(RACINE / "gimaly" / "trading"))
        import sig25519
    return sig25519


def _canon(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def version_locale():
    try:
        d = json.loads(FICHIER_VERSION_LOCALE.read_text(encoding="utf-8"))
        return int(d.get("numero", 0)), str(d.get("version", "?"))
    except Exception:  # noqa: BLE001
        return 0, "?"


def cle_publique():
    try:
        h = FICHIER_CLE_PUBLIQUE.read_text(encoding="utf-8-sig").strip()
        return h if len(bytes.fromhex(h)) == 32 else None
    except Exception:  # noqa: BLE001
        return None


def _lire_etat():
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _ecrire_etat(**champs):
    etat = _lire_etat()
    etat.update(champs)
    try:
        DOSSIER_MAJ.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps(etat, indent=1), encoding="utf-8")
    except OSError:
        pass


def _telecharger(nom, limite):
    req = urllib.request.Request(f"{SOURCE.rstrip('/')}/{nom}", headers=AGENT)
    with urllib.request.urlopen(req, timeout=20) as r:
        donnees = r.read(limite + 1)
    if len(donnees) > limite:
        raise ValueError(f"{nom} : fichier trop gros")
    return donnees


def marche_ferme(maintenant=None):
    """True si le marche de l'or est ferme (fin de semaine) : moment sur pour redemarrer le bot.
    Ferme : vendredi 22:30 UTC -> dimanche 22:00 UTC."""
    t = time.gmtime(maintenant if maintenant is not None else time.time())
    jour, heure = t.tm_wday, t.tm_hour + t.tm_min / 60
    return jour == 5 or (jour == 4 and heure >= 22.5) or (jour == 6 and heure < 22.0)


# ---------------------------------------------------------------- verification
def chercher():
    """Interroge le depot. Renvoie (None, message) s'il n'y a rien a faire, sinon (manifeste, message).
    Ne leve jamais d'exception."""
    try:
        pub = cle_publique()
        if not pub:
            return None, "mise a jour desactivee : pas de cle publique dans ce paquet"
        brut = _telecharger("version.json", 100_000)
        env = json.loads(brut.decode("utf-8"))
        manifeste, sig = env["p"], env["e"]
        if not isinstance(manifeste, dict) or not isinstance(sig, str):
            return None, "version.json mal forme"
        if not _sig().verifier_hex(pub, _canon(manifeste).encode("utf-8"), sig):
            journal("ALERTE : signature de version.json INVALIDE : mise a jour ignoree")
            return None, "signature invalide"
        numero = int(manifeste["numero"])
        local, _ = version_locale()
        if numero <= local:
            return None, f"a jour (version {local})"
        if numero in (_lire_etat().get("echecs") or []):
            return None, f"version {numero} deja essayee sans succes : en attente d'une plus recente"
        if not NOM_ZIP.match(str(manifeste.get("fichier", ""))):
            return None, "nom de fichier de mise a jour refuse"
        if str(manifeste.get("quand", "demarrage")) not in ("immediat", "week-end", "demarrage"):
            manifeste["quand"] = "demarrage"
        return manifeste, f"nouvelle version {manifeste.get('version')} (numero {numero}) disponible"
    except Exception as exc:  # noqa: BLE001
        return None, f"verification impossible ({exc!r}) : on reessaiera plus tard"


# ---------------------------------------------------------------- application
def _chemin_sur(nom):
    nom = nom.replace("\\", "/")
    if nom.endswith("/"):
        return None
    if nom.startswith("/") or ".." in nom.split("/") or ":" in nom:
        raise ValueError(f"chemin refuse : {nom}")
    if nom.lower() in {j.lower() for j in JAMAIS}:      # Windows ignore la casse : on aussi
        return None
    if not AUTORISES.match(nom):
        raise ValueError(f"type de fichier refuse : {nom}")
    return nom


def _extraire(zip_octets, staging):
    fichiers = {}
    with zipfile.ZipFile(io.BytesIO(zip_octets)) as z:
        infos = z.infolist()
        if len(infos) > FICHIERS_MAX:
            raise ValueError("trop de fichiers dans la mise a jour")
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            nom = _chemin_sur(info.filename)
            if nom is None:
                continue
            total += info.file_size
            if total > 100 * 1024 * 1024:
                raise ValueError("mise a jour trop volumineuse une fois decompressee")
            donnees = z.read(info)
            cible = staging / nom
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(donnees)
            fichiers[nom] = hashlib.sha256(donnees).hexdigest()
    if not fichiers:
        raise ValueError("mise a jour vide")
    if "gimaly/trading/trading.py" not in fichiers:
        raise ValueError("mise a jour incomplete (trading.py absent)")
    return fichiers


def _python_console():
    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        py = py[:-len("pythonw.exe")] + "python.exe"
    return py


def _tester(racine):
    """Compile tous les .py puis importe les modules cles avec le Python du paquet. Leve en cas d'echec."""
    for p in racine.rglob("*.py"):
        if ".venv" in p.parts or "__pycache__" in p.parts:
            continue
        compile(p.read_bytes(), str(p), "exec")          # erreur de syntaxe = echec, rien n'est ecrit sur disque
    code = "import gimaly.trading.trading, gimaly.trading.signaux_distants, gimaly.trading.sig25519"
    r = subprocess.run([_python_console(), "-c", code],
                       cwd=str(racine), capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": str(racine)})
    if r.returncode != 0:
        raise RuntimeError("import impossible : " + (r.stderr or r.stdout)[-400:])


def appliquer(manifeste):
    """Telecharge, verifie, remplace, teste. Renvoie (True, message) ou (False, message) ; en cas d'echec
    l'ancienne version est remise en place. Ne leve jamais d'exception."""
    numero = int(manifeste["numero"])
    local, _ = version_locale()
    travail = DOSSIER_MAJ / f"travail-{numero}"
    sauvegarde = DOSSIER_MAJ / "sauvegardes" / f"avant-{numero}"
    remplaces, crees = [], []
    remplacement_commence = False
    try:
        if numero <= local:
            return False, "version deja installee"
        shutil.rmtree(travail, ignore_errors=True)
        travail.mkdir(parents=True)
        zip_octets = _telecharger(manifeste["fichier"], TAILLE_MAX_ZIP)
        if hashlib.sha256(zip_octets).hexdigest() != str(manifeste.get("sha256", "")).lower():
            raise ValueError("empreinte SHA-256 du zip differente de celle annoncee : telechargement rejete")
        staging = travail / "nouveau"
        nouveaux = _extraire(zip_octets, staging)

        # requirements : si les composants changent, on les installe avant de remplacer quoi que ce soit
        ancien_req = (RACINE / "requirements.txt")
        nouveau_req = staging / "requirements.txt"
        if nouveau_req.exists() and (not ancien_req.exists() or ancien_req.read_bytes() != nouveau_req.read_bytes()):
            journal("composants modifies : installation des nouveaux composants")
            r = subprocess.run([_python_console(), "-m", "pip", "install", "-r", str(nouveau_req)], capture_output=True,
                               text=True, timeout=600)
            if r.returncode != 0:
                raise RuntimeError("installation des composants impossible : " + (r.stderr or r.stdout)[-300:])

        # sauvegarde puis remplacement
        remplacement_commence = True
        sauvegarde.mkdir(parents=True, exist_ok=True)
        for nom in nouveaux:
            cible = RACINE / nom
            if cible.exists():
                dest = sauvegarde / nom
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cible, dest)
                remplaces.append(nom)
            else:
                crees.append(nom)
        for nom in nouveaux:
            cible = RACINE / nom
            cible.parent.mkdir(parents=True, exist_ok=True)
            tmp = cible.with_name(cible.name + ".maj_tmp")
            shutil.copyfile(staging / nom, tmp)
            os.replace(tmp, cible)
        journal(f"{len(nouveaux)} fichier(s) remplace(s) ; test de la nouvelle version")
        _tester(RACINE)

        FICHIER_VERSION_LOCALE.write_text(
            json.dumps({"numero": numero, "version": str(manifeste.get("version", "?"))}), encoding="utf-8")
        _ecrire_etat(derniere_maj=time.strftime("%d/%m/%Y %H:%M:%S"), derniere_version=manifeste.get("version"))
        shutil.rmtree(travail, ignore_errors=True)
        notes = str(manifeste.get("notes", "")).strip()[:300]
        return True, f"mise a jour installee : version {manifeste.get('version')} (numero {numero})" + (f" - {notes}" if notes else "")
    except Exception as exc:  # noqa: BLE001
        journal(f"ECHEC de la mise a jour ({exc!r}) : retour a l'ancienne version")
        for nom in remplaces:
            try:
                shutil.copy2(sauvegarde / nom, RACINE / nom)
            except OSError as e:
                journal(f"  retour impossible pour {nom} : {e!r}")
        for nom in crees:
            try:
                (RACINE / nom).unlink()
            except OSError:
                pass
        # echec apres remplacement (code defectueux) : on n'insiste pas avec cette version.
        # echec avant (reseau, cache du depot, empreinte) : on reessaie, 3 fois au plus.
        etat = _lire_etat()
        essais = dict(etat.get("essais") or {})
        essais[str(numero)] = essais.get(str(numero), 0) + 1
        echecs = list(etat.get("echecs") or [])
        if remplacement_commence or essais[str(numero)] >= 3:
            echecs.append(numero)
        _ecrire_etat(echecs=echecs[-20:], essais=essais)
        shutil.rmtree(travail, ignore_errors=True)
        return False, f"mise a jour {numero} annulee ({exc})"


def verifier_et_appliquer(quand_ok=None):
    """Pour le lanceur. quand_ok(manifeste) -> bool : decide si le moment est bon (sinon on garde pour plus tard).
    Renvoie (etat, message) avec etat dans {"rien", "attente", "installee", "echec"}."""
    manifeste, msg = chercher()
    if manifeste is None:
        return "rien", msg
    if quand_ok is not None and not quand_ok(manifeste):
        return "attente", msg + " (installation au moment prevu)"
    ok, msg2 = appliquer(manifeste)
    return ("installee" if ok else "echec"), msg2


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--etat"
    if arg == "--etat":
        n, v = version_locale()
        manifeste, msg = chercher()
        print(f"version installee : {v} (numero {n})\nsource : {SOURCE}\n{msg}")
    elif arg == "--appliquer":
        manifeste, msg = chercher()
        print(msg)
        if manifeste:
            ok, m = appliquer(manifeste)
            print(m)
            sys.exit(0 if ok else 1)
    else:
        print("usage : maj_auto.py [--etat | --appliquer]")


if __name__ == "__main__":
    main()
