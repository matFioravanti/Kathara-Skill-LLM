# DNS lab

The existing static network hosts a private DNS hierarchy. pc1–pc13 serve the zones shown in the topology, pc14 resolves recursively from pc1, and pc16–pc20 use pc14. DNSSEC validation is disabled for these unsigned private zones. `www.example.com` points to pc4 (10.14.1.14); this is a DNS record and does not itself install a web server. The MX records likewise describe mail hosts without installing mail services.

Start the lab with `kathara lstart`. The configured `kathara/base` image must provide BIND 9 (`named`) and the usual network utilities. After startup, from a client such as pc16, check the complete delegation chain with:

```sh
dig @10.14.4.14 www.example.com A +short
dig @10.14.4.14 shop.example.com A +short
dig @10.14.4.14 api.service.com A +short
dig @10.14.4.14 ci.tools.net A +short
dig @10.14.4.14 ai.research.lab.net A +short
dig @10.14.4.14 data.research.lab.net A +short
dig @10.14.4.14 lab.net MX +short
```

Expected A answers, in order, are 10.14.1.14, 10.14.3.11, 10.14.3.12, 10.14.4.11, 10.14.4.12, and 10.14.4.13. The MX answer is `10 mail.lab.net.`. Query an authoritative server directly, for example `dig @10.14.1.11 com NS`, to inspect a referral. Use `named-checkconf /etc/bind/lab.conf` and `named-checkzone` inside a DNS server if troubleshooting.
