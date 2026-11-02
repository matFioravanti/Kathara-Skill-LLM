# Lab DNS

pc1–pc31 serve the assigned zones using BIND. pc32 (10.15.8.14) is the recursive resolver; all PC startup scripts point their resolver to it. The resolver starts with the lab root hint at pc1 and follows the NS delegations and glue. Each authoritative server disables recursion. The configuration assumes the existing `kathara/base` image provides BIND (`named`).

The service names at delegated zone apices resolve to their respective authoritative PCs. `www.example.com` points to pc6. The MX records for company.com and university.edu point to mail hosts on pc7 and pc11 respectively; these are DNS references and do not install web or mail servers.

After starting the lab, for example, run on a client:

```sh
dig @10.15.8.14 ai.research.lab.net A
dig @10.15.8.14 www.example.com A
dig @10.15.8.14 company.com MX
dig @10.15.8.14 mail.university.edu A
dig @10.15.1.11 com NS +norecurse
```

The DNS hierarchy is private to this lab; the root server only delegates the four configured TLDs. DNSSEC validation is disabled for these unsigned zones.
