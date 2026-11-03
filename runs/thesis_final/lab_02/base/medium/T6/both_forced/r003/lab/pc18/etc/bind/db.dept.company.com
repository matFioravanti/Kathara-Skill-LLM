$TTL 3600
@ IN SOA ns.dept.company.com. hostmaster.dept.company.com. ( 1 3600 900 604800 300 )
@ IN NS ns.dept.company.com.
ns.dept.company.com. IN A 10.15.5.12
dept.company.com. IN A 10.15.5.12
