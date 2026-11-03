$TTL 3600
$ORIGIN company.com.
@ IN SOA ns.company.com. hostmaster.company.com. ( 1 3600 900 604800 300 )
@ IN NS ns.company.com.
ns.company.com. IN A 10.15.2.14
dept IN A 10.15.5.12
intranet IN A 10.15.5.13
mail IN A 10.15.2.13
@ IN MX 10 mail.company.com.
