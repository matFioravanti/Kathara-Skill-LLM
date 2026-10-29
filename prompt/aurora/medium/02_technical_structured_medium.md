Generate the DNS configuration for the existing Kathara laboratory without changing the topology, IP addresses, or previously configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, four TLDs (tech, cloud, academy, and city), ten main domains, and their respective delegated subzones. The hierarchy must contain a total of **31 authoritative zones and 30 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc3]
  - TLD tech → [pc31]
  - TLD cloud → [pc17]
  - TLD academy → [pc24]
  - TLD city → [pc12]
  - Zone nimbus.tech → [pc10]
  - Zone orbit.tech → [pc6]
  - Zone forge.tech → [pc26]
  - Zone quantum.cloud → [pc5]
  - Zone matrix.cloud → [pc2]
  - Zone summit.academy → [pc29]
  - Zone cedar.academy → [pc13]
  - Zone polaris.city → [pc4]
  - Zone riverton.city → [pc22]
  - Zone highland.city → [pc30]
  - Zone store.nimbus.tech → [pc25]
  - Zone insights.nimbus.tech → [pc23]
  - Zone division.orbit.tech → [pc7]
  - Zone internal.orbit.tech → [pc1]
  - Zone gateway.forge.tech → [pc28]
  - Zone experiments.quantum.cloud → [pc15]
  - Zone models.experiments.quantum.cloud → [pc20]
  - Zone datasets.experiments.quantum.cloud → [pc18]
  - Zone sandbox.quantum.cloud → [pc14]
  - Zone build.matrix.cloud → [pc8]
  - Zone secure.summit.academy → [pc11]
  - Zone lessons.summit.academy → [pc9]
  - Zone entry.cedar.academy → [pc21]
  - Zone students.polaris.city → [pc19]
  - Zone requests.riverton.city → [pc16]
  - Zone statistics.highland.city → [pc27]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `tech`, `cloud`, `academy` and `city`.
  - `tech` delegates `nimbus.tech`, `orbit.tech` and `forge.tech`.
  - `cloud` delegates `quantum.cloud` and `matrix.cloud`.
  - `academy` delegates `summit.academy` and `cedar.academy`.
  - `city` delegates `polaris.city`, `riverton.city` and `highland.city`.
  - `nimbus.tech` delegates `store.nimbus.tech` and `insights.nimbus.tech`.
  - `orbit.tech` delegates `division.orbit.tech` and `internal.orbit.tech`.
  - `forge.tech` delegates `gateway.forge.tech`.
  - `quantum.cloud` delegates `experiments.quantum.cloud` and `sandbox.quantum.cloud`.
  - `matrix.cloud` delegates `build.matrix.cloud`.
  - `experiments.quantum.cloud` delegates `models.experiments.quantum.cloud` and `datasets.experiments.quantum.cloud`.
  - `summit.academy` delegates `secure.summit.academy` and `lessons.summit.academy`.
  - `cedar.academy` delegates `entry.cedar.academy`.
  - `polaris.city` delegates `students.polaris.city`.
  - `riverton.city` delegates `requests.riverton.city`.
  - `highland.city` delegates `statistics.highland.city`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on an existing machine not assigned to any authoritative zone. Client resolvers must send DNS queries to this server; it must be able to query the name servers of the hierarchy when necessary, starting at the root and following delegations until the target zone is reached. All existing clients must be able to use this resolution service.

- **Services:** Configure the necessary DNS records so that `store.nimbus.tech`, `insights.nimbus.tech`, `division.orbit.tech`, `internal.orbit.tech`, `gateway.forge.tech`, `experiments.quantum.cloud`, `models.experiments.quantum.cloud`, `datasets.experiments.quantum.cloud`, `sandbox.quantum.cloud`, `build.matrix.cloud`, `secure.summit.academy`, `lessons.summit.academy`, `entry.cedar.academy`, `students.polaris.city`, `requests.riverton.city` and `statistics.highland.city` resolve to the IP addresses of their respective machines. In the `nimbus.tech` zone, configure `web.nimbus.tech` for the web service. Provide DNS references for the email service of the specified business and academic domains, including `orbit.tech` and `summit.academy`.

- **Mail records:** Configure the following MX records:
  - `orbit.tech` → MX priority 10, mail server `mx.orbit.tech`, with an A record pointing to the existing IP address of [pc6].
  - `summit.academy` → MX priority 10, mail server `mx.summit.academy`, with an A record pointing to the existing IP address of [pc29].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. All 31 machines assigned to authoritative zones above must act as the authoritative servers for their respective zones. Select the local name server and clients from the other existing machines. Do not add devices or alter network links, IP addresses, or existing routing.
