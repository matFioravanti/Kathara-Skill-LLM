Generate the DNS configuration for the existing Kathara laboratory without changing the topology, IP addresses, or previously configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, four TLDs (innovation, infrastructure, learning, and territory), ten main domains, and their respective delegated subzones. The hierarchy must contain a total of **31 authoritative zones and 30 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc27]
  - TLD innovation → [pc25]
  - TLD infrastructure → [pc10]
  - TLD learning → [pc2]
  - TLD territory → [pc9]
  - Zone aster.innovation → [pc23]
  - Zone pinnacle.innovation → [pc30]
  - Zone vector.innovation → [pc6]
  - Zone cascade.infrastructure → [pc5]
  - Zone compass.infrastructure → [pc14]
  - Zone northstar.learning → [pc26]
  - Zone equinox.learning → [pc17]
  - Zone helios.territory → [pc20]
  - Zone brookfield.territory → [pc12]
  - Zone sierra.territory → [pc22]
  - Zone catalog.aster.innovation → [pc31]
  - Zone stories.aster.innovation → [pc8]
  - Zone units.pinnacle.innovation → [pc4]
  - Zone private.pinnacle.innovation → [pc28]
  - Zone integration.vector.innovation → [pc15]
  - Zone studies.cascade.infrastructure → [pc16]
  - Zone agents.studies.cascade.infrastructure → [pc11]
  - Zone warehouse.studies.cascade.infrastructure → [pc29]
  - Zone prototype.cascade.infrastructure → [pc21]
  - Zone automation.compass.infrastructure → [pc1]
  - Zone remote.northstar.learning → [pc18]
  - Zone lectures.northstar.learning → [pc3]
  - Zone homepage.equinox.learning → [pc24]
  - Zone scholars.helios.territory → [pc7]
  - Zone assistance.brookfield.territory → [pc13]
  - Zone indicators.sierra.territory → [pc19]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `innovation`, `infrastructure`, `learning` and `territory`.
  - `innovation` delegates `aster.innovation`, `pinnacle.innovation` and `vector.innovation`.
  - `infrastructure` delegates `cascade.infrastructure` and `compass.infrastructure`.
  - `learning` delegates `northstar.learning` and `equinox.learning`.
  - `territory` delegates `helios.territory`, `brookfield.territory` and `sierra.territory`.
  - `aster.innovation` delegates `catalog.aster.innovation` and `stories.aster.innovation`.
  - `pinnacle.innovation` delegates `units.pinnacle.innovation` and `private.pinnacle.innovation`.
  - `vector.innovation` delegates `integration.vector.innovation`.
  - `cascade.infrastructure` delegates `studies.cascade.infrastructure` and `prototype.cascade.infrastructure`.
  - `compass.infrastructure` delegates `automation.compass.infrastructure`.
  - `studies.cascade.infrastructure` delegates `agents.studies.cascade.infrastructure` and `warehouse.studies.cascade.infrastructure`.
  - `northstar.learning` delegates `remote.northstar.learning` and `lectures.northstar.learning`.
  - `equinox.learning` delegates `homepage.equinox.learning`.
  - `helios.territory` delegates `scholars.helios.territory`.
  - `brookfield.territory` delegates `assistance.brookfield.territory`.
  - `sierra.territory` delegates `indicators.sierra.territory`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on an existing machine not assigned to any authoritative zone. Client resolvers must send DNS queries to this server; it must be able to query the name servers of the hierarchy when necessary, starting at the root and following delegations until the target zone is reached. All existing clients must be able to use this resolution service.

- **Services:** Configure the necessary DNS records so that `catalog.aster.innovation`, `stories.aster.innovation`, `units.pinnacle.innovation`, `private.pinnacle.innovation`, `integration.vector.innovation`, `studies.cascade.infrastructure`, `agents.studies.cascade.infrastructure`, `warehouse.studies.cascade.infrastructure`, `prototype.cascade.infrastructure`, `automation.compass.infrastructure`, `remote.northstar.learning`, `lectures.northstar.learning`, `homepage.equinox.learning`, `scholars.helios.territory`, `assistance.brookfield.territory` and `indicators.sierra.territory` resolve to the IP addresses of their respective machines. In the `aster.innovation` zone, configure `portalweb.aster.innovation` for the web service. Provide DNS references for the email service of the specified business and academic domains, including `pinnacle.innovation` and `northstar.learning`.

- **Mail records:** Configure the following MX records:
  - `pinnacle.innovation` → MX priority 10, mail server `inbox.pinnacle.innovation`, with an A record pointing to the existing IP address of [pc30].
  - `northstar.learning` → MX priority 10, mail server `inbox.northstar.learning`, with an A record pointing to the existing IP address of [pc26].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. All 31 machines assigned to authoritative zones above must act as the authoritative servers for their respective zones. Select the local name server and clients from the other existing machines. Do not add devices or alter network links, IP addresses, or existing routing.
