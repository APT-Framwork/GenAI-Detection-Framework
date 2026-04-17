import { useEffect, useRef } from "react";
import { useAlertsStore } from "../stores/alerts-store";
import type { Alert, Severity } from "../lib/mock-data";

const ALERT_TEMPLATES: Omit<Alert, "id" | "timestamp" | "timeAgo">[] = [
  {
    severity: "critical",
    title: "Suspicious Process Spawned",
    description: "Unknown child process from svchost.exe on endpoint WS-312.",
    mitreTechnique: "T1055",
    mitreLabel: "Process Injection",
    acknowledged: false,
  },
  {
    severity: "warning",
    title: "Anomalous DNS Query",
    description: "High-entropy domain resolution detected from VLAN-08 segment.",
    mitreTechnique: "T1071",
    mitreLabel: "Application Layer Protocol",
    acknowledged: false,
  },
  {
    severity: "critical",
    title: "Port Scan Detected",
    description: "Sequential port scanning from 10.0.0.55 targeting DMZ subnet.",
    mitreTechnique: "T1046",
    mitreLabel: "Network Service Discovery",
    acknowledged: false,
  },
  {
    severity: "info",
    title: "Signature DB Synced",
    description: "Latest CVE signatures synchronized across all sensor nodes.",
    acknowledged: false,
  },
  {
    severity: "warning",
    title: "Failed Auth Spike",
    description: "12 failed authentications in 30s on VPN gateway from geo: RU.",
    mitreTechnique: "T1110",
    mitreLabel: "Brute Force",
    acknowledged: false,
  },
];

export function useSocket() {
  const addAlert = useAlertsStore((s) => s.addAlert);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      const template =
        ALERT_TEMPLATES[Math.floor(Math.random() * ALERT_TEMPLATES.length)];
      const now = new Date();
      const newAlert: Alert = {
        ...template,
        id: `live-${Date.now()}`,
        timestamp: now.toISOString().slice(11, 19) + " UTC",
        timeAgo: "just now",
      };
      addAlert(newAlert);
    }, 30000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [addAlert]);
}
