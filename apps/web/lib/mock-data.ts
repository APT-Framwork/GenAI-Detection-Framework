import type {
  Alert,
  Notification,
  KPIMetric,
  KillChainStage,
  TimelineEvent,
  TopologyNode,
  TopologyEdge,
  ThreatIntelEntry,
  Prediction,
  ModelMetrics,
  LogEntry,
} from "@/types"

// ── Dashboard KPIs ──────────────────────────────────────────
export const dashboardKPIs: KPIMetric[] = [
  { label: "Alerts Active", value: "1,402", change: 12.4 },
  { label: "Uptime", value: "99.2%", unit: "SLA" },
  { label: "Interfaces Linked", value: "482" },
  { label: "AI Response", value: "22s" },
]

// ── Alerts ──────────────────────────────────────────────────
export const mockAlerts: Alert[] = [
  {
    id: "alert-001",
    title: "Unauthorized Data Exfiltration Attempt",
    description:
      "Sentinel Node 04 flagged a high-volume outbound transfer to an unrecognized IP range: 194.21.92.112. Potential PII exposure detected.",
    severity: "critical",
    status: "active",
    timestamp: "02:14 AM — UTC",
    source: "Sentinel Node 04",
    category: "CRITICAL THREAT ATTACK",
    ip: "194.21.92.112",
  },
  {
    id: "alert-002",
    title: "Anomalous API Latency Spike",
    description:
      "Core Gateway v2 experienced a 450ms increase in response time. Resource saturation suspected in the US-EAST cluster. Scaling protocols initiated.",
    severity: "medium",
    status: "active",
    timestamp: "01:43 AM — UTC",
    source: "Core Gateway v2",
    category: "SYSTEM WARNING",
  },
  {
    id: "alert-003",
    title: "New CVE Definition: OpenSSL 3.1.2",
    description:
      "Threat Database updated with new descriptors for CVE-2023-XXXX. Automated patching scheduled for 04:00 AM during low-traffic window.",
    severity: "info",
    status: "active",
    timestamp: "Yesterday — 11:30 PM",
    source: "Threat Database",
    category: "INTEL UPDATE",
  },
  {
    id: "alert-004",
    title: "Weekly Database Rotation Success",
    description:
      "Archived 4.2TB of redundant logs from Q3. All parity checks passed.",
    severity: "low",
    status: "acknowledged",
    timestamp: "Yesterday — 09:12 PM",
    source: "System",
    category: "PROCESS",
  },
  {
    id: "alert-005",
    title: "Unauthorized Access: Surgical Robot Alpha-4",
    description:
      "External IP (192.168.4.112) attempted root bypass on life-critical hardware. Automatic quarantine protocol ARQS-9 initiated successfully.",
    severity: "critical",
    status: "active",
    timestamp: "3m AGO",
    source: "Surgical Robot Alpha-4",
    category: "CRITICAL TARGET ATTACK",
  },
  {
    id: "alert-006",
    title: "Data Exfiltration Warning: Patient Records",
    description:
      "High-volume data transfer detected from node DB-SENTINEL-02 to unverified encrypted relay. Transfer size: 4.2GB. Pending verification.",
    severity: "high",
    status: "active",
    timestamp: "5m AGO",
    source: "DB-SENTINEL-02",
    category: "KNOWLEDGE ENRICHMENT",
  },
  {
    id: "alert-007",
    title: "External Brute-Force Violation",
    description:
      "Attempted unauthorized access from IP 192.168.3.104. Firewall threshold exceeded. Neural sentinel has locked target origin.",
    severity: "critical",
    status: "active",
    timestamp: "3m AGO",
    source: "Firewall",
    category: "CRITICAL THREAT",
  },
  {
    id: "alert-008",
    title: "Kernel Integrity Breach",
    description:
      "Unauthorized modifications detected in /sys/kernel/debug. System state is currently unstable. AI remediation requested.",
    severity: "critical",
    status: "active",
    timestamp: "10m AGO",
    source: "Kernel Monitor",
    category: "CRITICAL THREAT",
  },
]

// ── Notifications ───────────────────────────────────────────
export const mockNotifications: Notification[] = [
  {
    id: "notif-001",
    title: "External Brute-Force Violation",
    description:
      "Attempted unauthorized access from IP 192.168.3.104. Firewall threshold exceeded.",
    severity: "critical",
    category: "critical_threat",
    timestamp: "3m ago",
    read: false,
  },
  {
    id: "notif-002",
    title: "Kernel Integrity Breach",
    description:
      "Unauthorized modifications detected in /sys/kernel/debug. System state unstable.",
    severity: "critical",
    category: "critical_threat",
    timestamp: "10m ago",
    read: false,
  },
  {
    id: "notif-003",
    title: "API Latency Spike",
    description:
      "Region US-EAST-1 experiencing 450ms latency. Auto-scaling initiated.",
    severity: "medium",
    category: "system_warning",
    timestamp: "1h ago",
    read: false,
  },
  {
    id: "notif-004",
    title: "Neural Engine V4.2.0",
    description: "Enhanced decryption speeds by 14%.",
    severity: "info",
    category: "intel_update",
    timestamp: "2h ago",
    read: true,
  },
  {
    id: "notif-005",
    title: "Weekly Audit Finished",
    description: "0 non-compliance points detected.",
    severity: "low",
    category: "intel_update",
    timestamp: "3h ago",
    read: true,
  },
]

