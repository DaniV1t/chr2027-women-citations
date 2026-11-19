"""
Step 2 of the revised pipeline: link the names in menzioni.csv to Wikidata.
Run this on your own computer (it needs access to wikidata.org).

Changes from the pilot:
- a candidate is accepted only if it is a HUMAN (P31 = Q5). The pilot accepted
  any item, so bare first names ("Angela", "Anita", "Margherita") were linked to
  the Wikidata item of the given name, and "Garibaldi" once to a cruiser;
- a candidate must be born before the earliest lecture in which the name
  appears (when the birth date is known);
- gender is recorded for every linked person, not only for classified ones;
- occupations are kept as a multi-label set (all P106 values), plus the
  categories of the pilot (author, political, scientist, artist, religious)
  and two new ones (military, educator);
- candidates are fetched in one batch call (wbgetentities) instead of one call
  each, and full-text search is restricted to humans (haswbstatement:P31=Q5);
- every decision is logged with its tier, the number of human candidates and
  the sitelink count of the chosen entity, so ambiguous links can be reviewed.

Grouping of name variants by surname is the same as in the pilot.

Usage:  python link_wikidata.py menzioni.csv
        (set WIKIDATA_CONTACT to your e-mail address: Wikimedia asks for a contact in the User-Agent)
Output: entita.csv (one row per group), forme_entita.csv (surface form -> group),
        cache_wikidata_v2.json (reused on the next run; network errors are not cached)
"""
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

MENZIONI = sys.argv[1] if len(sys.argv) > 1 else "menzioni.csv"
CACHE_FILE = Path("cache_wikidata_v2.json")
API = "https://www.wikidata.org/w/api.php"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = f"WomenLecturesItaly-research/2.0 (mailto:{os.environ.get('WIKIDATA_CONTACT', 'your.email@example.org')})"
TIMEOUT = 25
PAUSE = 0.1

CODES = {
    "author": {"Q36180", "Q49757", "Q6625963", "Q1930187", "Q4964182", "Q214917", "Q28389",
               "Q13418253", "Q201788", "Q1607826", "Q11774202"},  # + historian, editor, essayist
    "political": {"Q82955", "Q30461", "Q116", "Q1097498", "Q193391", "Q372436", "Q2304859"},
    "scientist": {"Q901", "Q169470", "Q593644", "Q864503", "Q170790", "Q11063", "Q212980", "Q39631"},
    "artist": {"Q483501", "Q1028181", "Q1281618", "Q639669", "Q36834", "Q2526255", "Q10800557",
               "Q33999", "Q2405480", "Q42973", "Q177220"},  # + architect, singer
    "religious": {"Q42603", "Q250867", "Q733786", "Q191808", "Q29182", "Q611644", "Q1234713"},
    "military": {"Q47064", "Q189290", "Q4991371", "Q1402561"},
    "educator": {"Q974144", "Q37226", "Q1231865", "Q1622272"},
}
GENDER = {"Q6581097": "male", "Q6581072": "female"}
TITLES = ["Generale", "Capitano", "Sommo Pontefice", "Sua Santità", "Re", "Regina", "Duca",
          "Duchessa", "Conte", "Contessa", "Professor", "Professore", "Prof.", "Don", "Donna",
          "Madonna", "Papà", "Cavaliere", "Barone", "Marchese", "Marchesa", "Monsignor", "San",
          "Santa", "Sant'", "Signora", "Signor", "Dott.", "Dottor"]

cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def save_cache():
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CACHE_FILE)


def get(params, retries=4):
    params = {**params, "format": "json"}
    wait = 2
    for attempt in range(retries):
        try:
            r = SESSION.get(API, params=params, timeout=TIMEOUT)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.RequestException(f"HTTP {r.status_code}")
            time.sleep(PAUSE)
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(wait)
            wait *= 2


def strip_title(name):
    for t in TITLES:
        if name.startswith(t + " ") or (t.endswith("'") and name.startswith(t)):
            return name[len(t):].strip()
    return name


def plausible(query, label):
    q = [t.lower() for t in query.split() if len(t) > 2]
    lab = {t.lower() for t in re.split(r"[\s\-]+", label)}
    if not q:
        return True
    overlap = sum(t in lab for t in q)
    return overlap == len(q) if len(q) <= 2 else overlap >= len(q) - 1


def year_of(claims, prop):
    for c in claims.get(prop, []):
        try:
            t = c["mainsnak"]["datavalue"]["value"]["time"]  # '+1835-07-27T00:00:00Z'
            return int(t[:5]) if t[0] in "+-" else int(t[:4])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def describe(entity):
    claims = entity.get("claims", {})
    occ = []
    for c in claims.get("P106", []):
        try:
            occ.append(c["mainsnak"]["datavalue"]["value"]["id"])
        except (KeyError, TypeError):
            pass
    g = None
    for c in claims.get("P21", []):
        try:
            g = GENDER.get(c["mainsnak"]["datavalue"]["value"]["id"], "other")
            break
        except (KeyError, TypeError):
            pass
    labels = entity.get("labels", {})
    label = (labels.get("it") or labels.get("en") or next(iter(labels.values()), {})).get("value", entity["id"])
    is_human = any(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
                   for c in claims.get("P31", []))
    return {
        "qid": entity["id"], "label": label, "human": is_human, "gender": g,
        "birth": year_of(claims, "P569"), "death": year_of(claims, "P570"),
        "occupations": occ, "categories": sorted(k for k, s in CODES.items() if s & set(occ)),
        "sitelinks": len(entity.get("sitelinks", {})),
    }


