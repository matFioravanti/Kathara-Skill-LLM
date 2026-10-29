Generate the DNS configuration for the existing Kathara laboratory, consisting of 4 routers, 20 PCs/hosts, and 6 access LANs, while preserving the topology, IP addresses, and already configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, two TLDs (innovation and infrastructure), four main domains (aster.innovation, vector.innovation, cascade.infrastructure, and compass.infrastructure), and their respective delegated subzones. The hierarchy must contain a total of **13 authoritative zones and 12 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc16]
  - TLD innovation → [pc8]
  - TLD infrastructure → [pc18]
  - Zone aster.innovation → [pc15]
  - Zone vector.innovation → [pc7]
  - Zone cascade.infrastructure → [pc5]
  - Zone compass.infrastructure → [pc20]
  - Zone catalog.aster.innovation → [pc12]
  - Zone integration.vector.innovation → [pc11]
  - Zone studies.cascade.infrastructure → [pc9]
  - Zone automation.compass.infrastructure → [pc3]
  - Zone agents.studies.cascade.infrastructure → [pc13]
  - Zone warehouse.studies.cascade.infrastructure → [pc19]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `innovation` and `infrastructure`.
  - `innovation` delegates `aster.innovation` and `vector.innovation`.
  - `infrastructure` delegates `cascade.infrastructure` and `compass.infrastructure`.
  - `aster.innovation` delegates `catalog.aster.innovation`.
  - `vector.innovation` delegates `integration.vector.innovation`.
  - `cascade.infrastructure` delegates `studies.cascade.infrastructure`.
  - `compass.infrastructure` delegates `automation.compass.infrastructure`.
  - `studies.cascade.infrastructure` delegates `agents.studies.cascade.infrastructure` and `warehouse.studies.cascade.infrastructure`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on [pc17] to receive DNS queries from the five clients [pc1], [pc6], [pc4], [pc10], and [pc14], and to query the other name servers in the hierarchy when needed.

- **Services:** Configure DNS records so that `catalog.aster.innovation`, `integration.vector.innovation`, `automation.compass.infrastructure`, `agents.studies.cascade.infrastructure` and `warehouse.studies.cascade.infrastructure` resolve to the IP addresses of their respective machines. Configure `portalweb.aster.innovation` for the web service in the `aster.innovation` zone. Also provide DNS references for email at the four main domains `aster.innovation`, `vector.innovation`, `cascade.infrastructure`, and `compass.infrastructure`.

- **Mail records:** Configure the following MX records:
  - `aster.innovation` → MX priority 10, mail server `inbox.aster.innovation`, with an A record pointing to the existing IP address of [pc15].
  - `vector.innovation` → MX priority 10, mail server `inbox.vector.innovation`, with an A record pointing to the existing IP address of [pc7].
  - `cascade.infrastructure` → MX priority 10, mail server `inbox.cascade.infrastructure`, with an A record pointing to the existing IP address of [pc5].
  - `compass.infrastructure` → MX priority 10, mail server `inbox.compass.infrastructure`, with an A record pointing to the existing IP address of [pc20].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. The 13 assigned authoritative machines must host their respective zones; [pc17] must act as the local name server, and [pc1], [pc6], [pc4], [pc10], and [pc14] must act as clients. Configure DNS on the assigned devices without changing network links, IP addresses, or existing routing.