// ── Kill Chain Stages ───────────────────────────────────────
export const killChainStages: KillChainStage[] = [
  { id: "kc-1", name: "RECON", status: "completed", timestamp: "08:14", description: "External scanning from 185.22.x.x detected via NGINX logs." },
  { id: "kc-2", name: "WEAPONIZE", status: "completed", timestamp: "08:21" },
  { id: "kc-3", name: "DELIVERY", status: "completed", timestamp: "08:34", description: "Phishing payload executed on WS-Fin-09. Local admin compromised." },
  { id: "kc-4", name: "EXPLOIT", status: "detected", timestamp: "08:41" },
  { id: "kc-5", name: "INSTALLATION", status: "active", timestamp: "08:52" },
  { id: "kc-6", name: "C2 CONTROL", status: "pending" },
  { id: "kc-7", name: "EXFILTRATION", status: "pending" },
]

// ── Timeline Events ─────────────────────────────────────────
export const timelineEvents: TimelineEvent[] = [
  { id: "ev-1", timestamp: "08:14:22", type: "RECON", description: "External scanning from 185.22.x.x detected", severity: "medium" },
  { id: "ev-2", timestamp: "08:21:45", type: "WEAPONIZE", description: "Payload signature matched APT-29 pattern", severity: "high" },
  { id: "ev-3", timestamp: "08:34:11", type: "DELIVERY", description: "Phishing email delivered to WS-Fin-09", severity: "high" },
  { id: "ev-4", timestamp: "08:41:33", type: "EXPLOIT", description: "Local admin privileges escalated", severity: "critical" },
  { id: "ev-5", timestamp: "08:52:07", type: "INSTALLATION", description: "Registry key persistence mechanism detected", severity: "critical" },
]

// ── Topology Nodes & Edges ──────────────────────────────────
export const topologyNodes: TopologyNode[] = [
  { id: "node-1", label: "STRIX_CORE", type: "server", status: "healthy", ip: "10.0.1.1" },
  { id: "node-2", label: "WEB_GATEWAY", type: "firewall", status: "healthy", ip: "10.0.1.2" },
  { id: "node-3", label: "DB_CLUSTER", type: "database", status: "healthy", ip: "10.0.2.1" },
  { id: "node-4", label: "NODE_04_02_3BV", type: "endpoint", status: "warning", ip: "10.0.3.15" },
  { id: "node-5", label: "SENTINEL_01", type: "server", status: "healthy", ip: "10.0.1.5" },
  { id: "node-6", label: "EXT_ATTACKER", type: "attacker", status: "compromised", ip: "185.22.x.x" },
  { id: "node-7", label: "pClient_srv_01", type: "endpoint", status: "compromised", ip: "10.0.4.22" },
  { id: "node-8", label: "SQL-CLUSTER", type: "database", status: "healthy", ip: "10.0.2.5" },
]

export const topologyEdges: TopologyEdge[] = [
  { id: "edge-1", source: "node-1", target: "node-2", type: "normal" },
  { id: "edge-2", source: "node-2", target: "node-3", type: "normal" },
  { id: "edge-3", source: "node-1", target: "node-5", type: "normal" },
  { id: "edge-4", source: "node-6", target: "node-4", type: "malicious", label: "APT vector" },
  { id: "edge-5", source: "node-4", target: "node-7", type: "malicious", label: "Lateral movement" },
  { id: "edge-6", source: "node-7", target: "node-8", type: "malicious" },
  { id: "edge-7", source: "node-3", target: "node-8", type: "encrypted" },
]

// ── Threat Intelligence ─────────────────────────────────────
export const threatIntelEntries: ThreatIntelEntry[] = [
  { indicator: "kdoe@vanguard.io", source: "Breach Database G5T2", reputation: "malicious", timestamp: "2023.11.24 14:48", type: "email" },
  { indicator: "155.122.204.14", source: "Host: Moscow, RU", reputation: "malicious", timestamp: "2023.11.24 14:22", type: "ip" },
  { indicator: "secure-login.strix-app.net", source: "Phishing Candidate", reputation: "suspicious", timestamp: "2023.11.24 11:38", type: "domain" },
  { indicator: "SSH_RSA_0921X", source: "Leaked Key Fragment", reputation: "unknown", timestamp: "2023.11.24 09:14", type: "hash" },
]

