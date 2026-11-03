$TTL 3600
@ IN SOA ns.blog.example.com. hostmaster.blog.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.blog.example.com.
@ IN A 10.16.5.11
ns IN A 10.16.5.11
