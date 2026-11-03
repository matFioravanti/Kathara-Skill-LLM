$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.example.com.
ns.example.com. IN A 10.16.2.12
@ IN A 10.16.2.12
shop.example.com. IN NS ns.shop.example.com.
ns.shop.example.com. IN A 10.16.4.14
blog.example.com. IN NS ns.blog.example.com.
ns.blog.example.com. IN A 10.16.5.11