// ── AI Predictions ──────────────────────────────────────────
export const mockPredictions: Prediction[] = [
  {
    id: "pred-001",
    alertId: "alert-001",
    aptFamily: "APT-39 (Static-Shadow)",
    confidence: 87,
    analysis:
      "Behavioral patterns (entropy of payload, T1059.003 usage) correlate with high relevance to APT-39 infrastructure.",
    nextStep: "Data Staging via SMB",
  },
  {
    id: "pred-002",
    alertId: "alert-005",
    aptFamily: "APT-42 (Lateral Pivot)",
    confidence: 88,
    analysis:
      "System predicts attacker will attempt to aggregate CSV files in the /data/export/Li_folder within the next 6 minutes.",
    nextStep: "Database Pivot",
  },
]

// ── Model Performance ───────────────────────────────────────
export const modelMetrics: ModelMetrics = {
  accuracy: 94.2,
  f1Score: 0.92,
  throughput: "1.4M / hr",
  latency: "14ms",
  health: "optimal",
}

export const modelConfidenceData = [
  { name: "D-1", classifier: 78, gnn: 65, vae: 70 },
  { name: "D-2", classifier: 82, gnn: 68, vae: 73 },
  { name: "D-3", classifier: 85, gnn: 72, vae: 75 },
  { name: "D-4", classifier: 88, gnn: 75, vae: 78 },
  { name: "D-5", classifier: 90, gnn: 78, vae: 80 },
  { name: "D-6", classifier: 91, gnn: 80, vae: 82 },
  { name: "D-7", classifier: 93, gnn: 82, vae: 84 },
  { name: "D-8", classifier: 94, gnn: 84, vae: 85 },
  { name: "D-9", classifier: 92, gnn: 83, vae: 83 },
  { name: "D-10", classifier: 94, gnn: 85, vae: 86 },
]

// ── Forensic Logs ───────────────────────────────────────────
export const forensicLogs: LogEntry[] = [
  { timestamp: "[14:22:01]", level: "AUTH", message: "Biometric validation confirmed at Terminal_Node_4." },
  { timestamp: "[14:35:12]", level: "AUTH", message: "Deep packet inspection initiated on inbound segment 0x5F" },
  { timestamp: "[15:01:44]", level: "INFO", message: "Kernel heartbeat stable. Sentinel_Core_01 active status updated." },
  { timestamp: "[15:12:09]", level: "ALERT", message: "Unauthorized script execution blocked on DB_Cluster_7." },
  { timestamp: "[15:45:30]", level: "PROCESS", message: "Metadata archive compressed and sent." },
  { timestamp: "[08:14:22]", level: "AUTH", message: "Factory: Sample credentials for user 'op' from 202.148.1.205" },
  { timestamp: "[08:21:15]", level: "WARN", message: "Factory: Sample credentials for user 'op' from 202.148.1.205" },
  { timestamp: "[08:34:33]", level: "NOTICE", message: "Successful login for user 'sa' from 192.168.1.143 via TLS protocol" },
  { timestamp: "[08:41:07]", level: "ERROR", message: "sp_addrolemember 'sysadmin12_ops' (SecurityBytes.bypass strateg3de.installer.StealthDaemon7.sh)" },
  { timestamp: "[08:44:19]", level: "INFO", message: "Software connection established to 160.22.33.21 (cmd: (11 minute duration))" },
  { timestamp: "[08:48:55]", level: "PROCESS", message: "Process started: csvtool.exe (PID: 24620) - Parent: utlite321" },
  { timestamp: "[09:01:33]", level: "STRIX_AI", message: "Pattern analysis RR_01 | T059-001 > Command and Scripting interpreter: Powershell." },
  { timestamp: "[09:14:22]", level: "STRIX_AI", message: "Unusual lateral movement pattern detected in Subnet Alpha. Reconstruction error above threshold 0.012G" },
  { timestamp: "[09:25:44]", level: "STRIX_AI", message: "Graph topology refreshed, 1,432 new edges processed. High-density cluster identified in Active Directory nodes." },
]

// ── Network vitals for topology ─────────────────────────────
export const networkVitals = {
  latency: "14.2s",
  bandwidth: "1.2 Gbps",
  activeConnections: 847,
  cpuUsage: 62,
  memUsage: 78,
  packetLoss: "0.02%",
}

// ── Status bar stats ────────────────────────────────────────
export const globalStats = {
  globalUptime: "99.998%",
  activeNodes: 1402,
  secScansMin: "42.4k",
}
