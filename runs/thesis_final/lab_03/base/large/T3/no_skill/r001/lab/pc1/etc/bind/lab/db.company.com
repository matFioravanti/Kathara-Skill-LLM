$TTL 3600
@ IN SOA ns.company.com. hostmaster.company.com. ( 2026110301 3600 900 604800 3600 )
@ IN NS ns.company.com.
ns IN A 10.16.1.11
dept.company.com. IN A 10.16.5.12
intranet.company.com. IN A 10.16.5.13
mail.company.com. IN A 10.16.2.13
mail.dept.company.com. IN A 10.16.5.12
company.com. IN MX 10 mail.company.com.
dept.company.com. IN MX 10 mail.dept.company.com.
