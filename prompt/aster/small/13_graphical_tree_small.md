```text
[ Root domain "." ] ──> [ Authoritative NS: pc16 ]
│
├── delegates "innovation"
│   └──> [ Authoritative NS: pc8 ]
│        │
│        └── [ innovation ]
│            │
│            ├── delegates "aster.innovation"
│            │   └──> [ Authoritative NS: pc15 ]
│            │        │
│            │        └── [ aster.innovation ]
│            │            │
│            │            ├── delegates "catalog.aster.innovation"
│            │            │   └──> [ Authoritative NS: pc12 ]
│            │            │        │
│            │            │        └── [ catalog.aster.innovation ]
│            │            │            └── A → IP of pc12
│            │            │
│            │            ├── portalweb.aster.innovation
│            │            │   └──> [ Web service: A record ]
│            │            │
│            │            ├── MX aster.innovation
│            │            │   └──> [ 10 inbox.aster.innovation ]
│            │            │
│            │            └── inbox.aster.innovation
│            │                └──> [ A record → IP of pc15 ]
│            │
│            └── delegates "vector.innovation"
│                └──> [ Authoritative NS: pc7 ]
│                     │
│                     └── [ vector.innovation ]
│                         │
│                         ├── delegates "integration.vector.innovation"
│                         │   └──> [ Authoritative NS: pc11 ]
│                         │        │
│                         │        └── [ integration.vector.innovation ]
│                         │            └── A → IP of pc11
│                         │
│                         ├── MX vector.innovation
│                         │   └──> [ 10 inbox.vector.innovation ]
│                         │
│                         └── inbox.vector.innovation
│                             └──> [ A record → IP of pc7 ]
│
└── delegates "infrastructure"
    └──> [ Authoritative NS: pc18 ]
         │
         └── [ infrastructure ]
             │
             ├── delegates "cascade.infrastructure"
             │   └──> [ Authoritative NS: pc5 ]
             │        │
             │        └── [ cascade.infrastructure ]
             │            │
             │            ├── delegates "studies.cascade.infrastructure"
             │            │   └──> [ Authoritative NS: pc9 ]
             │            │        │
             │            │        └── [ studies.cascade.infrastructure ]
             │            │            │
             │            │            ├── delegates "agents.studies.cascade.infrastructure"
             │            │            │   └──> [ Authoritative NS: pc13 ]
             │            │            │        │
             │            │            │        └── [ agents.studies.cascade.infrastructure ]
             │            │            │            └── A → IP of pc13
             │            │            │
             │            │            └── delegates "warehouse.studies.cascade.infrastructure"
             │            │                └──> [ Authoritative NS: pc19 ]
             │            │                     │
             │            │                     └── [ warehouse.studies.cascade.infrastructure ]
             │            │                         └── A → IP of pc19
             │            │
             │            ├── MX cascade.infrastructure
             │            │   └──> [ 10 inbox.cascade.infrastructure ]
             │            │
             │            └── inbox.cascade.infrastructure
             │                └──> [ A record → IP of pc5 ]
             │
             └── delegates "compass.infrastructure"
                 └──> [ Authoritative NS: pc20 ]
                      │
                      └── [ compass.infrastructure ]
                          │
                          ├── delegates "automation.compass.infrastructure"
                          │   └──> [ Authoritative NS: pc3 ]
                          │        │
                          │        └── [ automation.compass.infrastructure ]
                          │            └── A → IP of pc3
                          │
                          ├── MX compass.infrastructure
                          │   └──> [ 10 inbox.compass.infrastructure ]
                          │
                          └── inbox.compass.infrastructure
                              └──> [ A record → IP of pc20 ]

[ Client: pc1, pc6, pc4, pc10, pc14 ]
               │
               └── [ Client resolvers ]
                           │
                           └── DNS query
                                     │
                                     ▼
                        [ Local NS: pc17 ]
                                     │
                           Recursive resolution
                                     │
                                     └── Root hints: pc16
                                             │
                                             ▼
                          [ Root authoritative NS ]
                                     │
                                     └── Follows the delegations
                                         of the DNS tree
```
