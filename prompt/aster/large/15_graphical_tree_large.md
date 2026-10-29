```text
[ Root domain "." ] ──> [ Authoritative NS: pc37 ]
│
├── delegates "innovation"
│   └──> [ Authoritative NS: pc3 ]
│        │
│        └── [ innovation ]
│            │
│            ├── delegates "aster.innovation"
│            │   └──> [ Authoritative NS: pc14 ]
│            │        │
│            │        └── [ aster.innovation ]
│            │            │
│            │            ├── delegates "catalog.aster.innovation"
│            │            │   └──> [ Authoritative NS: pc27 ]
│            │            │        │
│            │            │        └── [ catalog.aster.innovation ]
│            │            │            └── A → IP of pc27
│            │            │
│            │            └── delegates "stories.aster.innovation"
│            │                └──> [ Authoritative NS: pc38 ]
│            │                     │
│            │                     └── [ stories.aster.innovation ]
│            │                         └── A → IP of pc38
│            │
│            ├── delegates "pinnacle.innovation"
│            │   └──> [ Authoritative NS: pc39 ]
│            │        │
│            │        └── [ pinnacle.innovation ]
│            │            │
│            │            ├── delegates "units.pinnacle.innovation"
│            │            │   └──> [ Authoritative NS: pc5 ]
│            │            │        │
│            │            │        └── [ units.pinnacle.innovation ]
│            │            │            │
│            │            │            ├── A → IP of pc5
│            │            │            │
│            │            │            ├── MX units.pinnacle.innovation
│            │            │            │   └──> [ 10 inbox.units.pinnacle.innovation ]
│            │            │            │
│            │            │            └── inbox.units.pinnacle.innovation
│            │            │                └──> [ A record → IP of pc5 ]
│            │            │
│            │            ├── delegates "private.pinnacle.innovation"
│            │            │   └──> [ Authoritative NS: pc31 ]
│            │            │        │
│            │            │        └── [ private.pinnacle.innovation ]
│            │            │            └── A → IP of pc31
│            │            │
│            │            ├── MX pinnacle.innovation
│            │            │   └──> [ 10 inbox.pinnacle.innovation ]
│            │            │
│            │            └── inbox.pinnacle.innovation
│            │                └──> [ A record → IP of pc39 ]
│            │
│            └── delegates "vector.innovation"
│                └──> [ Authoritative NS: pc6 ]
│                     │
│                     └── [ vector.innovation ]
│                         │
│                         └── delegates "integration.vector.innovation"
│                             └──> [ Authoritative NS: pc11 ]
│                                  │
│                                  └── [ integration.vector.innovation ]
│                                      └── A → IP of pc11
│
├── delegates "infrastructure"
│   └──> [ Authoritative NS: pc15 ]
│        │
│        └── [ infrastructure ]
│            │
│            ├── delegates "cascade.infrastructure"
│            │   └──> [ Authoritative NS: pc1 ]
│            │        │
│            │        └── [ cascade.infrastructure ]
│            │            │
│            │            ├── delegates "studies.cascade.infrastructure"
│            │            │   └──> [ Authoritative NS: pc43 ]
│            │            │        │
│            │            │        └── [ studies.cascade.infrastructure ]
│            │            │            │
│            │            │            ├── delegates "agents.studies.cascade.infrastructure"
│            │            │            │   └──> [ Authoritative NS: pc42 ]
│            │            │            │        │
│            │            │            │        └── [ agents.studies.cascade.infrastructure ]
│            │            │            │            └── A → IP of pc42
│            │            │            │
│            │            │            └── delegates "warehouse.studies.cascade.infrastructure"
│            │            │                └──> [ Authoritative NS: pc30 ]
│            │            │                     │
│            │            │                     └── [ warehouse.studies.cascade.infrastructure ]
│            │            │                         └── A → IP of pc30
│            │            │
│            │            └── delegates "prototype.cascade.infrastructure"
│            │                └──> [ Authoritative NS: pc41 ]
│            │                     │
│            │                     └── [ prototype.cascade.infrastructure ]
│            │                         └── A → IP of pc41
│            │
│            └── delegates "compass.infrastructure"
│                └──> [ Authoritative NS: pc9 ]
│                     │
│                     └── [ compass.infrastructure ]
│                         │
│                         └── delegates "automation.compass.infrastructure"
│                             └──> [ Authoritative NS: pc36 ]
│                                  │
│                                  └── [ automation.compass.infrastructure ]
│                                      └── A → IP of pc36
│
├── delegates "learning"
│   └──> [ Authoritative NS: pc29 ]
│        │
│        └── [ learning ]
│            │
│            ├── delegates "northstar.learning"
│            │   └──> [ Authoritative NS: pc22 ]
│            │        │
│            │        └── [ northstar.learning ]
│            │            │
│            │            ├── delegates "remote.northstar.learning"
│            │            │   └──> [ Authoritative NS: pc16 ]
│            │            │        │
│            │            │        └── [ remote.northstar.learning ]
│            │            │            └── A → IP of pc16
│            │            │
│            │            ├── delegates "lectures.northstar.learning"
│            │            │   └──> [ Authoritative NS: pc46 ]
│            │            │        │
│            │            │        └── [ lectures.northstar.learning ]
│            │            │            └── A → IP of pc46
│            │            │
│            │            ├── MX northstar.learning
│            │            │   └──> [ 10 inbox.northstar.learning ]
│            │            │
│            │            └── inbox.northstar.learning
│            │                └──> [ A record → IP of pc22 ]
│            │
│            └── delegates "equinox.learning"
│                └──> [ Authoritative NS: pc21 ]
│                     │
│                     └── [ equinox.learning ]
│                         │
│                         └── delegates "homepage.equinox.learning"
│                             └──> [ Authoritative NS: pc45 ]
│                                  │
│                                  └── [ homepage.equinox.learning ]
│                                      └── A → IP of pc45
│
├── delegates "territory"
│   └──> [ Authoritative NS: pc28 ]
│        │
│        └── [ territory ]
│            │
│            ├── delegates "helios.territory"
│            │   └──> [ Authoritative NS: pc33 ]
│            │        │
│            │        └── [ helios.territory ]
│            │            │
│            │            └── delegates "scholars.helios.territory"
│            │                └──> [ Authoritative NS: pc48 ]
│            │                     │
│            │                     └── [ scholars.helios.territory ]
│            │                         └── A → IP of pc48
│            │
│            ├── delegates "brookfield.territory"
│            │   └──> [ Authoritative NS: pc24 ]
│            │        │
│            │        └── [ brookfield.territory ]
│            │            │
│            │            └── delegates "assistance.brookfield.territory"
│            │                └──> [ Authoritative NS: pc26 ]
│            │                     │
│            │                     └── [ assistance.brookfield.territory ]
│            │                         └── A → IP of pc26
│            │
│            └── delegates "sierra.territory"
│                └──> [ Authoritative NS: pc7 ]
│                     │
│                     └── [ sierra.territory ]
│                         │
│                         └── delegates "indicators.sierra.territory"
│                             └──> [ Authoritative NS: pc2 ]
│                                  │
│                                  └── [ indicators.sierra.territory ]
│                                      └── A → IP of pc2
│
├── delegates "nonprofit"
│   └──> [ Authoritative NS: pc4 ]
│        │
│        └── [ nonprofit ]
│            │
│            ├── delegates "alliance.nonprofit"
│            │   └──> [ Authoritative NS: pc23 ]
│            │        │
│            │        └── [ alliance.nonprofit ]
│            │            │
│            │            └── delegates "history.alliance.nonprofit"
│            │                └──> [ Authoritative NS: pc34 ]
│            │                     │
│            │                     └── [ history.alliance.nonprofit ]
│            │                         └── A → IP of pc34
│            │
│            └── delegates "blueprint.nonprofit"
│                └──> [ Authoritative NS: pc32 ]
│                     │
│                     └── [ blueprint.nonprofit ]
│                         │
│                         └── delegates "references.blueprint.nonprofit"
│                             └──> [ Authoritative NS: pc44 ]
│                                  │
│                                  └── [ references.blueprint.nonprofit ]
│                                      └── A → IP of pc44
│
├── delegates "compute"
│   └──> [ Authoritative NS: pc35 ]
│        │
│        └── [ compute ]
│            │
│            ├── delegates "ember.compute"
│            │   └──> [ Authoritative NS: pc12 ]
│            │        │
│            │        └── [ ember.compute ]
│            │            │
│            │            └── delegates "microservice.ember.compute"
│            │                └──> [ Authoritative NS: pc8 ]
│            │                     │
│            │                     └── [ microservice.ember.compute ]
│            │                         └── A → IP of pc8
│            │
│            └── delegates "krypton.compute"
│                └──> [ Authoritative NS: pc47 ]
│                     │
│                     └── [ krypton.compute ]
│                         │
│                         └── delegates "monitor.krypton.compute"
│                             └──> [ Authoritative NS: pc20 ]
│                                  │
│                                  └── [ monitor.krypton.compute ]
│                                      └── A → IP of pc20
│
├── delegates "services"
│   └──> [ Authoritative NS: pc17 ]
│        │
│        └── [ services ]
│            │
│            └── delegates "federal.services"
│                └──> [ Authoritative NS: pc19 ]
│                     │
│                     └── [ federal.services ]
│                         │
│                         ├── delegates "disclosure.federal.services"
│                         │   └──> [ Authoritative NS: pc10 ]
│                         │        │
│                         │        └── [ disclosure.federal.services ]
│                         │            └── A → IP of pc10
│                         │
│                         └── delegates "serviceshub.federal.services"
│                             └──> [ Authoritative NS: pc13 ]
│                                  │
│                                  └── [ serviceshub.federal.services ]
│                                      │
│                                      ├── A → IP of pc13
│                                      │
│                                      ├── MX serviceshub.federal.services
│                                      │   └──> [ 10 inbox.serviceshub.federal.services ]
│                                      │
│                                      └── inbox.serviceshub.federal.services
│                                          └──> [ A record → IP of pc13 ]
│
└── delegates "journal"
    └──> [ Authoritative NS: pc49 ]
         │
         └── [ journal ]
             │
             └── delegates "chronicle.journal"
                 └──> [ Authoritative NS: pc40 ]
                      │
                      └── [ chronicle.journal ]
                          │
                          ├── delegates "neighborhood.chronicle.journal"
                          │   └──> [ Authoritative NS: pc18 ]
                          │        │
                          │        └── [ neighborhood.chronicle.journal ]
                          │            └── A → IP of pc18
                          │
                          └── delegates "channels.chronicle.journal"
                              └──> [ Authoritative NS: pc25 ]
                                   │
                                   └── [ channels.chronicle.journal ]
                                       └── A → IP of pc25

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
                                   └── Root hints: pc37
                                           │
                                           ▼
                        [ Root authoritative NS ]
                                   │
                                   └── Follows the delegations
                                       of the DNS tree
```
