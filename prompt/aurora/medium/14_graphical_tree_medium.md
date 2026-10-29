```text
[ Root domain "." ] ──> [ Authoritative NS: pc3 ]
│
├── delegates "tech"
│   └──> [ Authoritative NS: pc31 ]
│        │
│        └── [ tech ]
│            │
│            ├── delegates "nimbus.tech"
│            │   └──> [ Authoritative NS: pc10 ]
│            │        │
│            │        └── [ nimbus.tech ]
│            │            │
│            │            ├── delegates "store.nimbus.tech"
│            │            │   └──> [ Authoritative NS: pc25 ]
│            │            │        │
│            │            │        └── [ store.nimbus.tech ]
│            │            │            └── A → IP of pc25
│            │            │
│            │            ├── delegates "insights.nimbus.tech"
│            │            │   └──> [ Authoritative NS: pc23 ]
│            │            │        │
│            │            │        └── [ insights.nimbus.tech ]
│            │            │            └── A → IP of pc23
│            │            │
│            │            └── web.nimbus.tech
│            │                └──> [ Web service: A record ]
│            │
│            ├── delegates "orbit.tech"
│            │   └──> [ Authoritative NS: pc6 ]
│            │        │
│            │        └── [ orbit.tech ]
│            │            │
│            │            ├── delegates "division.orbit.tech"
│            │            │   └──> [ Authoritative NS: pc7 ]
│            │            │        │
│            │            │        └── [ division.orbit.tech ]
│            │            │            └── A → IP of pc7
│            │            │
│            │            ├── delegates "internal.orbit.tech"
│            │            │   └──> [ Authoritative NS: pc1 ]
│            │            │        │
│            │            │        └── [ internal.orbit.tech ]
│            │            │            └── A → IP of pc1
│            │            │
│            │            ├── MX orbit.tech
│            │            │   └──> [ 10 mx.orbit.tech ]
│            │            │
│            │            └── mx.orbit.tech
│            │                └──> [ A record → IP of pc6 ]
│            │
│            └── delegates "forge.tech"
│                └──> [ Authoritative NS: pc26 ]
│                     │
│                     └── [ forge.tech ]
│                         │
│                         └── delegates "gateway.forge.tech"
│                             └──> [ Authoritative NS: pc28 ]
│                                  │
│                                  └── [ gateway.forge.tech ]
│                                      └── A → IP of pc28
│
├── delegates "cloud"
│   └──> [ Authoritative NS: pc17 ]
│        │
│        └── [ cloud ]
│            │
│            ├── delegates "quantum.cloud"
│            │   └──> [ Authoritative NS: pc5 ]
│            │        │
│            │        └── [ quantum.cloud ]
│            │            │
│            │            ├── delegates "experiments.quantum.cloud"
│            │            │   └──> [ Authoritative NS: pc15 ]
│            │            │        │
│            │            │        └── [ experiments.quantum.cloud ]
│            │            │            │
│            │            │            ├── delegates "models.experiments.quantum.cloud"
│            │            │            │   └──> [ Authoritative NS: pc20 ]
│            │            │            │        │
│            │            │            │        └── [ models.experiments.quantum.cloud ]
│            │            │            │            └── A → IP of pc20
│            │            │            │
│            │            │            └── delegates "datasets.experiments.quantum.cloud"
│            │            │                └──> [ Authoritative NS: pc18 ]
│            │            │                     │
│            │            │                     └── [ datasets.experiments.quantum.cloud ]
│            │            │                         └── A → IP of pc18
│            │            │
│            │            └── delegates "sandbox.quantum.cloud"
│            │                └──> [ Authoritative NS: pc14 ]
│            │                     │
│            │                     └── [ sandbox.quantum.cloud ]
│            │                         └── A → IP of pc14
│            │
│            └── delegates "matrix.cloud"
│                └──> [ Authoritative NS: pc2 ]
│                     │
│                     └── [ matrix.cloud ]
│                         │
│                         └── delegates "build.matrix.cloud"
│                             └──> [ Authoritative NS: pc8 ]
│                                  │
│                                  └── [ build.matrix.cloud ]
│                                      └── A → IP of pc8
│
├── delegates "academy"
│   └──> [ Authoritative NS: pc24 ]
│        │
│        └── [ academy ]
│            │
│            ├── delegates "summit.academy"
│            │   └──> [ Authoritative NS: pc29 ]
│            │        │
│            │        └── [ summit.academy ]
│            │            │
│            │            ├── delegates "secure.summit.academy"
│            │            │   └──> [ Authoritative NS: pc11 ]
│            │            │        │
│            │            │        └── [ secure.summit.academy ]
│            │            │            └── A → IP of pc11
│            │            │
│            │            ├── delegates "lessons.summit.academy"
│            │            │   └──> [ Authoritative NS: pc9 ]
│            │            │        │
│            │            │        └── [ lessons.summit.academy ]
│            │            │            └── A → IP of pc9
│            │            │
│            │            ├── MX summit.academy
│            │            │   └──> [ 10 mx.summit.academy ]
│            │            │
│            │            └── mx.summit.academy
│            │                └──> [ A record → IP of pc29 ]
│            │
│            └── delegates "cedar.academy"
│                └──> [ Authoritative NS: pc13 ]
│                     │
│                     └── [ cedar.academy ]
│                         │
│                         └── delegates "entry.cedar.academy"
│                             └──> [ Authoritative NS: pc21 ]
│                                  │
│                                  └── [ entry.cedar.academy ]
│                                      └── A → IP of pc21
│
└── delegates "city"
    └──> [ Authoritative NS: pc12 ]
         │
         └── [ city ]
             │
             ├── delegates "polaris.city"
             │   └──> [ Authoritative NS: pc4 ]
             │        │
             │        └── [ polaris.city ]
             │            │
             │            └── delegates "students.polaris.city"
             │                └──> [ Authoritative NS: pc19 ]
             │                     │
             │                     └── [ students.polaris.city ]
             │                         └── A → IP of pc19
             │
             ├── delegates "riverton.city"
             │   └──> [ Authoritative NS: pc22 ]
             │        │
             │        └── [ riverton.city ]
             │            │
             │            └── delegates "requests.riverton.city"
             │                └──> [ Authoritative NS: pc16 ]
             │                     │
             │                     └── [ requests.riverton.city ]
             │                         └── A → IP of pc16
             │
             └── delegates "highland.city"
                 └──> [ Authoritative NS: pc30 ]
                      │
                      └── [ highland.city ]
                          │
                          └── delegates "statistics.highland.city"
                              └──> [ Authoritative NS: pc27 ]
                                   │
                                   └── [ statistics.highland.city ]
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
                                   └── Root hints: pc3
                                           │
                                           ▼
                        [ Root authoritative NS ]
                                   │
                                   └── Follows the delegations
                                       of the DNS tree
```
