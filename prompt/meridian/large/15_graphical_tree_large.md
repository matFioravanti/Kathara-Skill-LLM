```text
[ Root domain "." ] ──> [ Authoritative NS: pc38 ]
│
├── delegates "digital"
│   └──> [ Authoritative NS: pc17 ]
│        │
│        └── [ digital ]
│            │
│            ├── delegates "meridian.digital"
│            │   └──> [ Authoritative NS: pc10 ]
│            │        │
│            │        └── [ meridian.digital ]
│            │            │
│            │            ├── delegates "market.meridian.digital"
│            │            │   └──> [ Authoritative NS: pc22 ]
│            │            │        │
│            │            │        └── [ market.meridian.digital ]
│            │            │            └── A → IP of pc22
│            │            │
│            │            └── delegates "journal.meridian.digital"
│            │                └──> [ Authoritative NS: pc23 ]
│            │                     │
│            │                     └── [ journal.meridian.digital ]
│            │                         └── A → IP of pc23
│            │
│            ├── delegates "vantage.digital"
│            │   └──> [ Authoritative NS: pc48 ]
│            │        │
│            │        └── [ vantage.digital ]
│            │            │
│            │            ├── delegates "teams.vantage.digital"
│            │            │   └──> [ Authoritative NS: pc29 ]
│            │            │        │
│            │            │        └── [ teams.vantage.digital ]
│            │            │            │
│            │            │            ├── A → IP of pc29
│            │            │            │
│            │            │            ├── MX teams.vantage.digital
│            │            │            │   └──> [ 10 mailhub.teams.vantage.digital ]
│            │            │            │
│            │            │            └── mailhub.teams.vantage.digital
│            │            │                └──> [ A record → IP of pc29 ]
│            │            │
│            │            ├── delegates "office.vantage.digital"
│            │            │   └──> [ Authoritative NS: pc43 ]
│            │            │        │
│            │            │        └── [ office.vantage.digital ]
│            │            │            └── A → IP of pc43
│            │            │
│            │            ├── MX vantage.digital
│            │            │   └──> [ 10 mailhub.vantage.digital ]
│            │            │
│            │            └── mailhub.vantage.digital
│            │                └──> [ A record → IP of pc48 ]
│            │
│            └── delegates "vertex.digital"
│                └──> [ Authoritative NS: pc5 ]
│                     │
│                     └── [ vertex.digital ]
│                         │
│                         └── delegates "interface.vertex.digital"
│                             └──> [ Authoritative NS: pc6 ]
│                                  │
│                                  └── [ interface.vertex.digital ]
│                                      └── A → IP of pc6
│
├── delegates "network"
│   └──> [ Authoritative NS: pc35 ]
│        │
│        └── [ network ]
│            │
│            ├── delegates "cipher.network"
│            │   └──> [ Authoritative NS: pc40 ]
│            │        │
│            │        └── [ cipher.network ]
│            │            │
│            │            ├── delegates "testing.cipher.network"
│            │            │   └──> [ Authoritative NS: pc24 ]
│            │            │        │
│            │            │        └── [ testing.cipher.network ]
│            │            │            │
│            │            │            ├── delegates "neural.testing.cipher.network"
│            │            │            │   └──> [ Authoritative NS: pc47 ]
│            │            │            │        │
│            │            │            │        └── [ neural.testing.cipher.network ]
│            │            │            │            └── A → IP of pc47
│            │            │            │
│            │            │            └── delegates "records.testing.cipher.network"
│            │            │                └──> [ Authoritative NS: pc27 ]
│            │            │                     │
│            │            │                     └── [ records.testing.cipher.network ]
│            │            │                         └── A → IP of pc27
│            │            │
│            │            └── delegates "staging.cipher.network"
│            │                └──> [ Authoritative NS: pc4 ]
│            │                     │
│            │                     └── [ staging.cipher.network ]
│            │                         └── A → IP of pc4
│            │
│            └── delegates "gateway.network"
│                └──> [ Authoritative NS: pc33 ]
│                     │
│                     └── [ gateway.network ]
│                         │
│                         └── delegates "pipeline.gateway.network"
│                             └──> [ Authoritative NS: pc3 ]
│                                  │
│                                  └── [ pipeline.gateway.network ]
│                                      └── A → IP of pc3
│
├── delegates "science"
│   └──> [ Authoritative NS: pc1 ]
│        │
│        └── [ science ]
│            │
│            ├── delegates "oakridge.science"
│            │   └──> [ Authoritative NS: pc37 ]
│            │        │
│            │        └── [ oakridge.science ]
│            │            │
│            │            ├── delegates "tunnel.oakridge.science"
│            │            │   └──> [ Authoritative NS: pc44 ]
│            │            │        │
│            │            │        └── [ tunnel.oakridge.science ]
│            │            │            └── A → IP of pc44
│            │            │
│            │            ├── delegates "classes.oakridge.science"
│            │            │   └──> [ Authoritative NS: pc11 ]
│            │            │        │
│            │            │        └── [ classes.oakridge.science ]
│            │            │            └── A → IP of pc11
│            │            │
│            │            ├── MX oakridge.science
│            │            │   └──> [ 10 mailhub.oakridge.science ]
│            │            │
│            │            └── mailhub.oakridge.science
│            │                └──> [ A record → IP of pc37 ]
│            │
│            └── delegates "lighthouse.science"
│                └──> [ Authoritative NS: pc7 ]
│                     │
│                     └── [ lighthouse.science ]
│                         │
│                         └── delegates "dashboard.lighthouse.science"
│                             └──> [ Authoritative NS: pc46 ]
│                                  │
│                                  └── [ dashboard.lighthouse.science ]
│                                      └── A → IP of pc46
│
├── delegates "region"
│   └──> [ Authoritative NS: pc2 ]
│        │
│        └── [ region ]
│            │
│            ├── delegates "solstice.region"
│            │   └──> [ Authoritative NS: pc28 ]
│            │        │
│            │        └── [ solstice.region ]
│            │            │
│            │            └── delegates "learners.solstice.region"
│            │                └──> [ Authoritative NS: pc45 ]
│            │                     │
│            │                     └── [ learners.solstice.region ]
│            │                         └── A → IP of pc45
│            │
│            ├── delegates "meadow.region"
│            │   └──> [ Authoritative NS: pc30 ]
│            │        │
│            │        └── [ meadow.region ]
│            │            │
│            │            └── delegates "forms.meadow.region"
│            │                └──> [ Authoritative NS: pc8 ]
│            │                     │
│            │                     └── [ forms.meadow.region ]
│            │                         └── A → IP of pc8
│            │
│            └── delegates "valley.region"
│                └──> [ Authoritative NS: pc25 ]
│                     │
│                     └── [ valley.region ]
│                         │
│                         └── delegates "metrics.valley.region"
│                             └──> [ Authoritative NS: pc39 ]
│                                  │
│                                  └── [ metrics.valley.region ]
│                                      └── A → IP of pc39
│
├── delegates "foundation"
│   └──> [ Authoritative NS: pc16 ]
│        │
│        └── [ foundation ]
│            │
│            ├── delegates "bridge.foundation"
│            │   └──> [ Authoritative NS: pc49 ]
│            │        │
│            │        └── [ bridge.foundation ]
│            │            │
│            │            └── delegates "collections.bridge.foundation"
│            │                └──> [ Authoritative NS: pc41 ]
│            │                     │
│            │                     └── [ collections.bridge.foundation ]
│            │                         └── A → IP of pc41
│            │
│            └── delegates "horizon.foundation"
│                └──> [ Authoritative NS: pc36 ]
│                     │
│                     └── [ horizon.foundation ]
│                         │
│                         └── delegates "guides.horizon.foundation"
│                             └──> [ Authoritative NS: pc19 ]
│                                  │
│                                  └── [ guides.horizon.foundation ]
│                                      └── A → IP of pc19
│
├── delegates "platform"
│   └──> [ Authoritative NS: pc20 ]
│        │
│        └── [ platform ]
│            │
│            ├── delegates "sprout.platform"
│            │   └──> [ Authoritative NS: pc13 ]
│            │        │
│            │        └── [ sprout.platform ]
│            │            │
│            │            └── delegates "functions.sprout.platform"
│            │                └──> [ Authoritative NS: pc26 ]
│            │                     │
│            │                     └── [ functions.sprout.platform ]
│            │                         └── A → IP of pc26
│            │
│            └── delegates "helix.platform"
│                └──> [ Authoritative NS: pc9 ]
│                     │
│                     └── [ helix.platform ]
│                         │
│                         └── delegates "uptime.helix.platform"
│                             └──> [ Authoritative NS: pc32 ]
│                                  │
│                                  └── [ uptime.helix.platform ]
│                                      └── A → IP of pc32
│
├── delegates "public"
│   └──> [ Authoritative NS: pc31 ]
│        │
│        └── [ public ]
│            │
│            └── delegates "central.public"
│                └──> [ Authoritative NS: pc21 ]
│                     │
│                     └── [ central.public ]
│                         │
│                         ├── delegates "opendata.central.public"
│                         │   └──> [ Authoritative NS: pc42 ]
│                         │        │
│                         │        └── [ opendata.central.public ]
│                         │            └── A → IP of pc42
│                         │
│                         └── delegates "support.central.public"
│                             └──> [ Authoritative NS: pc14 ]
│                                  │
│                                  └── [ support.central.public ]
│                                      │
│                                      ├── A → IP of pc14
│                                      │
│                                      ├── MX support.central.public
│                                      │   └──> [ 10 mailhub.support.central.public ]
│                                      │
│                                      └── mailhub.support.central.public
│                                          └──> [ A record → IP of pc14 ]
│
└── delegates "press"
    └──> [ Authoritative NS: pc34 ]
         │
         └── [ press ]
             │
             └── delegates "bulletin.press"
                 └──> [ Authoritative NS: pc18 ]
                      │
                      └── [ bulletin.press ]
                          │
                          ├── delegates "district.bulletin.press"
                          │   └──> [ Authoritative NS: pc15 ]
                          │        │
                          │        └── [ district.bulletin.press ]
                          │            └── A → IP of pc15
                          │
                          └── delegates "broadcast.bulletin.press"
                              └──> [ Authoritative NS: pc12 ]
                                   │
                                   └── [ broadcast.bulletin.press ]
                                       └── A → IP of pc12

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
                                   └── Root hints: pc38
                                           │
                                           ▼
                        [ Root authoritative NS ]
                                   │
                                   └── Follows the delegations
                                       of the DNS tree
```
