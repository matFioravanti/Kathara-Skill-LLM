$TTL 300
@ IN SOA ns.company.com. hostmaster.company.com. ( 1 3600 600 604800 300 )
@ IN NS ns.company.com.
ns IN A 10.15.1.11
@ IN MX 10 mail.company.com.
dept IN A 10.15.5.12
intranet IN A 10.15.5.13
mail IN A 10.15.2.13
