"""
analizza.py - numeri, intervalli di confidenza, rete e figure per lo short paper CHR 2027.

Uso:
    python analizza.py --menzioni menzioni_finali_v2.csv --unita unita.csv \
        --predizioni predizioni.jsonl --gold gold_annotato_v23.xlsx \
        --metadati metadati.tsv --out risultati

Escludi testi con --escludi (predefinito: 10b,372).
Gli intervalli di confidenza al 95% sono bootstrap per conferenza (si ricampionano
intere conferenze, 2000 ripetizioni, seme 2027), così una conferenza che nomina molte
volte la stessa persona non pesa più del dovuto.
Con --campione si analizzano solo le unità del campione casuale stratificato;
senza, si escludono le unità del gold.
"""
import argparse, json, os
import numpy as np
import pandas as pd

PERIODI = ["1870-1899", "1900-1914", "1915-1922", "1923-1936"]
BLU, ARANCIO = "#2a78d6", "#eb6834"


def periodo(a):
    try:
        y = int(str(a)[:4])
    except ValueError:
        return "n.d."
    return PERIODI[0] if y <= 1899 else PERIODI[1] if y <= 1914 else PERIODI[2] if y <= 1922 else PERIODI[3]


def boot(df, stat, B=2000, seed=2027):
    """Bootstrap per conferenza: restituisce (stima, lo, hi)."""
    est = stat(df)
    groups = {d: g for d, g in df.groupby("doc_id")}
    ids = np.array(list(groups))
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        s = pd.concat([groups[i] for i in rng.choice(ids, len(ids))])
        v = stat(s)
        if v == v:
            vals.append(v)
    lo, hi = np.percentile(vals, [2.5, 97.5]) if vals else (np.nan, np.nan)
    return est, lo, hi


def pct(t):
    e, lo, hi = t
    return f"{e:.1%} [{lo:.1%}–{hi:.1%}]"


