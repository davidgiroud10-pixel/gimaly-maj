# -*- coding: utf-8 -*-
r"""Patch : FERMETURE PARTAGEE. Quand tu fermes un trade a la main (MT5, ou le bouton / --fermer), le bot envoie aux bots des amis un
ordre signe « fermer » ; leur bot ferme alors la position correspondante (meme sens, meme genre, meme signal) au prix du marche.

  * Transport : le canal d'ORDRES prive de chaque ami (celui de « mets-toi a jour »), signe Ed25519. Les bots qui ne connaissent pas
    l'ordre (7.15 a 7.18) l'ignorent : aucun risque d'ouverture par erreur. Seuls les bots 7.19 et suivants ferment.
  * Cote editeur : detecte la fermeture a la main au niveau du deal MT5 (origine client/mobile/web, ou commentaire « fermeture »).
    Les sorties du bot lui-meme (TP, duree maximale, fausse cassure, filet de stop) ne sont PAS propagees : chaque ami a les siennes.
    Coupe-circuit : trading_fermeture_amis: false.
  * Cote ami : coupe-circuit trading_fermeture_editeur: false.
  * Correctif joint : les moteurs tendance_m5 / tendance_pullback ne tournent plus sur un bot AMI (signaux_source: distant) ; il
    recevait deja le signal de l'editeur, il aurait ouvert un doublon.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_fermeture_amis.py   puis redemarrer le bot.
Sauvegardes : trading.py.avant_fermeture, signaux_distants.py.avant_fermeture. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd() / "gimaly" / "trading"
F_TR = RACINE / "trading.py"
F_SD = RACINE / "signaux_distants.py"
M_TR = "def _fermeture_aux_amis"
M_SD = "def publier_commande_en_fond"

# ------------------------------------------------------------------ signaux_distants.py
S_A = "# ---------------------------------------------------------------- recepteur\n"
S_B = '''def publier_commande_en_fond(payload, secret_commun=None, relais=RELAIS, journal=print):
    """Editeur : envoie un ORDRE (ex. {"cmd": "fermer", ...}) sur le canal d'ordres PRIVE de chaque ami actif (et sur celui du canal
    commun tant que des amis n'ont pas migre). Signe comme un signal. Un bot qui ne connait pas l'ordre l'ignore."""
    amis, ancien = lire_amis()
    cibles = {f"ami {nom}": a["secret"] for nom, a in amis.items()}
    if (ancien or not amis) and secret_commun:
        cibles["canal commun"] = secret_commun

    def envoyer(nom, secret):
        ok, msg = publier(dict(payload), canal_commande(secret), secret, relais)
        if not ok:
            journal(f"[signaux] ordre {payload.get('cmd')} -> {nom} : {msg}")

    for nom, secret in cibles.items():
        threading.Thread(target=envoyer, args=(nom, secret), daemon=True, name="gimaly-publier").start()
    return len(cibles)


''' + S_A
CH_SD = [(S_A, S_B)]

# ------------------------------------------------------------------ trading.py
T1_A = '''            from gimaly.trading import signaux_distants as sd
            sd.publier_en_fond({
'''
T1_B = '''            import uuid
            from gimaly.trading import signaux_distants as sd
            sid = uuid.uuid4().hex                      # identifiant du signal : sert a retrouver le trade chez l'ami
            sd.publier_en_fond({
'''
T2_A = '''                "pe_ref": trade["pe"], "t_signal": signal.get("t"),
            }, r["signaux_canal"], r["signaux_secret"], journal=journal)
'''
T2_B = '''                "pe_ref": trade["pe"], "t_signal": signal.get("t"), "id": sid,
            }, r["signaux_canal"], r["signaux_secret"], journal=journal)
            trade["signal_id"] = sid
