---
name: kathara-dns
description: "Configure, extend, validate or repair BIND9 DNS in an EXISTING Kathara lab from natural language, JSON or YAML. Covers artificial roots, authoritative/secondary zones, NS/delegations/glue, recursive resolvers, client resolv.conf, forward/reverse records, IPv4/IPv6 and Kathara Lab Checker inputs. Preserve network topology and routing. Use for any Kathara task involving DNS, named, nameservers, zones or name resolution; not for building labs from scratch."
argument-hint: "Existing lab path + DNS requirements (zones, roles, records, clients, IP family, constraints)"
user-invocable: true
---

# Kathara DNS Configuration

Configure DNS in an existing Kathara lab; change only what the requested DNS behavior requires. Prefer verifiable configuration over plausible-looking output.

## 1. Contract and boundaries

- **Inputs:** lab path + free text/JSON/YAML. Extract positive requirements (P), prohibitions (N) and requested checks. Explicit request > existing lab evidence > defaults. Record nontrivial assumptions. Ask only if a missing decision is essential and no safe inference exists; otherwise proceed and report blocked items.
- **Allowed edits:** `<dev>[image]` in `lab.conf` (only to add BIND without breaking existing services); DNS files under `<dev>/etc/bind/`; client `<dev>/etc/resolv.conf` or `<dev>/etc/kathara-dns/resolv.conf`; DNS commands appended to `<dev>.startup`. Preserve every pre-existing startup line, `shared.startup`, non-DNS files and unrelated DNS zones. A previously skill-managed DNS trailer may be updated only when necessary; never touch original startup lines.
- **Never create/remove devices, links or interfaces; never modify addresses, routes, forwarding, MACs, `[ipv6]` flags or routing daemons.** Collision-domain identifiers are labels, not IP networks. Existing interfaces are up; no `ip link set up`. Runtime-only changes do not count as persistent fixes.
- **Do not fabricate role IPs:** NS/glue/hints, `masters`, transfers and client nameservers must use usable IPs configured on the assigned device. Explicit record values may point outside the lab if requested. Keep requested zone/host names unchanged (normalize DNS trailing dots only).
- **Role isolation:** authoritative = `recursion no`; recursive resolver = `recursion yes`, no authoritative zones (root **hint** is permitted). A host may serve several authoritative zones. Do not combine authoritative and resolver roles in one BIND instance without an explicitly requested, validated custom design; otherwise BLOCK that assignment.
- **Status:** `COMPLETE` = all P/N checks and static checks pass, no known unreachable dependencies; `PARTIAL` = some deliverables valid but others blocked/failed or required static tools are unavailable; `IMPOSSIBLE` = none feasible, leave lab unchanged. Report runtime `PASSED` / `FAILED` / `NOT_RUN` separately. Never claim end-to-end success from static checks alone.

## 2. Procedure (fixed order)

1. **Inventory** `lab.conf`, optional global `kathara.conf`, all `.startup`/`shared.startup`, device folders (`etc/bind`, existing `resolv.conf`, services/routing configs). Build `device | image | ethN→CD | IPv4/IPv6/prefix | routes | forwarding | services | DNS evidence`.
2. **Normalize** P/N into zones, authorities (primary/secondary), NS names, RRsets, resolvers, clients, families, reverse zones and tests. Recognize Kathara Lab Checker keys (§3).
3. **Plan before writing:** role→device→published IP; zone→parent→NS/glue; record→closest authoritative zone; client→resolver/family; image changes; dependent paths. Mark each item `OK/BLOCKED`, with reasons. Do not write yet.
4. **Apply only feasible items** using §4–§8. Reuse existing roles and configuration; avoid speculative changes. Preserve backups for rollback. For large record sets use a deterministic temporary generator (outside the lab), not hand-copied IPs.
5. **Validate** syntax, dependencies, diff, then runtime if available/authorized (§9). Repair minimal DNS defects and re-check. On irreparable failure, roll back this run's invalid item and its dependent changes.
6. **Report** roles, files, assumptions, blocked items, static result, runtime result and commands to reproduce failed checks. No verbose explanation of standard DNS concepts.

## 3. Inventory and interpretation

