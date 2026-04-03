// ─── Types ───────────────────────────────────────────────
export type Severity = "critical" | "warning" | "info" | "update";

export interface Alert {
  id: string;
  severity: Severity;
  title: string;
  description: string;
  timestamp: string;
  timeAgo: string;
  mitreTechnique?: string;
  mitreLabel?: string;
  source?: string;
  acknowledged: boolean;
}

export interface KPIMetric {
  id: string;
  label: string;
  value: string;
  unit?: string;
  trend?: "up" | "down" | "stable";
  trendValue?: string;
  color?: string;
}

export interface User {
  id: string;
  name: string;
  designation: string;
  role: string;
  site: string;
  level: number;
  avatar?: string;
  efficiency: number;
  accuracy: number;
  responseTime: string;
}

export interface Service {
  id: string;
  name: string;
  status: "operational" | "degraded" | "down" | "maintenance";
  uptime: string;
  latency: string;
  lastCheck: string;
}

export interface ChartPoint {
  day: number;
  value: number;
  label?: string;
}

export interface Prediction {
  id: string;
  title: string;
  severity: Severity;
  confidence: string;
  description: string;
  icon: string;
}

export interface IntelFeedItem {
  id: string;
  time: string;
  source: string;
  message: string;
  highlighted?: boolean;
}

// ─── Mock Alerts ─────────────────────────────────────────
export const mockAlerts: Alert[] = [
  {
    id: "a1",
    severity: "critical",
    title: "Unauthorized Privilege Escalation",
    description:
      "System detected an attempt to elevate user permissions on DB-CORE-04. Source IP: 192.168.1.104",
    timestamp: "02:45:12 UTC",
    timeAgo: "2m ago",
    mitreTechnique: "T1068",
    mitreLabel: "Exploitation",
    source: "internal-node-402",
    acknowledged: false,
  },
  {
    id: "a2",
    severity: "warning",
    title: "Unusual Traffic Volume",
    description:
      "Outbound traffic to external node cloud-edge-va exceeds baseline by 240%.",
    timestamp: "03:12:05 UTC",
    timeAgo: "15m ago",
    mitreTechnique: "T1041",
    mitreLabel: "Exfiltration",
    source: "Engineering Workstation B",
    acknowledged: false,
  },
  {
    id: "a3",
    severity: "update",
    title: "Sentinel Engine 4.2.0",
    description:
      "New heuristic modules are available for deployment. This update requires a 45-second core restart.",
    timestamp: "05:22:48 UTC",
    timeAgo: "1h ago",
    acknowledged: false,
  },
  {
    id: "a4",
    severity: "critical",
    title: "Brute Force Attack Detected",
    description:
      "Multiple failed login attempts detected on SSH root access from unknown IP: 192.168.1.105.",
    timestamp: "06:01:33 UTC",
    timeAgo: "2h ago",
    mitreTechnique: "T1110",
    mitreLabel: "Brute Force",
    source: "SSH Gateway",
    acknowledged: false,
  },
  {
    id: "a5",
    severity: "warning",
    title: "DNS Tunneling Suspected",
    description:
      "Anomalous DNS query patterns detected from VLAN-12, potentially indicative of data exfiltration via DNS.",
    timestamp: "07:15:22 UTC",
    timeAgo: "3h ago",
    mitreTechnique: "T1071",
    mitreLabel: "Application Layer Protocol",
    acknowledged: false,
  },
  {
    id: "a6",
    severity: "critical",
    title: "Ransomware Signature Matched",
    description:
      "File encryption patterns matching BlackCat variant detected on fileserver-03. Containment initiated.",
    timestamp: "08:30:00 UTC",
    timeAgo: "4h ago",
    mitreTechnique: "T1486",
    mitreLabel: "Data Encrypted for Impact",
    acknowledged: true,
  },
  {
    id: "a7",
    severity: "info",
    title: "Threat Database V.24.0.8",
    description:
      "The STRIX AI has ingested 4,200+ new signatures related to recent zero-day exploits in containerized environments.",
    timestamp: "09:00:00 UTC",
    timeAgo: "5h ago",
    acknowledged: true,
  },
  {
    id: "a8",
    severity: "warning",
    title: "Suspicious PowerShell Execution",
    description:
      "Encoded PowerShell command executed on endpoint WS-204 with network callback to external C2.",
    timestamp: "09:45:10 UTC",
    timeAgo: "6h ago",
    mitreTechnique: "T1059",
    mitreLabel: "Command and Scripting",
    acknowledged: false,
  },
  {
    id: "a9",
    severity: "critical",
    title: "Zero-Day Exploit Attempt",
    description:
      "CVE-2024-XXXX exploit attempt detected against Apache Struts on web-proxy-01.",
    timestamp: "10:12:45 UTC",
    timeAgo: "7h ago",
    mitreTechnique: "T1190",
    mitreLabel: "Exploit Public-Facing App",
    acknowledged: false,
  },
  {
    id: "a10",
    severity: "info",
    title: "Firewall Rules Updated",
    description:
      "Automated rule deployment completed. 24 new deny rules applied across perimeter firewalls.",
    timestamp: "11:00:00 UTC",
    timeAgo: "8h ago",
    acknowledged: true,
  },
  {
    id: "a11",
    severity: "warning",
    title: "Lateral Movement Detected",
    description:
      "PsExec-style remote execution detected from WS-108 to DC-MAIN. Non-standard service account used.",
    timestamp: "11:30:22 UTC",
    timeAgo: "9h ago",
    mitreTechnique: "T1021",
    mitreLabel: "Remote Services",
    acknowledged: false,
  },
  {
    id: "a12",
    severity: "update",
    title: "ML Model Retrained",
    description:
      "Anomaly detection model v3.8 has completed retraining with 2.1M new samples. F1 score: 0.967.",
    timestamp: "12:00:00 UTC",
    timeAgo: "10h ago",
    acknowledged: true,
  },
  {
    id: "a13",
    severity: "critical",
    title: "Credential Dump Detected",
    description:
      "LSASS memory dump detected on domain controller DC-02. Immediate containment required.",
    timestamp: "12:45:00 UTC",
    timeAgo: "11h ago",
    mitreTechnique: "T1003",
    mitreLabel: "OS Credential Dumping",
    acknowledged: false,
  },
  {
    id: "a14",
    severity: "info",
    title: "Scheduled Maintenance Window",
    description:
      "Planned maintenance for ES cluster nodes 4-7 begins at 03:00 UTC. Expected downtime: 15 minutes.",
    timestamp: "13:00:00 UTC",
    timeAgo: "12h ago",
    acknowledged: true,
  },
  {
    id: "a15",
    severity: "warning",
    title: "Certificate Expiry Warning",
    description:
      "TLS certificate for api-gateway.strix.io expires in 7 days. Auto-renewal scheduled.",
    timestamp: "14:00:00 UTC",
    timeAgo: "13h ago",
    acknowledged: false,
  },
];

