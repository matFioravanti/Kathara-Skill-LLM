---
name: kathara-dns-configuration
description: "Analyze an existing Kathara lab and directly configure DNS and optional web services from positive and negative constraints. Preserve existing topology, addressing, and routing; assign DNS roles, build zones and delegations, and directly modify the persistent lab files."
argument-hint: "lab_path, natural-language DNS/web requirements, and optional operating options"
user-invocable: true
---

# Automated DNS Configuration in Kathara

This skill is intended to be loaded by a Python script that orchestrates the LLM. The LLM directly accesses the lab, analyzes its files, and applies the required changes itself.

The lab already exists and its topology is described by `lab.conf`. Topology, addressing, forwarding, and routing are immutable inputs: they may be analyzed to place resolvers, authorities, and DNS-related flows correctly, but they must not be generated or modified by this skill.

## Authoritative References

### Kathara

- Main command reference: https://www.kathara.org/man-pages/kathara.1.html
- Network scenario configuration (`lab.conf`): https://www.kathara.org/man-pages/kathara-lab.conf.5.html
- Network scenario directory structure: https://www.kathara.org/man-pages/kathara-lab-dirs.7.html
- Execute commands in a device: https://www.kathara.org/man-pages/kathara-exec.1.html
- Official network scenarios: https://github.com/KatharaFramework/Kathara-Labs
- Official DNS lab directory: https://github.com/KatharaFramework/Kathara-Labs/tree/main/main-labs/application-level/dns
- Official integrated DNS + web-server lab: https://github.com/KatharaFramework/Kathara-Labs/tree/main/main-labs/labs-integrating-several-technologies/small-internet-with-dns-and-web-server
- Kathara Lab Checker: https://github.com/KatharaFramework/kathara-lab-checker
- Official Docker images: https://github.com/KatharaFramework/Docker-Images/tree/develop

### BIND 9 and DNS

- BIND 9 Administrator Reference Manual: https://bind9.readthedocs.io/en/stable/
- BIND 9.11 reference: https://ftp.ripe.net/mirrors/sites/ftp.isc.org/isc/bind/9.11.5/doc/arm/Bv9ARM.ch06.html
- Current BIND configuration reference: https://bind9.readthedocs.io/en/stable/reference.html
- BIND manual pages: https://bind9.readthedocs.io/en/stable/manpages.html
- RFC 1034: https://datatracker.ietf.org/doc/html/rfc1034
- RFC 1035: https://datatracker.ietf.org/doc/html/rfc1035

Before using a BIND option not covered here, verify its syntax against official documentation compatible with the version detected in the lab.

## Essential Concepts

- A Kathara lab is centered on `lab.conf`, with optional `<device>.startup` scripts and persistent per-device directories.
- A device directory mirrors the device root filesystem: `ns1/etc/bind/named.conf` becomes `/etc/bind/named.conf` inside `ns1`.
- Changes must persist in the lab files; do not rely on interactive container edits.
- A collision domain connects interfaces but does not automatically assign addresses, routes, or DNS roles.
- A root name server is authoritative for `.`; a resolver containing root hints is not a root name server.
- An authoritative server publishes data for one or more zones; a local/recursive resolver follows delegations and answers clients.
- An `NS` record alone does not make a machine a functioning name server.
- Successful DNS resolution does not imply that the associated service is reachable.

## Execution Contract

The Python script provides at least:

- `lab_path`;
- the natural-language DNS/web specification;
- any operating options.

The LLM works directly under `lab_path`.

Rules:

1. Do not ask questions during automated execution.
2. Fully analyze the lab and check feasibility before the first modification.
3. If indispensable data is missing or requirements conflict, do not modify the lab and return a concise error.
4. If configuration is feasible, directly create or modify only the persistent files required by the roles actually assigned to each device.
5. Do not modify topology, addresses, forwarding, or routes.
6. Do not create `dns-plan.yaml`, intermediate JSON, planning files, or test files.
7. At the end, return only a concise summary of the applied changes or the blocking error.