def fetch(qids):
    if not qids:
        return []
    data = get({"action": "wbgetentities", "ids": "|".join(qids[:50]),
                "props": "claims|sitelinks|labels", "languages": "it|en"})
    return [describe(e) for e in data.get("entities", {}).values() if "missing" not in e]


def choose(query, candidates, before_year):
    """Keep humans with a plausible label, born before the lecture; pick most sitelinks."""
    ok = [c for c in candidates if c["human"] and plausible(query, c["label"])
          and (before_year is None or c["birth"] is None or c["birth"] < before_year)]
    if not ok:
        return None, 0
    return max(ok, key=lambda c: c["sitelinks"]), len(ok)


def search(query, before_year):
    """Return (result_dict, network_error). Cached by (query, before_year)."""
    key = f"{query}||{before_year}"
    if key in cache:
        return cache[key], False
    try:
        hits = get({"action": "wbsearchentities", "search": query, "language": "it",
                    "uselang": "it", "type": "item", "limit": 10}).get("search", [])
        best, n = choose(query, fetch([h["id"] for h in hits]), before_year)
        tier = "direct"
        if best is None:
            hits = get({"action": "query", "list": "search", "srnamespace": 0, "srlimit": 10,
                        "srsearch": f"{query} haswbstatement:P31=Q5"}).get("query", {}).get("search", [])
            best, n = choose(query, fetch([h["title"] for h in hits]), before_year)
            tier = "fulltext"
    except (requests.RequestException, ValueError):
        return None, True
    res = {"found": best is not None, "tier": tier if best else "not_found", "n_human_candidates": n}
    if best:
        res.update(best)
    cache[key] = res
    return res, False


# ---------------------------------------------------------------- grouping (as in the pilot)
def first_token(name):
    t = name.split()
    return t[0].strip(".,;:") if len(t) > 1 else None


def compatible(a, b):
    if a is None or b is None:
        return True
    a, b = a.lower(), b.lower()
    return a == b or (a.endswith(".") and b.startswith(a[:-1])) or (b.endswith(".") and a.startswith(b[:-1]))


def group_by_surname(names):
    by_surname = defaultdict(list)
    for n in names:
        by_surname[n.split()[-1].strip(".,;:")].append(n)
    groups = {}
    for surname, variants in by_surname.items():
        full = [v for v in variants if len(v.split()) > 1]
        bare = [v for v in variants if len(v.split()) == 1]
        if len(full) <= 1:
            groups[full[0] if full else surname] = variants
            continue
        clusters = []
        for name in full:
            fn = first_token(name)
            for c in clusters:
                if compatible(fn, c["fn"]):
                    c["names"].append(name)
                    if fn and len(fn) > len(c["fn"] or ""):
                        c["fn"] = fn
                    break
            else:
                clusters.append({"fn": fn, "names": [name]})
        if len(clusters) == 1:
            groups[max(clusters[0]["names"], key=lambda v: len(v.split()))] = clusters[0]["names"] + bare
        else:
            for c in clusters:
                groups[max(c["names"], key=lambda v: len(v.split()))] = c["names"]
            if bare:
                groups[f"{surname} (bare, ambiguous)"] = bare
    return groups


# ---------------------------------------------------------------- main
first_year = {}
with open(MENZIONI, encoding="utf-8", newline="") as f:
    for r in csv.DictReader(f):
        y = int(r["anno"][:4]) if r["anno"][:4].isdigit() else None
        if y and (first_year.get(r["forma"]) is None or y < first_year[r["forma"]]):
            first_year[r["forma"]] = y
        first_year.setdefault(r["forma"], None)

groups = group_by_surname(list(first_year))
print(f"{len(first_year)} distinct forms -> {len(groups)} groups")

rows, form_rows, pending = [], [], []
for i, (gkey, variants) in enumerate(groups.items(), 1):
    rep = strip_title(max(variants, key=lambda v: (len(v.split()), len(v))))
    years = [first_year[v] for v in variants if first_year[v]]
    before = min(years) if years else None
    res, err = search(rep, before)
    tier_used = None
    if not err and not res["found"] and len(rep.split()) > 1:
        res2, err = search(rep.split()[-1], before)  # surname-only fallback
        if not err and res2["found"]:
            res, tier_used = dict(res2), "surname_only"
    if err:
        pending.append(gkey)
        status = "network_error"
        res = {"found": False}
    else:
        status = tier_used or res["tier"]
    rows.append({
        "group": gkey, "query": rep, "variants": " | ".join(sorted(variants)), "first_year": before or "",
        "status": status, "qid": res.get("qid", ""), "label": res.get("label", ""),
        "gender": res.get("gender") or "", "birth": res.get("birth") or "", "death": res.get("death") or "",
        "categories": ", ".join(res.get("categories", [])), "occupations": ", ".join(res.get("occupations", [])),
        "sitelinks": res.get("sitelinks", ""), "n_human_candidates": res.get("n_human_candidates", ""),
    })
    for v in variants:
        form_rows.append({"forma": v, "group": gkey, "qid": res.get("qid", "")})
    if i % 25 == 0:
        save_cache()
        print(f"  {i}/{len(groups)}  pending(network)={len(pending)}")
save_cache()

with open("entita.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
with open("forme_entita.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["forma", "group", "qid"])
    w.writeheader()
    w.writerows(form_rows)

found = sum(r["qid"] != "" for r in rows)
print(f"\nGroups: {len(rows)}  linked to a human: {found}  not found: "
      f"{sum(r['status'] == 'not_found' for r in rows)}  network errors: {len(pending)}")
if pending:
    print("Re-run the script to retry the groups that hit network errors (they are not cached).")
