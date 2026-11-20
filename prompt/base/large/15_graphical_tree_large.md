```text
[ Root domain "." ] ──> [ Authoritative NS: pc1 ]
│
├── delegates "com"
│   └──> [ Authoritative NS: pc2 ]
│        │
│        └── [ com ]
│            │
│            ├── delegates "example.com"
│            │   └──> [ Authoritative NS: pc6 ]
│            │        │
│            │        └── [ example.com ]
│            │            │
│            │            ├── delegates "shop.example.com"
│            │            │   └──> [ Authoritative NS: pc16 ]
│            │            │        │
│            │            │        └── [ shop.example.com ]
│            │            │            └── A → IP of pc16
│            │            │
│            │            ├── delegates "blog.example.com"
│            │            │   └──> [ Authoritative NS: pc17 ]
│            │            │        │
│            │            │        └── [ blog.example.com ]
│            │            │            └── A → IP of pc17
│            │            │
│            │            ├── www.example.com
│            │            │   └──> [ Web service: A record ]
│            │            │
│            │            └── A → IP of pc6
│            │
│            ├── delegates "company.com"
│            │   └──> [ Authoritative NS: pc7 ]
│            │        │
│            │        └── [ company.com ]
│            │            │
│            │            ├── delegates "dept.company.com"
│            │            │   └──> [ Authoritative NS: pc18 ]
│            │            │        │
│            │            │        └── [ dept.company.com ]
│            │            │            │
│            │            │            ├── A → IP of pc18
│            │            │            │
│            │            │            ├── MX dept.company.com
│            │            │            │   └──> [ 10 mail.dept.company.com ]
│            │            │            │
│            │            │            └── mail.dept.company.com
│            │            │                └──> [ A record → IP of pc18 ]
│            │            │
│            │            ├── delegates "intranet.company.com"
│            │            │   └──> [ Authoritative NS: pc19 ]
│            │            │        │
│            │            │        └── [ intranet.company.com ]
│            │            │            └── A → IP of pc19
│            │            │
│            │            ├── A → IP of pc7
│            │            │
│            │            ├── MX company.com
│            │            │   └──> [ 10 mail.company.com ]
│            │            │
│            │            └── mail.company.com
│            │                └──> [ A record → IP of pc7 ]
│            │
│            └── delegates "service.com"
│                └──> [ Authoritative NS: pc8 ]
│                     │
│                     └── [ service.com ]
│                         │
│                         ├── delegates "api.service.com"
│                         │   └──> [ Authoritative NS: pc20 ]
│                         │        │
│                         │        └── [ api.service.com ]
│                         │            └── A → IP of pc20
│                         │
│                         └── A → IP of pc8
│
├── delegates "net"
│   └──> [ Authoritative NS: pc3 ]
│        │
│        └── [ net ]
│            │
│            ├── delegates "lab.net"
│            │   └──> [ Authoritative NS: pc9 ]
│            │        │
│            │        └── [ lab.net ]
│            │            │
│            │            ├── delegates "research.lab.net"
│            │            │   └──> [ Authoritative NS: pc21 ]
│            │            │        │
│            │            │        └── [ research.lab.net ]
│            │            │            │
│            │            │            ├── delegates "ai.research.lab.net"
│            │            │            │   └──> [ Authoritative NS: pc22 ]
│            │            │            │        │
│            │            │            │        └── [ ai.research.lab.net ]
│            │            │            │            └── A → IP of pc22
│            │            │            │
│            │            │            ├── delegates "data.research.lab.net"
│            │            │            │   └──> [ Authoritative NS: pc23 ]
│            │            │            │        │
│            │            │            │        └── [ data.research.lab.net ]
│            │            │            │            └── A → IP of pc23
│            │            │            │
│            │            │            └── A → IP of pc21
│            │            │
│            │            ├── delegates "dev.lab.net"
│            │            │   └──> [ Authoritative NS: pc24 ]
│            │            │        │
│            │            │        └── [ dev.lab.net ]
│            │            │            └── A → IP of pc24
│            │            │
│            │            └── A → IP of pc9
│            │
│            └── delegates "tools.net"
│                └──> [ Authoritative NS: pc10 ]
│                     │
│                     └── [ tools.net ]
│                         │
│                         ├── delegates "ci.tools.net"
│                         │   └──> [ Authoritative NS: pc25 ]
│                         │        │
│                         │        └── [ ci.tools.net ]
│                         │            └── A → IP of pc25
│                         │
│                         └── A → IP of pc10
│
├── delegates "edu"
│   └──> [ Authoritative NS: pc4 ]
│        │
│        └── [ edu ]
│            │
│            ├── delegates "university.edu"
│            │   └──> [ Authoritative NS: pc11 ]
│            │        │
│            │        └── [ university.edu ]
│            │            │
│            │            ├── delegates "vpn.university.edu"
│            │            │   └──> [ Authoritative NS: pc26 ]
│            │            │        │
│            │            │        └── [ vpn.university.edu ]
│            │            │            └── A → IP of pc26
│            │            │
│            │            ├── delegates "courses.university.edu"
│            │            │   └──> [ Authoritative NS: pc27 ]
│            │            │        │
│            │            │        └── [ courses.university.edu ]
│            │            │            └── A → IP of pc27
│            │            │
│            │            ├── A → IP of pc11
│            │            │
│            │            ├── MX university.edu
│            │            │   └──> [ 10 mail.university.edu ]
│            │            │
│            │            └── mail.university.edu
│            │                └──> [ A record → IP of pc11 ]
│            │
│            └── delegates "campus.edu"
│                └──> [ Authoritative NS: pc12 ]
│                     │
│                     └── [ campus.edu ]
│                         │
│                         ├── delegates "portal.campus.edu"
│                         │   └──> [ Authoritative NS: pc28 ]
│                         │        │
│                         │        └── [ portal.campus.edu ]
│                         │            └── A → IP of pc28
│                         │
│                         └── A → IP of pc12
│
├── delegates "it"
│   └──> [ Authoritative NS: pc5 ]
│        │
│        └── [ it ]
│            │
│            ├── delegates "unibo.it"
│            │   └──> [ Authoritative NS: pc13 ]
│            │        │
│            │        └── [ unibo.it ]
│            │            │
│            │            ├── delegates "studenti.unibo.it"
│            │            │   └──> [ Authoritative NS: pc29 ]
│            │            │        │
│            │            │        └── [ studenti.unibo.it ]
│            │            │            └── A → IP of pc29
│            │            │
│            │            └── A → IP of pc13
│            │
│            ├── delegates "comune.it"
│            │   └──> [ Authoritative NS: pc14 ]
│            │        │
│            │        └── [ comune.it ]
│            │            │
│            │            ├── delegates "servizi.comune.it"
│            │            │   └──> [ Authoritative NS: pc30 ]
│            │            │        │
│            │            │        └── [ servizi.comune.it ]
│            │            │            └── A → IP of pc30
│            │            │
│            │            └── A → IP of pc14
│            │
│            └── delegates "regione.it"
│                └──> [ Authoritative NS: pc15 ]
│                     │
│                     └── [ regione.it ]
│                         │
│                         ├── delegates "dati.regione.it"
│                         │   └──> [ Authoritative NS: pc31 ]
│                         │        │
│                         │        └── [ dati.regione.it ]
│                         │            └── A → IP of pc31
│                         │
│                         └── A → IP of pc15
│
├── delegates "org"
│   └──> [ Authoritative NS: pc32 ]
│        │
│        └── [ org ]
│            │
│            ├── delegates "foundation.org"
│            │   └──> [ Authoritative NS: pc36 ]
│            │        │
│            │        └── [ foundation.org ]
│            │            │
│            │            ├── delegates "archive.foundation.org"
│            │            │   └──> [ Authoritative NS: pc42 ]
│            │            │        │
│            │            │        └── [ archive.foundation.org ]
│            │            │            └── A → IP of pc42
│            │            │
│            │            └── A → IP of pc36
│            │
│            └── delegates "project.org"
│                └──> [ Authoritative NS: pc37 ]
│                     │
│                     └── [ project.org ]
│                         │
│                         ├── delegates "docs.project.org"
│                         │   └──> [ Authoritative NS: pc43 ]
│                         │        │
│                         │        └── [ docs.project.org ]
│                         │            └── A → IP of pc43
│                         │
│                         └── A → IP of pc37
│
├── delegates "io"
│   └──> [ Authoritative NS: pc33 ]
│        │
│        └── [ io ]
│            │
│            ├── delegates "startup.io"
│            │   └──> [ Authoritative NS: pc38 ]
│            │        │
│            │        └── [ startup.io ]
│            │            │
│            │            ├── delegates "api.startup.io"
│            │            │   └──> [ Authoritative NS: pc44 ]
│            │            │        │
│            │            │        └── [ api.startup.io ]
│            │            │            └── A → IP of pc44
│            │            │
│            │            └── A → IP of pc38
│            │
│            └── delegates "platform.io"
│                └──> [ Authoritative NS: pc39 ]
│                     │
│                     └── [ platform.io ]
│                         │
│                         ├── delegates "status.platform.io"
│                         │   └──> [ Authoritative NS: pc45 ]
│                         │        │
│                         │        └── [ status.platform.io ]
│                         │            └── A → IP of pc45
│                         │
│                         └── A → IP of pc39
│
├── delegates "gov"
│   └──> [ Authoritative NS: pc34 ]
│        │
│        └── [ gov ]
│            │
│            └── delegates "ministero.gov"
│                └──> [ Authoritative NS: pc40 ]
│                     │
│                     └── [ ministero.gov ]
│                         │
│                         ├── delegates "open.ministero.gov"
│                         │   └──> [ Authoritative NS: pc46 ]
│                         │        │
│                         │        └── [ open.ministero.gov ]
│                         │            └── A → IP of pc46
│                         │
│                         ├── delegates "servizi.ministero.gov"
│                         │   └──> [ Authoritative NS: pc47 ]
│                         │        │
│                         │        └── [ servizi.ministero.gov ]
│                         │            │
│                         │            ├── A → IP of pc47
│                         │            │
│                         │            ├── MX servizi.ministero.gov
│                         │            │   └──> [ 10 mail.servizi.ministero.gov ]
│                         │            │
│                         │            └── mail.servizi.ministero.gov
│                         │                └──> [ A record → IP of pc47 ]
│                         │
│                         └── A → IP of pc40
│
└── delegates "info"
    └──> [ Authoritative NS: pc35 ]
         │
         └── [ info ]
             │
             └── delegates "news.info"
                 └──> [ Authoritative NS: pc41 ]
                      │
                      └── [ news.info ]
                          │
                          ├── delegates "local.news.info"
                          │   └──> [ Authoritative NS: pc48 ]
                          │        │
                          │        └── [ local.news.info ]
                          │            └── A → IP of pc48
                          │
                          ├── delegates "media.news.info"
                          │   └──> [ Authoritative NS: pc49 ]
                          │        │
                          │        └── [ media.news.info ]
                          │            └── A → IP of pc49
                          │
                          └── A → IP of pc41

[ Client: pc51, pc52, pc53, pc54, pc55, pc56, pc57, pc58, pc59, pc60 ]
               │
               └── [ Client resolvers ]
                           │
                           └── DNS query
                                     │
                                     ▼
                        [ Local NS: pc50 ]
                        [ Non-authoritative host ]
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

Each authoritative zone must contain SOA and NS records; each delegation must contain NS records and any necessary glue records.