- `dev[N]="CD[/MAC]"` maps `ethN` to a collision domain; IPs come from startup commands/files (`ip addr add`, `ifconfig`, including IPv6), **not** from `CD`. Inspect routes in both directions. Dynamic routing implies `UNVERIFIED`, not automatically unreachable.
- Classify routers via forwarding/routing process or routing image (FRR, Quagga, BIRD, OpenBGPD); switches/controllers via image. Never change those images. An explicitly requested router can be a DNS server only if its current image already supports BIND and port 53 does not conflict; otherwise BLOCK. Routers can be DNS **clients** when explicitly requested.
- Use `kathara.conf` `image` and `enable_ipv6` if accessible; absent `[image]` inherits the **configured** default (`kathara/base` only if unchanged). `[ipv6]` overrides the global IPv6 flag. If effective IPv6 state cannot be established, mark IPv6 feasibility `UNVERIFIED`, not guaranteed.
- Recognize input aliases: `authoritative/auth/ns` = authorities, `local_ns/ldns/recursive` = resolvers, `records/hosts` = RRsets, `slave` = secondary. Checker form is nested under `test.applications.dns`: `authoritative: {zone:[server_ip...]}` = authority IPs; `local_ns: {resolver_ip:[client...]}` = client resolver assignment; `records: {TYPE:{fqdn:[values...]}}` = exact RRsets. Separately, `test.reachability: {device:[ip_or_dns_name...]}` specifies reachability from each device; `test.ip_mapping` cross-checks inventory (configured lab addresses win; role IP mismatches BLOCK).
- Infer roles in order: explicit device/IP owner → existing BIND/description → device name → free non-router host near consumers. Prefer reusing BIND-capable images; avoid hosts running dnsmasq on port 53. Do not silently repurpose explicitly client-only devices. If no safe candidate, BLOCK. Choose resolver per explicit mapping → same reachable subnet → shortest known route → unique resolver.
- Select server's published IP per family: explicit owned address → interface on a reachable path to parent/resolver/clients → appropriate routed interface → lowest-numbered usable interface. Exclude loopback, IPv6 link-local (`fe80::/10`), missing-interface and unconfigured addresses. Test both forward and return paths.
- Defaults: IPv4 if unspecified and viable; include IPv6 only when requested or the required path is IPv6-only. No reverse zones, secondaries, forwarders, search domains or DNSSEC unless requested. Create an artificial root only if requested or needed for autonomous recursive resolution inside the lab; never replace an existing functioning external hierarchy without a requirement. Derive unprovided NS labels deterministically (`ns1.<zone>.`, etc.; root e.g. `a.root-servers.`), ensuring they are not occluded by delegations.
- Unspecified zone for an RR: use the **deepest existing/planned authoritative suffix**; create a parent zone only when an authoritative server can safely be assigned. No zone/device inference solely from an arbitrary collision-domain label. Report unresolved placement.

## 4. Images, file placement, boot order

- Files under `<lab>/<dev>/` are copied to the device's `/`; `shared.startup` executes before `<dev>.startup`. An earlier startup command can therefore overwrite `etc/resolv.conf`. Keep service starts after address/route setup.
- BIND available in `kathara/bind` and `kathara/base`; `core` lacks BIND. Preserve matching images/tags; `core`→`bind` only on an assigned BIND server. For Apache or other required services, change to a **verified** superset (e.g. `base`) only if compatible. Unknown/routing image: do not replace; BLOCK if BIND is unavailable. Default image may be overridden globally.
- BIND files: `<dev>/etc/bind/named.conf`, `db.root` for authoritative `.`, `db.<zone>` for other primary zones, `db.hints` for resolvers; secondary zone files belong in `/var/cache/bind/` and are populated by transfers. Never point two zone declarations on one device at the same zone.
- Start BIND exactly once **after** networking: normally append `systemctl start named` on modern BIND or `systemctl start bind9` for verified legacy 9.11 images; preserve an existing suitable start command. If one runs before addressing and restart is needed, append a single restart. A blocking foreground command earlier in startup is a BLOCKER. Match the installed unit/image version instead of assuming every tag uses 9.18.
- Never include `named.conf.default-zones` in a generated config for artificial-root authorities or resolvers: it can conflict with `zone "."`. For an existing unmanaged config, preserve unrelated options/includes and remove only conflicting DNS statements. Do not introduce duplicate `options` or `zone` clauses.

## 5. BIND configuration (generate complete files only when new/managed)

**Authoritative** (`.` uses file `db.root`; ordinary zones use `db.<zone>`):

```conf
options { directory "/var/cache/bind"; recursion no; allow-query { any; };
  dnssec-validation no; listen-on { any; }; listen-on-v6 { any; }; };
zone "<zone>" { type master; file "/etc/bind/db.<zone>"; };  // for zone "." use db.root
```

**Recursive resolver for an unsigned artificial root:**

```conf
options { directory "/var/cache/bind"; recursion yes;
  allow-query { any; }; allow-recursion { any; }; allow-query-cache { any; };
  dnssec-validation no; empty-zones-enable no;
  listen-on { any; }; listen-on-v6 { any; }; };
zone "." { type hint; file "/etc/bind/db.hints"; };
```