## Image Compatibility

First detect the image and version declared in `lab.conf`; preserve existing images when they already provide the required software.

| Purpose | Normally compatible images |
|---|---|
| Generic host/router | `kathara/core`, `kathara/base` |
| DNS with BIND 9 | `kathara/bind`, `kathara/bind:9.11`, `kathara/bind:9.11.5`, `kathara/base` |
| Web with Apache | `kathara/apache`, `kathara/base` |
| DNS + web on the same device | `kathara/base` |

With BIND 9.11 use compatible syntax: `type master`, `type slave`, and `masters`. Do not automatically replace compatible images or tags, and do not place `apt install` in startup scripts.

## Global Rules

- Preserve the topology declared in `lab.conf`.
- Treat addressing, forwarding, and routing as read-only.
- Configure IPv4 and IPv6 independently.
- Never assign a DNS role forbidden by the specification.
- Never weaken a negative requirement to satisfy a positive one.
- Do not use accidental `SERVFAIL` as an intentional denial mechanism.
- Use trailing-dot FQDNs in zone files when a name is absolute.
- Use root hints for the artificial hierarchy, not public-Internet root hints.
- For an intentionally unsigned artificial root, disable DNSSEC validation unless DNSSEC is explicitly required.
- Apply the smallest coherent change and preserve unrelated content, comments, and configuration.
- Treat every `<device>/` directory as a sparse persistent filesystem overlay: create only the paths required by the roles actually assigned to that device, and never create role-specific directories merely for symmetry.
- Use `systemctl` to start services from startup scripts.
- Do not claim runtime results that were not observed.

## Keep the Three Planes Separate

For each requirement distinguish:

1. **DNS resolution**: client → local resolver → root/authorities.
2. **Application**: client → service address returned by DNS.
3. **Existing routing**: path imposed by the Layer-3 configuration.

These are not equivalent:

- `pc1` resolves `www.example.test.`;
- `pc1` reaches the returned address;
- `pc1` HTTP traffic crosses `r4`;
- resolver queries toward the authority cross `r4`.

Routing is a constraint on role placement and DNS/web flows, not configuration to rewrite.

## Requirement Interpretation

Accept specifications written in Italian or English, including long prose. Preserve device names, interface names, collision-domain labels, FQDNs, and technical identifiers exactly; normalize internally only DNS case and trailing dots on FQDNs.

### DNS Requirement Types

| Kind | Meaning |
|---|---|
| `role-required` | A device must perform a DNS role. |
| `role-forbidden` | A device must not perform one or more DNS roles. |
| `authority` | A device must or must not be authoritative for a zone. |
| `resolution` | A client or group must obtain a specific result for QNAME/QTYPE. |
| `resolver-use` | A client must or must not use a local resolver. |
| `query-waypoint` | A client→resolver or resolver→authority flow must traverse specified routers. |
| `query-avoidance` | A DNS flow must avoid specified routers. |
| `delegation` | A parent zone must delegate a child zone to selected authorities. |

Supported roles:

- `root-authoritative`;
- `zone-authoritative`;
- `recursive-resolver`;
- `secondary-authoritative`;
- `dns-client`.

Examples:

- All clients must resolve `www.example.test.` with A and AAAA.
- `pc3` must not be a name server.
- `server2` may be authoritative for `example.test.` but not for `.`.
- `pc2` must receive `REFUSED` for `private.test.`.
- `pc1` must use `ldns1`.
- Queries from `ldns1` to the authority for `example.test.` must cross `r4`.

### Web Requirement Types

| Kind | Meaning |
|---|---|
| `web-publish` | An FQDN must map to the web server's real address(es). |
| `web-reachability` | Specified clients must or must not complete an HTTP request. |
| `web-waypoint` | Client→web-server traffic must include or avoid specified routers. |

### Normative Semantics

