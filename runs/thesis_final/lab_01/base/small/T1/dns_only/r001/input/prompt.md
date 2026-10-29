Generate the DNS configuration for the existing Kathara laboratory, consisting of 4 routers, 20 PCs/hosts, and 6 access LANs, while preserving the topology, IP addresses, and already configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, two TLDs (com and net), four main domains (example.com, service.com, lab.net, and tools.net), and their respective delegated subzones. The hierarchy must contain a total of **13 authoritative zones and 12 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc1]
  - TLD com → [pc2]
  - TLD net → [pc3]
  - Zone example.com → [pc4]
  - Zone service.com → [pc5]
  - Zone lab.net → [pc6]
  - Zone tools.net → [pc7]
  - Zone shop.example.com → [pc8]
  - Zone api.service.com → [pc9]
  - Zone research.lab.net → [pc10]
  - Zone ci.tools.net → [pc11]
  - Zone ai.research.lab.net → [pc12]
  - Zone data.research.lab.net → [pc13]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `com` and `net`.
  - `com` delegates `example.com` and `service.com`.
  - `net` delegates `lab.net` and `tools.net`.
  - `example.com` delegates `shop.example.com`.
  - `service.com` delegates `api.service.com`.
  - `lab.net` delegates `research.lab.net`.
  - `tools.net` delegates `ci.tools.net`.
  - `research.lab.net` delegates `ai.research.lab.net` and `data.research.lab.net`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on [pc14] to receive DNS queries from the five clients [pc16], [pc17], [pc18], [pc19], and [pc20], and to query the other name servers in the hierarchy when needed.

- **Services:** Configure DNS records so that `shop.example.com`, `api.service.com`, `ci.tools.net`, `ai.research.lab.net` and `data.research.lab.net` resolve to the IP addresses of their respective machines. Configure `www.example.com` for the web service in the `example.com` zone. Also provide DNS references for email at the four main domains `example.com`, `service.com`, `lab.net`, and `tools.net`.

- **Mail records:** Configure the following MX records:
  - `example.com` → MX priority 10, mail server `mail.example.com`, with an A record pointing to the existing IP address of [pc4].
  - `service.com` → MX priority 10, mail server `mail.service.com`, with an A record pointing to the existing IP address of [pc5].
  - `lab.net` → MX priority 10, mail server `mail.lab.net`, with an A record pointing to the existing IP address of [pc6].
  - `tools.net` → MX priority 10, mail server `mail.tools.net`, with an A record pointing to the existing IP address of [pc7].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. Machines [pc1] through [pc13] must act as their assigned authoritative servers, [pc14] as the local name server, and [pc16] through [pc20] as clients. Configure DNS on the assigned devices without changing network links, IP addresses, or existing routing.
