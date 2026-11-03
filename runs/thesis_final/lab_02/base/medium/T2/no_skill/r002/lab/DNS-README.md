# Laboratory DNS

The authoritative servers run on pc1–pc31, one zone per machine. Each
zone's BIND configuration and zone file are in `pcN/etc/bind/`. Delegations
use `ns.<child-zone>` and include its existing address as glue. pc1 is the
private root, using `ns.root.`.

pc32 (10.15.8.14) is the recursive resolver. Its root hints point only to pc1;
DNSSEC validation is disabled because this private hierarchy is unsigned.
The PC startup scripts configure `/etc/resolv.conf` to use pc32. The existing
network configuration is unchanged. The `kathara/base` image must provide
BIND's `named` executable.

After starting the lab, queries can be checked from a PC, for example:

```sh
dig @10.15.8.14 ai.research.lab.net A
dig @10.15.8.14 data.research.lab.net A
dig @10.15.8.14 www.example.com A
dig @10.15.8.14 company.com MX
dig @10.15.8.14 university.edu MX
dig @10.15.8.14 mail.company.com A
dig @10.15.8.14 mail.university.edu A
```

A cold-cache lookup may take a little longer while the resolver follows the
delegations. For direct referral inspection, query the parent server with
`+norecurse`, for example `dig @10.15.6.11 ai.research.lab.net NS +norecurse`.