- “A can resolve X” requires `NOERROR` and the requested records through A's assigned resolver.
- “A cannot resolve zone Z” normally means deliberate `REFUSED`; use `NXDOMAIN` only when the name must appear nonexistent.
- A timeout is appropriate only when the requirement explicitly asks for network unreachability.
- `SERVFAIL` indicates a broken chain or server error.
- “M cannot be a name server” forbids root authority, non-root authority, secondary, and recursive-resolver roles on M.
- “M cannot be root” forbids only authority for `.`.
- “All machines can resolve” applies to endpoints expected to act as DNS clients; pure transit routers are included only when explicitly required.
- A path constraint referring to an FQDN applies to application traffic toward the resolved address unless it explicitly refers to the DNS query.
- Do not generate reverse DNS or DNSSEC unless requested.
- Use one primary per zone in the minimum configuration; add secondaries only when required.

## Procedure

### 1) Analyze the Lab and Build the Network Model

Read directly:

- `lab.conf`;
- `*.startup` and any `*.shutdown` files;
- persistent per-device directories;
- existing BIND configuration, `resolv.conf`, and web content.

Derive devices, images, interfaces, collision domains, IPv4/IPv6 addresses, routes, and existing forwarding configuration.

Build an internal read-only Layer-3 view, separately for IPv4 and IPv6. Use existing routes, longest-prefix match, and return paths when required to determine:

- client → resolver;
- resolver → root;
- resolver → authority;
- required/forbidden waypoints;
- web-server reachability.

Do not modify files yet. If indispensable data is unavailable, stop.

### 2) Parse Requirements, Namespace, and Feasibility

Convert the specification into explicit DNS/web constraints and build the namespace tree.

For absolute names use internally normalized trailing-dot FQDNs. Preserve explicit zone cuts. If cuts are not specified:

1. `.` is a zone;
2. every top-level domain below `.` is a delegated zone;
3. every organizational second-level domain containing host/service records is a delegated zone;
4. deeper labels remain in the nearest organizational zone unless another requirement says otherwise.

Do not automatically turn every namespace node into a zone.

Before modifying the lab, verify that at least one solution satisfies all constraints. Configuration is infeasible, for example, when:

- no allowed device can act as root authority;
- a zone needs an authority but no device may be a name server;
- a mandatory resolver is unreachable from required clients;
- the required chain does not exist over the requested address family;
- the same client/QNAME/QTYPE must both succeed and fail under identical conditions;
- the same flow must both traverse and avoid the same waypoint;
- no resolver can reach a complete delegation chain.

If infeasible, stop before edits and return the technical reason.

### 3) Assign DNS Roles and Derive Flows

Choose only allowed devices with existing stable addresses.

The root authority must be reachable from the relevant resolvers and able to serve `.`.

For every non-root zone select at least one authority reachable by the relevant resolvers.

Each local resolver must:

- be reachable from assigned clients;
- reach at least one root authority;
- reach at least one authority at each delegation level;
- satisfy address-family, waypoint, and avoidance constraints.

If one resolver cannot cover all clients, use the minimum allowed set.

When assignments are equivalent, prefer in this order:

1. dedicated server devices;
2. non-router endpoints;
3. dual-stack devices;
4. devices with fewer existing roles;
5. lexicographically smallest device name.

Consider these flows:

1. client → resolver, UDP/TCP 53;
2. resolver → root, UDP/TCP 53;
3. resolver → delegated authorities, UDP/TCP 53;
4. primary → secondary, TCP 53, when requested;
5. client → web server, TCP 80/443, when requested.

Do not assume that a stub client directly contacts authoritative servers during ordinary recursive resolution.

### 4) Build Zones, Delegations, and Records

For each zone derive:

- SOA;
- apex NS;
- A/AAAA data for name servers;
- host and service records;
- child-zone delegations;
- glue A/AAAA when required.

For `child.parent.`:

- the parent contains the delegation NS;
- the parent contains glue when the NS target is in-bailiwick;
- the child contains its own SOA and NS records;
- the selected server actually loads the child zone.

