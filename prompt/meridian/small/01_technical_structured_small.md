Generate the DNS configuration for the existing Kathara laboratory, consisting of 4 routers, 20 PCs/hosts, and 6 access LANs, while preserving the topology, IP addresses, and already configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, two TLDs (digital and network), four main domains (meridian.digital, vertex.digital, cipher.network, and gateway.network), and their respective delegated subzones. The hierarchy must contain a total of **13 authoritative zones and 12 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc17]
  - TLD digital → [pc7]
  - TLD network → [pc5]
  - Zone meridian.digital → [pc14]
  - Zone vertex.digital → [pc16]
  - Zone cipher.network → [pc4]
  - Zone gateway.network → [pc9]
  - Zone market.meridian.digital → [pc10]
  - Zone interface.vertex.digital → [pc2]
  - Zone testing.cipher.network → [pc20]
  - Zone pipeline.gateway.network → [pc15]
  - Zone neural.testing.cipher.network → [pc18]
  - Zone records.testing.cipher.network → [pc3]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `digital` and `network`.
  - `digital` delegates `meridian.digital` and `vertex.digital`.
  - `network` delegates `cipher.network` and `gateway.network`.
  - `meridian.digital` delegates `market.meridian.digital`.
  - `vertex.digital` delegates `interface.vertex.digital`.
  - `cipher.network` delegates `testing.cipher.network`.
  - `gateway.network` delegates `pipeline.gateway.network`.
  - `testing.cipher.network` delegates `neural.testing.cipher.network` and `records.testing.cipher.network`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on [pc8] to receive DNS queries from the five clients [pc12], [pc19], [pc11], [pc1], and [pc6], and to query the other name servers in the hierarchy when needed.

- **Services:** Configure DNS records so that `market.meridian.digital`, `interface.vertex.digital`, `pipeline.gateway.network`, `neural.testing.cipher.network` and `records.testing.cipher.network` resolve to the IP addresses of their respective machines. Configure `site.meridian.digital` for the web service in the `meridian.digital` zone. Also provide DNS references for email at the four main domains `meridian.digital`, `vertex.digital`, `cipher.network`, and `gateway.network`.

- **Mail records:** Configure the following MX records:
  - `meridian.digital` → MX priority 10, mail server `mailhub.meridian.digital`, with an A record pointing to the existing IP address of [pc14].
  - `vertex.digital` → MX priority 10, mail server `mailhub.vertex.digital`, with an A record pointing to the existing IP address of [pc16].
  - `cipher.network` → MX priority 10, mail server `mailhub.cipher.network`, with an A record pointing to the existing IP address of [pc4].
  - `gateway.network` → MX priority 10, mail server `mailhub.gateway.network`, with an A record pointing to the existing IP address of [pc9].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. The 13 assigned authoritative machines must host their respective zones; [pc8] must act as the local name server, and [pc12], [pc19], [pc11], [pc1], and [pc6] must act as clients. Configure DNS on the assigned devices without changing network links, IP addresses, or existing routing.
