The lab DNS server runs on pc21 (10.15.6.11) using BIND. Its configuration
and authoritative zone files are in pc21/etc/lab-dns. Every PC and router
uses this server through /etc/resolv.conf; existing addressing and routes are
unchanged. The Kathara image must provide the `named` executable.

The server is authoritative for the domains represented in those files, so
other records within those domains must be added there. Other domains use
recursive DNS, subject to the lab having connectivity to external DNS servers.
The MX records advertise mail.company.com and mail.university.edu; they do
not install or configure mail services on pc7 or pc11.

After starting the lab, check from machines on different LANs, for example:

    dig @10.15.6.11 ai.research.lab.net A
    dig @10.15.6.11 company.com MX
    dig @10.15.6.11 university.edu MX
    getent hosts servizi.comune.it