def unita_persona(u, m):
    """Collega ogni unità alla menzione verificata (persona, genere, esito)."""
    m = m.assign(k=m.doc_id + "|" + m.fonte + "|" + m.paragrafo_idx)
    idx = {}
    for r in m.itertuples():
        idx.setdefault((r.k, r.forma), r)
    order = {"OK": 0, "FIX": 0, "FIG": 1, "NP": 2, "X": 3}
    rows = []
    for r in u.itertuples():
        k = f"{r.doc_id}|{r.fonte}|{r.paragrafo_idx}"
        hits = [idx[(k, f.strip())] for f in str(r.forme).split("|") if (k, f.strip()) in idx]
        if hits:
            h = sorted(hits, key=lambda x: order.get(x.esito, 4))[0]
            ge = getattr(h, "genere_esteso", None)
            fz = str(getattr(h, "finzione", "False")) == "True"
            rows.append((r.unit_id, h.esito, h.persona if h.esito in ("OK", "FIX") else None,
                         h.genere if h.esito in ("OK", "FIX") else None,
                         ge if isinstance(ge, str) else None, getattr(h, "fonte_genere", None), fz))
        else:
            rows.append((r.unit_id, None, None, None, None, None, False))
    return pd.DataFrame(rows, columns=["unit_id", "esito_wd", "persona_wd", "genere_wd", "genere_esteso", "fonte_genere", "finzione"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--menzioni", required=True)
    ap.add_argument("--unita", required=True)
    ap.add_argument("--predizioni", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--metadati", required=True)
    ap.add_argument("--escludi", default="10b,372")
    ap.add_argument("--campione", default=None, help="CSV con la colonna unit_id del campione casuale stratificato: se dato, si analizzano solo queste unità")
    ap.add_argument("--out", default="risultati")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    escl = set(a.escludi.split(",")) if a.escludi else set()
    R = []  # righe del report

    # ---------- 1. menzioni e Wikidata ----------
    m = pd.read_csv(a.menzioni, dtype=str)
    m = m[~m.doc_id.isin(escl)].copy()
    m["periodo"] = m.anno.map(periodo)
    m["coll"] = m.esito.isin(["OK", "FIX"])
    L = m[m.coll].copy()
    # id persona = QID; le menzioni corrette a mano senza QID prendono il QID dello stesso nome
    q = L.dropna(subset=["qid"]).groupby("persona").qid.agg(lambda x: x.mode().iat[0])
    L["pid"] = L.qid.fillna(L.persona.map(q)).fillna(L.persona)
    L["donna"] = (L.genere == "female").astype(float)
    P = L.drop_duplicates("pid")
    R += ["# Risultati", "", f"Testi esclusi: {', '.join(sorted(escl)) or 'nessuno'}", "",
          "## 1. Menzioni e collegamento a Wikidata", "",
          f"- Menzioni: {len(m)} in {m.doc_id.nunique()} testi",
          f"- Collegate a una persona storica: {len(L)} ({pct(boot(m, lambda d: d.coll.mean()))})",
          f"- Persone distinte: {L.pid.nunique()}; donne tra le persone: {(P.genere == 'female').mean():.1%}",
          f"- Donne tra le menzioni collegate: {pct(boot(L, lambda d: d.donna.mean()))}",
          "", "| Periodo | Testi | Menzioni | Collegate | Donne tra le collegate (IC 95%) |", "|---|---|---|---|---|"]
    fig1 = []
    for p in PERIODI:
        mp, lp = m[m.periodo == p], L[L.periodo == p]
        b = boot(lp, lambda d: d.donna.mean())
        fig1.append((p, *b, len(lp)))
        R.append(f"| {p} | {mp.doc_id.nunique()} | {len(mp)} | {len(lp)} ({len(lp)/len(mp):.1%}) | {pct(b)} |")

    # ---------- 2. rete oratrici - persone citate ----------
    meta = pd.read_csv(a.metadati, sep="\t", dtype=str)
    L = L.merge(meta[["id", "autrice"]].rename(columns={"id": "doc_id"}), on="doc_id", how="left")
    rete = (L.groupby(["persona", "genere"])
            .agg(menzioni=("doc_id", "size"), conferenze=("doc_id", "nunique"), oratrici=("autrice", "nunique"))
            .reset_index().sort_values(["conferenze", "menzioni"], ascending=False))
    rete.to_csv(f"{a.out}/persone_rete.csv", index=False)
    (L.groupby(["autrice", "persona"]).size().reset_index(name="peso")
     .to_csv(f"{a.out}/archi_oratrici_persone.csv", index=False))
    R += ["", "## 2. Rete: persone nominate da più conferenze", "",
          "| Persona | Menzioni | Conferenze | Oratrici |", "|---|---|---|---|"]
    R += [f"| {r.persona} | {r.menzioni} | {r.conferenze} | {r.oratrici} |" for r in rete.head(20).itertuples()]
    R += ["", "**Donne**", "", "| Persona | Menzioni | Conferenze | Oratrici |", "|---|---|---|---|"]
    R += [f"| {r.persona} | {r.menzioni} | {r.conferenze} | {r.oratrici} |"
          for r in rete[rete.genere == "female"].head(15).itertuples()]

    # ---------- 3. classificazione Mistral sul campione ----------
    u = pd.read_csv(a.unita, dtype=str)
    pr = pd.DataFrame([json.loads(l) for l in open(a.predizioni, encoding="utf-8") if l.strip()])
    pr = pr.drop_duplicates("unit_id", keep="last")
    g = pd.read_excel(a.gold, dtype=str)
    gold_ids = set(g.unit_id.dropna())
    c = u.merge(pr[["unit_id", "livello1", "livello2", "valido", "prompt"]], on="unit_id")
    if a.campione:
        keep = set(pd.read_csv(a.campione, dtype=str).unit_id)
        c = c[c.unit_id.isin(keep) & ~c.doc_id.isin(escl) & c.valido.astype(bool)].copy()
    else:
        c = c[~c.unit_id.isin(gold_ids) & ~c.doc_id.isin(escl) & c.valido.astype(bool)].copy()
    c["periodo"] = c.anno.map(periodo)
    c = c.merge(unita_persona(c, pd.read_csv(a.menzioni, dtype=str)), on="unit_id", how="left")
    R += ["", "## 3. Classificazione automatica (campione)", "",
          f"- Unità: {len(c)} in {c.doc_id.nunique()} conferenze; prompt: {', '.join(sorted(c.prompt.unique()))}",
          "- Attenzione: leggere insieme all'accordo con il gold (valutazione separata).", "",
          "| Livello 1 | Quota (IC 95%) |", "|---|---|"]
    for lab in ["CITAZIONE", "MENZIONE", "SOGGETTO", "ERRORE"]:
        R.append(f"| {lab} | {pct(boot(c, lambda d, l=lab: (d.livello1 == l).mean()))} |")
    cit = c[c.livello1 == "CITAZIONE"]
    R += ["", "| Livello 2 (sulle citazioni) | Quota (IC 95%) |", "|---|---|"]
    for lab in ["GENEALOGIA", "ALLINEAMENTO", "CONTESTAZIONE", "APPROPRIAZIONE", "ALTRO"]:
        R.append(f"| {lab} | {pct(boot(cit, lambda d, l=lab: (d.livello2 == l).mean()))} |")
    R += ["", "| Periodo | Unità | CITAZIONE | di cui GENEALOGIA | di cui ALLINEAMENTO |", "|---|---|---|---|---|"]
    for p in PERIODI:
        cp = c[c.periodo == p]; ct = cp[cp.livello1 == "CITAZIONE"]
        R.append(f"| {p} | {len(cp)} | {pct(boot(cp, lambda d: (d.livello1 == 'CITAZIONE').mean()))} | "
                 f"{pct(boot(ct, lambda d: (d.livello2 == 'GENEALOGIA').mean()))} | "
                 f"{pct(boot(ct, lambda d: (d.livello2 == 'ALLINEAMENTO').mean()))} |")

    # ---------- 4. genere: citate o solo menzionate? ----------
    cg = c[c.genere_wd.isin(["female", "male"])].copy()
    cg["donna"] = (cg.genere_wd == "female").astype(float)
    R += ["", "## 4. Donne tra le persone citate e tra quelle solo menzionate", "",
          f"Unità con persona collegata e genere noto: {len(cg)}", "",
          "| Ruolo assegnato | Unità | Donne (IC 95%) |", "|---|---|---|"]
    fig2 = []
    for lab in ["CITAZIONE", "MENZIONE", "SOGGETTO"]:
        s = cg[cg.livello1 == lab]
        b = boot(s, lambda d: d.donna.mean())
        fig2.append((lab, *b, len(s)))
        R.append(f"| {lab} | {len(s)} | {pct(b)} |")
    diff = boot(cg, lambda d: d[d.livello1 == "CITAZIONE"].donna.mean() - d[d.livello1 == "MENZIONE"].donna.mean())
    R.append(f"\nDifferenza CITAZIONE − MENZIONE: {diff[0]*100:+.1f} punti [{diff[1]*100:+.1f}; {diff[2]*100:+.1f}]")

    fig3 = []
    if c.genere_esteso.notna().any():
        ce = c[c.genere_esteso.isin(["female", "male"]) & ~c.finzione.astype(bool)].copy()
        ce["donna"] = (ce.genere_esteso == "female").astype(float)
        R += ["", "### 4b. Persone reali, con il genere esteso (Wikidata + nome o titolo" + (" + verifica manuale" if (ce.fonte_genere == "manuale").any() else "") + ")", "",
              f"Unità con genere noto: {len(ce)} di {len(c)} (fonti: {ce.fonte_genere.value_counts().to_dict()})", "",
              "| Ruolo assegnato | Unità | Donne (IC 95%) |", "|---|---|---|"]
        for lab in ["CITAZIONE", "MENZIONE", "SOGGETTO"]:
            s_ = ce[ce.livello1 == lab]
            b = boot(s_, lambda d: d.donna.mean())
            fig3.append((lab, *b, len(s_)))
            R.append(f"| {lab} | {len(s_)} | {pct(b)} |")
        d2 = boot(ce, lambda d: d[d.livello1 == "CITAZIONE"].donna.mean() - d[d.livello1 == "MENZIONE"].donna.mean())
        R.append(f"\nDifferenza CITAZIONE − MENZIONE: {d2[0]*100:+.1f} punti [{d2[1]*100:+.1f}; {d2[2]*100:+.1f}]")
        cf = c[c.genere_esteso.isin(["female", "male"]) & c.finzione.astype(bool)].copy()
        if len(cf):
            cf["donna"] = (cf.genere_esteso == "female").astype(float)
            R += ["", "### 4c. Personaggi del mito e della finzione", "",
                  f"Unità: {len(cf)}; donne {cf.donna.mean():.1%}", "",
                  "| Ruolo assegnato da Mistral | Unità | Donne |", "|---|---|---|"]
            for lab in ["CITAZIONE", "MENZIONE", "SOGGETTO", "ERRORE"]:
                s_ = cf[cf.livello1 == lab]
                R.append(f"| {lab} | {len(s_)} | {s_.donna.mean():.1%} |" if len(s_) else f"| {lab} | 0 | – |")
        if "genere_esteso" in m.columns:
            fz = m.finzione.astype(str).eq("True") if "finzione" in m.columns else False
            me = m[m.genere_esteso.isin(["female", "male"]) & ~fz].copy()
            me["donna"] = (me.genere_esteso == "female").astype(float)
            R += ["", "Donne tra tutte le menzioni di persone reali con genere noto: "
                  f"{pct(boot(me, lambda d: d.donna.mean()))} su {len(me)} menzioni", "",
                  "| Periodo | Menzioni con genere | Donne (IC 95%) |", "|---|---|---|"]
            for p in PERIODI:
                mp = me[me.periodo == p]
                R.append(f"| {p} | {len(mp)} | {pct(boot(mp, lambda d: d.donna.mean()))} |")

    open(f"{a.out}/risultati.md", "w", encoding="utf-8").write("\n".join(R) + "\n")
    c.to_csv(f"{a.out}/campione_classificato.csv", index=False)

    # ---------- figure ----------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#888", "axes.labelcolor": "#333", "xtick.color": "#333", "ytick.color": "#333"})

    def barfig(data, fname, ylabel, color):
        fig, ax = plt.subplots(figsize=(3.3, 2.2))
        labs = [d[0] for d in data]; est = [d[1] for d in data]
        err = [[d[1] - d[2] for d in data], [d[3] - d[1] for d in data]]
        x = np.arange(len(data))
        ax.bar(x, est, width=0.55, color=color, zorder=2)
        ax.errorbar(x, est, yerr=err, fmt="none", ecolor="#333", elinewidth=0.8, capsize=2.5, zorder=3)
        for xi, d in zip(x, data):
            ax.text(xi, d[3] + 0.01, f"{d[1]:.0%}\nn={d[4]}", ha="center", va="bottom", fontsize=6.5, color="#333")
        ax.set_xticks(x, labs)
        ax.set_ylabel(ylabel)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
        ax.set_ylim(0, max(d[3] for d in data) * 1.35)
        ax.grid(axis="y", color="#e5e5e5", linewidth=0.6, zorder=0)
        fig.tight_layout()
        fig.savefig(f"{a.out}/{fname}.pdf"); fig.savefig(f"{a.out}/{fname}.png", dpi=200)
        plt.close(fig)

    barfig(fig1, "fig_donne_periodo", "Donne tra le menzioni collegate", BLU)
    barfig(fig2, "fig_donne_ruolo", "Donne tra le persone", ARANCIO)
    if fig3:
        barfig(fig3, "fig_donne_ruolo_esteso", "Donne tra le persone", ARANCIO)
    print("\n".join(R))


if __name__ == "__main__":
    main()