// ─── Mock KPI Metrics ────────────────────────────────────
export const mockMetrics: KPIMetric[] = [
  { id: "m1", label: "Threat Level", value: "74", unit: "%", color: "#00666d" },
  { id: "m2", label: "Daily Scans", value: "1.2k", trend: "up", trendValue: "+12%" },
  { id: "m3", label: "Anomalies", value: "12", color: "#b31b25", trend: "up", trendValue: "+3" },
  { id: "m4", label: "Uptime Vigil", value: "99.8", unit: "%", trend: "stable" },
  { id: "m5", label: "Threat Latency", value: "12", unit: "ms", trend: "down", trendValue: "-2ms" },
  { id: "m6", label: "Active Nodes", value: "847", trend: "stable" },
];

// ─── Mock User ───────────────────────────────────────────
export const mockUser: User = {
  id: "u1",
  name: "Yacine Naoui",
  designation: "SENTINEL_CORE_01",
  role: "Security Analyst",
  site: "HQ-ALPHA",
  level: 4,
  efficiency: 94.2,
  accuracy: 98.7,
  responseTime: "1.2s",
};

// ─── Mock System Status ──────────────────────────────────
export const mockSystemStatus: Service[] = [
  { id: "s1", name: "AI Inference Engine", status: "operational", uptime: "99.99%", latency: "8ms", lastCheck: "2s ago" },
  { id: "s2", name: "Elasticsearch Cluster", status: "operational", uptime: "99.95%", latency: "12ms", lastCheck: "5s ago" },
  { id: "s3", name: "WebSocket Gateway", status: "operational", uptime: "99.98%", latency: "3ms", lastCheck: "1s ago" },
  { id: "s4", name: "PostgreSQL Primary", status: "operational", uptime: "99.99%", latency: "5ms", lastCheck: "3s ago" },
  { id: "s5", name: "Redis Cache", status: "operational", uptime: "100%", latency: "1ms", lastCheck: "1s ago" },
  { id: "s6", name: "Threat Intel Feed", status: "degraded", uptime: "98.2%", latency: "450ms", lastCheck: "10s ago" },
  { id: "s7", name: "MITRE ATT&CK Sync", status: "operational", uptime: "99.9%", latency: "200ms", lastCheck: "30s ago" },
  { id: "s8", name: "Notification Service", status: "operational", uptime: "99.97%", latency: "15ms", lastCheck: "2s ago" },
  { id: "s9", name: "Celery Worker Pool", status: "maintenance", uptime: "95.0%", latency: "N/A", lastCheck: "1m ago" },
  { id: "s10", name: "Log Aggregator", status: "operational", uptime: "99.8%", latency: "25ms", lastCheck: "4s ago" },
];

// ─── Mock Chart Data (30 days) ───────────────────────────
export const mockChartData: ChartPoint[] = Array.from({ length: 30 }, (_, i) => ({
  day: i + 1,
  value: Math.round(40 + Math.random() * 50 + Math.sin(i / 3) * 15),
  label: `Day ${i + 1}`,
}));

// ─── Mock Predictions ────────────────────────────────────
export const mockPredictions: Prediction[] = [
  {
    id: "p1",
    title: "SQL Injection",
    severity: "critical",
    confidence: "92%",
    description: "Pattern matched in V4 clusters.",
    icon: "alert-triangle",
  },
  {
    id: "p2",
    title: "Credential Spraying",
    severity: "warning",
    confidence: "78%",
    description: "Anomalous login attempts from 4 regions.",
    icon: "key",
  },
  {
    id: "p3",
    title: "Network Topology Drift",
    severity: "info",
    confidence: "65%",
    description: "Detected structural change in sub-net 12.",
    icon: "git-branch",
  },
];

// ─── Mock Intelligence Feed ──────────────────────────────
export const mockIntelFeed: IntelFeedItem[] = [
  {
    id: "f1",
    time: "14:02",
    source: "SYSTEM",
    message: "Automated firewall patch deployed successfully to 18 nodes.",
    highlighted: true,
  },
  {
    id: "f2",
    time: "13:45",
    source: "AI-CORE",
    message: "Heuristic baseline updated for Weekend Traffic patterns.",
  },
  {
    id: "f3",
    time: "13:20",
    source: "SENTINEL",
    message: "New threat vector catalogued: supply-chain package injection via npm.",
  },
  {
    id: "f4",
    time: "12:58",
    source: "SYSTEM",
    message: "Geo-IP database refreshed. 14,000 new ranges classified.",
  },
];
