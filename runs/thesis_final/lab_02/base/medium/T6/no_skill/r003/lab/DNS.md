# Laboratory DNS

pc1–pc31 run the authoritative BIND servers in the order specified by the lab hierarchy. pc32 (10.15.8.14) runs the recursive resolver, using pc1 (10.15.1.11) as its only root hint. Every PC uses pc32 for DNS. Authoritative servers do not perform recursion; DNSSEC validation is disabled because this private hierarchy is unsigned. Each server starts `named` from its startup script, so the configured `kathara/base` image must contain BIND 9 (`named`).

The original lab has no configured web service. `www.example.com` points to the existing address of pc33 (10.15.9.11), selected as the prospective web host; DNS configuration alone does not start a web service.

After starting the lab, example checks from a PC with DNS tools installed are:

```
dig @10.15.8.14 ai.research.lab.net A
dig @10.15.8.14 company.com MX
dig @10.15.1.11 com NS +norecurse
dig @10.15.1.12 example.com NS +norecurse
```
