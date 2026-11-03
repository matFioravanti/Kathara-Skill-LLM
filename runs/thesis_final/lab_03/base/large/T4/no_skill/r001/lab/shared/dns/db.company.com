$TTL 300
@ IN SOA ns.company.com. hostmaster.company.com. ( 2026110301 3600 600 604800 300 )
@ IN NS ns.company.com.
ns IN A 10.16.1.11
dept IN A 10.16.5.12
intranet IN A 10.16.5.13
mail IN A 10.16.2.13
mail.dept IN A 10.16.5.12
@ IN MX 10 mail.company.com.
dept IN MX 10 mail.dept.company.com.