Do not use IP addresses as NS targets, do not use a CNAME as an NS target, and do not place a CNAME at an apex that also contains SOA/NS data.

### 5) Preserve Layout and Persistent Structure

Adapt generation to the layout already used by the lab. Do not impose `named.conf.local`, a `zones/` directory, or `root.hints` when the lab uses another structure.

A Kathara device directory is a **sparse persistent overlay** of that device's root filesystem. For example:

```text
pc1/etc/bind/named.conf
```

becomes:

```text
/etc/bind/named.conf
```

inside `pc1`.

The persistent directory tree must be driven by the roles actually assigned to each device. Do **not** create the same directory structure on every host.

Use this role-to-path mapping:

| Device role | Persistent path normally required |
|---|---|
| Root authoritative DNS | `<device>/etc/bind/` |
| Non-root authoritative DNS | `<device>/etc/bind/` |
| Recursive/local DNS | `<device>/etc/bind/` |
| Stub DNS client | `<device>/etc/resolv.conf` |
| Web server | `<device>/var/www/html/` |
| Pure router/transit node | no DNS/web persistent path unless explicitly required |

If one device performs multiple roles, create the **union** of the paths required by those roles.

A minimal role-based layout may therefore look like:

```text
lab/
├── lab.conf
│
├── ldns.startup
├── ldns/
│   └── etc/bind/
│       ├── named.conf
│       ├── named.conf.options
│       └── db.root
│
├── root.startup
├── root/
│   └── etc/bind/
│       ├── named.conf
│       ├── named.conf.options
│       └── db.root
│
├── auth.startup
├── auth/
│   └── etc/bind/
│       ├── named.conf
│       ├── named.conf.options
│       └── db.<zone>
│
├── client/
│   └── etc/resolv.conf
│
└── web/
    └── var/www/html/
        └── index.html
```

Interpretation:

- on the local resolver, `db.root` may contain root hints for the artificial hierarchy;
- on the root name server, `db.root` may be the authoritative file for zone `.`;
- the role is determined by the `zone` declaration in `named.conf`, not by the filename;
- authoritative zone files may live directly under `/etc/bind/` when that is the lab convention;
- a stub client's resolver configuration may be persisted directly with `<client>/etc/resolv.conf`.

#### Sparse-layout rules

Apply all of the following:

1. Create `<device>/etc/bind/` only when that device actually runs BIND as an authoritative server, recursive resolver, secondary, or another explicitly requested DNS-server role.
2. Create `<device>/etc/resolv.conf` only when that device is required to behave as a **stub DNS client** through the selected local resolver.
3. Do not create `resolv.conf` merely because a device:
   - has IPv4 or IPv6 connectivity;
   - runs BIND;
   - is authoritative for a zone;
   - is the recursive resolver;
   - hosts a web service.
4. A recursive resolver does **not** need a `resolv.conf` pointing to itself unless the specification explicitly requires the host itself to perform stub resolution through that resolver.
5. An authoritative DNS server does **not** automatically need `resolv.conf`.
6. A web server does **not** automatically need `resolv.conf`; add it only if that same device is also a required DNS client.
7. Do not create `/etc/bind/` on pure clients or pure web servers.
8. Do not create `/var/www/html/` on devices that do not host a web service.
9. Do not create empty role directories.
10. Do not create placeholder copies of BIND files on devices that do not load those files.
11. Preserve existing unrelated persistent files and directories.
12. Prefer safe local edits to existing files and do not delete files unless explicitly necessary.

Before writing files, derive an internal role-to-filesystem map such as:

```text
root1 -> DNS authoritative -> etc/bind/
auth1 -> DNS authoritative -> etc/bind/
ldns1 -> recursive resolver -> etc/bind/
pc3   -> DNS client         -> etc/resolv.conf
web1  -> web server         -> var/www/html/
```

Use that map to decide which directories and files are legal to create. The final persistent structure should be the smallest structure that fully implements the requested roles.

