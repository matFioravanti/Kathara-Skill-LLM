# Lab DNS

The existing `kathara/base` image must provide BIND 9 (`named`) on pc1–pc14 and Python 3 on pc4. The startup scripts start BIND after configuring the existing network; pc4 also serves `/var/www/html` on HTTP port 80. The DNS files are copied into each machine using Kathara's per-machine filesystem directories.

pc14 (10.14.4.14) is the recursive resolver. Its only root hint is pc1 (10.14.1.11), and recursion is allowed for the two client LANs. pc16–pc20 use pc14 in `/etc/resolv.conf`. DNSSEC validation is disabled because this is a private, unsigned hierarchy.

After starting the lab, run these from any client (for example, pc16):

```sh
dig @10.14.4.14 shop.example.com A +short
dig @10.14.4.14 api.service.com A +short
dig @10.14.4.14 ci.tools.net A +short
dig @10.14.4.14 ai.research.lab.net A +short
dig @10.14.4.14 data.research.lab.net A +short
dig @10.14.4.14 example.com MX +short
dig @10.14.4.14 service.com MX +short
dig @10.14.4.14 lab.net MX +short
dig @10.14.4.14 tools.net MX +short
curl http://www.example.com/
```

To inspect a referral directly, for example: `dig @10.14.3.13 ai.research.lab.net NS +norecurse`. The response should contain the child NS in the authority section and its address as glue in the additional section. Repeat with the other parent servers to inspect the hierarchy.

The MX and A records provide mail routing information. They do not install or configure an SMTP server or mailboxes.
