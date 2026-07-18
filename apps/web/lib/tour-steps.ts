// -----------------------------------------------------------------------------
// Guided-tour script — one entry per step, in presentation order.
//
// target   CSS selector of the element to spotlight (data-tour attributes are
//          sprinkled across the layout + pages). null = centered modal step.
// route    pathname the step lives on; the overlay navigates there first.
// placement  preferred tooltip side; the overlay flips automatically when the
//            preferred side doesn't fit.
// tip      optional "how to interact" line rendered under the body.
// -----------------------------------------------------------------------------

export type TourPlacement = "top" | "bottom" | "left" | "right" | "auto"

export interface TourStep {
  id: string
  section: string
  route: string
  target: string | null
  title: string
  body: string
  tip?: string
  placement?: TourPlacement
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    section: "Welcome",
    route: "/",
    target: null,
    title: "Welcome to CAVIX",
    body:
      "This is your SOC console for the STRIX detection engine: five deep-learning models and a reinforcement-learning agent watching the lab, reconstructing attack kill chains in real time and intervening before the damage stage. This tour walks through every major surface — it takes about three minutes.",
    tip: "Use the → and ← arrow keys to move, Esc to exit. Restart anytime from the ? icon in the top bar.",
  },
  {
    id: "sidebar",
    section: "Navigation",
    route: "/",
    target: '[data-tour="sidebar-nav"]',
    title: "Navigate the platform",
    body:
      "Everything lives one click away: the live Dashboard, the Cases triage queue, the Hunt query console, the two intelligence surfaces (CTI and Threat Intel), Model Monitoring for the AI engine, and the lab Simulation view. Settings and Support sit at the bottom.",
    tip: "The chevron on the rail's edge collapses it to icons when you need more room.",
    placement: "right",
  },
  {
    id: "topbar-status",
    section: "Navigation",
    route: "/",
    target: '[data-tour="topbar-status"]',
    title: "Live connection & threat level",
    body:
      "The LIVE pill shows the state of the real-time SSE stream and the time since the last event — if the stream drops, the console falls back to polling. Next to it, the global threat level summarises the most severe activity currently open.",
    placement: "bottom",
  },
  {
    id: "topbar-search",
    section: "Navigation",
    route: "/",
    target: '[data-tour="topbar-search"]',
    title: "Global search",
    body:
      "Jump to any page by name or keyword — try “drift”, “ioc” or “model”. Press Enter to open the first match.",
    placement: "bottom",
  },
  {
    id: "topbar-bell",
    section: "Navigation",
    route: "/",
    target: '[data-tour="topbar-bell"]',
    title: "Intervention notifications",
    body:
      "Every RL intervention lands here — ESCALATE as a warning, ISOLATE_HOST and BLOCK_USER_IP as critical. The badge shows the live count, and the same alerts are pushed to the CAVIX mobile app.",
    placement: "bottom",
  },
  {
    id: "topbar-theme",
    section: "Navigation",
    route: "/",
    target: '[data-tour="topbar-theme"]',
    title: "Light & dark themes",
    body:
      "Toggle between the light clinical theme and the dark ops-room theme. Your preference is remembered per browser.",
    placement: "bottom",
  },
  {
    id: "dash-banner",
    section: "Dashboard",
    route: "/",
    target: '[data-tour="dash-banner"]',
    title: "Live Sentinel — run banner",
    body:
      "The dashboard follows the latest simulation run: run ID, emulated APT group, attacker IP and start time. When the lab is idle it keeps showing the most recent completed run.",
    placement: "bottom",
  },
  {
    id: "dash-kpis",
    section: "Dashboard",
    route: "/",
    target: '[data-tour="dash-kpis"]',
    title: "Pipeline vitals",
    body:
      "Live status counts — critical, warnings, updates — plus ingest throughput, streamed over SSE straight from the inference pipeline.",
    placement: "bottom",
  },
  {
    id: "dash-apt-timeline",
    section: "Dashboard",
    route: "/",
    target: '[data-tour="dash-apt-timeline"]',
    title: "APT Attack Timeline",
    body:
      "The attacker's live progression — one row per active kill chain, paced per Cyber-Kill-Chain stage. Rows appear the moment a host emits a MITRE-tagged event; the panel idles while traffic is benign.",
    placement: "right",
  },
  {
    id: "dash-rl-timeline",
    section: "Dashboard",
    route: "/",
    target: '[data-tour="dash-rl-timeline"]',
    title: "STRIX Intervention Timeline",
    body:
      "The agent's verdict per chain, frozen at its final state. PREDETECTED means STRIX intervened before stage 7 (Actions on Objectives) — early detection is the platform's headline claim, and this panel is where it shows.",
    placement: "left",
  },
  {
    id: "dash-predetection",
    section: "Dashboard",
    route: "/",
    target: '[data-tour="dash-predetection"]',
    title: "Predetection receipts",
    body:
      "The proof artifacts. For every caught chain: the stage it was caught at, time-to-detect, the Transformer's confidence and the agent's recommendation — with the prevented stages struck through.",
    placement: "top",
  },
  {
    id: "cases-filters",
    section: "Triage",
    route: "/cases",
    target: '[data-tour="cases-filters"]',
    title: "Cases — the triage queue",
    body:
      "Every reconstructed attack chain becomes a case. Filter by triage status, minimum kill-chain stage, or host — the counts in the chips update live.",
    placement: "bottom",
  },
  {
    id: "cases-table",
    section: "Triage",
    route: "/cases",
    target: '[data-tour="cases-table"]',
    title: "Work the queue",
    body:
      "One dense row per chain: host, CKC stage badge, MITRE techniques, the agent's last action and age. Click any row to open the full forensic Attack Analysis page; tick checkboxes to bulk-mark cases investigating, contained or closed.",
    tip: "Rows flash their status rail when a live event touches their chain.",
    placement: "auto",
  },
  {
    id: "hunt-query",
    section: "Hunt",
    route: "/hunt",
    target: '[data-tour="hunt-query"]',
    title: "Hunt — query console",
    body:
      "KQL-lite over every ingested event. Combine host:, user:, technique: and time: with free text — for example technique:T1057 time:24h. Malformed input never errors; it degrades to full-text search and underlines the token it couldn't parse.",
    tip: "MITRE technique chips elsewhere in the app deep-link straight back here.",
    placement: "bottom",
  },
  {
    id: "hunt-saved",
    section: "Hunt",
    route: "/hunt",
    target: '[data-tour="hunt-saved"]',
    title: "Saved queries",
    body:
      "Bookmark the hunts you repeat. Click one to run it instantly; the bookmark icon in the query bar saves whatever you're currently running.",
    placement: "left",
  },
  {
    id: "intel-overview",
    section: "Intelligence",
    route: "/intel",
    target: '[data-tour="intel-header"]',
    title: "CTI — actors & campaigns",
    body:
      "The strategic layer: tracked APT groups, their campaigns, automatic attribution of your chains via tactic-set similarity, live external feeds (FeodoTracker, URLhaus) and the top indicators observed inside your own telemetry.",
    tip: "The Actors, Campaigns and Graph buttons open the deeper CTI views, including the radial pivot graph.",
    placement: "bottom",
  },
  {
    id: "ti-tabs",
    section: "Intelligence",
    route: "/threat-intel",
    target: '[data-tour="ti-tabs"]',
    title: "Threat Intel — reputation & coverage",
    body:
      "Two registries in one page: the IOC table with per-indicator reputation (VirusTotal-backed when a key is configured), and the ATT&CK coverage matrix of every technique observed in the lab. Click an indicator to open its pivot drawer.",
    tip: "Export CSV produces a report-ready dump of the current registry view.",
    placement: "bottom",
  },
  {
    id: "ai-kpis",
    section: "AI Engine",
    route: "/ai-engine",
    target: '[data-tour="ai-kpis"]',
    title: "Model Monitoring — scoreboard",
    body:
      "Composite accuracy and F1 across the five models (training-time test sets), plus the live inference rate sourced from the SSE feed.",
    placement: "bottom",
  },
  {
    id: "ai-live",
    section: "AI Engine",
    route: "/ai-engine",
    target: '[data-tour="ai-live"]',
    title: "Live inference & verdict stream",
    body:
      "One panel per model: AE reconstruction error, VAE malicious probability, GNN node risk, Transformer next-stage prediction, and the STRIX agent's Q-values with its chosen action. The Inference Stream table underneath logs every verdict as it happens.",
    placement: "auto",
  },
  {
    id: "topo-sim",
    section: "Simulation",
    route: "/topology",
    target: '[data-tour="topo-sim"]',
    title: "Simulation topology",
    body:
      "The lab as the platform sees it: attacker, victims and the Wazuh manager for the active run, with per-host malicious / benign / alert counters. Nodes pulse as tactics fire.",
    placement: "right",
  },
  {
    id: "topo-gnn",
    section: "Simulation",
    route: "/topology",
    target: '[data-tour="topo-gnn"]',
    title: "GNN victim graph",
    body:
      "The propagation model's view of the same lab: per-host risk evolving as the attack spreads laterally. Frames stream in while a simulation is running.",
    placement: "left",
  },
  {
    id: "finish",
    section: "Done",
    route: "/",
    target: null,
    title: "You're ready",
    body:
      "That's the full loop: watch the Dashboard, triage Cases, dig deeper with Hunt and the intelligence surfaces, keep an eye on the models — and let STRIX intervene early. Fire a simulation (bash jury_demo.sh) to see every panel light up.",
    tip: "Restart this tour anytime from the ? icon in the top bar, or from the Support page.",
  },
]
