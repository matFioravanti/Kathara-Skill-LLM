# 03 — Technical structured — COST266 European multi-TLD (from pre-DNS backbone)

## Task and initial state

Starting from the **supplied existing Kathara laboratory** (`lab.conf` and its 37 router `.startup` files), **extend and configure the laboratory** to provide a self-contained IPv4 DNS hierarchy using BIND9. The initial laboratory includes **37 COST266 routers and 57 point-to-point WAN collision domains**, already addressed and connected through static routing; it **does not yet contain** DNS hosts or access LANs. Build the required access layer first, then configure DNS. The logical hierarchy must follow the European multi-TLD tree specified below.

**Mandatory network invariants:** preserve all 37 original routers, their original WAN interfaces/links/collision-domain names, IPv4 addresses, loopbacks, IPv4 forwarding, and all **3,327 existing backbone static-route entries**. Do not remove or replace existing router configuration or switch to dynamic routing. Add only the access interfaces, hosts, access networks, and static routes needed by this task; do not introduce additional backbone routers or WAN links. Persist everything in Kathara files, not only through interactive commands. The target is the **same pre-DNS laboratory**, not a separately generated network.

## 1. Required final size and roles

- **37** existing routers, **57** existing WAN links, unchanged.
- **16** new hosts, exactly: **12 authoritative DNS hosts**, **2 recursive resolver hosts**, and **2 clients**; final total **53 devices**.
- **10** new IPv4 access collision domains, attached to 10 existing routers; no other access networks.
- Artificial root zone `.` and exactly six artificial TLDs `europa.`, `infra.`, `research.`, `services.`, `lab.`, and `test.`.
- Authoritative inventory: **1 root + 6 TLD + 22 country zones + 37 city zones + 111 delegated city subzones + 24 additional functional zones = 201 zones**.
- For every non-root zone, implement its delegation from the direct parent: **200 parent–child delegations**.
- Application/service DNS records: **37 MX + 333 A = 370 records**, in addition to the mandatory SOA/NS/nameserver-address records for each authoritative zone.

### 1.1 Access networks and interface expansion

Each access network is `10.210.<index>.0/24` with router gateway `10.210.<index>.1/24`. Add the new interface at the **next free eth index** of the specified existing router. The network names and host addresses are fixed and must not be changed.

| Existing router | New interface | Collision domain | Access subnet | Router IPv4 gateway |
|---|---|---|---|---|
| `r_amsterdam` | `eth4` | `access_00` | `10.210.0.0/24` | `10.210.0.1/24` |
| `r_athens` | `eth3` | `access_01` | `10.210.1.0/24` | `10.210.1.1/24` |
| `r_frankfurt` | `eth4` | `access_12` | `10.210.12.0/24` | `10.210.12.1/24` |
| `r_helsinki` | `eth3` | `access_15` | `10.210.15.0/24` | `10.210.15.1/24` |
| `r_lisbon` | `eth3` | `access_17` | `10.210.17.0/24` | `10.210.17.1/24` |
| `r_london` | `eth5` | `access_18` | `10.210.18.0/24` | `10.210.18.1/24` |
| `r_paris` | `eth5` | `access_26` | `10.210.26.0/24` | `10.210.26.1/24` |
| `r_rome` | `eth4` | `access_28` | `10.210.28.0/24` | `10.210.28.1/24` |
| `r_warsaw` | `eth3` | `access_34` | `10.210.34.0/24` | `10.210.34.1/24` |
| `r_zurich` | `eth3` | `access_36` | `10.210.36.0/24` | `10.210.36.1/24` |

Ensure that every new host `eth0` is attached to the correct access domain, that every new host has its assigned `/24` address and the correct default gateway, and that all the new access subnets are reachable throughout the original 37-router backbone. Extend the *static* router configuration with routes to all remote access `/24` networks; a router directly attached to an access subnet uses its connected route. Use the pre-existing routing next hops and do not modify the original 3,327 entries. An expected minimal extension is **360 additional static access-subnet routes** (one for every remotely located access subnet at each router).

