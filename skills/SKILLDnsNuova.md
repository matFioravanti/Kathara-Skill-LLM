---
name: kathara-dns
description: "Configure, extend or repair DNS with BIND9 inside an EXISTING Kathara lab: artificial root, TLDs and child zones, delegations and glue, primary/secondary authoritative servers, recursive resolvers, reverse zones and client resolv.conf, over IPv4, IPv6 or dual-stack. Accepts natural-language, JSON or YAML requests. Use whenever a task touches DNS, BIND, named, root servers, resolvers, zones, delegations or nameservers in a Kathara lab, even if not phrased as 'DNS skill'. Never changes topology, addressing or routing. Not for creating labs from scratch or configuring routing."
argument-hint: "Lab path + DNS request (zones, server roles, host records, resolvers/clients, IP family), as free text, JSON or YAML"
user-invocable: true
---

# Kathara DNS Configuration

Add, change or repair the DNS layer of an existing Kathara lab so that every requested name resolves through a self-contained DNS hierarchy, without touching the network underneath.

## 0. Operating mode
- **Non-interactive.** Never ask questions. Fill gaps with the defaults in §5, record each choice as an assumption, and list it in the report.
- **No `kathara` commands** (`lstart`, `exec`, `connect`, ...): dynamic validation happens externally. Static tools (`named-checkconf`, `named-checkzone`, `docker run` of a BIND image) are allowed when available.
- **Partial success, never silent failure.** Build everything that is feasible. Skip any requested item that would require breaking an invariant, and report why it was skipped.

## 1. Invariants (never violate)
1. **The network stays as it is.** In `lab.conf`, only add or change `<dev>[image]=` lines, and only for devices that will run `named`. Never add or remove devices, interfaces, collision domains or options such as `ipv6`, `sysctl`, `bridged` or `exec`.
2. **Existing files are preserved.** In `.startup` files, never delete, reorder or edit lines that aren't about DNS: only append at the end. In `<dev>/` folders, only create or edit DNS files (`etc/bind/*`, `etc/resolv.conf`). Existing DNS lines and files (BIND config, zone files, `resolv.conf` writes) may be edited only when the request requires it.
3. **No invented addresses.** Every IP used for a server role (NS address, glue, hint, `masters`, `allow-transfer`, `resolv.conf`) must already be configured on that device in the lab. Never add IPs or routes. A missing address or an unreachable path produces a warning, not a fix.
4. **Names are used verbatim.** Use zone and host names exactly as given in the request.
5. **Roles are separate.** Authoritative servers have `recursion no`. Resolvers hold no authoritative zones, only the root hint zone. Put several roles on one device only when the request says so.
6. **Everything persists in lab files.** Kathara interfaces are already up, so never use `ip link set ... up`. Start services with `systemctl`.

## 2. Kathara and BIND facts this skill relies on
- `<dev>[N]="CD"` (optionally `"CD/<mac>"`) puts interface `ethN` of `<dev>` on collision domain `CD`. Collision-domain names are only labels: addresses come only from `.startup` (or `shared.startup`) commands.
- At boot, each device does the following in order:
  1. Unmounts Docker's `/etc/resolv.conf` and `/etc/hosts`.
  2. Copies `<dev>/` over the container's root filesystem, overwriting existing files.
  3. Runs `shared.startup`, then `<dev>.startup`. Startup output goes to `/var/log/startup.log`.

  As a result, `<dev>/etc/bind/named.conf` replaces the packaged file, and `<dev>/etc/resolv.conf` is honoured.
- A device with no `[image]` line runs Kathara's default image, which is `kathara/base` unless the local settings change it.
- IPv6 is disabled inside a device unless `<dev>[ipv6]="true"` is set or the global `enable_ipv6` setting is on. The default is off.
- Images:

  | Image | Contents | BIND version and service unit |
  |---|---|---|
  | `kathara/bind:latest` | core + BIND9 | BIND 9.18 (Debian 12), `named` |
  | `kathara/bind:9.11.5` | core + BIND9 | BIND 9.11 (Debian 10), `bind9` |
  | `kathara/base` | core + BIND9 + Apache + dnsmasq | BIND 9.18, `named` |
  | `kathara/core` | network tools and `dig`, no BIND | none |
