$TTL 300
@ IN SOA ns.example.com. hostmaster.example.com. ( 2026110301 3600 600 604800 300 )
@ IN NS ns.example.com.
ns IN A 10.15.6.11
shop IN A 10.15.4.14
blog IN A 10.15.5.11
