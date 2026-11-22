#!/usr/bin/env python3
"""Scansione statica delle run del benchmark Kathara (nessuna chiamata a modelli).

Per ogni run cerca nei file generati in <run>/lab/:
  1. ACL dei resolver che bloccherebbero una query diretta all'IP del resolver stesso
     (causa dei REFUSED su CS08): allow-query / allow-recursion / allow-query-cache.
  2. Nomi NS fuori zona, o senza record A nel file di zona del server autorevole
     (causa degli indirizzi NS vuoti su CS08).
  3. Dispositivi con named.conf ma senza una riga di avvio di named nello startup (CS05).

Uso:
  python scan_dns_runs.py [runs_dir] [--mode dns_only --mode both_forced] [--csv out.csv]

La struttura attesa e' .../<albero>/<size>/<prompt>/<skill_mode>/rNNN/lab/ ; size, prompt e
modo sono letti dagli ultimi componenti del percorso.
"""
import argparse
import csv
import ipaddress
import re
import sys
from collections import defaultdict
from pathlib import Path

RUN_RE = re.compile(r"^r\d{3}$")
ACL_OPTS = ("allow-query", "allow-recursion", "allow-query-cache")


# ---------- utilita' ----------
def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def strip_conf_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"(?m)^\s*#.*$", "", text)


def device_ips(lab, dev):
    """IP configurati (escluso loopback) letti da shared.startup e <dev>.startup."""
    text = read(lab / "shared.startup") + "\n" + read(lab / f"{dev}.startup")
    ips = []
    for m in re.finditer(r"ip\s+(?:-[46]\s+)?addr(?:ess)?\s+add\s+([0-9a-fA-F:.]+)(?:/(\d+))?", text):
        ips.append(m.group(1))
    for m in re.finditer(r"ifconfig\s+\S+\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", text):
        ips.append(m.group(1))
    out = []
    for ip in ips:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not a.is_loopback and not a.is_link_local:
            out.append(a)
    return out


# ---------- controllo 1: ACL del resolver ----------
def parse_acls(conf):
    acls = {}
    for m in re.finditer(r'acl\s+"?([\w.-]+)"?\s*\{([^}]*)\}\s*;', conf):
        acls[m.group(1)] = [e.strip() for e in m.group(2).split(";") if e.strip()]
    return acls


def expand(entries, acls, depth=0):
    out = []
    for e in entries:
        neg = e.startswith("!")
        name = e[1:].strip() if neg else e
        if name in acls and depth < 3:
            sub = expand(acls[name], acls, depth + 1)
            out.extend([("!" + s if neg and not s.startswith("!") else s) for s in sub])
        else:
            out.append(e)
    return out


def allowed(ip, entries):
    """Prima corrispondenza vince, come in BIND. Ritorna True/False/None (nessuna)."""
    for e in entries:
        neg = e.startswith("!")
        name = (e[1:] if neg else e).strip()
        if name in ("any", "localhost", "localnets"):
            # per un IP del server stesso, localhost e localnets corrispondono sempre
            hit = True
        elif name == "none":
            hit = True
            return False if not neg else None
        else:
            try:
                hit = ip in ipaddress.ip_network(name, strict=False) if "/" in name else ip == ipaddress.ip_address(name)
            except ValueError:
                hit = False
        if hit:
            return not neg
    return None


def check_resolver_acl(lab, dev, conf, issues):
    if not re.search(r"recursion\s+yes", conf):
        return
    acls = parse_acls(conf)
    ips = device_ips(lab, dev)
    for opt in ACL_OPTS:
        m = re.search(rf"{opt}\s*\{{([^}}]*)\}}\s*;", conf)
        if not m:
            continue  # default BIND: localnets + localhost, ammette l'IP locale
        entries = expand([e.strip() for e in m.group(1).split(";") if e.strip()], acls)
        if not ips:
            issues["acl_indeterminato"].append(f"{dev}:{opt}")
            continue
        if not any(allowed(ip, entries) for ip in ips):
            issues["acl_bloccante"].append(f"{dev}:{opt}")


# ---------- controllo 2: nomi NS ----------
def parse_zone(text, zone):
    base = "." if zone == "." else zone.lower().rstrip(".") + "."
    origin = base
    text = re.sub(r";[^\n]*", "", text)
    text = re.sub(r"\([^)]*\)", lambda m: m.group(0).replace("\n", " "), text, flags=re.S)

    def absname(n):
        n = n.lower()
        if n == "@":
            return origin
        if n.endswith("."):
            return n
        return n + "." if origin == "." else f"{n}.{origin}"

    recs, last = [], origin
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.upper().startswith("$ORIGIN"):
            origin = absname(line.split()[1])
            continue
        if line.startswith("$"):
            continue
        toks = line.replace("(", " ").replace(")", " ").split()
        if line[0] in " \t":
            owner = last
        else:
            owner = absname(toks.pop(0))
            last = owner
        while toks and re.fullmatch(r"\d+[smhdwSMHDW]?|IN|CH|HS", toks[0], re.I):
            toks.pop(0)
        if len(toks) < 2:
            continue
        rtype = toks.pop(0).upper()
        recs.append((owner, rtype, [t for t in toks]))
    return base, recs, absname


