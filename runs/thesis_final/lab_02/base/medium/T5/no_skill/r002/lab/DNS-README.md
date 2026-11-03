# Laboratory DNS

The lab uses BIND (`named`), which must be present in the `kathara/base` image. pc1 through pc31 serve the zones in the requested hierarchy; each zone's `ns.<zone>` address is included as glue in its parent. pc32 (10.15.8.14) is the recursive resolver, using pc1 (10.15.1.11) as its sole root hint. All PCs use pc32 in `/etc/resolv.conf`. DNSSEC validation is disabled for this unsigned private hierarchy.

`www.example.com` points to pc6 (10.15.2.12), since no web server address was specified. This is a DNS record only; no HTTP server is configured. The mail records similarly provide DNS records only.

After starting the lab, from a client such as pc40, check recursion and delegation with:

```sh
dig @10.15.8.14 www.example.com A
dig @10.15.8.14 ai.research.lab.net A
dig @10.15.8.14 company.com MX
dig @10.15.8.14 university.edu MX
dig @10.15.1.11 com NS +norecurse
dig @10.15.8.14 nonexistent.example.com A
```

Expected results include 10.15.2.12 for www.example.com, 10.15.6.12 for ai.research.lab.net, and NXDOMAIN for the nonexistent name. The root query returns a referral for com. To validate individual configuration and zone files inside a server, run `named-checkconf /etc/bind/named.conf` and `named-checkzone <zone> /etc/bind/db.zone`.