### 1.2 Fixed host roles, addresses and attachments

One physical DNS host may host many distinct **authoritative** zones as assigned below. This multiplexing is intentional and mandatory; **do not create 201 separate devices**. Use a BIND9-capable image (e.g. `kathara/base`) on the DNS hosts and make `dig` available to the clients.

| Role | Kathara host (create) | IPv4 on `eth0` | Attached router | Host default gateway |
|---|---|---|---|---|
| `root` | `c266_root` | `10.210.0.10/24` | `r_amsterdam` | `10.210.0.1` |
| `tld_europa` | `c266_tld_europa` | `10.210.0.11/24` | `r_amsterdam` | `10.210.0.1` |
| `tld_infra` | `c266_tld_infra` | `10.210.12.11/24` | `r_frankfurt` | `10.210.12.1` |
| `tld_research` | `c266_tld_research` | `10.210.12.12/24` | `r_frankfurt` | `10.210.12.1` |
| `tld_services` | `c266_tld_services` | `10.210.28.11/24` | `r_rome` | `10.210.28.1` |
| `tld_lab` | `c266_tld_lab` | `10.210.26.11/24` | `r_paris` | `10.210.26.1` |
| `tld_test` | `c266_tld_test` | `10.210.18.11/24` | `r_london` | `10.210.18.1` |
| `countries` | `c266_countries` | `10.210.12.10/24` | `r_frankfurt` | `10.210.12.1` |
| `cities` | `c266_cities` | `10.210.28.10/24` | `r_rome` | `10.210.28.1` |
| `subzones` | `c266_subzones` | `10.210.26.10/24` | `r_paris` | `10.210.26.1` |
| `functional_1` | `c266_functional_1` | `10.210.18.10/24` | `r_london` | `10.210.18.1` |
| `functional_2` | `c266_functional_2` | `10.210.15.10/24` | `r_helsinki` | `10.210.15.1` |
| `resolver_1` | `c266_resolver_1` | `10.210.34.10/24` | `r_warsaw` | `10.210.34.1` |
| `resolver_2` | `c266_resolver_2` | `10.210.36.10/24` | `r_zurich` | `10.210.36.1` |
| `client_1` | `c266_client_1` | `10.210.1.10/24` | `r_athens` | `10.210.1.1` |
| `client_2` | `c266_client_2` | `10.210.17.10/24` | `r_lisbon` | `10.210.17.1` |

Authoritative hosts: `c266_root`, the six `c266_tld_*` hosts, `c266_countries`, `c266_cities`, `c266_subzones`, `c266_functional_1` and `c266_functional_2` (12 total). Resolvers: `c266_resolver_1`, `c266_resolver_2`. Clients: `c266_client_1`, `c266_client_2`.

## 2. Authoritative DNS hierarchy — complete tree

**Every named line in this tree is a separate authoritative DNS zone**, not a mere directory or a resource record. The bracketed item is the exact host serving that zone; the host IPv4 address is fixed in §1.2. Parent–child edges are mandatory DNS `NS` delegations (with glue where necessary). A country in this tree is a logical zone below `europa.`, not a public Internet country-code TLD. All names below are absolute FQDNs.