- `systemctl` inside Kathara images is a lightweight replacement for systemd: use plain `systemctl start <unit>`.
- Generated configuration must load on **both BIND 9.11 and 9.18** (§7.2).

## 3. Procedure
1. **Inventory** the lab (§4) and build the device table.
2. **Normalize** the request into the DNS model (§5.1).
3. **Assign roles** (§5.3) and **choose the addresses to publish** (§5.4).
4. **Plan zones top-down.** For each zone, its parent is the closest enclosing zone in the plan (the root if there is none). Delegations go in that parent.
5. **Feasibility gate.** Check every planned item against §1. Drop infeasible items and record a warning for each.
6. **Write files** (§6, §7, §8, §10).
7. **Validate statically** (§11). Fix the files and repeat until clean.
8. **Report** (§13).

For larger requests (more than about 5 zones or 15 records), keep the plan as a data structure (YAML/JSON) and generate the files with a short throwaway script, then review the output. This avoids copy errors in glue records and IPs. The script is a working file, not part of the lab.

## 4. Inventory
Read and parse the following:
- **`lab.conf`:** devices, `<dev>[N]` interfaces, `[image]`, `[ipv6]`, `LAB_DESCRIPTION`.
- **`.startup` files and `shared.startup`:**
  - Addresses: `ip addr|address add`, `ip -4/-6 addr add`, `ifconfig ethN <ip>[/len] [netmask ..] up`, `ifconfig ethN inet6 add`.
  - Routes: `ip [-6] route add`, `route add`.
  - Forwarding: `sysctl ... forwarding=1`, `echo 1 > .../ip_forward`.
  - Services started (`systemctl`, `/etc/init.d/...`): frr, quagga, bird, named, bind9, apache2, dnsmasq.
  - Any write to `/etc/resolv.conf`.
- **`<dev>/` folders:** `etc/bind/*`, `etc/resolv.conf`, routing daemon configs.

Build the table: `dev | image (explicit/default) | ethN → CD, IPv4/len, IPv6/len | routes (default gw, static) | class | services | existing DNS config`.

**Class.** A device is a *router* if any of these is true:
- its image is frr, quagga, bird\*, openbgpd, openvswitch, bmv2 or pox;
- its startup enables forwarding;
- its startup starts a routing daemon.

A switch is any openvswitch/bmv2 device. Everything else is a *host*, including multi-homed hosts without forwarding. **Routers and switches never get DNS roles.**

## 5. Request handling

### 5.1 Normalized model
Accept free text, JSON, YAML or a mix. Map keys by meaning, not by spelling. For example, `authoritative`, `auth`, `nameservers` and `ns` all describe zone servers; `slave` and `secondary` mean the same; `dns_resolver`, `recursive`, `local_dns` and `ldns` all mean resolver. Normalize everything to this model:
```yaml
ip_family: ipv4 | ipv6 | dual
root:      { servers: [<dev>], ns_names: [<fqdn.>] }
zones:                                   # forward and reverse, any depth
  - name: <zone>                         # "it", "uniroma1.it", "0.0.10.in-addr.arpa"
    primary: <dev>
    secondaries: [<dev>]
    ns_names: { <dev>: <fqdn.> }
    records: [ { name: <label|fqdn.>, type: A|AAAA|CNAME|MX|TXT|SRV|PTR, value: <dev|ip|fqdn.|text> } ]
resolvers: [ { device: <dev>, forwarders: [] } ]
clients:   [ { device: <dev>, resolver: <dev>, search: [] } ]
extras:    { reverse: none|auto|[zones], dnssec: false }
```
Resolution rules:
- **Record values.** A value that names a device resolves to that device's published address for the selected family (§5.4). An explicit IP used as a record value is kept as given, since it's data, but produces a warning if no lab device has it.
- **Server addresses.** An explicit IP given for a server role must exist on that device. If it doesn't, drop the role and warn.
- **Host phrases.** "pc1 in uniroma1.it" becomes `pc1.uniroma1.it.` with pc1's address. A bare zone list ("zones it, uniroma1.it") means zones with only SOA, NS and NS address records.
- **Conflicts.** Explicit beats inferred, specific beats general; otherwise the first occurrence wins. Report every conflict.
- **Unknown keys and unsupported features** (views, TSIG, dynamic update, ...) are ignored and listed in the report.