'''
T3_A = "    def _traiter_signaux_distants(self):\n"
T3_B = '''    def _fermeture_aux_amis(self, trade, deals=None, motif="manuelle"):
        """Editeur : le trade vient d'etre ferme A LA MAIN (MT5 ou bouton) -> ordre signe « fermer » aux bots des amis, sur le canal
        d'ordres prive. `deals` : operations MT5 du trade (on ne propage que l'origine client/mobile/web ou « fermeture » : jamais
        une sortie du bot lui-meme) ; None = fermeture demandee au bot (fermer_tout). Ne leve jamais, une seule fois par trade."""
        try:
            r = self.reglages
            if not r.get("fermeture_amis", True) or not r.get("signaux_publier") or not trade.get("strict", True):
                return
            if not r.get("signaux_canal") or not r.get("signaux_secret"):
                return
            if trade.get("fermeture_envoyee") or trade.get("sortie_anticipee"):
                return
            if deals is not None:
                sorties = sorted((d for d in deals if d.entry != 0), key=lambda d: d.time)
                if not sorties:
                    return
                dernier = sorties[-1]
                manuel = (getattr(dernier, "reason", None) in (0, 1, 2)
                          or "fermeture" in str(getattr(dernier, "comment", "") or "").lower())
                if not manuel:
                    return
            trade["fermeture_envoyee"] = True
            from gimaly.trading import signaux_distants as sd
            n = sd.publier_commande_en_fond(
                {"cmd": "fermer", "sens": trade["sens"], "genre": trade["genre"], "sid": trade.get("signal_id"),
                 "motif": motif}, r["signaux_secret"], journal=journal)
            journal(f"{trade['sens']} ({trade['genre']}) : fermeture a la main, ordre « fermer » envoye ({n} destinataire(s))")
        except Exception as exc:  # noqa: BLE001 - ne doit jamais gener le bot
            journal(f"fermeture partagee (envoi) : erreur ignoree {exc!r}")

    def _ecouter_fermetures(self):
        """Ami : ordres « fermer » de l'editeur (canal d'ordres prive, signe Ed25519, distinct des signaux de trade). Ne leve jamais."""
        try:
            if not self.reglages.get("fermeture_editeur", True):
                return
            rc = self.__dict__.get("_recepteur_cmd")
            if rc is None:
                if time.time() - self.__dict__.get("_cmd_essai", 0) < 60:
                    return
                self._cmd_essai = time.time()
                secret = self.reglages.get("signaux_secret")
                from gimaly.trading import signaux_distants as sd
                if not secret or sd.cle_publique_installee() is None:
                    return
                rc = self._recepteur_cmd = sd.Recepteur(sd.canal_commande(secret), secret, journal=journal)
                rc.suivre_dernier = False
                rc.demarrer()
                journal("source distante : ecoute des ordres de fermeture de l'editeur")
            for p in rc.recuperer():
                if p.get("cmd") == "fermer":
                    self._fermer_a_la_demande(p)
        except Exception as exc:  # noqa: BLE001
            journal(f"fermeture partagee (reception) : erreur ignoree {exc!r}")

    def _fermer_a_la_demande(self, p):
        """Ami : ferme au marche le(s) trade(s) correspondant a l'ordre (meme sens, meme genre ; si les deux bots connaissent
        l'identifiant du signal, il doit etre identique). Aucun trade correspondant : rien (le stop ou l'objectif a deja agi)."""
        sens, genre, sid = p.get("sens"), p.get("genre"), p.get("sid")
        cibles = []
        for position, trade in list(self.trades.items()):
            if trade.get("sens") != sens or trade.get("genre") != genre:
                continue
            if sid and trade.get("signal_id") and trade["signal_id"] != sid:
                continue
            cibles.append((position, trade))
        if not cibles:
            return
        ouvertes = {x.ticket: x for x in self.positions()}
        for position, trade in cibles:
            if position not in ouvertes:
                continue
            journal(f"{sens} ({genre}) : l'editeur a ferme son trade a la main, sortie au prix du marche")
            trade["ferme_editeur"] = True
            self._fermer_partiel(trade, ouvertes[position], tout=True)

    def _traiter_signaux_distants(self):
'''
T4_A = '''        for p in rec.recuperer():
            trade, message = self.ouvrir(
'''
T4_B = '''        self._ecouter_fermetures()
        for p in rec.recuperer():
            trade, message = self.ouvrir(
'''
T5_A = '''        self._sortie_reelle(trade, miens)
        if not trade["tp_atteints"]:
'''
T5_B = '''        self._sortie_reelle(trade, miens)
        self._fermeture_aux_amis(trade, miens)
        if not trade["tp_atteints"]:
'''
T6_A = '''        for trade in list(self.trades.values()):
            trade["tp_atteints"] = trade["tp_atteints"] or []
            self._journal(trade, raison)
'''
T6_B = '''        for trade in list(self.trades.values()):
            trade["tp_atteints"] = trade["tp_atteints"] or []
            self._fermeture_aux_amis(trade, None, "fermer_tout")
            self._journal(trade, raison)
'''
T7_A = '            if not r.get("tendance_actif", True) or not r["actif"]:\n'
T7_B = '            if not r.get("tendance_actif", True) or not r["actif"] or r.get("signaux_source") == "distant":\n'
T8_A = '            if not r.get("pullback_actif", True) or not r.get("tendance_actif", True) or not r["actif"]:\n'
T8_B = ('            if (not r.get("pullback_actif", True) or not r.get("tendance_actif", True) or not r["actif"]\n'
        '                    or r.get("signaux_source") == "distant"):\n')
CH_TR = [(T1_A, T1_B), (T2_A, T2_B), (T3_A, T3_B), (T4_A, T4_B), (T5_A, T5_B), (T6_A, T6_B), (T7_A, T7_B), (T8_A, T8_B)]


def lire(f):
    brut = f.read_bytes()
    return (brut.decode("utf-8-sig").replace("\r\n", "\n"), brut.startswith(b"\xef\xbb\xbf"),
            brut.count(b"\r\n") > brut.count(b"\n") / 2)


def appliquer(txt, changements):
    manquants = [a.strip()[:90] for a, _ in changements if txt.count(a) != 1]
    if manquants:
        return None, "\n".join(manquants)
    for ancien, nouveau in changements:
        txt = txt.replace(ancien, nouveau)
    return txt, None


def main():
    for f in (F_TR, F_SD):
        if not f.exists():
            print(f"{f} introuvable : lance ce script depuis le dossier gimaly.")
            return 1
    ecritures = []
    for f, marque, changements in ((F_SD, M_SD, CH_SD), (F_TR, M_TR, CH_TR)):
        txt, bom, crlf = lire(f)
        if marque in txt:
            print(f"{f.name} : deja corrige (rien a faire).")
            continue
        nouveau, erreur = appliquer(txt, changements)
        if erreur:
            print(f"REPERE INTROUVABLE (ou en double) dans {f.name} : rien n'est modifie. Envoie-moi cette erreur :")
            print(erreur)
            return 2
        try:
            compile(nouveau, str(f), "exec")
        except SyntaxError as exc:
            print(f"Erreur de syntaxe apres modification de {f.name} : {exc}. Rien n'est ecrit.")
            return 3
        ecritures.append((f, nouveau, bom, crlf))
    for f, nouveau, bom, crlf in ecritures:
        shutil.copy2(f, f.with_name(f.name + ".avant_fermeture"))
        sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
        f.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
        print(f"{f.name} : corrige (sauvegarde {f.name}.avant_fermeture).")
    if ecritures:
        print("Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
