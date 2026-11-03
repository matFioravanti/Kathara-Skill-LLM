$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.example.com.
ns.example.com. IN A 10.16.4.11
shop.example.com. IN A 10.16.4.14
blog.example.com. IN A 10.16.5.11