### 5.2 Defaults
| Missing detail | Default |
|---|---|
| IP family | `ipv4`. Use `dual` if the request mentions IPv6 alongside IPv4 or dual-stack. Use `ipv6` if the request says IPv6-only, or if the required devices have no IPv4 address. |
| Root | Create an artificial root `.` whenever there is a resolver or more than one zone level. |
| Root NS names | `a.root-servers.`, `b.root-servers.`, ... If the request uses a TLD named `root-servers`, use `rootns<N>.` instead. |
| Zone NS names | `ns1.<zone>.` for the primary, then `ns2.<zone>.`, ... for the others, in order. |
| Resolver | One resolver if the request mentions clients, lookups from hosts, or "resolution". |
| Clients | Devices named as clients in the request; otherwise every host with no DNS role. |
| Several servers for one zone, type unspecified | Identical primary copies on each server, with no zone transfer. Use a secondary only if the request says secondary, slave or transfer. |
| Reverse zones | None. If requested without detail: one zone per subnet that contains published records, cut on an octet (IPv4) or nibble (IPv6) boundary. |
| Forwarders, DNSSEC, `search` | None. |
| TTL and SOA timers | `$TTL 300`, SOA `( <serial> 3600 600 86400 60 )`. Serial is `1` for a new zone; increment it by 1 when editing an existing zone. |

### 5.3 Role assignment
Candidates are hosts only (§4). Exclude devices running dnsmasq or another DNS daemon (port 53 conflict), and devices whose image cannot get BIND under §7.1. Assign roles in this order of precedence:
1. Explicit in the request.
2. Evidence in the lab: existing `etc/bind` files or a `named`/`bind9` start command for that zone; name tokens in the device (`root`, `dnsroot`, `rootns` → root; the zone label, e.g. `dnsit` → `it`, `dnsuni` → `uniroma1.it`; `ns`, `dns`, `auth` → authoritative; `resolver`, `local`, `ldns`, `rdns`, `recursive` → resolver); `LAB_DESCRIPTION`.
3. A free host whose image already has BIND, then a free `kathara/core` host. Prefer one on the same collision domain as the role's main peer (the parent server for zones, clients for a resolver). Break ties alphabetically.

Constraints:
- One device per role.
- Clients are not servers unless the request says so.
- **If there are not enough hosts,** several authoritative zones may share one authoritative server (warn when you do this). Never merge a resolver with an authoritative server unless asked. If no host is available at all, skip the role and warn.

**Which resolver a client uses** (first match wins): the one named in the request; the resolver on the client's collision domain; the resolver reachable through the fewest routers; the first resolver.

### 5.4 Address to publish for a server
This address is used in NS address records, glue, hints, `masters` and `resolv.conf`. Pick it in this order:
1. The address given in the request, which must exist on the device.
2. The address on a collision domain shared with its consumers. Consumers are resolvers for NS, glue and hint addresses; clients for `resolv.conf`; secondaries for `masters`.
3. The address of the interface that carries the device's default route, or its routes toward the consumers.
4. The lowest `ethN`.

