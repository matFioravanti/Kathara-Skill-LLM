---
name: kathara-dns-config
description: "Configure DNS (BIND9 authoritative servers, artificial root, TLD/child zones, delegations, glue, recursive resolvers, client resolv.conf) inside an EXISTING Kathara lab from a natural-language request. Use whenever a task asks to add, fix or change DNS/BIND/named/root server/resolver/zone/delegation behavior in a Kathara lab, even if not phrased as 'DNS skill'. Not for creating labs from scratch or configuring routing."
argument-hint: "Lab path + DNS request (zones, roles, host records, IP families)"
user-invocable: true
---

# Kathara DNS Configuration

Modify an existing lab so its DNS hierarchy works. Non-interactive: never ask questions; resolve ambiguity with the rules below and list assumptions in the final report. Dynamic validation (`kathara lstart`, `dig`) is done externally: do not run kathara commands.

## Invariants
1. `lab.conf`: change only `<dev>[image]=` lines, only for devices that must run `named`. No new devices/interfaces/collision domains; collision-domain names are labels, not addressing.
2. Preserve every existing line of `.startup` and `<dev>/` files (addresses, routes, routing daemons). Only append DNS lines at the end; never reorder or delete.
3. Never add/change IPs or routes. Use IPs exactly as configured in the lab; never invent any. If a required IP/route is missing or a DNS path is unreachable, report it as a warning; do not fix silently.
4. Use zone/host names from the request verbatim.
5. Role separation: authoritative servers have `recursion no`; resolvers hold no authoritative zones (only root hints). One device holds several roles only if the request says so.
6. Interfaces are already up (no `ip link set up`). Persist everything in lab files; interactive changes are ephemeral. Services via `systemctl`.

## Procedure
1. Inventory: from `lab.conf` (devices, images, interfaces→domains), each `.startup` (IPv4/IPv6 per interface, routes, forwarding, daemons), existing `<dev>/etc/bind/*`, `LAB_DESCRIPTION`. Build table dev → {iface, ip4, ip6, domain, image, role hints}.
2. Parse request: zone tree, server roles, host records, resolvers/clients, IP families, extras (secondary, reverse, forwarders).
3. Assign roles, set images, write files, append startup lines, self-check, report.

