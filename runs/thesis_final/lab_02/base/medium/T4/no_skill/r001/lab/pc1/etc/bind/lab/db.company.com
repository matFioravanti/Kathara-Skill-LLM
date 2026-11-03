$TTL 3600
@ IN SOA ns.lab.net. hostmaster.lab.net. (
    2026110201 3600 900 604800 3600 )
  IN NS ns.lab.net.
  IN MX 10 mail.company.com.
dept IN A 10.15.5.12
intranet IN A 10.15.5.13
mail IN A 10.15.2.13