Never publish loopback addresses, link-local addresses (`fe80::/10`), or addresses of another device. Publish one address per family per NS name unless the request asks for more.

## 6. Images and service start

### 6.1 lab.conf image lines
| Current image | Action |
|---|---|
| `kathara/bind[:tag]`, `kathara/base[:tag]` | Keep as is, including the tag. |
| No `[image]` line | Add `<dev>[image]="kathara/base"`. This is the stock default and has BIND, so the result no longer depends on local settings. |
| `kathara/core` | Change to `kathara/bind`. |
| `kathara/apache` (Apache in use) | Change to `kathara/base`. |
| Routing, SDN or custom images | Not a candidate. If the request forces this device, keep its image and warn that BIND may be missing. |

Keep the file's existing quoting style, and put the new line next to that device's other lines.

### 6.2 Startup line
Append exactly once, after every existing line:
- BIND 9.18 images (`kathara/bind`, `kathara/bind:latest`, `kathara/base`): `systemctl start named`
- `kathara/bind:9.11.5`: `systemctl start bind9`

If the startup already starts BIND in any form, don't add a second start. Before appending, make sure the file ends with a newline. Use LF line endings only: CRLF breaks startup scripts.

## 7. named.conf

### 7.1 General rules
- Write one complete, self-contained `<dev>/etc/bind/named.conf`.
- Never `include` `named.conf.options`, `named.conf.local` or `named.conf.default-zones`. The default zones add a second `zone "."` hint: on a resolver that fails with "zone '.' already exists", and it also points to Internet roots.
- If the file already exists, edit it in place. Keep unrelated zones and options unless they break a rule here; report any that do.
- Files go in `<dev>/etc/bind/`: zone files are `db.root` (for `.`) and `db.<zone>` otherwise; resolvers also get `db.hints`.

### 7.2 Compatibility (9.11 and 9.18)
- **Use:** `type master|slave|hint` and `masters`.
- **Never use** `primaries` or `type primary|secondary` (they need ≥ 9.16), `dnssec-policy`, or `trust-anchors` on 9.11.
- **Never use** `dnssec-enable` or `dnssec-lookaside`: on 9.18, named refuses to start with "option no longer exists". `auto-dnssec` is deprecated: don't use it either.

### 7.3 Templates
Authoritative server (also used for the root, with `zone "." { type master; file "/etc/bind/db.root"; };`):
```
options {
    directory "/var/cache/bind";
    recursion no;
    allow-query { any; };
    dnssec-validation no;
    listen-on { any; };
    listen-on-v6 { any; };
};
zone "<zone>" { type master; file "/etc/bind/db.<zone>"; };
```
Primary with secondaries: add to that zone `allow-transfer { <every IP of each secondary>; }; also-notify { <secondary published IP>; };`.

Secondary:
```
zone "<zone>" { type slave; masters { <primary published IP>; }; file "/var/cache/bind/db.<zone>"; };
```
If the primary is multi-homed, also add `allow-notify { <every IP of the primary>; };`. Secondary zone files must live in `/var/cache/bind`, which is writable by named.

Recursive resolver:
```
options {
    directory "/var/cache/bind";
    recursion yes;
    allow-recursion { any; };
    allow-query { any; };
    allow-query-cache { any; };
    dnssec-validation no;
    empty-zones-enable no;
    listen-on { any; };
    listen-on-v6 { any; };
};
zone "." { type hint; file "/etc/bind/db.hints"; };
```
Forwarders are allowed only if requested: `forwarders { <ip>; }; forward only;`. The hint zone stays.

