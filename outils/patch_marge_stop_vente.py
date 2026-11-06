# -*- coding: utf-8 -*-
r"""Patch : pour les trades RECUS A DISTANCE (bots des amis), le stop d'une VENTE est decale du spread de leur courtier, comme l'objectif l'etait deja.

Probleme : une vente se ferme au prix ASK. Son stop se declenche donc quand l'ask touche le niveau, alors que le graphique (bid) est encore un spread
plus bas. Chez ton courtier (spread ~0,2 $) le trade survit, chez un courtier au spread plus large (0,3 a 0,55 $) il est stoppe : meme signal,
issue differente. Le bot corrigeait deja l'objectif d'une vente du spread (_tp_mt5) mais pas son stop.
Test sur tes 233 trades (analyse_marge_stop.py) : sans correctif, un courtier +0,5 $ est stoppe sur 7 trades ou tu ne l'es pas ; avec la marge : 0.
Ce que fait le patch (uniquement quand ouvrir(..., distant=True), c'est-a-dire un signal recu ; TON bot et tes trades ne changent pas) :
  1. marge = spread courant du courtier au moment de l'entree (+ 0,02 $, plafonnee a 1 $) ;
  2. le stop ENVOYE a MetaTrader d'une vente = stop publie + marge (ordre d'ouverture, pose apres ouverture, point mort, reprise) ;
  3. le volume est calcule sur la distance + marge : le risque en argent reste celui voulu (1 R = distance + marge) ;
  4. le stop « logique » du bot (journal, messages, R) reste le niveau publie ; le filet de securite (stop_garde) et la detection « point mort » tiennent compte de la marge.
Reglage : reglages["marge_stop_vente_distant"] (vrai par defaut ; mettre faux pour desactiver sans retirer le patch).
Limites : la marge est celle du spread a l'ENTREE ; si le spread s'elargit ensuite (annonce, changement de jour), l'ecart residuel reste possible. Un achat suit
le graphique (bid) : rien a decaler, mais les differences de cotation entre courtiers (quelques dixiemes, dans les deux sens) ne peuvent pas etre supprimees.
Apres une reprise du bot en cours de trade, la marge d'un trade deja ouvert n'est pas rejouee (le stop de MetaTrader, lui, la contient deja).
Retour arriere : restaurer gimaly/trading/trading.py.avant_marge_stop. Idempotent. Rien n'est ecrit si un repere manque ou si le fichier ne compile plus.
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_marge_stop_vente.py [--annuler]   puis relancer le bot."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
SAUVEGARDE = F.with_name(F.name + ".avant_marge_stop")
MARQUE = "marge_stop_vente_distant"

REMPLACEMENTS = [
    ("volume sur distance + marge",
     '        tp = [pe + r * distance if achat else pe - r * distance for r in self.reglages["tp_r"]]\n'
     '        lots = min(self.volume(distance, float((contexte or {}).get("risque_facteur") or 1.0)),\n',
     '        tp = [pe + r * distance if achat else pe - r * distance for r in self.reglages["tp_r"]]\n'
     '        # patch_marge_stop_vente : signal recu, vente -> stop decale du spread (marge_stop_vente_distant)\n'
     '        marge_sl = self._marge_stop(achat, tick) if distant else 0.0\n'
     '        lots = min(self.volume(distance + marge_sl, float((contexte or {}).get("risque_facteur") or 1.0)),\n'),
    ("stop de l'ordre d'ouverture",
     '"price": pe, "sl": round(sl, info.digits), "deviation": 20,',
     '"price": pe, "sl": round(sl + marge_sl, info.digits), "deviation": 20,'),
    ("pose apres ouverture",
     '        self._poser_sltp(trade["position"], sl, self._tp_mt5(achat, tp[-1]))\n        trade["message_id"] = self._publier_setup(trade)',
     '        trade["marge_sl"] = marge_sl\n'
     '        self._poser_sltp(trade["position"], sl, self._tp_mt5(achat, tp[-1]), marge=marge_sl)\n        trade["message_id"] = self._publier_setup(trade)'),
    ("_poser_sltp : marge",
     '    def _poser_sltp(self, ticket, sl, tp):\n'
     '        """Ecrit le stop et l\'objectif sur la position, pour qu\'ils soient\n'
     '        visibles dans MT5 comme pour un trade passe a la main."""\n'
     '        mt5 = self._mt5()\n',
     '    def _poser_sltp(self, ticket, sl, tp, marge=None):\n'
     '        """Ecrit le stop et l\'objectif sur la position, pour qu\'ils soient\n'
     '        visibles dans MT5 comme pour un trade passe a la main.\n'
     '        marge : decalage du stop d\'une vente (spread du courtier, trades recus a distance)."""\n'
     '        if marge is None:\n'
     '            t = self.trades.get(ticket) or {}\n'
     '            marge = float(t.get("marge_sl") or 0) if t.get("sens") == "vente" else 0.0\n'
     '        if marge and sl:\n'
     '            sl = float(sl) + marge\n'
     '        mt5 = self._mt5()\n'),
    ("filet de securite",
     '        depasse = prix_sortie <= stop if achat else prix_sortie >= stop\n',
     '        depasse = prix_sortie <= stop if achat else prix_sortie >= stop + float(trade.get("marge_sl") or 0)\n'),
    ("point mort detecte (sortie reelle)",
     '                trade["sl_be"] = gain >= -0.3\n',
     '                trade["sl_be"] = gain >= -0.3 - float(trade.get("marge_sl") or 0)\n'),
    ("point mort detecte (sortie anticipee)",
     '                resultat = "point mort" if ecart >= -0.3 else "stop loss"\n',
     '                resultat = "point mort" if ecart >= -0.3 - float(trade.get("marge_sl") or 0) else "stop loss"\n'),
    ("methode _marge_stop",
     '    def _tp_mt5(self, achat, tp):\n',
     '    def _marge_stop(self, achat, tick=None):\n'
     '        """Marge ajoutee au stop d\'une vente recue a distance : spread courant du courtier (+ 0,02 $, plafonne a 1 $).\n'
     '        Une vente se ferme a l\'ask : sans elle, le stop saute quand l\'ask touche le niveau, avant le graphique (patch_marge_stop_vente)."""\n'
     '        if achat or not self.reglages.get("marge_stop_vente_distant", True):\n'
     '            return 0.0\n'
     '        try:\n'
     '            tick = tick or self._mt5().symbol_info_tick(SYMBOLE)\n'
     '            spread = max(0.0, tick.ask - tick.bid)\n'
     '        except Exception:\n'
     '            spread = 0.3\n'
     '        return round(min(spread, 1.0) + 0.02, 2)\n'
     '\n'
     '    def _tp_mt5(self, achat, tp):\n'),
]


def main():
    if "--annuler" in sys.argv:
        if not SAUVEGARDE.exists():
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        shutil.copy2(SAUVEGARDE, F)
        print(f"Restaure : {F.name} remis tel qu'avant le patch.")
        return 0
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    crlf = "\r\n" in src
    src = src.replace("\r\n", "\n")
    if "def _marge_stop" in src:
        print("Deja installe : rien a faire.")
        return 0
    nouveau = src
    for nom, ancien, remplacant in REMPLACEMENTS:
        if nouveau.count(ancien) != 1:
            print(f"Repere introuvable ou ambigu ({nom}) : ton trading.py differe de celui que j'ai teste. RIEN n'est modifie.")
            return 1
        nouveau = nouveau.replace(ancien, remplacant)
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as e:
        print(f"Le fichier modifie ne compile pas ({e}) : RIEN n'est modifie.")
        return 1
    shutil.copy2(F, SAUVEGARDE)
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print(f"Installe : {len(REMPLACEMENTS)} modifications dans {F.name} (sauvegarde {SAUVEGARDE.name}). Relance le bot pour qu'elles soient prises en compte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
