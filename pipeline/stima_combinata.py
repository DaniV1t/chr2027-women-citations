"""stima_combinata.py - quota di donne per ruolo: persone reali (stima corretta per l'errore di Mistral,
come valuta_gold_donne.py) + personaggi di finzione annotati a mano nel campione casuale (conteggi esatti).
Uso: python stima_combinata.py --gold-donne data/gold_donne_annotato.xlsx --gold data/gold_annotato_v23_r3.xlsx
     --predizioni data/predizioni_v3.jsonl --menzioni data/menzioni_finali_v5.csv
     --campione-classificato data/campione_classificato.csv --finzione data/finzione_annotato.xlsx
     --campione data/campione_casuale_ids.csv [--unita unita.csv]

--unita serve solo se il gold principale non ha le colonne doc_id, fonte, paragrafo_idx e forme:
in quel caso il genere delle unita' del gold si ricava dal file delle unita' (che contiene i testi).
Le persone reali sono le unita' senza il segno "finzione" (menzioni_finali_v5.csv): i personaggi di finzione
si contano a parte, con le etichette dell'autrice. Con menzioni_finali_v4.csv (finzione gia' esclusa) il risultato e' lo stesso."""
import argparse, json, os, importlib.util, numpy as np, pandas as pd
R = ["CITAZIONE", "MENZIONE", "SOGGETTO", "ERRORE"]
ap = argparse.ArgumentParser()
for k in ["gold-donne", "gold", "predizioni", "menzioni", "campione-classificato", "finzione", "campione"]:
    ap.add_argument("--" + k, required=True)
ap.add_argument("--unita", default=None)
ap.add_argument("--escludi", default="10b,372")
a = ap.parse_args()
spec = importlib.util.spec_from_file_location("an", os.path.join(os.path.dirname(os.path.abspath(__file__)), "analizza.py"))
an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
P = {json.loads(l)["unit_id"]: json.loads(l)["livello1"] for l in open(a.predizioni, encoding="utf-8") if l.strip()}
gd = pd.read_excel(a.gold_donne, dtype=str); gd["L1"] = gd.L1.str.strip().str.upper()
gd = gd[~gd.note.fillna("").str.lower().str.contains("uomo")].copy(); gd["p"] = gd.unit_id.map(P)
g = pd.read_excel(a.gold, dtype=str)
# colonna con le unita' escluse ("ESCLUSA: ..."): cercata per contenuto, cosi' funziona anche se si tolgono colonne
col_esc = next((k for k in g.columns if g[k].fillna("").astype(str).str.startswith("ESCLUSA").any()), None)
esclusa = g[col_esc].fillna("").str.startswith("ESCLUSA") if col_esc else False
g = g[g.unit_id.notna() & ~esclusa].copy()
g["L1"] = g.L1.str.strip()
m = pd.read_csv(a.menzioni, dtype=str)
CHIAVE = ["doc_id", "fonte", "paragrafo_idx", "forme"]
if all(k in g.columns for k in CHIAVE):
    u = g[["unit_id"] + CHIAVE]  # il gold contiene gia' la chiave delle unita'
elif a.unita:
    u = pd.read_csv(a.unita, dtype=str); u = u[u.unit_id.isin(g.unit_id)]
else:
    raise SystemExit("Il gold non ha le colonne " + ", ".join(CHIAVE) + ": aggiungi --unita unita.csv")
up = an.unita_persona(u, m)
g = g.drop(columns=[k for k in up.columns if k != "unit_id" and k in g.columns]).merge(up, on="unit_id")
g["p"] = g.unit_id.map(P)
reale = lambda d: ~d.finzione.astype(str).eq("True") if "finzione" in d.columns else True
gm = g[(g.genere_esteso == "male") & reale(g)]
c = pd.read_csv(a.campione_classificato, dtype=str); c = c[reale(c)]
# the correction applies to the classifier's own labels: read them from --predizioni (raw Mistral output)
c["livello1"] = c.unit_id.map(P).fillna(c.livello1)
Nf = c[c.genere_esteso == "female"].livello1.value_counts().to_dict(); Nm = c[c.genere_esteso == "male"].livello1.value_counts().to_dict()
# personaggi di finzione: etichette dell'autrice, solo campione casuale
f = pd.read_excel(a.finzione, dtype=str); f["L1"] = f.L1.str.strip().str.upper()
ids = set(pd.read_csv(a.campione).unit_id); esc = set(a.escludi.split(","))
f = f[f.unit_id.isin(ids) & ~f.unit_id.str.split("-").str[0].isin(esc)]
maschio = f.note.fillna("").str.lower().str.contains("uom|maschio")
Ff = f[~maschio].L1.value_counts().to_dict(); Fm = f[maschio].L1.value_counts().to_dict()
def T(gold, N):
    t = dict.fromkeys(R, 0.0)
    for l in R:
        s = gold[gold.p == l]
        for r in R:
            if len(s): t[r] += N.get(l, 0) * (s.L1 == r).mean()
    return t
def stats(gf, gm_):
    tf, tm = T(gf, Nf), T(gm_, Nm); out = {}
    for r in R[:3]:
        out[f"reali_{r}"] = tf[r] / (tf[r] + tm[r])
        out[f"insieme_{r}"] = (tf[r] + Ff.get(r, 0)) / (tf[r] + tm[r] + Ff.get(r, 0) + Fm.get(r, 0))
        out[f"quota_finzione_tra_donne_{r}"] = Ff.get(r, 0) / (tf[r] + Ff.get(r, 0))
    return out
est = stats(gd, gm); rng = np.random.default_rng(3); B = []
for _ in range(2000):
    bf = pd.concat([gd[gd.p == l].sample(frac=1, replace=True, random_state=int(rng.integers(1e9))) for l in R if (gd.p == l).any()])
    B.append(stats(bf, gm.sample(frac=1, replace=True, random_state=int(rng.integers(1e9)))))
B = pd.DataFrame(B)
print("finzione (campione casuale): donne", Ff, "uomini", Fm)
for k, v in est.items():
    lo, hi = np.nanpercentile(B[k], [2.5, 97.5]); print(f"{k}: {v:.1%} [{lo:.1%}–{hi:.1%}]")