### 7.4 Why each setting matters
| Setting | What happens without it |
|---|---|
| `recursion no` (authoritative) | The server would answer as a resolver too, which mixes roles and hides delegation errors. |
| `allow-recursion { any; }` | BIND's default is `localnets; localhost;`, so hosts in other subnets get REFUSED. |
| `dnssec-validation no` | The default `auto` validates with the real Internet root key, and the unsigned artificial root gives SERVFAIL (verified). |
| `empty-zones-enable no` | Resolvers create automatic empty zones for 10/8, 172.16/12, 192.168/16, 100.64/10, 169.254/16, the TEST-NETs, `fd00::/8`, `fe80::/10`, `2001:db8::/32`, `home.arpa`, ... Reverse lookups in lab address space then get NXDOMAIN from the resolver itself (verified). The setting is harmless otherwise, so always set it. |
| Hint zone `.` | The resolver falls back to built-in Internet root hints. |
| `also-notify` | If a secondary boots before its primary, its first transfer fails and it stays empty for minutes. A NOTIFY triggers the transfer immediately (verified). |

### 7.5 db.hints
Add one NS line per root server, plus its address(es) for the chosen family:
```
.                  3600000 IN NS   a.root-servers.
a.root-servers.    3600000 IN A    <root published IPv4>
a.root-servers.    3600000 IN AAAA <root published IPv6>   ; only for ipv6/dual
```

## 8. Zone files
```
$TTL 300
@              IN SOA  <primary-ns>. <rname>. ( <serial> 3600 600 86400 60 )
@              IN NS   <ns1>.
<in-zone-ns>.  IN A    <published IPv4>
; delegations (with glue only when needed)
<child>.       IN NS   <child-ns>.
<child-ns>.    IN A    <child server published IPv4>
; requested host records
```
- `<rname>` is `hostmaster.<zone>.`, except for the root zone, which uses `hostmaster.`. Writing `hostmaster.<zone>.` for the root gives `hostmaster..`, an "empty label" error, and the zone isn't loaded (verified).
- End every file with a newline, and use LF line endings.

## 9. Zone data rules
- **Trailing dot.** Every absolute name ends with a dot. Without it, `ns1.it` inside zone `it` becomes `ns1.it.it.`, and the zone fails to load.
- **Every zone** needs an SOA, at least one apex NS, and an A/AAAA record for every in-zone NS name. Without those addresses, named logs "has no address records" and doesn't load the zone.
- **Where delegations go.** A delegation goes in the closest enclosing zone in the plan, and it may skip labels. For example, the root can delegate `uniroma1.it.` directly if no `it` zone exists, or `0.0.10.in-addr.arpa.` directly.
- **Glue.** Glue is required when the NS name is at or below the delegated zone. The glue IP must equal the child server's published address. Missing glue passes `named-checkzone` but gives SERVFAIL at runtime (verified), so check it by hand (§11).
- **Out-of-bailiwick NS names** need no glue, but they must resolve through the hierarchy. Never create cycles: zone A's NS under zone B and zone B's NS under zone A, with no glue on either side.
- **Matching NS sets.** The parent's delegation NS set must equal the child's apex NS set, and every listed server must actually serve the zone. Otherwise the delegation is lame.
- **Occlusion.** Data below a delegation point in the parent is occluded: keep child records only in the child zone (glue excepted). Root NS names must not fall under a TLD that the root zone delegates.
- **CNAME.** Never at the apex, never next to other data with the same name, never as an NS or MX target. MX and SRV targets need A/AAAA records.
- **Which records to write.** Only the requested names plus the NS names. Add router records only if the request asks.
- **Reverse zones.** IPv4 zones are cut on an octet boundary (`/8`, `/16`, `/24`) with the octets reversed; unaligned prefixes use the enclosing octet zone. Use RFC 2317 only if requested. IPv6 zones are cut on a nibble boundary: for example, `2001:db8:1::/48` → `1.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa`. PTR values are FQDNs with a trailing dot. Reverse zones are delegated like forward zones.
- **Several root servers** all serve the same root zone. All of them are listed in the root apex NS and in every `db.hints`.
- **Editing an existing zone.** Increment the serial and keep unrelated records.