```text
.   [ROOT: c266_root, 10.210.0.10]
├── europa.   [c266_tld_europa]
│   ├── at.europa.   [c266_countries]
│   │   └── vienna.at.europa.   [c266_cities]
│   │       ├── services.vienna.at.europa.   [c266_subzones]
│   │       ├── research.vienna.at.europa.   [c266_subzones]
│   │       └── admin.vienna.at.europa.   [c266_subzones]
│   ├── be.europa.   [c266_countries]
│   │   └── brussels.be.europa.   [c266_cities]
│   │       ├── services.brussels.be.europa.   [c266_subzones]
│   │       ├── research.brussels.be.europa.   [c266_subzones]
│   │       └── admin.brussels.be.europa.   [c266_subzones]
│   ├── bg.europa.   [c266_countries]
│   │   └── sofia.bg.europa.   [c266_cities]
│   │       ├── services.sofia.bg.europa.   [c266_subzones]
│   │       ├── research.sofia.bg.europa.   [c266_subzones]
│   │       └── admin.sofia.bg.europa.   [c266_subzones]
│   ├── ch.europa.   [c266_countries]
│   │   └── zurich.ch.europa.   [c266_cities]
│   │       ├── services.zurich.ch.europa.   [c266_subzones]
│   │       ├── research.zurich.ch.europa.   [c266_subzones]
│   │       └── admin.zurich.ch.europa.   [c266_subzones]
│   ├── cz.europa.   [c266_countries]
│   │   └── prague.cz.europa.   [c266_cities]
│   │       ├── services.prague.cz.europa.   [c266_subzones]
│   │       ├── research.prague.cz.europa.   [c266_subzones]
│   │       └── admin.prague.cz.europa.   [c266_subzones]
│   ├── de.europa.   [c266_countries]
│   │   ├── berlin.de.europa.   [c266_cities]
│   │   │   ├── services.berlin.de.europa.   [c266_subzones]
│   │   │   ├── research.berlin.de.europa.   [c266_subzones]
│   │   │   └── admin.berlin.de.europa.   [c266_subzones]
│   │   ├── dusseldorf.de.europa.   [c266_cities]
│   │   │   ├── services.dusseldorf.de.europa.   [c266_subzones]
│   │   │   ├── research.dusseldorf.de.europa.   [c266_subzones]
│   │   │   └── admin.dusseldorf.de.europa.   [c266_subzones]
│   │   ├── frankfurt.de.europa.   [c266_cities]
│   │   │   ├── services.frankfurt.de.europa.   [c266_subzones]
│   │   │   ├── research.frankfurt.de.europa.   [c266_subzones]
│   │   │   └── admin.frankfurt.de.europa.   [c266_subzones]
│   │   ├── hamburg.de.europa.   [c266_cities]
│   │   │   ├── services.hamburg.de.europa.   [c266_subzones]
│   │   │   ├── research.hamburg.de.europa.   [c266_subzones]
│   │   │   └── admin.hamburg.de.europa.   [c266_subzones]
│   │   └── munich.de.europa.   [c266_cities]
│   │       ├── services.munich.de.europa.   [c266_subzones]
│   │       ├── research.munich.de.europa.   [c266_subzones]
│   │       └── admin.munich.de.europa.   [c266_subzones]
│   ├── dk.europa.   [c266_countries]
│   │   └── copenhagen.dk.europa.   [c266_cities]
│   │       ├── services.copenhagen.dk.europa.   [c266_subzones]
│   │       ├── research.copenhagen.dk.europa.   [c266_subzones]
│   │       └── admin.copenhagen.dk.europa.   [c266_subzones]
│   ├── es.europa.   [c266_countries]
│   │   ├── barcelona.es.europa.   [c266_cities]
│   │   │   ├── services.barcelona.es.europa.   [c266_subzones]
│   │   │   ├── research.barcelona.es.europa.   [c266_subzones]
│   │   │   └── admin.barcelona.es.europa.   [c266_subzones]
│   │   ├── madrid.es.europa.   [c266_cities]
│   │   │   ├── services.madrid.es.europa.   [c266_subzones]
│   │   │   ├── research.madrid.es.europa.   [c266_subzones]
│   │   │   └── admin.madrid.es.europa.   [c266_subzones]
│   │   └── seville.es.europa.   [c266_cities]
│   │       ├── services.seville.es.europa.   [c266_subzones]
│   │       ├── research.seville.es.europa.   [c266_subzones]
│   │       └── admin.seville.es.europa.   [c266_subzones]
│   ├── fi.europa.   [c266_countries]
│   │   └── helsinki.fi.europa.   [c266_cities]
│   │       ├── services.helsinki.fi.europa.   [c266_subzones]
│   │       ├── research.helsinki.fi.europa.   [c266_subzones]
│   │       └── admin.helsinki.fi.europa.   [c266_subzones]
│   ├── fr.europa.   [c266_countries]
│   │   ├── bordeaux.fr.europa.   [c266_cities]
│   │   │   ├── services.bordeaux.fr.europa.   [c266_subzones]
│   │   │   ├── research.bordeaux.fr.europa.   [c266_subzones]
│   │   │   └── admin.bordeaux.fr.europa.   [c266_subzones]
│   │   ├── lyon.fr.europa.   [c266_cities]
│   │   │   ├── services.lyon.fr.europa.   [c266_subzones]
│   │   │   ├── research.lyon.fr.europa.   [c266_subzones]
│   │   │   └── admin.lyon.fr.europa.   [c266_subzones]
│   │   ├── marseille.fr.europa.   [c266_cities]
│   │   │   ├── services.marseille.fr.europa.   [c266_subzones]
│   │   │   ├── research.marseille.fr.europa.   [c266_subzones]
│   │   │   └── admin.marseille.fr.europa.   [c266_subzones]
│   │   ├── paris.fr.europa.   [c266_cities]
│   │   │   ├── services.paris.fr.europa.   [c266_subzones]
│   │   │   ├── research.paris.fr.europa.   [c266_subzones]
│   │   │   └── admin.paris.fr.europa.   [c266_subzones]
│   │   └── strasbourg.fr.europa.   [c266_cities]
│   │       ├── services.strasbourg.fr.europa.   [c266_subzones]
│   │       ├── research.strasbourg.fr.europa.   [c266_subzones]
│   │       └── admin.strasbourg.fr.europa.   [c266_subzones]
│   ├── gr.europa.   [c266_countries]
│   │   └── athens.gr.europa.   [c266_cities]
│   │       ├── services.athens.gr.europa.   [c266_subzones]
│   │       ├── research.athens.gr.europa.   [c266_subzones]
│   │       └── admin.athens.gr.europa.   [c266_subzones]
│   ├── hr.europa.   [c266_countries]
│   │   └── zagreb.hr.europa.   [c266_cities]
│   │       ├── services.zagreb.hr.europa.   [c266_subzones]
│   │       ├── research.zagreb.hr.europa.   [c266_subzones]
│   │       └── admin.zagreb.hr.europa.   [c266_subzones]
│   ├── hu.europa.   [c266_countries]
│   │   └── budapest.hu.europa.   [c266_cities]
│   │       ├── services.budapest.hu.europa.   [c266_subzones]
│   │       ├── research.budapest.hu.europa.   [c266_subzones]
│   │       └── admin.budapest.hu.europa.   [c266_subzones]
│   ├── ie.europa.   [c266_countries]
│   │   └── dublin.ie.europa.   [c266_cities]
│   │       ├── services.dublin.ie.europa.   [c266_subzones]
│   │       ├── research.dublin.ie.europa.   [c266_subzones]
│   │       └── admin.dublin.ie.europa.   [c266_subzones]
│   ├── it.europa.   [c266_countries]
│   │   ├── milan.it.europa.   [c266_cities]
│   │   │   ├── services.milan.it.europa.   [c266_subzones]
│   │   │   ├── research.milan.it.europa.   [c266_subzones]
│   │   │   └── admin.milan.it.europa.   [c266_subzones]
│   │   ├── palermo.it.europa.   [c266_cities]
│   │   │   ├── services.palermo.it.europa.   [c266_subzones]
│   │   │   ├── research.palermo.it.europa.   [c266_subzones]
│   │   │   └── admin.palermo.it.europa.   [c266_subzones]
│   │   └── rome.it.europa.   [c266_cities]
│   │       ├── services.rome.it.europa.   [c266_subzones]
│   │       ├── research.rome.it.europa.   [c266_subzones]
│   │       └── admin.rome.it.europa.   [c266_subzones]
│   ├── nl.europa.   [c266_countries]
│   │   └── amsterdam.nl.europa.   [c266_cities]
│   │       ├── services.amsterdam.nl.europa.   [c266_subzones]
│   │       ├── research.amsterdam.nl.europa.   [c266_subzones]
│   │       └── admin.amsterdam.nl.europa.   [c266_subzones]
│   ├── no.europa.   [c266_countries]
│   │   └── oslo.no.europa.   [c266_cities]
│   │       ├── services.oslo.no.europa.   [c266_subzones]
│   │       ├── research.oslo.no.europa.   [c266_subzones]
│   │       └── admin.oslo.no.europa.   [c266_subzones]
│   ├── pl.europa.   [c266_countries]
│   │   ├── krakow.pl.europa.   [c266_cities]
│   │   │   ├── services.krakow.pl.europa.   [c266_subzones]
│   │   │   ├── research.krakow.pl.europa.   [c266_subzones]
│   │   │   └── admin.krakow.pl.europa.   [c266_subzones]
│   │   └── warsaw.pl.europa.   [c266_cities]
│   │       ├── services.warsaw.pl.europa.   [c266_subzones]
│   │       ├── research.warsaw.pl.europa.   [c266_subzones]
│   │       └── admin.warsaw.pl.europa.   [c266_subzones]
│   ├── pt.europa.   [c266_countries]
│   │   └── lisbon.pt.europa.   [c266_cities]
│   │       ├── services.lisbon.pt.europa.   [c266_subzones]
│   │       ├── research.lisbon.pt.europa.   [c266_subzones]
│   │       └── admin.lisbon.pt.europa.   [c266_subzones]
│   ├── rs.europa.   [c266_countries]
│   │   └── belgrade.rs.europa.   [c266_cities]
│   │       ├── services.belgrade.rs.europa.   [c266_subzones]
│   │       ├── research.belgrade.rs.europa.   [c266_subzones]
│   │       └── admin.belgrade.rs.europa.   [c266_subzones]
│   ├── se.europa.   [c266_countries]
│   │   └── stockholm.se.europa.   [c266_cities]
│   │       ├── services.stockholm.se.europa.   [c266_subzones]
│   │       ├── research.stockholm.se.europa.   [c266_subzones]
│   │       └── admin.stockholm.se.europa.   [c266_subzones]
│   └── uk.europa.   [c266_countries]
│       ├── birmingham.uk.europa.   [c266_cities]
│       │   ├── services.birmingham.uk.europa.   [c266_subzones]
│       │   ├── research.birmingham.uk.europa.   [c266_subzones]
│       │   └── admin.birmingham.uk.europa.   [c266_subzones]
│       ├── glasgow.uk.europa.   [c266_cities]
│       │   ├── services.glasgow.uk.europa.   [c266_subzones]
│       │   ├── research.glasgow.uk.europa.   [c266_subzones]
│       │   └── admin.glasgow.uk.europa.   [c266_subzones]
│       └── london.uk.europa.   [c266_cities]
│           ├── services.london.uk.europa.   [c266_subzones]
│           ├── research.london.uk.europa.   [c266_subzones]
│           └── admin.london.uk.europa.   [c266_subzones]
├── infra.   [c266_tld_infra]
│   ├── dns.infra.   [c266_functional_1]
│   │   ├── root.dns.infra.   [c266_functional_2]
│   │   ├── tld.dns.infra.   [c266_functional_2]
│   │   └── resolvers.dns.infra.   [c266_functional_2]
│   ├── routing.infra.   [c266_functional_1]
│   └── monitoring.infra.   [c266_functional_1]
├── research.   [c266_tld_research]
│   ├── universities.research.   [c266_functional_1]
│   ├── experiments.research.   [c266_functional_1]
│   │   ├── latency.experiments.research.   [c266_functional_2]
│   │   └── failures.experiments.research.   [c266_functional_2]
│   └── datasets.research.   [c266_functional_1]
├── services.   [c266_tld_services]
│   ├── web.services.   [c266_functional_1]
│   │   └── portals.web.services.   [c266_functional_2]
│   ├── api.services.   [c266_functional_1]
│   └── mail.services.   [c266_functional_1]
├── lab.   [c266_tld_lab]
│   ├── benchmark.lab.   [c266_functional_1]
│   │   └── scenarios.benchmark.lab.   [c266_functional_2]
│   ├── checker.lab.   [c266_functional_1]
│   └── clients.lab.   [c266_functional_1]
└── test.   [c266_tld_test]
    ├── positive.test.   [c266_functional_1]
    ├── negative.test.   [c266_functional_1]
    │   ├── nxdomain.negative.test.   [c266_functional_2]
    │   └── delegation.negative.test.   [c266_functional_2]
    └── dnssec.test.   [c266_functional_1]
```

