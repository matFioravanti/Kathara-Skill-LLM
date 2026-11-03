$TTL 3600
@ IN SOA ns.blog.example.com. hostmaster.blog.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.blog.example.com.
ns.blog.example.com. IN A 10.15.5.11
blog.example.com. IN A 10.15.5.11