## 10. IP family and clients
- **`ipv4`:** A records only. No AAAA anywhere: not in NS addresses, glue or hints.
- **`ipv6`:** AAAA records only. Every server, resolver and client needs an IPv6 address, and IPv6 must be enabled on the device. If `[ipv6]` isn't `"true"`, warn that Kathara disables IPv6 by default; don't change `lab.conf`.
- **`dual`:** both A and AAAA for every NS name, glue and hint, and for host records when the device has both addresses.
- **A device lacking the required family:** publish what it has and warn.
- **Client resolver file:**
  - Follow the lab's existing convention. If the startup already writes `/etc/resolv.conf`, update that line; it runs after the folder copy, so it would win anyway.
  - Otherwise, create or overwrite `<dev>/etc/resolv.conf`, which is the convention of the official Kathara labs:
    ```
    nameserver <resolver published IPv4>
    nameserver <resolver published IPv6>    # dual/ipv6 only
    search <domain>                         # only if requested
    ```
  - Use at most 3 `nameserver` lines.
  - Never point a client at an authoritative-only server or a root server.
  - Leave the resolver files of server devices unchanged unless requested.

## 11. Static validation (mandatory)
**A. Tools, when available.** They catch syntax and load errors only.
- `named-checkzone <zone> <lab>/<dev>/etc/bind/db.<zone>`, and `named-checkzone . .../db.root` for the root.
- `named-checkconf <lab>/<dev>/etc/bind/named.conf`. This checks syntax only; don't add `-z`, because the zone paths are container paths.
- To check against the exact BIND version of the image, if Docker is available: `docker run --rm -v "<abs lab>/<dev>/etc/bind:/etc/bind:ro" <dev image> named-checkconf -z /etc/bind/named.conf`.

**B. Semantic checks.** The tools miss all of these, so do every one of them by hand or with the generator script:
1. Every planned zone is served by its assigned devices, and every referenced file exists.
2. Walk from the root to every requested name. At each step, check that the delegation sits in the right parent, the NS sets match, glue is present exactly when it's in-bailiwick, and each glue IP equals that server's published IP.
3. There is no occluded data and no glue cycle.
4. The root apex NS set equals the hints of every resolver, and each hint IP is a root server's published IP.
5. Every resolver has `recursion yes`, `allow-recursion { any; }`, `dnssec-validation no`, `empty-zones-enable no`, a hint zone, and no master zones. Every authoritative server has `recursion no`.
6. **Reachability (best effort).** Check each pair: resolver → every authoritative server, client → resolver, secondary → primary. A pair is OK if both ends share a subnet, or if each side has a matching or default route toward the other and every intermediate router has a matching route. Otherwise, warn "path unverified" or "unreachable".
7. **Diff against the original lab.** Only these changes are allowed: `[image]` lines, appended startup lines, and DNS files. No changed addresses, routes or daemons.
8. Files use LF line endings and end with a newline. No forbidden options (§7.2). IP families are consistent with the request.

## 12. Fix mode and extensions
- **Fix or change requests** on an existing DNS setup:
  1. Inventory the current BIND files.
  2. Run §11 on them and list the defects.
  3. Correct them with minimal edits: increment serials, and don't rewrite parts that already work.

  Typical defects: an authoritative server with recursion, a resolver serving zones, forwarders in an isolated lab, hints pointing to a non-root server, missing or wrong glue, lame delegation, `default-zones` included, DNSSEC validation left at its default, a `hostmaster..` RNAME, a missing trailing dot, `dnssec-enable` on 9.18.
- **DNSSEC (only if explicitly requested, and only if `dnssec-keygen`/`dnssec-signzone` are available locally):**
  1. Generate keys and sign zones bottom-up: sign a child zone, add its DS record to the parent, then sign the parent.
  2. Reference the signed files in `named.conf`.
  3. On resolvers, set `dnssec-validation yes` plus the root KSK: `trust-anchors { . static-key ...; }` on 9.18, `trusted-keys` on 9.11.

  If the tools are missing, configure the zones unsigned and warn.

