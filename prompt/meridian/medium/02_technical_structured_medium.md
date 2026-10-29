Generate the DNS configuration for the existing Kathara laboratory without changing the topology, IP addresses, or previously configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, four TLDs (digital, network, science, and region), ten main domains, and their respective delegated subzones. The hierarchy must contain a total of **31 authoritative zones and 30 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc25]
  - TLD digital → [pc14]
  - TLD network → [pc20]
  - TLD science → [pc6]
  - TLD region → [pc15]
  - Zone meridian.digital → [pc2]
  - Zone vantage.digital → [pc22]
  - Zone vertex.digital → [pc11]
  - Zone cipher.network → [pc17]
  - Zone gateway.network → [pc4]
  - Zone oakridge.science → [pc24]
  - Zone lighthouse.science → [pc5]
  - Zone solstice.region → [pc21]
  - Zone meadow.region → [pc18]
  - Zone valley.region → [pc19]
  - Zone market.meridian.digital → [pc13]
  - Zone journal.meridian.digital → [pc26]
  - Zone teams.vantage.digital → [pc23]
  - Zone office.vantage.digital → [pc16]
  - Zone interface.vertex.digital → [pc10]
  - Zone testing.cipher.network → [pc30]
  - Zone neural.testing.cipher.network → [pc9]
  - Zone records.testing.cipher.network → [pc12]
  - Zone staging.cipher.network → [pc28]
  - Zone pipeline.gateway.network → [pc7]
  - Zone tunnel.oakridge.science → [pc3]
  - Zone classes.oakridge.science → [pc1]
  - Zone dashboard.lighthouse.science → [pc29]
  - Zone learners.solstice.region → [pc8]
  - Zone forms.meadow.region → [pc31]
  - Zone metrics.valley.region → [pc27]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `digital`, `network`, `science` and `region`.
  - `digital` delegates `meridian.digital`, `vantage.digital` and `vertex.digital`.
  - `network` delegates `cipher.network` and `gateway.network`.
  - `science` delegates `oakridge.science` and `lighthouse.science`.
  - `region` delegates `solstice.region`, `meadow.region` and `valley.region`.
  - `meridian.digital` delegates `market.meridian.digital` and `journal.meridian.digital`.
  - `vantage.digital` delegates `teams.vantage.digital` and `office.vantage.digital`.
  - `vertex.digital` delegates `interface.vertex.digital`.
  - `cipher.network` delegates `testing.cipher.network` and `staging.cipher.network`.
  - `gateway.network` delegates `pipeline.gateway.network`.
  - `testing.cipher.network` delegates `neural.testing.cipher.network` and `records.testing.cipher.network`.
  - `oakridge.science` delegates `tunnel.oakridge.science` and `classes.oakridge.science`.
  - `lighthouse.science` delegates `dashboard.lighthouse.science`.
  - `solstice.region` delegates `learners.solstice.region`.
  - `meadow.region` delegates `forms.meadow.region`.
  - `valley.region` delegates `metrics.valley.region`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on an existing machine not assigned to any authoritative zone. Client resolvers must send DNS queries to this server; it must be able to query the name servers of the hierarchy when necessary, starting at the root and following delegations until the target zone is reached. All existing clients must be able to use this resolution service.

- **Services:** Configure the necessary DNS records so that `market.meridian.digital`, `journal.meridian.digital`, `teams.vantage.digital`, `office.vantage.digital`, `interface.vertex.digital`, `testing.cipher.network`, `neural.testing.cipher.network`, `records.testing.cipher.network`, `staging.cipher.network`, `pipeline.gateway.network`, `tunnel.oakridge.science`, `classes.oakridge.science`, `dashboard.lighthouse.science`, `learners.solstice.region`, `forms.meadow.region` and `metrics.valley.region` resolve to the IP addresses of their respective machines. In the `meridian.digital` zone, configure `site.meridian.digital` for the web service. Provide DNS references for the email service of the specified business and academic domains, including `vantage.digital` and `oakridge.science`.

- **Mail records:** Configure the following MX records:
  - `vantage.digital` → MX priority 10, mail server `mailhub.vantage.digital`, with an A record pointing to the existing IP address of [pc22].
  - `oakridge.science` → MX priority 10, mail server `mailhub.oakridge.science`, with an A record pointing to the existing IP address of [pc24].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. All 31 machines assigned to authoritative zones above must act as the authoritative servers for their respective zones. Select the local name server and clients from the other existing machines. Do not add devices or alter network links, IP addresses, or existing routing.
