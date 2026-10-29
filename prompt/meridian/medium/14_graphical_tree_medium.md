```text
[ Root domain "." ] ──> [ Authoritative NS: pc25 ]
│
├── delegates "digital"
│   └──> [ Authoritative NS: pc14 ]
│        │
│        └── [ digital ]
│            │
│            ├── delegates "meridian.digital"
│            │   └──> [ Authoritative NS: pc2 ]
│            │        │
│            │        └── [ meridian.digital ]
│            │            │
│            │            ├── delegates "market.meridian.digital"
│            │            │   └──> [ Authoritative NS: pc13 ]
│            │            │        │
│            │            │        └── [ market.meridian.digital ]
│            │            │            └── A → IP of pc13
│            │            │
│            │            ├── delegates "journal.meridian.digital"
│            │            │   └──> [ Authoritative NS: pc26 ]
│            │            │        │
│            │            │        └── [ journal.meridian.digital ]
│            │            │            └── A → IP of pc26
│            │            │
│            │            └── site.meridian.digital
│            │                └──> [ Web service: A record ]
│            │
│            ├── delegates "vantage.digital"
│            │   └──> [ Authoritative NS: pc22 ]
│            │        │
│            │        └── [ vantage.digital ]
│            │            │
│            │            ├── delegates "teams.vantage.digital"
│            │            │   └──> [ Authoritative NS: pc23 ]
│            │            │        │
│            │            │        └── [ teams.vantage.digital ]
│            │            │            └── A → IP of pc23
│            │            │
│            │            ├── delegates "office.vantage.digital"
│            │            │   └──> [ Authoritative NS: pc16 ]
│            │            │        │
│            │            │        └── [ office.vantage.digital ]
│            │            │            └── A → IP of pc16
│            │            │
│            │            ├── MX vantage.digital
│            │            │   └──> [ 10 mailhub.vantage.digital ]
│            │            │
│            │            └── mailhub.vantage.digital
│            │                └──> [ A record → IP of pc22 ]
│            │
│            └── delegates "vertex.digital"
│                └──> [ Authoritative NS: pc11 ]
│                     │
│                     └── [ vertex.digital ]
│                         │
│                         └── delegates "interface.vertex.digital"
│                             └──> [ Authoritative NS: pc10 ]
│                                  │
│                                  └── [ interface.vertex.digital ]
│                                      └── A → IP of pc10
│
├── delegates "network"
│   └──> [ Authoritative NS: pc20 ]
│        │
│        └── [ network ]
│            │
│            ├── delegates "cipher.network"
│            │   └──> [ Authoritative NS: pc17 ]
│            │        │
│            │        └── [ cipher.network ]
│            │            │
│            │            ├── delegates "testing.cipher.network"
│            │            │   └──> [ Authoritative NS: pc30 ]
│            │            │        │
│            │            │        └── [ testing.cipher.network ]
│            │            │            │
│            │            │            ├── delegates "neural.testing.cipher.network"
│            │            │            │   └──> [ Authoritative NS: pc9 ]
│            │            │            │        │
│            │            │            │        └── [ neural.testing.cipher.network ]
│            │            │            │            └── A → IP of pc9
│            │            │            │
│            │            │            └── delegates "records.testing.cipher.network"
│            │            │                └──> [ Authoritative NS: pc12 ]
│            │            │                     │
│            │            │                     └── [ records.testing.cipher.network ]
│            │            │                         └── A → IP of pc12
│            │            │
│            │            └── delegates "staging.cipher.network"
│            │                └──> [ Authoritative NS: pc28 ]
│            │                     │
│            │                     └── [ staging.cipher.network ]
│            │                         └── A → IP of pc28
│            │
│            └── delegates "gateway.network"
│                └──> [ Authoritative NS: pc4 ]
│                     │
│                     └── [ gateway.network ]
│                         │
│                         └── delegates "pipeline.gateway.network"
│                             └──> [ Authoritative NS: pc7 ]
│                                  │
│                                  └── [ pipeline.gateway.network ]
│                                      └── A → IP of pc7
│
├── delegates "science"
│   └──> [ Authoritative NS: pc6 ]
│        │
│        └── [ science ]
│            │
│            ├── delegates "oakridge.science"
│            │   └──> [ Authoritative NS: pc24 ]
│            │        │
│            │        └── [ oakridge.science ]
│            │            │
│            │            ├── delegates "tunnel.oakridge.science"
│            │            │   └──> [ Authoritative NS: pc3 ]
│            │            │        │
│            │            │        └── [ tunnel.oakridge.science ]
│            │            │            └── A → IP of pc3
│            │            │
│            │            ├── delegates "classes.oakridge.science"
│            │            │   └──> [ Authoritative NS: pc1 ]
│            │            │        │
│            │            │        └── [ classes.oakridge.science ]
│            │            │            └── A → IP of pc1
│            │            │
│            │            ├── MX oakridge.science
│            │            │   └──> [ 10 mailhub.oakridge.science ]
│            │            │
│            │            └── mailhub.oakridge.science
│            │                └──> [ A record → IP of pc24 ]
│            │
│            └── delegates "lighthouse.science"
│                └──> [ Authoritative NS: pc5 ]
│                     │
│                     └── [ lighthouse.science ]
│                         │
│                         └── delegates "dashboard.lighthouse.science"
│                             └──> [ Authoritative NS: pc29 ]
│                                  │
│                                  └── [ dashboard.lighthouse.science ]
│                                      └── A → IP of pc29
│
└── delegates "region"
    └──> [ Authoritative NS: pc15 ]
         │
         └── [ region ]
             │
             ├── delegates "solstice.region"
             │   └──> [ Authoritative NS: pc21 ]
             │        │
             │        └── [ solstice.region ]
             │            │
             │            └── delegates "learners.solstice.region"
             │                └──> [ Authoritative NS: pc8 ]
             │                     │
             │                     └── [ learners.solstice.region ]
             │                         └── A → IP of pc8
             │
             ├── delegates "meadow.region"
             │   └──> [ Authoritative NS: pc18 ]
             │        │
             │        └── [ meadow.region ]
             │            │
             │            └── delegates "forms.meadow.region"
             │                └──> [ Authoritative NS: pc31 ]
             │                     │
             │                     └── [ forms.meadow.region ]
             │                         └── A → IP of pc31
             │
             └── delegates "valley.region"
                 └──> [ Authoritative NS: pc19 ]
                      │
                      └── [ valley.region ]
                          │
                          └── delegates "metrics.valley.region"
                              └──> [ Authoritative NS: pc27 ]
                                   │
                                   └── [ metrics.valley.region ]
                                       └── A → IP of pc27

[ Laboratory clients ]
             │
             └── [ Client resolvers ]
                         │
                         └── DNS query
                                   │
                                   ▼
                    [ Local name server ]
                    [ Existing non-authoritative host ]
                                   │
                         Recursive resolution
                                   │
                                   └── Root hints: pc25
                                           │
                                           ▼
                        [ Root authoritative NS ]
                                   │
                                   └── Follows the delegations
                                       of the DNS tree
```
