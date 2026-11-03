# DNS lab

The existing IPv4 topology and static routes are used unchanged. PCs 1–31 run authoritative BIND servers for the zones in the diagram. pc32 (10.15.8.14) is the recursive resolver; all PCs use it through `/etc/resolv.conf`. Its only root hint is pc1 (10.15.1.11). DNSSEC validation is disabled because this private DNS hierarchy is unsigned. Each delegation uses an in-bailiwick `ns` name and glue in the parent zone.

`www.example.com` points to pc6 (10.15.2.12), since no web-server address was specified. The A record does not itself start a web service. The MX targets point to pc7 and pc11 respectively; these records do not install mail services.

The Kathara PC image must contain BIND 9 (`named`) and DNS client tools. Start the lab with `kathara lstart`. After startup, for example on pc40:

```sh
dig @10.15.8.14 ai.research.lab.net A
dig @10.15.8.14 shop.example.com A
dig @10.15.8.14 company.com MX
dig @10.15.8.14 university.edu MX
dig @10.15.1.11 ai.research.lab.net A +norecurse
```

The last query returns the root referral; subsequent referrals can be inspected by querying the indicated servers with `+norecurse`. pc32 caches answers, so repeated recursive queries may be answered from cache.
