```text
[ Root domain "." ] ──> [ Authoritative NS: pc27 ]
│
├── delegates "innovation"
│   └──> [ Authoritative NS: pc25 ]
│        │
│        └── [ innovation ]
│            │
│            ├── delegates "aster.innovation"
│            │   └──> [ Authoritative NS: pc23 ]
│            │        │
│            │        └── [ aster.innovation ]
│            │            │
│            │            ├── delegates "catalog.aster.innovation"
│            │            │   └──> [ Authoritative NS: pc31 ]
│            │            │        │
│            │            │        └── [ catalog.aster.innovation ]
│            │            │            └── A → IP of pc31
│            │            │
│            │            ├── delegates "stories.aster.innovation"
│            │            │   └──> [ Authoritative NS: pc8 ]
│            │            │        │
│            │            │        └── [ stories.aster.innovation ]
│            │            │            └── A → IP of pc8
│            │            │
│            │            └── portalweb.aster.innovation
│            │                └──> [ Web service: A record ]
│            │
│            ├── delegates "pinnacle.innovation"
│            │   └──> [ Authoritative NS: pc30 ]
│            │        │
│            │        └── [ pinnacle.innovation ]
│            │            │
│            │            ├── delegates "units.pinnacle.innovation"
│            │            │   └──> [ Authoritative NS: pc4 ]
│            │            │        │
│            │            │        └── [ units.pinnacle.innovation ]
│            │            │            └── A → IP of pc4
│            │            │
│            │            ├── delegates "private.pinnacle.innovation"
│            │            │   └──> [ Authoritative NS: pc28 ]
│            │            │        │
│            │            │        └── [ private.pinnacle.innovation ]
│            │            │            └── A → IP of pc28
│            │            │
│            │            ├── MX pinnacle.innovation
│            │            │   └──> [ 10 inbox.pinnacle.innovation ]
│            │            │
│            │            └── inbox.pinnacle.innovation
│            │                └──> [ A record → IP of pc30 ]
│            │
│            └── delegates "vector.innovation"
│                └──> [ Authoritative NS: pc6 ]
│                     │
│                     └── [ vector.innovation ]
│                         │
│                         └── delegates "integration.vector.innovation"
│                             └──> [ Authoritative NS: pc15 ]
│                                  │
│                                  └── [ integration.vector.innovation ]
│                                      └── A → IP of pc15
│
├── delegates "infrastructure"
│   └──> [ Authoritative NS: pc10 ]
│        │
│        └── [ infrastructure ]
│            │
│            ├── delegates "cascade.infrastructure"
│            │   └──> [ Authoritative NS: pc5 ]
│            │        │
│            │        └── [ cascade.infrastructure ]
│            │            │
│            │            ├── delegates "studies.cascade.infrastructure"
│            │            │   └──> [ Authoritative NS: pc16 ]
│            │            │        │
│            │            │        └── [ studies.cascade.infrastructure ]
│            │            │            │
│            │            │            ├── delegates "agents.studies.cascade.infrastructure"
│            │            │            │   └──> [ Authoritative NS: pc11 ]
│            │            │            │        │
│            │            │            │        └── [ agents.studies.cascade.infrastructure ]
│            │            │            │            └── A → IP of pc11
│            │            │            │
│            │            │            └── delegates "warehouse.studies.cascade.infrastructure"
│            │            │                └──> [ Authoritative NS: pc29 ]
│            │            │                     │
│            │            │                     └── [ warehouse.studies.cascade.infrastructure ]
│            │            │                         └── A → IP of pc29
│            │            │
│            │            └── delegates "prototype.cascade.infrastructure"
│            │                └──> [ Authoritative NS: pc21 ]
│            │                     │
│            │                     └── [ prototype.cascade.infrastructure ]
│            │                         └── A → IP of pc21
│            │
│            └── delegates "compass.infrastructure"
│                └──> [ Authoritative NS: pc14 ]
│                     │
│                     └── [ compass.infrastructure ]
│                         │
│                         └── delegates "automation.compass.infrastructure"
│                             └──> [ Authoritative NS: pc1 ]
│                                  │
│                                  └── [ automation.compass.infrastructure ]
│                                      └── A → IP of pc1
│
├── delegates "learning"
│   └──> [ Authoritative NS: pc2 ]
│        │
│        └── [ learning ]
│            │
│            ├── delegates "northstar.learning"
│            │   └──> [ Authoritative NS: pc26 ]
│            │        │
│            │        └── [ northstar.learning ]
│            │            │
│            │            ├── delegates "remote.northstar.learning"
│            │            │   └──> [ Authoritative NS: pc18 ]
│            │            │        │
│            │            │        └── [ remote.northstar.learning ]
│            │            │            └── A → IP of pc18
│            │            │
│            │            ├── delegates "lectures.northstar.learning"
│            │            │   └──> [ Authoritative NS: pc3 ]
│            │            │        │
│            │            │        └── [ lectures.northstar.learning ]
│            │            │            └── A → IP of pc3
│            │            │
│            │            ├── MX northstar.learning
│            │            │   └──> [ 10 inbox.northstar.learning ]
│            │            │
│            │            └── inbox.northstar.learning
│            │                └──> [ A record → IP of pc26 ]
│            │
│            └── delegates "equinox.learning"
│                └──> [ Authoritative NS: pc17 ]
│                     │
│                     └── [ equinox.learning ]
│                         │
│                         └── delegates "homepage.equinox.learning"
│                             └──> [ Authoritative NS: pc24 ]
│                                  │
│                                  └── [ homepage.equinox.learning ]
│                                      └── A → IP of pc24
│
└── delegates "territory"
    └──> [ Authoritative NS: pc9 ]
         │
         └── [ territory ]
             │
             ├── delegates "helios.territory"
             │   └──> [ Authoritative NS: pc20 ]
             │        │
             │        └── [ helios.territory ]
             │            │
             │            └── delegates "scholars.helios.territory"
             │                └──> [ Authoritative NS: pc7 ]
             │                     │
             │                     └── [ scholars.helios.territory ]
             │                         └── A → IP of pc7
             │
             ├── delegates "brookfield.territory"
             │   └──> [ Authoritative NS: pc12 ]
             │        │
             │        └── [ brookfield.territory ]
             │            │
             │            └── delegates "assistance.brookfield.territory"
             │                └──> [ Authoritative NS: pc13 ]
             │                     │
             │                     └── [ assistance.brookfield.territory ]
             │                         └── A → IP of pc13
             │
             └── delegates "sierra.territory"
                 └──> [ Authoritative NS: pc22 ]
                      │
                      └── [ sierra.territory ]
                          │
                          └── delegates "indicators.sierra.territory"
                              └──> [ Authoritative NS: pc19 ]
                                   │
                                   └── [ indicators.sierra.territory ]
                                       └── A → IP of pc19

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
                                   └── Root hints: pc27
                                           │
                                           ▼
                        [ Root authoritative NS ]
                                   │
                                   └── Follows the delegations
                                       of the DNS tree
```
