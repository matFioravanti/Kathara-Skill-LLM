# Laboratory DNS

PCs 1–31 serve their assigned zones with BIND. PC32 (10.15.8.14) is the recursive resolver, using PC1 (10.15.1.11) as its root hint. All 40 PCs use PC32 for DNS. The existing kathara/base image must provide BIND 9 (`named`); no package installation is performed at startup.

The server and zone files are in each PC's `etc/bind` directory. Each child server has an in-zone `ns` name, with matching glue in its parent. The `www.example.com` address is PC6's existing address. The MX targets for company.com and university.edu use PC7 and PC11 respectively; these records do not install or start mail or web services.

After starting the lab, examples to check from a PC include:

```sh
dig @10.15.8.14 ai.research.lab.net A
dig @10.15.8.14 www.example.com A
dig @10.15.8.14 company.com MX
dig @10.15.8.14 mail.university.edu A
dig @10.15.1.11 com NS +norecurse
```

The final query should return a referral with the com name server and its glue. To inspect an entire path, use `dig +trace ai.research.lab.net` from a PC with `dig` installed. The laboratory uses a private DNS root and disables DNSSEC validation for this unsigned hierarchy.
