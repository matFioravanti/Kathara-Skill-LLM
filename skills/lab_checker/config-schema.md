# Kathara Lab Checker — Configuration Schema Reference

Full annotated schema for `correction.yaml` (preferred) and `correction.json`.
All examples are shown in YAML first; JSON equivalents are noted where the syntax differs.

---

## Top-level structure (YAML)

```yaml
# Embed the expected lab topology inline (YAML only; use instead of a separate structure file)
lab_inline: |
  router1[0]="net12"
  router2[0]="net12"

labs_path: path/to/student/labs   # optional; overridden by --labs CLI flag
convergence_time: 60               # seconds to wait for routing convergence
default_image: kathara/frr         # fallback image if student lab omits image declaration

test:
  requiring_startup: [...]
  ip_mapping: {...}
  daemons: {...}
  kernel_routes: {...}
  protocols: {...}
  applications: {...}
  reachability: {...}
  custom_commands: {...}
```

> **JSON note**: replace `lab_inline` with a separate `structure` file and set
> `"structure": "structure"` in the JSON config.

---

## `lab_inline` / `structure`

In YAML, embed the topology directly using `lab_inline` (preferred):

```yaml
lab_inline: |
  as1r1[0]="net_12"
  as1r1[1]="net_1"
  as1r2[0]="net_1"
  as1r2[1]="net_13"
```

In JSON, create a separate file named `structure` (no extension) with the same
`lab.conf`-formatted content, and reference it:

```json
{ "structure": "structure" }
```

---

## `test` block

### `requiring_startup`

List of device names that must have a `.startup` file in the student lab.

```yaml
test:
  requiring_startup:
    - router1
    - router2
    - pc1
```

---

### `ip_mapping`

Per-device, per-interface expected IP with prefix. Keys are interface numbers as strings.

```yaml
test:
  ip_mapping:
    as1r1:
      "0": 10.20.0.1/30
      "1": 1.0.0.1/24
    as1r2:
      "0": 1.1.0.1/24
      "1": 1.0.0.2/24
      "2": 10.20.1.1/30
    pc1:
      "0": 192.168.1.2/24
```

Interface number `N` maps to `ethN` inside the device.

---

### `daemons`

Per-device daemon assertions. Bare name = must be running; `!name` = must NOT be running.

```yaml
test:
  daemons:
    as1r1:
      - bgpd
      - ripd
    local:
      - named
      - "!watchfrr"
    pc:
      - "!watchfrr"
      - "!ripd"
```

Common daemon names: `bgpd`, `ripd`, `ospfd`, `ospf6d`, `zebra`, `watchfrr`, `named`,
`dnsmasq`, `apache2`, `nginx`.

---

### `kernel_routes`

Per-device list of routes that must appear in the Linux routing table after convergence.

Simple form (presence only):

```yaml
test:
  kernel_routes:
    as1r1:
      - 1.0.0.0/24
      - 2.0.0.0/8
      - 10.20.0.0/30
    pc1:
      - 0.0.0.0/0
      - 192.168.1.0/24
```

With next-hop / interface assertion (list of two elements):

```yaml
test:
  kernel_routes:
    router1:
      - ["0.0.0.0/0", ["10.0.0.1", "eth0"]]
```

Include only routes that are **explicitly installed** by a routing daemon or a manual
`ip route add` command: IGP-learned (RIP/OSPF), BGP-learned, and static routes. Do
**not** include directly-connected subnets — Linux auto-installs those as
`proto kernel scope link` entries when an IP is assigned to an interface and the
checker does not count them. Listing them causes false failures: "wrong number of
routes" and "missing route X". For hosts that set a default gateway via
`ip route add default via ...`, only `0.0.0.0/0` should appear in `kernel_routes`.

---

### `protocols`

#### BGP (`bgpd`)

```yaml
test:
  protocols:
    bgpd:
      neighbors:
        as1r1:
          - ip: 1.0.0.2
            asn: 1
          - ip: 10.20.0.2
            asn: 2
        as2r1:
          - ip: 2.0.0.2
            asn: 2
          - ip: 10.20.0.1
            asn: 1
          - ip: 20.30.0.2
            asn: 3
      networks:
        as1r1:
          - 1.0.0.0/8
        as2r1:
          - 2.0.0.0/8
      injections:
        as1r1:
          - "!connected"   # connected routes must NOT be redistributed into BGP
        as2r1:
          - "!connected"
```

- `neighbors`: each entry needs `ip` (peer address, IPv4 or IPv6) and `asn`.
- `networks`: prefixes announced via BGP `network` statements.
- `injections` under `bgpd`: what is redistributed *into* BGP. Prefix `!` = must not be.

#### RIP (`ripd`)

```yaml
test:
  protocols:
    ripd:
      injections:
        as1r1:
          - connected
          - bgp
        as1r2:
          - connected
          - bgp
```

#### OSPF (`ospfd`)

```yaml
test:
  protocols:
    ospfd:
      neighbors:
        r1:
          - ip: 10.0.0.2
      routes:
        r1:
          - 192.168.1.0/24
      interfaces:
        r1:
          - name: eth0
            area: 0.0.0.0
```

#### EVPN / VTEP (advanced)

```yaml
test:
  protocols:
    evpn:
      sessions:
        leaf1:
          - ip: 10.0.0.2
            asn: 65001
      vtep:
        leaf1:
          - 10.0.0.1
      announced_vni:
        leaf1:
          - 100
          - 200
```

