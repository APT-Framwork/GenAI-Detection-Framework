import type { Alert } from "@/types"

type SocketCallback = (alert: Alert) => void

class MockSocketManager {
  private listeners: SocketCallback[] = []
  private interval: ReturnType<typeof setInterval> | null = null

  connect() {
    if (this.interval) return

    // Simulate periodic new alerts
    this.interval = setInterval(() => {
      const mockAlerts: Partial<Alert>[] = [
        {
          title: "Suspicious DNS Query Pattern",
          description: "Entropy analysis flagged unusual DNS query distribution from subnet 10.0.3.x",
          severity: "medium",
          category: "SYSTEM WARNING",
          source: "DNS Monitor",
        },
        {
          title: "Port Scan Detected",
          description: "Sequential port scanning activity from external IP 203.45.67.89",
          severity: "high",
          category: "CRITICAL THREAT",
          source: "Perimeter Firewall",
        },
        {
          title: "Certificate Expiry Warning",
          description: "TLS certificate for api.strix.internal expires in 72 hours",
          severity: "low",
          category: "SYSTEM WARNING",
          source: "Certificate Manager",
        },
      ]

      const randomAlert = mockAlerts[Math.floor(Math.random() * mockAlerts.length)]
      const alert: Alert = {
        id: `alert-ws-${Date.now()}`,
        title: randomAlert.title!,
        description: randomAlert.description!,
        severity: randomAlert.severity!,
        status: "active",
        timestamp: new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }) + " — UTC",
        source: randomAlert.source!,
        category: randomAlert.category!,
      }

      this.listeners.forEach((cb) => cb(alert))
    }, 15000) // Every 15 seconds
  }

  disconnect() {
    if (this.interval) {
      clearInterval(this.interval)
      this.interval = null
    }
  }

  onAlert(callback: SocketCallback) {
    this.listeners.push(callback)
    return () => {
      this.listeners = this.listeners.filter((cb) => cb !== callback)
    }
  }
}

export const socketManager = new MockSocketManager()
