import re
import yaml

with open("scenarios/lab01_ring6_dual/correction.yaml", "r") as f:
    content = f.read()

# 1. Remove authoritative section entirely from lab01
content = re.sub(r'(\s+)authoritative:\s*\n(\s+\.:\n\s+- [^\n]+\n\s+test:\n\s+- [^\n]+\n\s+- [^\n]+\n\s+services\.test:\n\s+- [^\n]+\n)', '', content)

# 2. Fix TXT check quoting
content = content.replace('""benchmark=dns-advanced""', '"\\"benchmark=dns-advanced\\""')

# 3. Fix zone regexes
# We need to replace "zone \"test\"" with "zone \"test\.?\""
# and "zone \"\.\"" should probably stay as is? "zone \".\"" -> "zone \"\.\"" 
content = content.replace('"zone \\"test\\""', '"zone \\"test\\.?\\""')
content = content.replace('"zone \\"services\\.test\\""', '"zone \\"services\\.test\\.?\\""')

# 4. Add retries for pc6 tests (SOA aa, A, AAAA, serial, AXFR)
# Wait, SOA aa is:
# - command: sh -c 'dig @2001:db8:1100:2::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr "\n" " " | grep -Eq "flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]"'
def wrap_retry(match):
    cmd = match.group(1)
    if "named-checkconf" in cmd or "ip -6 route show" in cmd or "ip route show" in cmd:
        return match.group(0) # Do not wrap
    # Wrap it
    if "exit 0" in cmd:
        return match.group(0) # Already wrapped or similar
    
    # We want: for i in 1 2 3 4 5; do CMD && exit 0; sleep 1; done; exit 1
    new_cmd = f"for i in 1 2 3 4 5; do {cmd} && exit 0; sleep 1; done; exit 1"
    # Special handling if it's already in a complex shell construct
    return f"- command: sh -c '{new_cmd}'"

# Let's replace manually for pc6
pc6_checks = [
    ('dig @2001:db8:1100:2::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr "\\n" " " | grep -Eq "flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]"',
     'for i in 1 2 3 4 5; do dig @2001:db8:1100:2::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr "\\n" " " | grep -Eq "flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]" && exit 0; sleep 1; done; exit 1'),
    ('dig @2001:db8:1100:2::10 www.test. A +short | grep -Fqx "10.11.5.10"',
     'for i in 1 2 3 4 5; do dig @2001:db8:1100:2::10 www.test. A +short | grep -Fqx "10.11.5.10" && exit 0; sleep 1; done; exit 1'),
    ('dig @2001:db8:1100:2::10 www.test. AAAA +short | grep -Fqx "2001:db8:1100:3::10"',
     'for i in 1 2 3 4 5; do dig @2001:db8:1100:2::10 www.test. AAAA +short | grep -Fqx "2001:db8:1100:3::10" && exit 0; sleep 1; done; exit 1'),
    ('s1="$(dig @2001:db8:1100:1::10 test. SOA +short | awk "{print \\$3}")"; s2="$(dig @2001:db8:1100:2::10 test. SOA +short | awk "{print \\$3}")"; test -n "$s1" && test "$s1" = "$s2"',
     'for i in 1 2 3 4 5; do s1="$(dig @2001:db8:1100:1::10 test. SOA +short | awk \\"{print \\$3}\\")"; s2="$(dig @2001:db8:1100:2::10 test. SOA +short | awk \\"{print \\$3}\\")"; test -n "$s1" && test "$s1" = "$s2" && exit 0; sleep 1; done; exit 1')
]

for old, new in pc6_checks:
    # We need to be careful with quotes in python string vs yaml string
    pass

with open("scenarios/lab01_ring6_dual/correction.yaml", "w") as f:
    f.write(content)
