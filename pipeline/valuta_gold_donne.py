"""
valuta_gold_donne.py - precisione e richiamo di Mistral sulle citazioni di donne (gold arricchito, stratificato
per etichetta di Mistral) e stima corretta della quota di donne per ruolo.

Uso:
  python valuta_gold_donne.py --gold-donne data/gold_donne_annotato.xlsx --gold data/gold_annotato_v23_r3.xlsx \
      --predizioni data/predizioni_v3.jsonl --unita data/unita.csv --menzioni data/menzioni_finali_v5.csv \
      --campione-classificato data/campione_classificato.csv
Uomini e pesi degli strati: solo persone reali (unita' senza il segno "finzione" in menzioni_finali_v5.csv;
con menzioni_finali_v4.csv, dove la finzione e' gia' esclusa, il risultato e' lo stesso).
Le unità con "uomo" nella nota sono escluse. I pesi degli strati sono le unità femminili del campione casuale
per etichetta di Mistral. Per gli uomini la matrice di confusione viene dal gold principale (unità con persona maschile).
IC 95% bootstrap dentro gli strati (2000 ripetizioni).
"""
import argparse, json, numpy as np, pandas as pd, importlib.util, os
R = ["CITAZIONE", "MENZIONE", "SOGGETTO", "ERRORE"]
ap = argparse.ArgumentParser()
for k in ["gold-donne", "gold", "predizioni", "unita", "menzioni", "campione-classificato"]: ap.add_argument("--" + k, required=True)
a = ap.parse_args()
spec = importlib.util.spec_from_file_location("an", os.path.join(os.path.dirname(os.path.abspath(__file__)), "analizza.py"))
an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
P = {json.loads(l)["unit_id"]: json.loads(l)["livello1"] for l in open(a.predizioni, encoding="utf-8") if l.strip()}
gd = pd.read_excel(a.gold_donne, dtype=str); gd["L1"] = gd.L1.str.strip().str.upper()
gd = gd[~gd.note.fillna("").str.lower().str.contains("uomo")].copy(); gd["p"] = gd.unit_id.map(P)
g = pd.read_excel(a.gold, dtype=str)
col_esc = next((k for k in g.columns if g[k].fillna("").astype(str).str.startswith("ESCLUSA").any()), None)
esclusa = g[col_esc].fillna("").str.startswith("ESCLUSA") if col_esc else False
g = g[g.unit_id.notna() & ~esclusa].copy()
g["L1"] = g.L1.str.strip()
u = pd.read_csv(a.unita, dtype=str); m = pd.read_csv(a.menzioni, dtype=str)
g = g.merge(an.unita_persona(u[u.unit_id.isin(g.unit_id)], m), on="unit_id"); g["p"] = g.unit_id.map(P)
reale = lambda d: ~d.finzione.astype(str).eq("True") if "finzione" in d.columns else True
gm = g[(g.genere_esteso == "male") & reale(g)]
c = pd.read_csv(a.campione_classificato, dtype=str); c = c[reale(c)]
# the correction applies to the classifier's own labels: read them from --predizioni (raw Mistral output)
c["livello1"] = c.unit_id.map(P).fillna(c.livello1)
Nf = c[c.genere_esteso == "female"].livello1.value_counts().to_dict()
Nm = c[c.genere_esteso == "male"].livello1.value_counts().to_dict()
def T(gold, N):
    t = dict.fromkeys(R, 0.0)
    for l in R:
        s = gold[gold.p == l]
        for r in R:
            if len(s): t[r] += N.get(l, 0) * (s.L1 == r).mean()
    return t
def stats(gf, gm_):
    tf, tm = T(gf, Nf), T(gm_, Nm)
    prec = (gf[gf.p == "CITAZIONE"].L1 == "CITAZIONE").mean()
    return dict(prec=prec, rec=prec * Nf.get("CITAZIONE", 0) / tf["CITAZIONE"],
                **{f"donne_{r}": tf[r] / (tf[r] + tm[r]) for r in R[:3]})
est = stats(gd, gm)
rng = np.random.default_rng(3); B = []
for _ in range(2000):
    bf = pd.concat([gd[gd.p == l].sample(frac=1, replace=True, random_state=int(rng.integers(1e9))) for l in R if (gd.p == l).any()])
    bm = gm.sample(frac=1, replace=True, random_state=int(rng.integers(1e9)))
    B.append(stats(bf, bm))
B = pd.DataFrame(B)
print(f"gold donne valide: {len(gd)}; unità femminili nel campione per etichetta: {Nf}")
print(pd.crosstab(gd.L1, gd.p, margins=True))
for k, v in est.items():
    lo, hi = np.nanpercentile(B[k], [2.5, 97.5]); print(f"{k}: {v:.1%} [{lo:.1%}–{hi:.1%}]")
d = B.donne_CITAZIONE - B.donne_MENZIONE
print(f"differenza CITAZIONE − MENZIONE (corretta): {(est['donne_CITAZIONE']-est['donne_MENZIONE'])*100:+.1f} punti "
      f"[{np.nanpercentile(d,2.5)*100:+.1f}; {np.nanpercentile(d,97.5)*100:+.1f}]")
