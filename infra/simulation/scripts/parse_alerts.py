import sys, json
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
buckets, samples = {}, {}
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        a = json.loads(line)
    except Exception:
        continue
    rule = a.get('rule', {})
    rid = rule.get('id','')
    mitre = rule.get('mitre', {}).get('id', [])
    mitre_s = ','.join(mitre) if isinstance(mitre, list) else str(mitre)
    desc = rule.get('description','')
    agent = a.get('agent', {}).get('name','')
    cmd = a.get('data',{}).get('audit',{}).get('command') or \
          a.get('data',{}).get('command','') or ''
    key = (rid, agent, mitre_s)
    buckets[key] = buckets.get(key, 0) + 1
    samples.setdefault(key, (desc[:55], str(cmd)[:40]))
print(f"{'cnt':>4}  {'rule':>6}  {'agent':9s}  {'mitre':18s}  {'desc':55s}  example_cmd")
for k, n in sorted(buckets.items(), key=lambda kv: -kv[1])[:20]:
    rid, agent, mitre_s = k
    desc, cmd = samples[k]
    print(f"{n:>4}  {rid:>6}  {agent:9s}  {mitre_s:18s}  {desc:55s}  {cmd}")
