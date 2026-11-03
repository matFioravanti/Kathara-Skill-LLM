$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.example.com.
ns.example.com. IN A 10.15.2.12
shop.example.com. IN NS ns.shop.example.com.
ns.shop.example.com. IN A 10.15.4.14
blog.example.com. IN NS ns.blog.example.com.
ns.blog.example.com. IN A 10.15.5.11
www IN A 10.15.2.12