## 13. External acceptance checks (the configuration must pass these)
Use the published IPs. Inside the lab these run as `kathara exec <dev> -- <cmd>`.
- **Authoritative server:** `dig @<auth_ip> <zone> SOA +norecurse` → NOERROR with the `aa` flag. For the root, query `.`.
- **Delegation:** `dig @<parent_ip> <child> NS +norecurse` → a referral with the child NS set and glue.
- **Resolver:** `dig @<resolver_ip> <name> A` (or AAAA) → NOERROR, the `ra` flag, the expected address.
- **Client:** `dig <name>` uses `resolv.conf` and must give the same answer. `dig -x <ip>` checks reverse zones.
- **Trace:** `dig <name> +trace` from a client. It resolves NS names through the client's `resolv.conf` and queries every server directly, so it also needs routes from the client to all servers.
- **Load errors:** `named-checkconf -z /etc/bind/named.conf` inside the device. `cat /var/log/startup.log` shows startup errors. A running service doesn't prove the zone loaded.
- **What a failure means:**

  | Result | Likely cause |
  |---|---|
  | REFUSED | `allow-query`/`allow-recursion`, a zone not loaded, or a query sent to an authoritative-only server |
  | SERVFAIL | Broken delegation or glue, DNSSEC validation left on, or an unreachable server |
  | NXDOMAIN | Missing or occluded record, or an automatic empty zone (reverse) |
  | Timeout | Routing, `listen-on`, or service down |

## 14. Final report (compact)
```
Roles:     <role> → <dev> (<published IPs>) ...
Files:     created ...; edited ...; startup lines appended ...
lab.conf:  image changes (<dev>: old → new) | none
Assumptions: one line each
Warnings:  missing IPs/families, unverified/unreachable paths, skipped items, ignored keys
Checks:    the §13 commands the external validator should run first
```

## Example (abridged)
Lab: `r1` (router, eth0 10.0.1.254, eth1 10.0.2.254); `dnsroot` 10.0.1.1; `dnsit` 10.0.1.2; `dnsuni` 10.0.2.1; `resolver` 10.0.2.2; `pc1` 10.0.2.10. Every host has a default route through r1. Images are `kathara/core` or absent.

Request: `{"zones": ["it", "uniroma1.it"], "hosts": {"www.uniroma1.it": "pc1"}, "clients": ["pc1"]}`

Plan:
- **Roles.** Root `a.root-servers.` → dnsroot; `it` (`ns1.it.`) → dnsit; `uniroma1.it` (`ns1.uniroma1.it.`) → dnsuni; resolver → resolver. All roles come from device names.
- **Delegations.** `db.root` delegates `it. NS ns1.it.` with glue 10.0.1.2. `db.it` delegates `uniroma1 NS ns1.uniroma1.it.` with glue 10.0.2.1. `db.uniroma1.it` holds `www A 10.0.2.10`.
- **Resolver.** `db.hints` has `a.root-servers. A 10.0.1.1`. `pc1/etc/resolv.conf` has `nameserver 10.0.2.2`.
- **Images and startup.** The four DNS devices get `kathara/bind` (or `kathara/base` where no image line existed). Each startup gets `systemctl start named` appended.
- **Report.** IP family `ipv4` (assumed). Paths across r1 are verified through the default routes.

## References
- `lab.conf`: https://www.kathara.org/man-pages/kathara-lab.conf.5.html
- `kathara exec`: https://www.kathara.org/man-pages/kathara-exec.1.html
- Kathara images: https://github.com/KatharaFramework/Docker-Images
- Official labs (DNS conventions): https://github.com/KatharaFramework/Kathara-Labs
- BIND 9.18 reference: https://bind9.readthedocs.io/en/v9.18-branch/reference.html