### 2.1 Delegation and NS/SOA requirements

1. The root `.` is authoritative on **`c266_root` (10.210.0.10)**. Its authoritative NS and SOA primary name is `a.root-servers.`, with A `a.root-servers. → 10.210.0.10`.
2. For **every other zone `Z`**, use its nameserver **`ns1.Z`** (absolute FQDN) and set the NS host address to the IPv4 address of the assigned authoritative device shown in §1.2. Every zone has a valid authoritative SOA, apex NS, and A record for its own nameserver.
3. Every parent zone must delegate **all** of its immediately subordinated child zones using `NS` records pointing to the exact child nameserver. Since `ns1.Z` is in-bailiwick of child `Z`, publish the required parent-side glue A with the **same address** as that child's nameserver A. All **200** delegations must be consistent and traversable from `.`.
4. The root delegates the six TLDs directly. `europa.` delegates 22 country zones. Each country zone delegates its listed city zones; each city delegates **exactly three** child zones `services`, `research`, and `admin`. The other five TLDs delegate their functional zones according to the tree; these branches must be real zones, including their nested descendants.
5. Do not confuse **zone names** with **A-record names** such as `www`, `mail`, `git`, `portal`, or `ns1`. These hostnames are records *inside* the corresponding zone and must **not** be added as separately delegated zones.