### 6) Configure Authoritative BIND Servers

Adapt syntax to the detected BIND version.

BIND 9.11 root-authority example:

```conf
include "/etc/bind/named.conf.options";

zone "." {
    type master;
    file "/etc/bind/db.root";
};
```

Non-root authority example:

```conf
include "/etc/bind/named.conf.options";

zone "es" {
    type master;
    file "/etc/bind/db.es";
};
```

Minimal authoritative options:

```conf
options {
    directory "/var/cache/bind";
    recursion no;
};
```

Add `allow-query`, `allow-transfer`, `listen-on`, `listen-on-v6`, or DNSSEC directives only when required or needed for compatibility.

For an explicitly requested BIND 9.11 secondary:

```conf
zone "example.test" {
    type slave;
    masters { <MASTER_IPV4>; <MASTER_IPV6>; };
    file "/var/cache/bind/db.example.test";
};
```

The master must permit transfers only to the selected secondary addresses.

### 7) Generate Zone Files

Use only names and addresses present in the specification or lab.

Example root authority delegating `es.`:

```dns
$TTL 70000
@   IN SOA ROOT-SERVER. root.ROOT-SERVER. (
        2026091901
        28800
        14400
        3600000
        0
)

@               IN NS ROOT-SERVER.
ROOT-SERVER.    IN A  <ROOT_IPV4>

es.             IN NS dnses.es.
dnses.es.       IN A  <ES_AUTH_IPV4>
```

`dnses.es. A ...` is glue because the delegated zone's name server belongs to the child zone.

Example `es` zone:

```dns
$TTL 70000
@   IN SOA dnses.es. root.dnses.es. (
        2026091901
        28800
        14400
        3600000
        0
)

@               IN NS   dnses.es.
dnses.es.       IN A    <AUTH_IPV4>
web.es.         IN A    <WEB_IPV4>
ipv6-web.es.    IN AAAA <WEB_IPV6>
```

Rules:

- increment the serial when modifying an existing zone;
- publish A and/or AAAA only for address families that actually exist and are required;
- place delegation data in the parent and authoritative data in the child;
- generate glue only when required;
- never invent addresses, names, or extra hierarchy levels.

### 8) Configure the Recursive/Local DNS

The local name server uses root hints for the artificial hierarchy and follows delegations. Do not host authoritative copies of zones merely to shorten resolution.

Example `named.conf`:

```conf
include "/etc/bind/named.conf.options";

zone "." {
    type hint;
    file "/etc/bind/db.root";
};
```

Minimal `db.root` hints:

```dns
.              IN NS ROOT-SERVER.
ROOT-SERVER.   IN A  <ROOT_IPV4>
```

Add AAAA only when the root actually has IPv6 and that family is required.

Example options:

```conf
options {
    directory "/var/cache/bind";
    allow-recursion { <CLIENT_PREFIXES>; };
    dnssec-validation no;
};
```

With BIND 9.11, preserve any legacy directives already required by the lab.

Key distinction:

- `zone "." { type hint; ... }` on the resolver = bootstrap;
- `zone "." { type master; ... }` on the root server = authority for `.`.

### 9) Implement Negative DNS Policies

| Requirement | Preferred mechanism | Result |
|---|---|---|
| Client not authorized for recursion/cache | `allow-recursion` and, when needed, `allow-query-cache` | `REFUSED` |
| Immediate source not authorized for a zone | zone-level `allow-query` | `REFUSED` |
| Client behind shared resolver with client-specific policy | resolver-side view/policy or separate resolver | `REFUSED` or `NXDOMAIN` |
| Different clients must see different data | BIND `view` on the server receiving the query directly | depends on the view |
| Name nonexistent for everyone | omit authoritative record | `NXDOMAIN` |
| Server intentionally unreachable | only when explicitly required | timeout |
| Device cannot be a name server | no BIND role and no NS record | role absent |
| Device cannot be root | no `.` master/primary zone | role absent |