- `allow-recursion`/`allow-query-cache`: permit all intended lab client subnets (use `any` only for an isolated lab when necessary). `empty-zones-enable no` prevents built-in private reverse zones from masking requested lab reverse delegations. `dnssec-validation no` applies to **unsigned artificial roots**, not to a request requiring DNSSEC validation; if DNSSEC signing/trust anchors are explicitly required and cannot be configured/validated, mark them BLOCKED rather than silently disabling them.
- Secondary: `zone "<zone>" { type slave; masters { <primary_ip>; }; file "/var/cache/bind/db.<zone>"; };` and on primary `allow-transfer { <secondary_ip>; }; also-notify { <secondary_ip>; };`. Verify reachability/permissions and multi-homed notify sources.
- No default Internet forwarders in isolated labs. If explicitly required, configure and verify reachability/authority of the forwarder; `forward only` prevents fallback to the artificial root. Preserve BIND 9.11/9.18 syntax (`type master/slave`, `masters`); avoid obsolete `dnssec-enable`, `dnssec-lookaside` and unsupported options.
- If fixing an existing authoritative with recursion enabled, change it to `recursion no` only when compatible with existing roles. If not safe, BLOCK the requested change; never silently accept mixed roles. Likewise a resolver retaining authoritative zones cannot be reported COMPLETE under this design.

## 6. Zone data, delegation, DNS records

```dns
$TTL 300
@ IN SOA <primary-ns-fqdn> <rname-fqdn> ( 1 3600 600 86400 60 )
@ IN NS <ns-fqdn>
<ns-fqdn> IN A <owned-v4>          ; include when usable/required
<ns-fqdn> IN AAAA <owned-v6>       ; include when usable/required
```

- All absolute FQDNs end with `.`. For a root SOA, RNAME is `hostmaster.` (never `hostmaster..`); other zones use `hostmaster.<zone>.`. Serial: `1` new; increment only when existing zone content changes, not on identical reruns. Preserve unrelated existing RRsets.
- One SOA and an apex NS set per zone; every in-zone NS has the needed authoritative A/AAAA. Every listed NS must actually serve the zone. Multiple authorities for the same zone need identical zone data (secondaries transfer, independent primaries replicate consistently).
- Delegate a child in its **closest served parent**: parent `child. NS ns.child.`; if the NS name lies inside the delegated child, put matching A/AAAA **glue** in the parent. Child apex NS set must match delegation. Never add unrelated child records below a delegation in the parent; only glue is allowed there. Do not place root NS names beneath any delegated TLD. Out-of-bailiwick NS requires a resolvable path, not invented glue.
- Generate `db.hints` only for resolvers: `. IN NS <root-ns-fqdn>` plus `<root-ns-fqdn> IN A/AAAA <root-owned-address>` for each actual root, matching root apex NS names. No public Internet roots in an artificial-root hierarchy. `CNAME` cannot coexist with other data at its owner; NS/MX targets cannot be CNAME; MX/SRV targets must resolve. Preserve exact requested record values and cardinality.
- Reverse only if requested: IPv4 octet-reversed `in-addr.arpa`, IPv6 nibble-reversed `ip6.arpa`; delegate like forward zones. Non-octet IPv4 delegation needs an explicitly supported RFC 2317 design; do not invent one. PTR targets use absolute FQDNs.

## 7. IPv4 and IPv6

- **DNS transport** (querying server via v4/v6) is independent of **RR type** (A/AAAA). Preserve explicitly requested AAAA even if the DNS query travels over IPv4, and vice versa.
- A required transport family is feasible only if enabled, every necessary DNS endpoint has an owned usable address of that family, and client↔resolver↔authorities (and secondary↔primary) paths are plausible **both ways**. A missing/disabled family is BLOCKED, not just a warning.
- Automatic NS addresses, glue, hints and `nameserver` entries must match feasible family/families; never invent a missing A/AAAA. For requested dual-stack, both required families must pass; if only one is feasible, configure that independent subset and report `PARTIAL`. Data RRsets requested explicitly are never silently discarded due to transport selection.
- A pre-existing `[ipv6]=false` or disabled global IPv6 is not silently changed. Report the exact enabling prerequisite. An IPv6-only checker expecting A records is incompatible; warn, do not fake an IPv4 address.

## 8. Client resolv.conf and idempotence