def check_ns(lab, dev, conf, issues):
    for m in re.finditer(r'zone\s+"([^"]+)"\s*\{([^}]*)\}', conf):
        zone, body = m.group(1), m.group(2)
        if not re.search(r"type\s+(master|primary)", body):
            continue
        f = re.search(r'file\s+"([^"]+)"', body)
        if not f:
            continue
        zpath = lab / dev / f.group(1).lstrip("/")
        text = read(zpath)
        if not text:
            issues["zona_file_mancante"].append(f"{dev}:{zone}")
            continue
        base, recs, absname = parse_zone(text, zone)
        names_with_addr = {o for (o, t, _) in recs if t in ("A", "AAAA")}
        for owner, rtype, rd in recs:
            if rtype != "NS" or owner != base:
                continue
            target = absname(rd[0])
            inside = base == "." or target == base or target.endswith("." + base)
            if not inside:
                issues["ns_fuori_zona"].append(f"{dev}:{zone}->{target}")
            elif target not in names_with_addr:
                issues["ns_senza_A"].append(f"{dev}:{zone}->{target}")


# ---------- controllo 3: avvio di named ----------
START_RE = re.compile(
    r"(systemctl\s+(?:re)?start\s+(?:named|bind9)\b"
    r"|service\s+(?:named|bind9)\s+(?:re)?start"
    r"|/etc/init\.d/(?:named|bind9)\s+(?:re)?start"
    r"|(?:^|[;&|\s])(?:/usr/sbin/)?named(?:\s+-[A-Za-z]|\s*(?:&|;|$)))",
    re.M,
)


def check_start(lab, dev, issues):
    text = "\n".join(l for l in (read(lab / "shared.startup") + "\n" + read(lab / f"{dev}.startup")).splitlines()
                     if not l.strip().startswith("#"))
    if not START_RE.search(text):
        issues["named_senza_avvio"].append(dev)


# ---------- scansione ----------
def scan_run(lab):
    issues = defaultdict(list)
    for conf_path in sorted(lab.glob("*/etc/bind/named.conf")):
        dev = conf_path.parts[len(lab.parts)]
        conf = strip_conf_comments(read(conf_path))
        check_resolver_acl(lab, dev, conf, issues)
        check_ns(lab, dev, conf, issues)
        check_start(lab, dev, issues)
    return issues


def find_runs(root):
    for lab in sorted(root.rglob("lab")):
        if lab.is_dir() and RUN_RE.match(lab.parent.name) and (lab / "lab.conf").exists():
            yield lab


COLS = ["acl_bloccante", "acl_indeterminato", "ns_fuori_zona", "ns_senza_A", "named_senza_avvio", "zona_file_mancante"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs_dir", nargs="?", default="runs")
    ap.add_argument("--mode", action="append", help="limita a uno o piu' skill_mode")
    ap.add_argument("--csv", default="dns_static_scan.csv")
    args = ap.parse_args()

    root = Path(args.runs_dir)
    if not root.is_dir():
        sys.exit(f"Cartella non trovata: {root}")

    rows, summary = [], defaultdict(lambda: defaultdict(int))
    for lab in find_runs(root):
        run_dir = lab.parent
        parts = run_dir.relative_to(root).parts
        mode = parts[-2] if len(parts) >= 2 else ""
        if args.mode and mode not in args.mode:
            continue
        prompt = parts[-3] if len(parts) >= 3 else ""
        size = parts[-4] if len(parts) >= 4 else ""
        issues = scan_run(lab)
        row = {"run": "/".join(parts), "mode": mode, "prompt": prompt, "size": size}
        for c in COLS:
            row[c] = "; ".join(issues.get(c, []))
        rows.append(row)
        key = (mode, prompt, size)
        summary[key]["run"] += 1
        for c in COLS:
            if issues.get(c):
                summary[key][c] += 1

    if not rows:
        sys.exit("Nessuna run trovata (cerco cartelle lab/ con lab.conf dentro rNNN).")

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "mode", "prompt", "size"] + COLS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} run scansionate -> {args.csv}\n")
    print(f"{'mode':14} {'prompt':6} {'size':8} {'run':>4} {'ACL':>5} {'NS fuori':>9} {'NS senza A':>11} {'no avvio':>9}")
    for (mode, prompt, size), s in sorted(summary.items()):
        print(f"{mode:14} {prompt:6} {size:8} {s['run']:>4} {s['acl_bloccante']:>5} "
              f"{s['ns_fuori_zona']:>9} {s['ns_senza_A']:>11} {s['named_senza_avvio']:>9}")
    flagged = [r for r in rows if any(r[c] for c in ("acl_bloccante", "ns_fuori_zona", "ns_senza_A", "named_senza_avvio"))]
    print(f"\nRun con almeno un problema: {len(flagged)}")
    for r in flagged:
        print(f"- {r['run']}")
        for c in ("acl_bloccante", "ns_fuori_zona", "ns_senza_A", "named_senza_avvio"):
            if r[c]:
                print(f"    {c}: {r[c]}")


if __name__ == "__main__":
    main()
