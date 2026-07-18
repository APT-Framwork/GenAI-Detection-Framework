# Hunt queries — jury_demo.sh --non-monotonic

## 1 — Reconnaissance
```
technique:T1595
```
```
invalid user
```

## 3 — Defense Evasion
```
technique:T1027
```

## 4 — Privilege Escalation
```
technique:T1548
```
```
sudo
```

## 5–7 — Persistence / C2 / Impact
```
technique:T1071
```
```
technique:T1049
```
```
technique:T1059
```

## Pivots
```
technique:T1057 host:001
```
```
technique:T1595 host:002
```
```
technique:T1071 time:30m
```

## Whole chain per host
```
host:001
```
```
host:002
```
