```text
[ Root domain "." ] ──> [ Authoritative NS: pc13 ]
│
├── delegates "tech"
│   └──> [ Authoritative NS: pc49 ]
│        │
│        └── [ tech ]
│            │
│            ├── delegates "nimbus.tech"
│            │   └──> [ Authoritative NS: pc20 ]
│            │        │
│            │        └── [ nimbus.tech ]
│            │            │
│            │            ├── delegates "store.nimbus.tech"
│            │            │   └──> [ Authoritative NS: pc8 ]
│            │            │        │
│            │            │        └── [ store.nimbus.tech ]
│            │            │            └── A → IP of pc8
│            │            │
│            │            └── delegates "insights.nimbus.tech"
│            │                └──> [ Authoritative NS: pc38 ]
│            │                     │
│            │                     └── [ insights.nimbus.tech ]
│            │                         └── A → IP of pc38
│            │
│            ├── delegates "orbit.tech"
│            │   └──> [ Authoritative NS: pc40 ]
│            │        │
│            │        └── [ orbit.tech ]
│            │            │
│            │            ├── delegates "division.orbit.tech"
│            │            │   └──> [ Authoritative NS: pc24 ]
│            │            │        │
│            │            │        └── [ division.orbit.tech ]
│            │            │            │
│            │            │            ├── A → IP of pc24
│            │            │            │
│            │            │            ├── MX division.orbit.tech
│            │            │            │   └──> [ 10 mx.division.orbit.tech ]
│            │            │            │
│            │            │            └── mx.division.orbit.tech
│            │            │                └──> [ A record → IP of pc24 ]
│            │            │
│            │            ├── delegates "internal.orbit.tech"
│            │            │   └──> [ Authoritative NS: pc18 ]
│            │            │        │
│            │            │        └── [ internal.orbit.tech ]
│            │            │            └── A → IP of pc18
│            │            │
│            │            ├── MX orbit.tech
│            │            │   └──> [ 10 mx.orbit.tech ]
│            │            │
│            │            └── mx.orbit.tech
│            │                └──> [ A record → IP of pc40 ]
│            │
│            └── delegates "forge.tech"
│                └──> [ Authoritative NS: pc39 ]
│                     │
│                     └── [ forge.tech ]
│                         │
│                         └── delegates "gateway.forge.tech"
│                             └──> [ Authoritative NS: pc22 ]
│                                  │
│                                  └── [ gateway.forge.tech ]
│                                      └── A → IP of pc22
│
├── delegates "cloud"
│   └──> [ Authoritative NS: pc7 ]
│        │
│        └── [ cloud ]
│            │
│            ├── delegates "quantum.cloud"
│            │   └──> [ Authoritative NS: pc2 ]
│            │        │
│            │        └── [ quantum.cloud ]
│            │            │
│            │            ├── delegates "experiments.quantum.cloud"
│            │            │   └──> [ Authoritative NS: pc43 ]
│            │            │        │
│            │            │        └── [ experiments.quantum.cloud ]
│            │            │            │
│            │            │            ├── delegates "models.experiments.quantum.cloud"
│            │            │            │   └──> [ Authoritative NS: pc6 ]
│            │            │            │        │
│            │            │            │        └── [ models.experiments.quantum.cloud ]
│            │            │            │            └── A → IP of pc6
│            │            │            │
│            │            │            └── delegates "datasets.experiments.quantum.cloud"
│            │            │                └──> [ Authoritative NS: pc9 ]
│            │            │                     │
│            │            │                     └── [ datasets.experiments.quantum.cloud ]
│            │            │                         └── A → IP of pc9
│            │            │
│            │            └── delegates "sandbox.quantum.cloud"
│            │                └──> [ Authoritative NS: pc47 ]
│            │                     │
│            │                     └── [ sandbox.quantum.cloud ]
│            │                         └── A → IP of pc47
│            │
│            └── delegates "matrix.cloud"
│                └──> [ Authoritative NS: pc3 ]
│                     │
│                     └── [ matrix.cloud ]
│                         │
│                         └── delegates "build.matrix.cloud"
│                             └──> [ Authoritative NS: pc15 ]
│                                  │
│                                  └── [ build.matrix.cloud ]
│                                      └── A → IP of pc15
│
├── delegates "academy"
│   └──> [ Authoritative NS: pc29 ]
│        │
│        └── [ academy ]
│            │
│            ├── delegates "summit.academy"
│            │   └──> [ Authoritative NS: pc4 ]
│            │        │
│            │        └── [ summit.academy ]
│            │            │
│            │            ├── delegates "secure.summit.academy"
│            │            │   └──> [ Authoritative NS: pc23 ]
│            │            │        │
│            │            │        └── [ secure.summit.academy ]
│            │            │            └── A → IP of pc23
│            │            │
│            │            ├── delegates "lessons.summit.academy"
│            │            │   └──> [ Authoritative NS: pc41 ]
│            │            │        │
│            │            │        └── [ lessons.summit.academy ]
│            │            │            └── A → IP of pc41
│            │            │
│            │            ├── MX summit.academy
│            │            │   └──> [ 10 mx.summit.academy ]
│            │            │
│            │            └── mx.summit.academy
│            │                └──> [ A record → IP of pc4 ]
│            │
│            └── delegates "cedar.academy"
│                └──> [ Authoritative NS: pc1 ]
│                     │
│                     └── [ cedar.academy ]
│                         │
│                         └── delegates "entry.cedar.academy"
│                             └──> [ Authoritative NS: pc33 ]
│                                  │
│                                  └── [ entry.cedar.academy ]
│                                      └── A → IP of pc33
│
├── delegates "city"
│   └──> [ Authoritative NS: pc48 ]
│        │
│        └── [ city ]
│            │
│            ├── delegates "polaris.city"
│            │   └──> [ Authoritative NS: pc16 ]
│            │        │
│            │        └── [ polaris.city ]
│            │            │
│            │            └── delegates "students.polaris.city"
│            │                └──> [ Authoritative NS: pc10 ]
│            │                     │
│            │                     └── [ students.polaris.city ]
│            │                         └── A → IP of pc10
│            │
│            ├── delegates "riverton.city"
│            │   └──> [ Authoritative NS: pc19 ]
│            │        │
│            │        └── [ riverton.city ]
│            │            │
│            │            └── delegates "requests.riverton.city"
│            │                └──> [ Authoritative NS: pc12 ]
│            │                     │
│            │                     └── [ requests.riverton.city ]
│            │                         └── A → IP of pc12
│            │
│            └── delegates "highland.city"
│                └──> [ Authoritative NS: pc34 ]
│                     │
│                     └── [ highland.city ]
│                         │
│                         └── delegates "statistics.highland.city"
│                             └──> [ Authoritative NS: pc5 ]
│                                  │
│                                  └── [ statistics.highland.city ]
│                                      └── A → IP of pc5
│
├── delegates "community"
│   └──> [ Authoritative NS: pc37 ]
│        │
│        └── [ community ]
│            │
│            ├── delegates "harbor.community"
│            │   └──> [ Authoritative NS: pc11 ]
│            │        │
│            │        └── [ harbor.community ]
│            │            │
│            │            └── delegates "vault.harbor.community"
│            │                └──> [ Authoritative NS: pc30 ]
│            │                     │
│            │                     └── [ vault.harbor.community ]
│            │                         └── A → IP of pc30
│            │
│            └── delegates "keystone.community"
│                └──> [ Authoritative NS: pc14 ]
│                     │
│                     └── [ keystone.community ]
│                         │
│                         └── delegates "manuals.keystone.community"
│                             └──> [ Authoritative NS: pc28 ]
│                                  │
│                                  └── [ manuals.keystone.community ]
│                                      └── A → IP of pc28
│
├── delegates "systems"
│   └──> [ Authoritative NS: pc31 ]
│        │
│        └── [ systems ]
│            │
│            ├── delegates "nova.systems"
│            │   └──> [ Authoritative NS: pc27 ]
│            │        │
│            │        └── [ nova.systems ]
│            │            │
│            │            └── delegates "endpoint.nova.systems"
│            │                └──> [ Authoritative NS: pc46 ]
│            │                     │
│            │                     └── [ endpoint.nova.systems ]
│            │                         └── A → IP of pc46
│            │
│            └── delegates "stratus.systems"
│                └──> [ Authoritative NS: pc36 ]
│                     │
│                     └── [ stratus.systems ]
│                         │
│                         └── delegates "health.stratus.systems"
│                             └──> [ Authoritative NS: pc32 ]
│                                  │
│                                  └── [ health.stratus.systems ]
│                                      └── A → IP of pc32
│
├── delegates "agency"
│   └──> [ Authoritative NS: pc44 ]
│        │
│        └── [ agency ]
│            │
│            └── delegates "civic.agency"
│                └──> [ Authoritative NS: pc45 ]
│                     │
│                     └── [ civic.agency ]
│                         │
│                         ├── delegates "transparency.civic.agency"
│                         │   └──> [ Authoritative NS: pc17 ]
│                         │        │
│                         │        └── [ transparency.civic.agency ]
│                         │            └── A → IP of pc17
│                         │
│                         └── delegates "citizens.civic.agency"
│                             └──> [ Authoritative NS: pc26 ]
│                                  │
│                                  └── [ citizens.civic.agency ]
│                                      │
│                                      ├── A → IP of pc26
│                                      │
│                                      ├── MX citizens.civic.agency
│                                      │   └──> [ 10 mx.citizens.civic.agency ]
│                                      │
│                                      └── mx.citizens.civic.agency
│                                          └──> [ A record → IP of pc26 ]
│
└── delegates "media"
    └──> [ Authoritative NS: pc42 ]
         │
         └── [ media ]
             │
             └── delegates "pulse.media"
                 └──> [ Authoritative NS: pc21 ]
                      │
                      └── [ pulse.media ]
                          │
                          ├── delegates "localdesk.pulse.media"
                          │   └──> [ Authoritative NS: pc35 ]
                          │        │
                          │        └── [ localdesk.pulse.media ]
                          │            └── A → IP of pc35
                          │
                          └── delegates "streams.pulse.media"
                              └──> [ Authoritative NS: pc25 ]
                                   │
                                   └── [ streams.pulse.media ]
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
                                   └── Root hints: pc13
                                           │
                                           ▼
                        [ Root authoritative NS ]
                                   │
                                   └── Follows the delegations
                                       of the DNS tree
```
