# Laboratory DNS

The existing static routes carry DNS traffic between the servers. pc1–pc49 each serve the zone assigned in the DNS tree; their BIND zone files and configuration are in `pcN/etc/bind/`. Each delegation has an in-bailiwick name server and glue pointing to the corresponding PC's existing IPv4 address. pc50 (10.16.13.12) is the recursive resolver, with pc1 (10.16.1.11) as its sole root hint. pc51–pc60 use pc50 through `/etc/resolv.conf`.

The `kathara/base` image must provide BIND 9's `named` executable. The startup scripts launch it after configuring the existing network. These are isolated laboratory zones, so DNSSEC validation is disabled on the resolver. The configured MX records are DNS records only; no mail service is installed.

After starting the lab with Kathara, run queries from a client, for example:

```sh
dig @10.16.13.12 ai.research.lab.net A
dig @10.16.13.12 servizi.ministero.gov MX
dig @10.16.1.11 com NS +norecurse
dig @10.16.13.12 nonexistent.example.com A
```

The first two should return `10.16.6.12` and `10 mail.servizi.ministero.gov.` respectively; the root query should return a referral, and the last query should return NXDOMAIN. Recursive answers may be cached.
