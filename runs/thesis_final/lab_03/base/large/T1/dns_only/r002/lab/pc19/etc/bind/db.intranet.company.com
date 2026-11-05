$TTL 3600
@ IN SOA ns.intranet.company.com. hostmaster.intranet.company.com. ( 1 3600 900 604800 300 )
@ IN NS ns.intranet.company.com.
@ IN A 10.16.5.13
ns.intranet.company.com. IN A 10.16.5.13
