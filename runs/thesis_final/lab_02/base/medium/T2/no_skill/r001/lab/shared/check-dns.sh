#!/bin/sh
set -eu
resolver=10.15.8.14
fail=0
check() {
  name=$1; expected=$2; type=${3:-A}
  actual=$(dig +time=3 +tries=2 +short @"$resolver" "$name" "$type" | sort)
  if [ "$actual" != "$expected" ]; then
    echo "FAIL $name $type: expected $expected, got $actual"; fail=1
  else
    echo "OK $name $type: $actual"
  fi
}
check com 10.15.1.12
check net 10.15.1.13
check edu 10.15.1.14
check it 10.15.2.11
check example.com 10.15.2.12
check company.com 10.15.2.13
check service.com 10.15.2.14
check lab.net 10.15.3.11
check tools.net 10.15.3.12
check university.edu 10.15.3.13
check campus.edu 10.15.3.14
check unibo.it 10.15.4.11
check comune.it 10.15.4.12
check regione.it 10.15.4.13
check shop.example.com 10.15.4.14
check blog.example.com 10.15.5.11
check dept.company.com 10.15.5.12
check intranet.company.com 10.15.5.13
check api.service.com 10.15.5.14
check research.lab.net 10.15.6.11
check ai.research.lab.net 10.15.6.12
check data.research.lab.net 10.15.6.13
check dev.lab.net 10.15.6.14
check ci.tools.net 10.15.7.11
check vpn.university.edu 10.15.7.12
check courses.university.edu 10.15.7.13
check portal.campus.edu 10.15.7.14
check studenti.unibo.it 10.15.8.11
check servizi.comune.it 10.15.8.12
check dati.regione.it 10.15.8.13
check www.example.com 10.15.2.12
check mail.company.com 10.15.2.13
check mail.university.edu 10.15.3.13
check company.com '10 mail.company.com.' MX
check university.edu '10 mail.university.edu.' MX
exit "$fail"