## 3. Required application/service records (370 records)

### 3.1 All 37 city zones

For **each** of the 37 zones `C = <city>.<country>.europa.` represented above, add the following four records in the **city zone served by `c266_cities` at 10.210.28.10**:

| Owner FQDN | Type | Exact value |
|---|---|---|
| `C` (zone apex) | `MX` | `10 mail.C` |
| `www.C` | `A` | `10.210.28.10` |
| `api.C` | `A` | `10.210.28.10` |
| `mail.C` | `A` | `10.210.28.10` |

Here `mail.C` means the absolute owner `mail.<city>.<country>.europa.` and **MX target names must end with a trailing dot**. The `mail` name is for DNS testing; it **does not require an SMTP daemon**. The `www`/`api` labels are similarly DNS aliases, not a requirement to deploy HTTP or API services. All 37 city zones use the **same actual existing DNS host** at `10.210.28.10`, even when the city name corresponds to a different original router.

### 3.2 All 111 delegated city subzones

For each of the 37 city zones `C`, add **three actual delegated authoritative zones**, all served by `c266_subzones` at `10.210.26.10`, with exactly the following two application A records in each:

| Delegated zone | Owner FQDNs | Type | Exact IPv4 for both |
|---|---|---|---|
| `services.C` | `portal.services.C`, `api.services.C` | `A` | `10.210.26.10` |
| `research.C` | `git.research.C`, `data.research.C` | `A` | `10.210.26.10` |
| `admin.C` | `monitor.admin.C`, `logs.admin.C` | `A` | `10.210.26.10` |

