# 🎓 STRIX — Jury Demo Cheat Sheet

> Copy-paste these blocks directly during the defense.
> Run everything from the repo root: `cd ~/Desktop/GenAI-Detection-Framework`
> Dashboard opens at **http://localhost:5600** · API at **http://localhost:8000**

---

## 0. Before the jury walks in (5 min warm-up)

```bash
cd ~/Desktop/GenAI-Detection-Framework
```

Optional sanity check that Docker + tooling are alive:

```bash
docker compose version && command -v honcho && echo "prereqs OK"
```

---

## 1. ⭐ THE MAIN DEMO — non-monotonic kill-chain

This is the headline run. The `--non-monotonic` mode drives a curated
forward/backward kill-chain (Discovery → Defense Evasion → PrivEsc →
Persistence → … → Impact) engineered to trip the DQN's ESCALATE
threshold so the **RL Intervention Timeline** lights up live.

> It brings the whole stack up, waits for the dashboard, then pauses
> with a prompt. **Open http://localhost:5600 first, confirm the LIVE
> pill is green, then press ENTER.**

```bash
bash jury_demo.sh --non-monotonic
```

That's the one command for the full proof. `--non-monotonic` ignores
`--apt` (mutually exclusive).

### Variants (if the jury asks for something specific)

```bash
# Longer run (more stages visible on the timeline)
bash jury_demo.sh --non-monotonic --duration 240s

# Background benign traffic per victim. Default is 300/min (≈600/min across
# the 2 victims) so benign dominates the topology ≈3×+ over the attack volume.
# Turn it down for a calmer screen, or up to flood the feed harder.
bash jury_demo.sh --non-monotonic --benign-rate 100/min   # calmer
bash jury_demo.sh --non-monotonic --benign-rate 600/min   # heavier noise
```

---

## 2. What to point at on the dashboard (http://localhost:5600)

- **Topology** — attacker → 2 victims, red pulses on each tactic
- **APT / RL Kill-Chain** — rows progressing 1 → … → 7, DQN intervenes mid-chain
- **RL Intervention Timeline** — ESCALATE / ISOLATE_HOST cards land here (the "pre-detection")
- **Detection Quality** — TP / FP / TN / FN populating once labels resolve
- **Forensic Logs** — real Wazuh / auditd lines flowing

---

## 3. 📱 Run the mobile app

The phone must reach the API over Wi-Fi, so it needs the laptop's **LAN
IP**, not `localhost`. Laptop and phone must be on the **same Wi-Fi**.

```bash
cd ~/Desktop/GenAI-Detection-Framework/apps/mobile

# Auto-detect this laptop's LAN IP (current value: 10.0.33.171)
export LAN_IP=$(hostname -I | awk '{print $1}')
echo "Phone will hit → http://$LAN_IP:8000"

# Critical: set the API URL BEFORE bundling, then start Metro
export EXPO_PUBLIC_API_URL=http://$LAN_IP:8000
npx expo start --clear
```

Then on the phone:
- **Android** → Expo Go → "Scan QR Code" → scan the terminal QR
- **iOS** → system **Camera** app → scan QR → tap the Expo Go banner

### Mobile fallbacks (only if scanning fails)

```bash
# Wi-Fi blocks device-to-device? Route over Expo's relay instead:
EXPO_PUBLIC_API_URL=http://$LAN_IP:8000 npx expo start --tunnel --clear

# Using the EAS dev build (real push notifications) instead of Expo Go:
EXPO_PUBLIC_API_URL=http://$LAN_IP:8000 npx expo start --dev-client --clear

# Firewall blocking the phone? (run once, then re-scan)
sudo ufw allow 8000/tcp
```

Verify the API is reachable from the LAN before blaming the app:

```bash
curl http://$LAN_IP:8000/health      # → {"status":"ok"}
```

---

## 4. Handy backup commands

```bash
# Bring the stack UP but DON'T run the sim (drive it manually after)
bash jury_demo.sh --non-monotonic --skip-sim

# …then trigger the kill-chain by hand whenever you're ready (keep
# --benign-rate or the topology shows BENIGN 0):
bash infra/scripts/lab_simulate.sh --non-monotonic --benign-rate 300/min --duration 180s

# Classic APT chain instead of non-monotonic (e.g. if asked)
bash jury_demo.sh --apt APT29
bash jury_demo.sh --apt APT41 --duration 240

# Watch the host-stack logs in a second terminal
tail -f /tmp/strix_honcho.log

# Full help text
bash jury_demo.sh --help
```

---

## 5. Tear down (after the demo)

```bash
bash jury_demo.sh stop
```

> Volumes are preserved, so Postgres keeps its data for next time.

---

## 6. Quick troubleshooting

| Symptom | Fix |
|---|---|
| `pnpm: command not found` / `web.1 rc=127` | `sudo rm -f /usr/bin/pnpm /usr/bin/pnpx && sudo npm install -g pnpm` |
| API `/health` never responds | `tail -f /tmp/strix_honcho.log` (missing env var, port 8000 busy, or alembic fail) |
| RL Timeline shows "0 PREDETECTED" | `bash jury_demo.sh stop && bash jury_demo.sh --non-monotonic` |
| Phone can't reach API | confirm `curl http://$LAN_IP:8000/health` works; open firewall; use `--tunnel` |
| App still hits localhost | you set `EXPO_PUBLIC_API_URL` *after* Metro started — kill it, re-export, `npx expo start --clear` |
