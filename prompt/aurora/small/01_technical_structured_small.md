Generate the DNS configuration for the existing Kathara laboratory, consisting of 4 routers, 20 PCs/hosts, and 6 access LANs, while preserving the topology, IP addresses, and already configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, two TLDs (tech and cloud), four main domains (nimbus.tech, forge.tech, quantum.cloud, and matrix.cloud), and their respective delegated subzones. The hierarchy must contain a total of **13 authoritative zones and 12 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc8]
  - TLD tech → [pc18]
  - TLD cloud → [pc12]
  - Zone nimbus.tech → [pc1]
  - Zone forge.tech → [pc17]
  - Zone quantum.cloud → [pc14]
  - Zone matrix.cloud → [pc9]
  - Zone store.nimbus.tech → [pc6]
  - Zone gateway.forge.tech → [pc11]
  - Zone experiments.quantum.cloud → [pc3]
  - Zone build.matrix.cloud → [pc16]
  - Zone models.experiments.quantum.cloud → [pc7]
  - Zone datasets.experiments.quantum.cloud → [pc20]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `tech` and `cloud`.
  - `tech` delegates `nimbus.tech` and `forge.tech`.
  - `cloud` delegates `quantum.cloud` and `matrix.cloud`.
  - `nimbus.tech` delegates `store.nimbus.tech`.
  - `forge.tech` delegates `gateway.forge.tech`.
  - `quantum.cloud` delegates `experiments.quantum.cloud`.
  - `matrix.cloud` delegates `build.matrix.cloud`.
  - `experiments.quantum.cloud` delegates `models.experiments.quantum.cloud` and `datasets.experiments.quantum.cloud`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on [pc2] to receive DNS queries from the five clients [pc19], [pc5], [pc10], [pc4], and [pc15], and to query the other name servers in the hierarchy when needed.

- **Services:** Configure DNS records so that `store.nimbus.tech`, `gateway.forge.tech`, `build.matrix.cloud`, `models.experiments.quantum.cloud` and `datasets.experiments.quantum.cloud` resolve to the IP addresses of their respective machines. Configure `web.nimbus.tech` for the web service in the `nimbus.tech` zone. Also provide DNS references for email at the four main domains `nimbus.tech`, `forge.tech`, `quantum.cloud`, and `matrix.cloud`.

- **Mail records:** Configure the following MX records:
  - `nimbus.tech` → MX priority 10, mail server `mx.nimbus.tech`, with an A record pointing to the existing IP address of [pc1].
  - `forge.tech` → MX priority 10, mail server `mx.forge.tech`, with an A record pointing to the existing IP address of [pc17].
  - `quantum.cloud` → MX priority 10, mail server `mx.quantum.cloud`, with an A record pointing to the existing IP address of [pc14].
  - `matrix.cloud` → MX priority 10, mail server `mx.matrix.cloud`, with an A record pointing to the existing IP address of [pc9].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. The 13 assigned authoritative machines must host their respective zones; [pc2] must act as the local name server, and [pc19], [pc5], [pc10], [pc4], and [pc15] must act as clients. Configure DNS on the assigned devices without changing network links, IP addresses, or existing routing.