This yields `37 × 3 × 2 = 222` A records in these subzones, in addition to the 111 required NS nameserver A records. The city-level requirement yields `37 × (3 A + 1 MX) = 148` records. Together they comprise **370 requested A/MX records**, plus SOA/NS/nameserver-address infrastructure records.

### 3.3 Functional zones under the five other TLDs

Create **all 24 functional zones** shown in the tree under `infra.`, `research.`, `services.`, `lab.` and `test.`. Zones directly under a TLD (depth two) are served by `c266_functional_1` at `10.210.18.10`; further delegated child zones (depth three) are served by `c266_functional_2` at `10.210.15.10`. Each needs its own SOA, apex NS, nameserver A and parent-side NS/glue. These are zones, not necessarily application endpoints. The zone named `dnssec.test.` is a thematic name: **DNSSEC signing is not required**.

## 4. BIND9 server behavior

- **Authoritative servers:** listen on their assigned IPv4 interfaces; set `recursion no`; permit queries from the laboratory; serve *only* their assigned authoritative zones. Do not enable recursion on an authoritative server.
- **Recursive servers:** `c266_resolver_1` (10.210.34.10) and `c266_resolver_2` (10.210.36.10); configure `recursion yes` and allow client queries. They must hold **no master/slave authoritative zones**. Instead, configure root hints for the private root `a.root-servers.` at `10.210.0.10`.
- **Isolated DNS hierarchy:** IPv4 only; `dnssec-validation no` while unsigned; **no external root hints, Internet DNS forwarders, or public-DNS dependency**. Avoid including default Internet root zones that conflict with the private root.
- **Persistence:** store the BIND configuration and zone files under each assigned host's persistent Kathara filesystem (e.g. `<host>/etc/bind/`) and launch/restart `named` via the host's `.startup` after its network configuration. Preserve original network files and commands.

