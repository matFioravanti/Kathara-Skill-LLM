$TTL 300
@ IN SOA ns.example.com. hostmaster.example.com. ( 2026110301 3600 600 604800 300 )
@ IN NS ns.example.com.
ns IN A 10.16.1.11
shop IN A 10.16.4.14
blog IN A 10.16.5.11
