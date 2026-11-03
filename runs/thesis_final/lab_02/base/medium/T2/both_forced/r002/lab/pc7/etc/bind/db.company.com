$TTL 3600
@ IN SOA ns.company.com. hostmaster.company.com. ( 1 3600 900 604800 300 )
@ IN NS ns.company.com.
ns.company.com. IN A 10.15.2.13
@ IN A 10.15.2.13
@ IN MX 10 mail.company.com.
mail IN A 10.15.2.13
dept IN NS ns.dept.company.com.
ns.dept.company.com. IN A 10.15.5.12
intranet IN NS ns.intranet.company.com.
ns.intranet.company.com. IN A 10.15.5.13