## 5. Client name resolution

- `c266_client_1` (10.210.1.10) must use **only** `c266_resolver_1` (`10.210.34.10`) through persistent `/etc/resolv.conf` configuration.
- `c266_client_2` (10.210.17.10) must use **only** `c266_resolver_2` (`10.210.36.10`) through persistent `/etc/resolv.conf` configuration.
- Both clients must resolve all **370** application A/MX records to their exact requested results by following the artificial DNS hierarchy; equivalently the two clients together must produce **740 successful record responses**. Querying a deeper child zone must follow its authoritative delegation chain instead of being answered incorrectly by the parent zone.

## 6. Acceptance requirements and restrictions

- **Physical correctness:** all original 37 routers and 57 WAN domains remain unchanged, with all original WAN/loopback IPv4 addresses, forwarding and 3,327 static backbone routes intact; the 16 required hosts and 10 access domains are present and routed without collisions.
- **Authoritative correctness:** all 201 zones have valid, loadable SOA and NS data and an A record for the assigned authoritative nameserver; all 200 NS/glue delegations use the correct target and IPv4 address. Child zones must return authoritative answers with the `aa` flag when queried directly.
- **Record correctness:** all 370 application DNS entries defined in §3 return the exact A or MX responses. The MX exchange FQDNs also resolve through their corresponding `mail` A records.
- **Recursive correctness:** both clients use their respective recursive resolvers and obtain correct results for all 370 application queries, including deeply nested city subzones; recursive responses advertise recursive availability.
- **No unwanted additions:** do not add 201 machines, do not change original WAN routing or router images, and do not install web/mail application daemons merely to satisfy the names of DNS A/MX records. All configuration must be persistent in the laboratory.
- **Output:** modify the supplied lab in place, producing a complete `lab.conf`, `.startup` scripts for the new hosts, appropriate append-only router updates, and valid persistent BIND9 configuration/zone files. Provide a short list of the created devices/files and any unmet constraints; do not create or alter the evaluation correction file. Runtime execution can be performed externally.

### Example authoritative and recursive queries

```shell
dig @10.210.0.10 . SOA +norecurse
dig @10.210.0.10 europa. NS +norecurse
dig @10.210.28.10 rome.it.europa. MX +norecurse
dig @10.210.28.10 www.amsterdam.nl.europa. A +norecurse
dig @10.210.26.10 portal.services.rome.it.europa. A +norecurse
dig @10.210.34.10 git.research.paris.fr.europa. A
dig @10.210.36.10 mail.milan.it.europa. A
```

The hierarchy must conform to the **zone-to-device assignment in the tree**, even where the visual layout suggests geographic locations. Logical country and city names do **not** entail extra city-specific physical DNS hosts.
