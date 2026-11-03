$TTL 300
@ IN SOA ns.company.com. hostmaster.company.com. ( 2026110301 3600 600 604800 300 )
@ IN NS ns.company.com.
ns IN A 10.15.6.11
dept IN A 10.15.5.12
intranet IN A 10.15.5.13
mail IN A 10.15.2.13
@ IN MX 10 mail.company.com.