ACLs and views see the immediate DNS source: an authority queried by a shared resolver sees the resolver, not the original stub client.

Do not break a delegation merely to manufacture failure.

### 10) Configure Client Resolvers

Configure `resolv.conf` **only** on devices that the requirement analysis has classified as DNS stub clients.

Do not infer the `dns-client` role merely because a device has an IP address or participates in the lab. Running an authoritative server, recursive resolver, or web server does not implicitly make that host a DNS client.

When the lab uses persistent per-device filesystems, prefer:

```text
<client>/etc/resolv.conf
```

Minimal IPv4 content:

```text
nameserver <LOCAL_DNS_IPV4>
```

Minimal IPv6 content when the client must reach the resolver over IPv6:

```text
nameserver <LOCAL_DNS_IPV6>
```

If both address families are explicitly required for the same stub client, include only the resolver addresses that are actually configured and reachable from that client.

Rules:

- add an IPv6 nameserver only when the resolver actually owns that IPv6 address and the client must use it over IPv6;
- use `search` only when short-name resolution is required;
- do not add public resolvers;
- do not add authoritative-server addresses directly to client `resolv.conf` unless that server is also explicitly assigned the recursive/local-resolver role;
- do not generate `resolv.conf` for root or authoritative servers merely because they run BIND;
- do not generate `resolv.conf` for the recursive resolver merely to point it to itself;
- do not generate `resolv.conf` for a web server unless that device is also a required DNS client.

If `resolv.conf` is already persistent on a device that must be a DNS client, modify it directly and preserve unrelated compatible content. Generate it from startup only when that is already the lab convention or a persistent file is unavailable.

### 11) Configure Service Startup

Add startup commands only to devices that actually host the service, preserving the style already used by the lab.

Examples:

```bash
systemctl start bind9
```

```bash
systemctl start apache2
```

Do not duplicate `start`/`restart`, do not start BIND with `named -g &`, do not hide errors with `|| true`, and do not insert runtime tests in startup scripts.

### 12) Configure Optional Web Services

- Do not overwrite existing web content unless explicitly required.
- If an endpoint is required and `index.html` does not exist, create minimal deterministic content in `<web-device>/var/www/html/index.html`.
- Publish A and AAAA only for address families configured on the web server.
- IPv4 and IPv6 web servers may be different devices.
- Configure a virtual host only when required by names, ports, or `ServerName`.
- Preserve any existing Apache commands in startup scripts.
- A pure web server requires only its web-service files and startup changes; do not create `/etc/bind/` or `/etc/resolv.conf` unless that device also has the corresponding DNS-server or DNS-client role.

## Direct Application and Final Result

After analysis and feasibility checking are complete, directly apply the required changes under `lab_path`. Make edits idempotent where possible; if an operation fails part-way through, report which files were already modified.

At the end return a concise plain-text summary containing:

- `SUCCESS`, `BLOCKED`, or `ERROR`;
- files created;
- files modified;
- main DNS role assignments;
- any warning or blocking reason.

Example:

```text
SUCCESS
Created:
- pc1/etc/bind/db.root
Modified:
- pc1/etc/bind/named.conf
- pc3/etc/resolv.conf
Assignments:
- local resolver: pc1
- root authority: pc2
- authority for es.: pc5
```

If generation is infeasible:

```text
BLOCKED
Reason: no device allowed to act as resolver can reach the authority for zone es. through the existing routing.
```

Do not return JSON and do not delegate DNS-file writing to the Python script.

## Final Criteria

Before terminating, ensure only that:

- every DNS/web requirement has been considered;
- topology, addressing, forwarding, and routing remain unchanged;
- roles, delegations, glue, records, and client resolvers are coherent;
- every required change is persistent in the lab files;
- each device directory contains only role-required persistent paths, with no unnecessary `etc/bind`, `resolv.conf`, web directories, or placeholder files;
- unrelated content has been preserved;
- the final summary reports only operations actually performed.
