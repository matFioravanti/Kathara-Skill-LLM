```text
[ Root domain "." ] ──> [ Authoritative NS: pc1 ]
│
├── delegates "com"
│   └──> [ Authoritative NS: pc2 ]
│        │
│        └── [ com ]
│            │
│            ├── delegates "example.com"
│            │   └──> [ Authoritative NS: pc4 ]
│            │        │
│            │        └── [ example.com ]
│            │            │
│            │            ├── delegates "shop.example.com"
│            │            │   └──> [ Authoritative NS: pc8 ]
│            │            │        │
│            │            │        └── [ shop.example.com ]
│            │            │            └── A → IP of pc8
│            │            │
│            │            ├── www.example.com
│            │            │   └──> [ Web service: A record ]
│            │            │
│            │            ├── MX example.com
│            │            │   └──> [ 10 mail.example.com ]
│            │            │
│            │            └── mail.example.com
│            │                └──> [ A record → IP of pc4 ]
│            │
│            └── delegates "service.com"
│                └──> [ Authoritative NS: pc5 ]
│                     │
│                     └── [ service.com ]
│                         │
│                         ├── delegates "api.service.com"
│                         │   └──> [ Authoritative NS: pc9 ]
│                         │        │
│                         │        └── [ api.service.com ]
│                         │            └── A → IP of pc9
│                         │
│                         ├── MX service.com
│                         │   └──> [ 10 mail.service.com ]
│                         │
│                         └── mail.service.com
│                             └──> [ A record → IP of pc5 ]
│
└── delegates "net"
    └──> [ Authoritative NS: pc3 ]
         │
         └── [ net ]
             │
             ├── delegates "lab.net"
             │   └──> [ Authoritative NS: pc6 ]
             │        │
             │        └── [ lab.net ]
             │            │
             │            ├── delegates "research.lab.net"
             │            │   └──> [ Authoritative NS: pc10 ]
             │            │        │
             │            │        └── [ research.lab.net ]
             │            │            │
             │            │            ├── delegates "ai.research.lab.net"
             │            │            │   └──> [ Authoritative NS: pc12 ]
             │            │            │        │
             │            │            │        └── [ ai.research.lab.net ]
             │            │            │            └── A → IP of pc12
             │            │            │
             │            │            └── delegates "data.research.lab.net"
             │            │                └──> [ Authoritative NS: pc13 ]
             │            │                     │
             │            │                     └── [ data.research.lab.net ]
             │            │                         └── A → IP of pc13
             │            │
             │            ├── MX lab.net
             │            │   └──> [ 10 mail.lab.net ]
             │            │
             │            └── mail.lab.net
             │                └──> [ A record → IP of pc6 ]
             │
             └── delegates "tools.net"
                 └──> [ Authoritative NS: pc7 ]
                      │
                      └── [ tools.net ]
                          │
                          ├── delegates "ci.tools.net"
                          │   └──> [ Authoritative NS: pc11 ]
                          │        │
                          │        └── [ ci.tools.net ]
                          │            └── A → IP of pc11
                          │
                          ├── MX tools.net
                          │   └──> [ 10 mail.tools.net ]
                          │
                          └── mail.tools.net
                              └──> [ A record → IP of pc7 ]

[ Client: pc16, pc17, pc18, pc19, pc20 ]
               │
               └── [ Client resolvers ]
                           │
                           └── DNS query
                                     │
                                     ▼
                        [ Local NS: pc14 ]
                                     │
                           Recursive resolution
                                     │
                                     └── Root hints: pc1
                                             │
                                             ▼
                          [ Root authoritative NS ]
                                     │
                                     └── Follows the delegations
                                         of the DNS tree
```
