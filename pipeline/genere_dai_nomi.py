"""
genere_dai_nomi.py - genere dal nome di battesimo o dal titolo, per le menzioni non collegate a Wikidata.

Il genere serve per l'analisi anche quando non si sa chi è la persona: "Margherita" o "la contessa X"
sono donne anche se non si possono identificare.

Regola (nell'ordine):
  1. titolo femminile o maschile nel nome (contessa, madame, suor... / conte, padre, don...);
  2. altrimenti il primo token che è un nome di battesimo italiano con genere noto
     (dizionario gender-guesser, paese "italy"); "mostly_" conta come il genere prevalente;
  3. altrimenti genere sconosciuto.
La regola viene validata sulle persone collegate a Wikidata (di cui il genere è noto).

Uso:
    pip install gender-guesser
    python genere_dai_nomi.py menzioni_finali_v2.csv menzioni_finali_v3.csv
Aggiunge le colonne: genere_nome (regola), genere_esteso (Wikidata se collegata, altrimenti regola),
fonte_genere (wikidata / wikidata_finzione / nome / titolo / manuale / manuale_non_persona / nessuna) e finzione (True per i personaggi del mito e della finzione). Con --manuale genere_manuale.xlsx
applica anche il genere assegnato a mano (foglio "genere", colonne "group", "genere": F / M / ? / FINZIONE / NON PERSONA, e "note": una nota con "finzione" esclude il nome come FINZIONE).
"""
import argparse, re, unicodedata
import pandas as pd
import gender_guesser.detector as gg

FT = {"madame", "madama", "mme", "miss", "mrs", "lady", "signora", "contessa", "marchesa", "duchessa", "regina",
      "principessa", "imperatrice", "donna", "santa", "beata", "suor", "suora", "baronessa", "dama", "madonna",
      "sorella", "signorina", "maestra", "dottoressa", "professoressa", "mademoiselle", "mlle", "mistress"}
MT = {"signor", "signore", "sig", "conte", "marchese", "duca", "re", "principe", "imperatore", "don", "san", "santo",
      "beato", "frate", "fra", "padre", "cardinale", "senatore", "generale", "capitano", "professore", "prof",
      "dottor", "dott", "sir", "lord", "monsieur", "mr", "barone", "cavaliere", "onorevole", "papa", "abate",
      "canonico", "monsignor", "monsignore", "maestro", "mister"}
DET = gg.Detector(case_sensitive=False)


def toks(s):
    s = re.sub(r"\s*\(bare, ambiguous\)", "", str(s))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z]+", s)


def genere_nome(name):
    t = toks(name)
    if any(x in FT for x in t):
        return "female", "titolo"
    if any(x in MT for x in t):
        return "male", "titolo"
    for x in t:
        if len(x) < 3:
            continue
        g = DET.get_gender(x, "italy")
        if g == "unknown":
            g = DET.get_gender(x)
        if g in ("female", "mostly_female"):
            return "female", "nome"
        if g in ("male", "mostly_male"):
            return "male", "nome"
    return None, "nessuna"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--manuale", default=None)
    a = ap.parse_args()
    m = pd.read_csv(a.inp, dtype=str)
    cache = {}
    def rule(name):
        if name not in cache:
            cache[name] = genere_nome(name)
        return cache[name]
    m["genere_nome"] = m.group.map(lambda x: rule(x)[0])
    src = m.group.map(lambda x: rule(x)[1])

    # validazione sulle persone collegate (genere da Wikidata)
    L = m[m.esito.isin(["OK", "FIX"]) & m.genere.isin(["female", "male"]) & m.genere_nome.notna()]
    P = L.drop_duplicates("group")
    print(f"validazione su {len(P)} nomi collegati con genere deducibile ({len(L)} menzioni):")
    for lab, d in (("nomi", P), ("menzioni", L)):
        ok = (d.genere == d.genere_nome)
        f = d[d.genere == "female"]; mm = d[d.genere == "male"]
        print(f"  {lab}: accordo {ok.mean():.1%}; donne riconosciute {(f.genere_nome=='female').mean():.1%} di {len(f)}; "
              f"uomini {(mm.genere_nome=='male').mean():.1%} di {len(mm)}; "
              f"precisione 'donna' {(d[d.genere_nome=='female'].genere=='female').mean():.1%}")

    linked = m.esito.isin(["OK", "FIX"]) & m.genere.isin(["female", "male"])
    person = ~m.esito.isin(["FIG", "NP"])
    m["genere_esteso"] = m.genere.where(linked)
    m.loc[~linked & person, "genere_esteso"] = m.genere_nome
    m["fonte_genere"] = "nessuna"
    m["finzione"] = m.esito.eq("FIG")
    # personaggi FIG di Wikidata: genere dalla verifica (persona/genere), tenuti con il flag finzione
    figg = m.esito.eq("FIG") & m.genere.isin(["female", "male"])
    m.loc[figg, "genere_esteso"] = m.loc[figg, "genere"]
    m.loc[figg, "fonte_genere"] = "wikidata_finzione"
    m.loc[linked, "fonte_genere"] = "wikidata"
    m.loc[~linked & person & m.genere_nome.notna(), "fonte_genere"] = src
    if a.manuale:
        man = pd.read_excel(a.manuale, sheet_name="genere", dtype=str)
        g = man.genere.fillna("").str.strip().str.upper()
        nota_f = man.note.fillna("").str.lower().str.contains("finzion")
        # convenzione dell'autrice: FINZIONE = personaggio di finzione maschile; F + nota "finzione" = personaggio femminile
        gen = g.map({"F": "female", "M": "male", "FINZIONE": "male"})
        fict = g.eq("FINZIONE") | nota_f
        nonp = g.eq("NON PERSONA")
        out = set(man.group[nonp])
        sel_out = ~linked & m.group.isin(out)
        m.loc[sel_out, "genere_esteso"] = None
        m.loc[sel_out, "fonte_genere"] = "manuale_non_persona"
        ok = man[gen.notna()]
        mp = dict(zip(ok.group, gen[gen.notna()]))
        sel = ~linked & m.group.isin(mp) & ~m.group.isin(out)
        m.loc[sel, "genere_esteso"] = m.loc[sel, "group"].map(mp)
        m.loc[sel, "fonte_genere"] = "manuale"
        fset = set(man.group[fict])
        m.loc[m.group.isin(fset), "finzione"] = True
        print("manuale:", {"genere applicato": int(sel.sum()), "non persone": int(sel_out.sum()),
                           "menzioni di personaggi di finzione (manuale)": int(m.group.isin(fset).sum())})
    print(m.fonte_genere.value_counts().to_dict())
    m.to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
