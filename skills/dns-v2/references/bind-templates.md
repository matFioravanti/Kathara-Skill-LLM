# BIND templates for new files

Substitute placeholders with inventory/task values. Use only the required role. Merge into existing configurations while preserving unrelated content. The conservative master/slave vocabulary works with BIND 9.11/9.18; check the actual image/version. Units and paths still require the G2 check.

## Authoritative server

For an unsigned artificial hierarchy:

```conf
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

For the authoritative root use exactly:
```conf
zone "." { type master; file "/etc/bind/db.root"; };
```
Its db.root holds the root SOA, apex NS and requested delegations. Do not add a hint zone on that server. Confirm query ACLs fit the isolated lab.

## Recursive resolver

```conf
options {
    directory "/var/cache/bind";
    recursion yes;
    allow-query { <client-subnets>; };
    allow-recursion { <client-subnets>; };
    allow-query-cache { <client-subnets>; };
    dnssec-validation no;
    empty-zones-enable no;
    listen-on { any; };
    listen-on-v6 { any; };
};
zone "." { type hint; file "/etc/bind/db.hints"; };
```

Substitute each subnet with a valid ACL element, including its semicolon. Retain explicitly required DNSSEC design instead of disabling validation. Use empty-zones-enable no where built-in reverse zones mask requested delegations. Add no authoritative lab zone or external forwarder unless explicitly required.

## Hints and zone records

db.hints contains every actual root NS and its usable owned transport addresses, matching root apex data:
```dns
. 300 IN NS <root-ns-fqdn>.
<root-ns-fqdn>. 300 IN A <owned-root-ipv4>
; Add AAAA only for the applicable IPv6 transport.
```

A primary zone file needs one apex SOA and its NS set:
```dns
$TTL 300
@ IN SOA <primary-ns-fqdn>. <rname-fqdn>. ( 1 3600 600 86400 60 )
@ IN NS <ns-fqdn>.
<ns-fqdn>. IN A <owned-ns-ipv4>
; Add authoritative AAAA where required/usable.
```
Placeholders omit the final dot, already present in the template. Root RNAME is hostmaster.; ordinary zone RNAME may be hostmaster.<zone>. Apply existing serial and exact requested RRsets rules. A/AAAA data belongs in the authoritative zone for the NS name. For a child whose NS lies beneath its own cut, add parent delegation and matching glue:
```dns
<child-zone>. IN NS <ns-in-child>.
<ns-in-child>. IN A <owned-ns-ipv4>
```
Match child apex NS and required address families. Out-of-bailiwick NS requires a separate resolution path. Add requested A/AAAA and MX records to their closest authoritative zone; use an absolute resolvable non-alias target for MX.

## Offline syntax checks

Run named-checkzone <zone> <host-zone-file> and named-checkconf <config-file> only when their files/includes resolve correctly in the selected environment. A compatible offline root with named-checkconf -t <root> -z /etc/bind/named.conf can validate primary-zone loading if all dependencies are supplied. Missing tools, include paths or matching versions leave the corresponding G2 checks UNVERIFIED. A nonzero result demonstrating a real syntax defect is FAIL.

Technical references: [BIND 9.18 manual pages](https://bind9.readthedocs.io/en/v9.18.38/manpages.html), [Kathara file/startup semantics](https://www.kathara.org/man-pages/kathara-lab-dirs.7.html).