## Role assignment (first match wins)
1. Explicit in request.
2. Lab evidence: device names (dns, ns, root, tld, auth, resolver), existing bind files, `named` in a startup, `LAB_DESCRIPTION`.
3. Topology: prefer leaf hosts.
- Router = image frr/quagga/bird*/openbgpd/openvswitch/bmv2, or startup enables forwarding/starts a routing daemon. Never give DNS roles to routers/switches; if no host is left, report.
- One distinct device per role (root, each zone's servers, resolver) unless the request merges them.
- Clients: devices named in the request; else non-DNS hosts.
- Client's resolver: the one named in the request; else the resolver on the same collision domain; else the only resolver.
- Secondary servers only if requested.
- Server address to publish (glue, hints, NS A records): the interface IP reachable from the querying side (parent/resolver), not an arbitrary interface.

## Images, files, service
- Devices running `named` need `kathara/bind` (or `kathara/base`): if current image lacks BIND set `<dev>[image]="kathara/bind"`. Never change the image of a router/routing-daemon device or of devices with no DNS server role.
- Files go in `<dev>/etc/bind/`: `named.conf` (create; if it exists, edit and keep unrelated zones), `db.<zone>`, and `db.hints` on resolvers.
- `named.conf` must be complete and must NOT include `named.conf.default-zones` (it defines a built-in `zone "."` that conflicts with the artificial root and relies on Internet roots).
- Last DNS line of the device's `.startup`, after all network lines: `systemctl restart named` (`bind9` is an alias). Do not duplicate an existing one.

## named.conf templates
Authoritative (primary):
```
options { directory "/var/cache/bind"; recursion no; allow-query { any; };
  dnssec-validation no; listen-on { any; }; listen-on-v6 { any; }; };
zone "<zone>" { type master; file "/etc/bind/db.<zone>"; };
```
Secondary: `type slave; masters { <primary_ip>; }; file "/var/cache/bind/db.<zone>";` and on the primary add `allow-transfer { <secondary_ip>; };`.

Recursive resolver:
```
options { directory "/var/cache/bind"; recursion yes; allow-recursion { any; }; allow-query { any; };
  dnssec-validation no; listen-on { any; }; listen-on-v6 { any; }; };
zone "." { type hint; file "/etc/bind/db.hints"; };
```
- Isolated lab: resolvers MUST use the lab's artificial root via explicit root hints; NO `forwarders` unless the request requires them; never rely on BIND's built-in Internet root hints.
- `dnssec-validation no` on all `named` while the hierarchy is unsigned (default `auto` gives SERVFAIL).
- `allow-recursion any` is required: the default (localnets) answers REFUSED to other lab hosts.

`db.hints` (one NS + address line per root server, using the root server's own IPs):
```
.                 3600000 IN NS <rootns>.
<rootns>.         3600000 IN A  <root_ip4>
<rootns>.         3600000 IN AAAA <root_ip6>   ; only if IPv6 required
```

## Zone file rules
```
$TTL 3600
@ IN SOA <ns>. hostmaster.<zone>. ( 1 3600 900 604800 300 )
@ IN NS  <ns>.
<ns-label> IN A <ip>
```
- Trailing dot on every absolute name (missing dot → `ns1.zone.zone.`).
- Every zone: SOA, apex NS, address record for each in-zone NS name.
- Delegation in parent: `<child> IN NS <ns>.` per child NS. Glue (A/AAAA) in the parent iff the NS name is inside the delegated child zone; glue IP must equal the child server's real IP. Out-of-bailiwick NS names need no glue but must resolve through the hierarchy.
- Child apex NS set must equal the parent's delegation NS set; each listed NS device must actually serve the zone.
- Records under a delegation point in the parent are occluded: keep child host records only in the child zone (glue excepted).
- Root zone: root NS names must not fall under a TLD delegated in that zone (e.g. use `a.root-servers.` if `root-servers.` is not delegated), otherwise they become occluded glue.
- NS/MX targets are never CNAMEs.
- Host records only for names in the request plus NS names; IPs from the lab.
- IPv6: add AAAA (server names, glue, hints) only if the request requires IPv6/dual-stack, using the IPv6 already configured on the same interface. IPv4-only request → no AAAA.
- Reverse zones only if requested; same delegation rules (`in-addr.arpa` octets reversed, `ip6.arpa` nibble-reversed).
- Bump SOA serial only when editing an existing zone.

## Clients
- Append to client `.startup`: `echo "nameserver <resolver_ip>" > /etc/resolv.conf` (overwrite with `>`, never `>>`). One `nameserver` per required family. Add `search <domain>` only if requested.
- Never point clients at an authoritative-only server or a root. Leave `resolv.conf` of server devices unchanged unless requested.

## Plausible-but-wrong (check before finishing)
- Authoritative server with `recursion yes`, or resolver serving zones.
- `forwarders` in an isolated lab; hints pointing to a non-root server.
- Glue missing, or glue IP ≠ actual IP; parent/child NS mismatch (lame delegation).
- Zone syntax error: `named` still starts, the zone is unloaded (REFUSED/SERVFAIL). Service active ≠ config correct.
- Image changed on a router; `default-zones` included; DNSSEC left on.
- Existing addresses/routes/daemons removed or altered.

## Static self-check
- If available locally: `named-checkzone <zone> <lab>/<dev>/etc/bind/db.<zone>` per zone; `named-checkconf <lab>/<dev>/etc/bind/named.conf` (syntax only, no `-z`: paths are container paths).
- Manual: each requested zone is served by the assigned device; every delegation chain from the root reaches every requested name; every resolver hint IP is a root server IP; every client has the right `nameserver`; no unintended edits (diff against original).

## External acceptance checks (config must satisfy these)
- Authoritative: `dig @<auth_ip> <zone> SOA +norecurse` → NOERROR, `aa` flag.
- Resolver: `dig @<resolver_ip> <name> A` → NOERROR, `ra` flag, expected answer; `+trace` succeeds only with a correct delegation/glue chain.
- Client: `dig <name>` (via `resolv.conf`) returns the same answer.
- Failure map: REFUSED = allow-query/recursion or zone not loaded; SERVFAIL = broken delegation/glue, DNSSEC or unreachable server; NXDOMAIN = missing/occluded record; timeout = routing, listen or service down.

## Final report (max 6 lines)
Role→device map; files created/edited; images changed; assumptions; warnings (missing IPs/routes, unreachable paths).

## References
- `lab.conf`: https://www.kathara.org/man-pages/kathara-lab.conf.5.html
- Images: https://github.com/KatharaFramework/Docker-Images/tree/develop
- Example labs: https://github.com/KatharaFramework/Kathara-Labs
- BIND 9 statements: https://bind9.readthedocs.io/en/v9.18-branch/reference.html