- Assign only recursive resolvers, never authoritative/root-only servers. For each client, put reachable resolver addresses first (at most 3 `nameserver` lines, one per required usable address; `search` only when requested). Do not confuse DNS family with the A/AAAA type requested.
- **If neither shared nor device startup writes `resolv.conf`:** write `<dev>/etc/resolv.conf` as a complete, deterministic file.
- **If any startup writes it:** write `<dev>/etc/kathara-dns/resolv.conf`, then append exactly once as the last relevant command in `<dev>.startup`: `cat /etc/kathara-dns/resolv.conf > /etc/resolv.conf`. Redirection changes contents without replacing the target inode. On later reruns update only the managed source, not the original startup lines. If later non-DNS commands overwrite the resolver, BLOCK/report rather than rearranging them.
- If a skill-managed trailer already exists, keep one active copy; never add duplicate starts or resolver overrides. Generate managed files in deterministic order. Re-run of an unchanged request must produce byte-identical files (including serials). Never delete unreferenced pre-existing files without permission.

## 9. Validation and diagnosis

**Static, mandatory before declaring success:**
1. Use `named-checkzone <zone> <host-path-to-zonefile>` (root: `.` and `db.root`) and `named-checkconf <host-path-to-named.conf>` if available; latter checks syntax only on host (container absolute paths do not resolve there). For zone-load check, use `named-checkconf -z` **inside** matching container/image if available. If syntax tools are unavailable report static `LIMITED`, not `PASS`.
2. Traverse **each** requested root→parent→child→record chain: server ownership; matching parent/child NS; correct glue IP; no cycles/occluded data/duplicate zones; proper hints; no conflicting role settings; exact required RRsets.
3. Validate every intended client effective nameserver after `shared.startup` and device startup; check required IPv4/IPv6 address ownership, all forward/return routes (dynamic routing = `UNVERIFIED`); check every N constraint.
4. Diff against pre-run state: no topology/address/routing changes; only permitted DNS files, image changes and startup additions. Roll back invalid edits, keeping unrelated configuration intact.

**Runtime, on the newly applied configuration only:**
- Edits to lab files do **not** automatically update already running devices. Validate only after a fresh start/restart explicitly authorized by the user, or when no changes were made and the running lab matches the checked files. Otherwise set runtime `NOT_RUN` (pending restart). Never automatically `lclean`, `wipe` or restart an unrelated running lab.
- Use separate commands, checking output/exit status after each: `kathara exec -d <lab> --wait <dev> -- <command>` (or run from the lab directory).
- Authority: `dig @<auth-ip> <zone> SOA +norecurse` → NOERROR + `aa`; check `NS` and each NS address directly against the authority. Secondary: authoritative SOA/serial after transfer.
- Resolver: `dig @<resolver-ip> <fqdn> <TYPE>` → NOERROR, expected RRset, `ra`; check both transports where required (`dig -4/-6`). Client: `cat /etc/resolv.conf` then `dig <fqdn> <TYPE>` and requested reverse/CNAME/MX lookups; compare answers. Test at least one end-to-end lookup per requested zone/client class and each required transport.
- Diagnose: `REFUSED` → ACL/recursion/unloaded zone; `SERVFAIL` → delegation/glue, DNSSEC, upstream or reachability; `NXDOMAIN` → wrong zone/occlusion/missing record; timeout → routes, service or listen address. Service running is not proof that a zone loaded. Inspect startup logs and server query results, then persist fixes in lab files and rerun failing checks.
- If runtime unavailable, report `NOT_RUN`, static outcome and concrete commands for later testing. Distinguish a static pass from verified end-to-end DNS success.

## 10. Final report (compact)

`Status: COMPLETE|PARTIAL|IMPOSSIBLE; static: PASS|FAIL|LIMITED; runtime: PASSED|FAILED|NOT_RUN`
`Roles: zone→device (IP, NS); resolvers→device; clients→resolver`
`Changes: created/edited files; image replacements; startup additions`
`Delegations: parent→child (NS, glue); records/reverse summary`
`Assumptions; BLOCKED/unreachable/UNVERIFIED items and exact reason; violated N constraints (if any)`
`Failed checks / next executable dig checks (only if needed)`

## Official references (consult for platform/version-specific uncertainties)

- [Kathara lab directory/startup semantics](https://www.kathara.org/man-pages/kathara-lab-dirs.7.html)
- [Kathara lab.conf syntax](https://www.kathara.org/man-pages/kathara-lab.conf.5.html) and [global defaults](https://www.kathara.org/man-pages/kathara.conf.5.html)
- [Kathara exec](https://www.kathara.org/man-pages/kathara-exec.1.html), [lstart](https://www.kathara.org/man-pages/kathara-lstart.1.html)
- [Kathara Docker images](https://github.com/KatharaFramework/Docker-Images)
- [BIND 9 ARM](https://bind9.readthedocs.io/en/bind-9.18/reference.html) and [Kathara Lab Checker](https://github.com/KatharaFramework/kathara-lab-checker)
