# Lab DNS

The existing `kathara/base` image must provide BIND 9 (`named`). Start the lab with `kathara lstart`; the machine startup scripts start the DNS servers after configuring their existing network settings. pc14 uses pc1 as its root hint and accepts recursive queries from pc16–pc20. The lab is an isolated DNS namespace; DNSSEC validation is disabled because these zones are unsigned.

From a client, verify resolution and mail records, for example:

```sh
dig shop.example.com A
dig api.service.com A
dig ci.tools.net A
dig ai.research.lab.net A
dig data.research.lab.net A
dig www.example.com A
dig example.com MX
dig mail.example.com A
```

Check the other mail domains in the same way. To inspect a delegation directly, query its parent with recursion disabled, for example `dig @10.14.3.13 ai.research.lab.net NS +norecurse`; the response should include the child's NS and glue. `www.example.com` points to pc4, the example.com server; DNS configuration does not start a web or mail service.
