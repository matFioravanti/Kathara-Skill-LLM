$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 2026110301 3600 900 604800 3600 )
@ IN NS ns.example.com.
ns IN A 10.16.1.11
blog.example.com. IN A 10.16.5.11
shop.example.com. IN A 10.16.4.14
