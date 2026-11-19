"""
Compare the manual gold annotation with the LLM predictions.

Usage:
    python valuta.py gold_annotato.xlsx predizioni.jsonl --out valutazione.md
    python valuta.py data/gold_annotato_v23_r3.xlsx data/predizioni_v3.jsonl \
        --escludi-unita data/finzione_annotato.xlsx      # only the units with real persons

--escludi-unita: an .xlsx or .csv with a unit_id column; those units are left out. The paper
reports agreement on the units with real persons: fictional characters were annotated by hand.
"""
import argparse
import json
from collections import Counter

from openpyxl import load_workbook
from sklearn.metrics import (classification_report, cohen_kappa_score,
                             confusion_matrix, f1_score)

L1 = ["CITAZIONE", "MENZIONE", "SOGGETTO", "ERRORE"]
L2 = ["CONTESTAZIONE", "GENEALOGIA", "APPROPRIAZIONE", "ALLINEAMENTO", "ALTRO"]


def norm(x):
    return str(x).strip().upper() if x not in (None, "") else None


def table(labels, cm):
    head = "| gold \\ LLM | " + " | ".join(labels) + " |\n|" + "---|" * (len(labels) + 1) + "\n"
    return head + "".join(f"| {l} | " + " | ".join(str(v) for v in row) + " |\n"
                          for l, row in zip(labels, cm))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gold_xlsx")
    ap.add_argument("pred_jsonl")
    ap.add_argument("--out", default="valutazione.md")
    ap.add_argument("--escludi-unita", default=None)
    args = ap.parse_args()
    skip = set()
    if args.escludi_unita:
        import pandas as pd
        rd = pd.read_excel if args.escludi_unita.endswith("xlsx") else pd.read_csv
        skip = set(rd(args.escludi_unita, dtype=str).unit_id.dropna())

    ws = load_workbook(args.gold_xlsx).active
    rows = list(ws.iter_rows(values_only=True))
    h = {name: i for i, name in enumerate(rows[0])}
    gold = {}
    for r in rows[1:]:
        if norm(r[h["L1"]]):
            gold[r[h["unit_id"]]] = (norm(r[h["L1"]]), norm(r[h["L2"]]),
                                     str(r[h["ambiguo"]] or "").lower().startswith("s"))

    pred = {}
    with open(args.pred_jsonl, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                p = json.loads(line)
                pred[p["unit_id"]] = (norm(p["livello1"]), norm(p.get("livello2")))

    ids = [i for i in gold if i in pred and i not in skip]
    out = [f"# Valutazione LLM contro gold\n\nUnità annotate: {len(gold)}; con predizione: {len(ids)}\n"]

    g1 = [gold[i][0] for i in ids]
    p1 = [pred[i][0] for i in ids]
    out.append("## Livello 1\n")
    out.append(f"- Accuratezza: {sum(a == b for a, b in zip(g1, p1)) / len(ids):.3f}")
    out.append(f"- F1 macro: {f1_score(g1, p1, labels=[l for l in L1 if l in g1 or l in p1], average='macro', zero_division=0):.3f}")
    out.append(f"- Kappa di Cohen: {cohen_kappa_score(g1, p1):.3f}")
    out.append(f"- Precisione della NER stimata sul gold (non ERRORE): "
               f"{sum(g != 'ERRORE' for g in g1) / len(g1):.3f}\n")
    out.append("```\n" + classification_report(g1, p1, labels=L1, zero_division=0) + "```\n")
    out.append(table(L1, confusion_matrix(g1, p1, labels=L1)))

    ids2 = [i for i in ids if gold[i][0] == "CITAZIONE" and pred[i][0] == "CITAZIONE"
            and gold[i][1] and pred[i][1]]
    out.append(f"\n## Livello 2 (unità che gold e LLM considerano CITAZIONE: {len(ids2)})\n")
    if ids2:
        g2 = [gold[i][1] for i in ids2]
        p2 = [pred[i][1] for i in ids2]
        out.append(f"- Accuratezza: {sum(a == b for a, b in zip(g2, p2)) / len(ids2):.3f}")
        out.append(f"- F1 macro: {f1_score(g2, p2, labels=[l for l in L2 if l in g2 or l in p2], average='macro', zero_division=0):.3f}")
        out.append(f"- Kappa di Cohen: {cohen_kappa_score(g2, p2):.3f}\n")
        out.append("```\n" + classification_report(g2, p2, labels=L2, zero_division=0) + "```\n")
        out.append(table(L2, confusion_matrix(g2, p2, labels=L2)))

    amb = [i for i in ids if gold[i][2]]
    out.append(f"\n## Casi ambigui secondo l'annotatrice: {len(amb)}")
    if amb:
        out.append(f"- Accordo L1 sui casi ambigui: {sum(gold[i][0] == pred[i][0] for i in amb) / len(amb):.3f}")
        nonamb = [i for i in ids if not gold[i][2]]
        if nonamb:
            out.append(f"- Accordo L1 sui casi non ambigui: "
                       f"{sum(gold[i][0] == pred[i][0] for i in nonamb) / len(nonamb):.3f}")

    out.append("\n## Distribuzione gold\n")
    out.append(f"- L1: {dict(Counter(g1))}")
    out.append(f"- L2: {dict(Counter(gold[i][1] for i in ids if gold[i][1]))}")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
