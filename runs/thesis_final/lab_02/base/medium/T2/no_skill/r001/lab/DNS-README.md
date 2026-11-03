# Laboratory DNS

The existing PC addresses and routes are unchanged. pc1 through pc31 each serve the zone specified in their `/etc/bind/named.conf`; pc32 (10.15.8.14) is the recursive resolver. PC startup scripts configure that resolver in `/etc/resolv.conf`. The resolver starts from the private root on pc1 (10.15.1.11); it does not use public DNS. Each zone has an apex address for its assigned PC, an authoritative `ns` address, and glue for its immediate children. `www.example.com` points to pc6. The two mail hosts point to pc7 and pc11 respectively.

The Kathara image must provide BIND's `named` executable; `dig` is needed for the check script. The startup scripts launch named in the background and log to `/var/log/named-lab.log` inside each DNS PC. DNSSEC validation is disabled because this is a private, unsigned hierarchy.

After starting the lab and allowing the nodes to boot, run this inside any PC:

```sh
sh /shared/check-dns.sh
```

This queries the recursive resolver for all 30 non-root zone apexes, the web and mail addresses, and both MX records. To inspect an individual referral or diagnose a failure, for example:

```sh
dig @10.15.1.11 net NS +norecurse
dig @10.15.6.11 ai.research.lab.net NS +norecurse
dig @10.15.8.14 ai.research.lab.net A
```
