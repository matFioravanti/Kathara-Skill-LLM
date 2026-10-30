# Laboratory DNS

The authoritative servers run BIND on pc1–pc13; pc14 resolves recursively using pc1 (10.14.1.11) as its only root hint. Clients pc16–pc20 use pc14 (10.14.4.14). DNSSEC validation is disabled for this unsigned private hierarchy.

No web service was present in the original lab. The `www.example.com` record points to the existing pc15 address, 10.14.5.11; the DNS configuration does not install a web server.

The PC images must provide BIND 9 (`named`). After starting the lab, test e.g. `dig @10.14.4.14 ai.research.lab.net A` and `dig @10.14.4.14 example.com MX` from a client.
