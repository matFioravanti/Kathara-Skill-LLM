```text
[ Root domain "." ] ──> [ Authoritative NS: pc8 ]
│
├── delegates "tech"
│   └──> [ Authoritative NS: pc18 ]
│        │
│        └── [ tech ]
│            │
│            ├── delegates "nimbus.tech"
│            │   └──> [ Authoritative NS: pc1 ]
│            │        │
│            │        └── [ nimbus.tech ]
│            │            │
│            │            ├── delegates "store.nimbus.tech"
│            │            │   └──> [ Authoritative NS: pc6 ]
│            │            │        │
│            │            │        └── [ store.nimbus.tech ]
│            │            │            └── A → IP of pc6
│            │            │
│            │            ├── web.nimbus.tech
│            │            │   └──> [ Web service: A record ]
│            │            │
│            │            ├── MX nimbus.tech
│            │            │   └──> [ 10 mx.nimbus.tech ]
│            │            │
│            │            └── mx.nimbus.tech
│            │                └──> [ A record → IP of pc1 ]
│            │
│            └── delegates "forge.tech"
│                └──> [ Authoritative NS: pc17 ]
│                     │
│                     └── [ forge.tech ]
│                         │
│                         ├── delegates "gateway.forge.tech"
│                         │   └──> [ Authoritative NS: pc11 ]
│                         │        │
│                         │        └── [ gateway.forge.tech ]
│                         │            └── A → IP of pc11
│                         │
│                         ├── MX forge.tech
│                         │   └──> [ 10 mx.forge.tech ]
│                         │
│                         └── mx.forge.tech
│                             └──> [ A record → IP of pc17 ]
│
└── delegates "cloud"
    └──> [ Authoritative NS: pc12 ]
         │
         └── [ cloud ]
             │
             ├── delegates "quantum.cloud"
             │   └──> [ Authoritative NS: pc14 ]
             │        │
             │        └── [ quantum.cloud ]
             │            │
             │            ├── delegates "experiments.quantum.cloud"
             │            │   └──> [ Authoritative NS: pc3 ]
             │            │        │
             │            │        └── [ experiments.quantum.cloud ]
             │            │            │
             │            │            ├── delegates "models.experiments.quantum.cloud"
             │            │            │   └──> [ Authoritative NS: pc7 ]
             │            │            │        │
             │            │            │        └── [ models.experiments.quantum.cloud ]
             │            │            │            └── A → IP of pc7
             │            │            │
             │            │            └── delegates "datasets.experiments.quantum.cloud"
             │            │                └──> [ Authoritative NS: pc20 ]
             │            │                     │
             │            │                     └── [ datasets.experiments.quantum.cloud ]
             │            │                         └── A → IP of pc20
             │            │
             │            ├── MX quantum.cloud
             │            │   └──> [ 10 mx.quantum.cloud ]
             │            │
             │            └── mx.quantum.cloud
             │                └──> [ A record → IP of pc14 ]
             │
             └── delegates "matrix.cloud"
                 └──> [ Authoritative NS: pc9 ]
                      │
                      └── [ matrix.cloud ]
                          │
                          ├── delegates "build.matrix.cloud"
                          │   └──> [ Authoritative NS: pc16 ]
                          │        │
                          │        └── [ build.matrix.cloud ]
                          │            └── A → IP of pc16
                          │
                          ├── MX matrix.cloud
                          │   └──> [ 10 mx.matrix.cloud ]
                          │
                          └── mx.matrix.cloud
                              └──> [ A record → IP of pc9 ]

[ Client: pc19, pc5, pc10, pc4, pc15 ]
               │
               └── [ Client resolvers ]
                           │
                           └── DNS query
                                     │
                                     ▼
                        [ Local NS: pc2 ]
                                     │
                           Recursive resolution
                                     │
                                     └── Root hints: pc8
                                             │
                                             ▼
                          [ Root authoritative NS ]
                                     │
                                     └── Follows the delegations
                                         of the DNS tree
```
