# DNS in the laboratory

The authoritative servers are pc1 through pc49. pc1 serves the root; each other PC serves the zone in its `/etc/bind/named.conf`. Delegations use `ns.<zone>` with an A record in the parent as glue. The resolver on pc50 (10.16.13.12) uses pc1 (10.16.1.11) as its only root hint and performs iterative resolution. All PCs use pc50 in `/etc/resolv.conf`.

The existing `kathara/base` image must provide BIND 9's `named` executable. DNS starts after each PC's existing network setup; no network settings were changed. DNSSEC validation is disabled for this private, unsigned namespace.

After starting the lab, examples of checks from any PC are:

```sh
dig @10.16.13.12 ai.research.lab.net A
dig @10.16.13.12 media.news.info A
dig @10.16.13.12 servizi.ministero.gov MX
dig @10.16.13.12 mail.servizi.ministero.gov A
dig @10.16.1.11 com NS +norecurse
```

The first recursive query after startup can take longer while the resolver discovers the hierarchy. Zone files and the root hint are mounted through Kathara's per-device filesystem directories; edit them there and restart the affected device to apply changes.
