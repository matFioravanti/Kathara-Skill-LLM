"""Check normalized DNS observations. Reads JSON; never runs lab commands."""
import argparse
from ipaddress import ip_address
import json
from pathlib import Path
import re


def within(name, zone):
    return zone == "." or name == zone or name.endswith("." + zone)


def usable(address):
    ip = ip_address(address)
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)



def gate_status(checks):
    """Summarize explicit check evidence, including missing tool checks."""
    checks = list(checks)
    if set(checks) - {"PASS", "FAIL", "UNVERIFIED"}:
        raise ValueError("Invalid check status")
    if "FAIL" in checks:
        return "FAIL"
    if not checks or "UNVERIFIED" in checks:
        return "UNVERIFIED"
    return "PASS"


def check_bind_and_records(data):
    """Optional resolved BIND declarations and RRsets, derived from final files."""
    errors = []
    for name, server in data["servers"].items():
        if "zone_types" not in server:
            continue
        types = server["zone_types"]
        if server["role"] == "resolver":
            if server.get("recursion") is not True or any(
                kind != "hint" or zone != "." for zone, kind in types.items()
            ):
                errors.append(f"{name}: resolver role conflicts with zone declarations")
        elif server["role"] == "authority":
            if server.get("recursion") is not False or any(
                kind not in ("master", "slave", "primary", "secondary")
                for kind in types.values()
            ):
                errors.append(f"{name}: authority role conflicts with zone declarations")
    # Both maps use absolute normalized owner names and canonical RDATA strings.
    if "required_records" in data or "records" in data:
        for owner, rrsets in data["required_records"].items():
            for kind, values in rrsets.items():
                actual = data["records"].get(owner, {}).get(kind, [])
                if set(actual) != set(values):
                    errors.append(f"{owner}: incorrect requested {kind} RRset")
    return errors


def check_dns(data):
    errors = []
    servers = data["servers"]
    for name, server in servers.items():
        network_ready = server["network_ready_at"]
        activations = server["activations"]
        late = [a for a in activations if a["at"] > network_ready]
        # Allow the v1 exception for one immutable early start plus one restart.
        valid_restart = (len(activations) == 2 and len(late) == 1
                         and late[0]["action"] == "restart"
                         and any(a["at"] <= network_ready and a["action"] == "start"
                                 for a in activations))
        if len(late) != 1 or not (len(activations) == 1 or valid_restart):
            errors.append(f"{name}: expected one effective BIND activation after networking")

    for client, required in data["clients"].items():
        # Observations are ordered from mounted file to last startup write.
        writes = data["resolver_writes"].get(client, [])
        effective = writes[-1] if writes else []
        expected = [ip_address(address) for address in required]
        if not expected or [ip_address(address) for address in effective] != expected:
            errors.append(f"{client}: missing or incorrect effective nameservers")
        for address in effective:
            ip = ip_address(address)
            owners = [name for name, server in servers.items()
                      if server["role"] == "resolver"
                      and ip in {ip_address(item) for item in server["addresses"]}]
            if ip.is_loopback:
                local = servers.get(client, {})
                valid = client in owners and str(ip) in local.get("verified_loopback", [])
            else:
                valid = usable(address) and bool(owners)
            if not valid:
                errors.append(f"{client}: no eligible resolver for {address}")

    zones = data["zones"]
    for zone in sorted(set(data["required_zones"]) - zones.keys()):
        errors.append(f"{zone}: missing required zone")
    for zone, observed in zones.items():
        if observed["soa_count"] != 1:
            errors.append(f"{zone}: expected one apex SOA")
        nameservers = observed["apex_ns"]
        if not nameservers:
            errors.append(f"{zone}: missing apex NS")
        parents = [candidate for candidate in zones
                   if candidate != zone and within(zone, candidate)]
        if not parents:
            if data["artificial_root"] and zone != ".":
                errors.append(f"{zone}: missing served path to artificial root")
            continue
        parent = max(parents, key=len)
        delegation = zones[parent]["delegations"].get(zone, {})
        if set(delegation.get("ns", [])) != set(nameservers):
            errors.append(f"{parent} -> {zone}: parent NS differ from child apex NS")
        for ns, addresses in nameservers.items():
            if within(ns, zone) and (not addresses or
                    {ip_address(ip) for ip in delegation.get("glue", {}).get(ns, [])}
                    != {ip_address(ip) for ip in addresses}):
                errors.append(f"{parent} -> {zone}: missing or mismatched glue for {ns}")
    return errors + check_bind_and_records(data)


_IMAGE = re.compile(rb'^\s*([a-zA-Z0-9_.-]+)\[image\]\s*=')


def check_topology(before, after, image_devices):
    """Check lab.conf and the preserved portions of shared/device startups."""
    def protected_conf(path):
        result = []
        for line in (path / "lab.conf").read_bytes().splitlines(keepends=True):
            image = _IMAGE.match(line)
            if not image or image[1].decode() not in image_devices:
                result.append(line)
        return result

    errors = []
    if protected_conf(before) != protected_conf(after):
        errors.append("lab.conf: topology or unapproved configuration changed")
    for startup in sorted(before.glob("*.startup")):
        candidate = after / startup.name
        original = startup.read_bytes()
        if not candidate.is_file():
            errors.append(f"{startup.name}: removed")
            continue
        current = candidate.read_bytes()
        # Only compare the protected prefix. The appended DNS commands still
        # require manual review, as do updates of older managed trailers.
        if startup.name == "shared.startup":
            preserved = current == original
        else:
            preserved = current == original or current.startswith(
                original if original.endswith(b"\n") else original + b"\n"
            )
        if not preserved:
            errors.append(f"{startup.name}: original commands changed")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    args = parser.parse_args()
    if (args.before is None) != (args.after is None):
        parser.error("--before and --after must be supplied together")
    try:
        data = json.loads(args.observation.read_text())
        errors = check_dns(data)
        gates = {gate: gate_status(checks) for gate, checks in data.get("gate_checks", {}).items()}
        if args.before is not None:
            errors += check_topology(args.before, args.after, data["image_devices"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(2, f"Invalid or incomplete audit input: {exc}\n")
    for gate, status in gates.items():
        print(f"{gate}: {status}")
    print("\n".join(errors) if errors else "No issues in supplied observations; complete the manual static gate.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
