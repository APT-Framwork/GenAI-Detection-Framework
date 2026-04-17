export type Severity = "critical" | "high" | "medium" | "low" | "info"

export type AlertStatus = "active" | "acknowledged" | "resolved"

export interface Alert {
  id: string
  title: string
  description: string
  severity: Severity
  status: AlertStatus
  timestamp: string
  source: string
  category: string
  ip?: string
}

export interface KPIMetric {
  label: string
  value: string | number
  unit?: string
  change?: number
  icon?: string
}

export interface TimelineEvent {
  id: string
  timestamp: string
  type: string
  description: string
  severity: Severity
}

export interface KillChainStage {
  id: string
  name: string
  status: "completed" | "detected" | "active" | "pending"
  timestamp?: string
  description?: string
}

export interface TopologyNode {
  id: string
  label: string
  type: "server" | "endpoint" | "firewall" | "database" | "attacker"
  status: "healthy" | "compromised" | "warning" | "offline"
  ip?: string
  x?: number
  y?: number
}

export interface TopologyEdge {
  id: string
  source: string
  target: string
  label?: string
  type?: "normal" | "malicious" | "encrypted"
}

export interface Prediction {
  id: string
  alertId: string
  aptFamily: string
  confidence: number
  analysis: string
  nextStep?: string
}

export interface ThreatIntelEntry {
  indicator: string
  source: string
  reputation: "malicious" | "suspicious" | "clean" | "unknown"
  timestamp: string
  type: "ip" | "domain" | "hash" | "email"
}

export interface ModelMetrics {
  accuracy: number
  f1Score: number
  throughput: string
  latency: string
  health: "optimal" | "degraded" | "critical"
}

export interface Notification {
  id: string
  title: string
  description: string
  severity: Severity
  category: "critical_threat" | "system_warning" | "intel_update" | "process"
  timestamp: string
  read: boolean
}

export interface UserProfile {
  id: string
  name: string
  designation: string
  role: string
  site: string
  level: number
  tags: string[]
  efficiency: number
  accuracy: number
  responseTime: string
  avatar?: string
}

export interface LogEntry {
  timestamp: string
  level: "AUTH" | "WARN" | "ERROR" | "INFO" | "ALERT" | "BLOCK" | "STRIX_AI" | "NOTICE" | "PROCESS"
  message: string
}

export interface NavItem {
  label: string
  href: string
  icon: string
  badge?: number
}
