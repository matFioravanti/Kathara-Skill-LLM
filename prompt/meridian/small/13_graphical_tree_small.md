```text
[ Root domain "." ] ──> [ Authoritative NS: pc17 ]
│
├── delegates "digital"
│   └──> [ Authoritative NS: pc7 ]
│        │
│        └── [ digital ]
│            │
│            ├── delegates "meridian.digital"
│            │   └──> [ Authoritative NS: pc14 ]
│            │        │
│            │        └── [ meridian.digital ]
│            │            │
│            │            ├── delegates "market.meridian.digital"
│            │            │   └──> [ Authoritative NS: pc10 ]
│            │            │        │
│            │            │        └── [ market.meridian.digital ]
│            │            │            └── A → IP of pc10
│            │            │
│            │            ├── site.meridian.digital
│            │            │   └──> [ Web service: A record ]
│            │            │
│            │            ├── MX meridian.digital
│            │            │   └──> [ 10 mailhub.meridian.digital ]
│            │            │
│            │            └── mailhub.meridian.digital
│            │                └──> [ A record → IP of pc14 ]
│            │
│            └── delegates "vertex.digital"
│                └──> [ Authoritative NS: pc16 ]
│                     │
│                     └── [ vertex.digital ]
│                         │
│                         ├── delegates "interface.vertex.digital"
│                         │   └──> [ Authoritative NS: pc2 ]
│                         │        │
│                         │        └── [ interface.vertex.digital ]
│                         │            └── A → IP of pc2
│                         │
│                         ├── MX vertex.digital
│                         │   └──> [ 10 mailhub.vertex.digital ]
│                         │
│                         └── mailhub.vertex.digital
│                             └──> [ A record → IP of pc16 ]
│
└── delegates "network"
    └──> [ Authoritative NS: pc5 ]
         │
         └── [ network ]
             │
             ├── delegates "cipher.network"
             │   └──> [ Authoritative NS: pc4 ]
             │        │
             │        └── [ cipher.network ]
             │            │
             │            ├── delegates "testing.cipher.network"
             │            │   └──> [ Authoritative NS: pc20 ]
             │            │        │
             │            │        └── [ testing.cipher.network ]
             │            │            │
             │            │            ├── delegates "neural.testing.cipher.network"
             │            │            │   └──> [ Authoritative NS: pc18 ]
             │            │            │        │
             │            │            │        └── [ neural.testing.cipher.network ]
             │            │            │            └── A → IP of pc18
             │            │            │
             │            │            └── delegates "records.testing.cipher.network"
             │            │                └──> [ Authoritative NS: pc3 ]
             │            │                     │
             │            │                     └── [ records.testing.cipher.network ]
             │            │                         └── A → IP of pc3
             │            │
             │            ├── MX cipher.network
             │            │   └──> [ 10 mailhub.cipher.network ]
             │            │
             │            └── mailhub.cipher.network
             │                └──> [ A record → IP of pc4 ]
             │
             └── delegates "gateway.network"
                 └──> [ Authoritative NS: pc9 ]
                      │
                      └── [ gateway.network ]
                          │
                          ├── delegates "pipeline.gateway.network"
                          │   └──> [ Authoritative NS: pc15 ]
                          │        │
                          │        └── [ pipeline.gateway.network ]
                          │            └── A → IP of pc15
                          │
                          ├── MX gateway.network
                          │   └──> [ 10 mailhub.gateway.network ]
                          │
                          └── mailhub.gateway.network
                              └──> [ A record → IP of pc9 ]

[ Client: pc12, pc19, pc11, pc1, pc6 ]
               │
               └── [ Client resolvers ]
                           │
                           └── DNS query
                                     │
                                     ▼
                        [ Local NS: pc8 ]
                                     │
                           Recursive resolution
                                     │
                                     └── Root hints: pc17
                                             │
                                             ▼
                          [ Root authoritative NS ]
                                     │
                                     └── Follows the delegations
                                         of the DNS tree
```
