Generate the DNS configuration for the existing Kathara laboratory without changing the topology, IP addresses, or previously configured routes.

- **Hierarchy:** Configure a DNS hierarchy consisting of the root domain `.`, four TLDs (com, net, edu, and it), ten main domains, and their respective delegated subzones. The hierarchy must contain a total of **31 authoritative zones and 30 DNS delegations**, assigned to the existing machines as follows:
  - Root domain `.` → [pc1]
  - TLD com → [pc2]
  - TLD net → [pc3]
  - TLD edu → [pc4]
  - TLD it → [pc5]
  - Zone example.com → [pc6]
  - Zone company.com → [pc7]
  - Zone service.com → [pc8]
  - Zone lab.net → [pc9]
  - Zone tools.net → [pc10]
  - Zone university.edu → [pc11]
  - Zone campus.edu → [pc12]
  - Zone unibo.it → [pc13]
  - Zone comune.it → [pc14]
  - Zone regione.it → [pc15]
  - Zone shop.example.com → [pc16]
  - Zone blog.example.com → [pc17]
  - Zone dept.company.com → [pc18]
  - Zone intranet.company.com → [pc19]
  - Zone api.service.com → [pc20]
  - Zone research.lab.net → [pc21]
  - Zone ai.research.lab.net → [pc22]
  - Zone data.research.lab.net → [pc23]
  - Zone dev.lab.net → [pc24]
  - Zone ci.tools.net → [pc25]
  - Zone vpn.university.edu → [pc26]
  - Zone courses.university.edu → [pc27]
  - Zone portal.campus.edu → [pc28]
  - Zone studenti.unibo.it → [pc29]
  - Zone servizi.comune.it → [pc30]
  - Zone dati.regione.it → [pc31]

- **Delegations:** Configure the following authoritative delegations:
  - `.` delegates `com`, `net`, `edu` and `it`.
  - `com` delegates `example.com`, `company.com` and `service.com`.
  - `net` delegates `lab.net` and `tools.net`.
  - `edu` delegates `university.edu` and `campus.edu`.
  - `it` delegates `unibo.it`, `comune.it` and `regione.it`.
  - `example.com` delegates `shop.example.com` and `blog.example.com`.
  - `company.com` delegates `dept.company.com` and `intranet.company.com`.
  - `service.com` delegates `api.service.com`.
  - `lab.net` delegates `research.lab.net` and `dev.lab.net`.
  - `tools.net` delegates `ci.tools.net`.
  - `research.lab.net` delegates `ai.research.lab.net` and `data.research.lab.net`.
  - `university.edu` delegates `vpn.university.edu` and `courses.university.edu`.
  - `campus.edu` delegates `portal.campus.edu`.
  - `unibo.it` delegates `studenti.unibo.it`.
  - `comune.it` delegates `servizi.comune.it`.
  - `regione.it` delegates `dati.regione.it`.
  - Configure all required NS records and any necessary glue records to enable correct name resolution throughout the hierarchy.

- **Local resolution:** Configure a local name server on an existing machine not assigned to any authoritative zone. Client resolvers must send DNS queries to this server; it must be able to query the name servers of the hierarchy when necessary, starting at the root and following delegations until the target zone is reached. All existing clients must be able to use this resolution service.

- **Services:** Configure the necessary DNS records so that `shop.example.com`, `blog.example.com`, `dept.company.com`, `intranet.company.com`, `api.service.com`, `research.lab.net`, `ai.research.lab.net`, `data.research.lab.net`, `dev.lab.net`, `ci.tools.net`, `vpn.university.edu`, `courses.university.edu`, `portal.campus.edu`, `studenti.unibo.it`, `servizi.comune.it` and `dati.regione.it` resolve to the IP addresses of their respective machines. In the `example.com` zone, configure `www.example.com` for the web service. Provide DNS references for the email service of the specified business and academic domains, including `company.com` and `university.edu`.

- **Mail records:** Configure the following MX records:
  - `company.com` → MX priority 10, mail server `mail.company.com`, with an A record pointing to the existing IP address of [pc7].
  - `university.edu` → MX priority 10, mail server `mail.university.edu`, with an A record pointing to the existing IP address of [pc11].
  - Each MX record must refer to the full name of its mail server, and that name must resolve through its corresponding A record. Use only IP addresses already present in the laboratory; do not introduce dedicated mail machines.

- **Machine assignments:** Preserve the correspondence between each DNS zone and the machine listed in square brackets. Machines [pc1] through [pc31] must act as their assigned authoritative servers. Select the local name server and clients from the other existing machines. Do not add devices or alter network links, IP addresses, or existing routing.