---

### `applications`

#### DNS

```yaml
test:
  applications:
    dns:
      authoritative:
        ".":
          - 1.1.0.2       # root nameserver IP
        net:
          - 2.1.0.2
      local_ns:
        3.2.0.2:          # resolver IP
          - as1r1         # these devices must use it as their local nameserver
          - as1r2
          - pc
      records:
        A:
          www.example.com:
            - 203.0.113.1
        AAAA:
          ipv6.example.com:
            - 2001:db8::1
        MX:
          example.com:
            - "10 mail.example.com"
```

- `authoritative`: zone → list of authoritative server IPs.
- `local_ns`: resolver IP → list of device names that must have it in `/etc/resolv.conf`.
- `records`: record type → DNS name → expected value(s).

#### HTTP

```yaml
test:
  applications:
    http:
      server1:
        - url: http://10.0.0.1/
          expected_status: 200
```

---

### `reachability`

Per-device list of IPs or DNS names that must be ping-reachable.

```yaml
test:
  reachability:
    as1r1:
      - 1.0.0.1
      - 1.0.0.2
      - 2.0.0.1
      - 10.20.0.1
      - 10.20.0.2
    pc1:
      - 192.168.1.1    # default gateway
      - 192.168.2.1
      - www.example.com
```

For fully-meshed scenarios, list every IP in the address plan for each device.

---

### `custom_commands`

Arbitrary commands executed inside a device. At least one of `regex_match`, `output`, or
`exit_code` is required per entry.

```yaml
test:
  custom_commands:
    router1:
      - command: sysctl net.ipv4.ip_forward
        regex_match: "net\\.ipv4\\.ip_forward = 1"
      - command: cat /etc/frr/frr.conf
        output: "router bgp 65001\n"
      - command: ping -c 1 8.8.8.8
        exit_code: 0
```

---

## Full YAML example (simple RIP lab)

```yaml
# Lab: simple-rip
# Two routers, two host subnets, RIP routing

lab_inline: |
  r1[0]="net12"
  r1[1]="net1"
  r2[0]="net12"
  r2[1]="net2"
  pc1[0]="net1"
  pc2[0]="net2"

convergence_time: 30
default_image: kathara/frr

test:
  requiring_startup:
    - r1
    - r2
    - pc1
    - pc2

  ip_mapping:
    r1:
      "0": 192.168.12.1/24
      "1": 192.168.1.1/24
    r2:
      "0": 192.168.12.2/24
      "1": 192.168.2.1/24
    pc1:
      "0": 192.168.1.2/24
    pc2:
      "0": 192.168.2.2/24

  daemons:
    r1:
      - ripd
      - zebra
    r2:
      - ripd
      - zebra
    pc1:
      - "!ripd"
      - "!zebra"
    pc2:
      - "!ripd"
      - "!zebra"

  kernel_routes:
    r1:
      - 192.168.12.0/24
      - 192.168.1.0/24
      - 192.168.2.0/24
    r2:
      - 192.168.12.0/24
      - 192.168.1.0/24
      - 192.168.2.0/24
    pc1:
      - 0.0.0.0/0
      - 192.168.1.0/24
    pc2:
      - 0.0.0.0/0
      - 192.168.2.0/24

  protocols:
    ripd:
      injections:
        r1:
          - connected
        r2:
          - connected

  reachability:
    r1:
      - 192.168.12.2
      - 192.168.1.2
      - 192.168.2.1
      - 192.168.2.2
    r2:
      - 192.168.12.1
      - 192.168.1.1
      - 192.168.1.2
      - 192.168.2.2
    pc1:
      - 192.168.1.1
      - 192.168.12.1
      - 192.168.12.2
      - 192.168.2.1
      - 192.168.2.2
    pc2:
      - 192.168.2.1
      - 192.168.12.1
      - 192.168.12.2
      - 192.168.1.1
      - 192.168.1.2
```

---

## Check priorities (execution order)

| Priority range | Category |
|---|---|
| 0–999 | Foundation / system-level (device existence, interfaces, daemons, reachability) |
| 1000–1999 | Protocol checks (BGP, OSPF, RIP, EVPN, SCION) |
| 2000–2999 | Routing table / data-plane (`kernel_routes`) |
| 3000–3999 | Application checks (DNS, HTTP) |
| 4000–4999 | Custom commands |

Specific priorities: `DeviceExistenceCheck`=0, `CollisionDomainCheck`=10,
`StartupExistenceCheck`=20, `InterfaceIPCheck`=50, `ReachabilityCheck`=70,
`DaemonCheck`=80, `BGPNeighborCheck`=1010, `BGPRoutesCheck`=1020,
`AnnouncedNetworkCheck`=1110, `ProtocolRedistributionCheck`=1120,
`KernelRouteCheck`=2000, `DNSAuthorityCheck`=3010, `LocalNSCheck`=3020,
`DNSRecordCheck`=3030, `HTTPCheck`=3040, `CustomCommandCheck`=4010.

---

## CLI flags reference

```
python3 -m kathara_lab_checker
  --config  <path>          Path to correction.yaml or correction.json (required)
  --labs    <path>          Path to directory containing student lab folders (required)
  --no-cache                Re-run all checks even if cached results exist
  --report-type excel|csv|none
                            Output format (default: csv)
```