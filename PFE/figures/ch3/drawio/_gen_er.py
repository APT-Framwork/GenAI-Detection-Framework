#!/usr/bin/env python3
"""Generate 3.7.6.b Database ER Diagram (drawio XML) — compact version.

Each table is a single HTML cell with its columns as a bulleted list.
FK relationships are drawn with crow's-foot endings between tables.
"""
from html import escape as esc

# ---------------------------------------------------------------------------
# Schema: list of (kind, "name : Type") per table
# kind ∈ {pk, fk, uk, ""}
# ---------------------------------------------------------------------------
def c(kind, decl): return (kind, decl)

tables = {
    "users": ("Identity", [
        c("pk", "user_id : UUID"),
        c("uk", "email : str"),
        c("",   "password_hash : str"),
        c("",   "role : enum"),
        c("",   "is_active : bool"),
        c("",   "designation : str?"),
        c("",   "created_at, updated_at : datetime"),
    ]),
    "hosts": ("Inventory", [
        c("pk", "host_id : UUID"),
        c("uk", "agent_id : str"),
        c("",   "agent_name : str"),
        c("",   "ip_address : str"),
        c("",   "is_manager : bool"),
        c("",   "first_seen_at : datetime"),
        c("",   "last_seen_at : datetime"),
    ]),
    "attack_chains": ("Detection", [
        c("pk", "chain_id : UUID"),
        c("fk", "host_id → hosts"),
        c("",   "opened_at : datetime"),
        c("",   "closed_at : datetime?"),
        c("",   "first_malicious_at : datetime?"),
        c("",   "max_ckc_stage : int"),
        c("",   "max_vae_prob : float"),
        c("",   "status : 'open' | 'closed'"),
        c("",   "triage_status : enum"),
        c("fk", "campaign_id → campaigns?"),
        c("",   "tlp : enum"),
        c("fk", "assignee_user_id → users?"),
    ]),
    "alerts": ("Detection-TS", [
        c("pk", "alert_id : str"),
        c("pk", "occurred_at : datetime"),
        c("fk", "host_id → hosts"),
        c("fk", "chain_id → attack_chains?"),
        c("",   "decoder_name, location : str"),
        c("",   "full_log : str"),
        c("",   "rule_id, rule_firedtimes : int"),
        c("",   "mitre_tactics, mitre_techniques : str[]"),
        c("",   "ckc_stage : int"),
        c("",   "raw_jsonb : JSONB"),
        c("",   "acknowledged_at : datetime?"),
        c("fk", "acknowledged_by → users?"),
    ]),
    "detections": ("Detection-TS", [
        c("pk", "alert_id, occurred_at  (1-1 FK to alerts)"),
        c("",   "host_id, chain_id, step_in_chain"),
        c("",   "ae_anomaly_score, ae_recon_error"),
        c("",   "vae_malicious_prob, vae_uncertainty"),
        c("",   "transformer_pred_ckc, _confidence"),
        c("",   "transformer_probabilities : float[8]"),
        c("",   "gnn_node_risk, _neighbor_risk, _growth"),
        c("",   "state_vector : float[13]"),
        c("",   "model_versions : JSONB"),
    ]),
    "dqn_actions": ("Detection", [
        c("pk", "action_id : UUID"),
        c("fk", "alert_id → alerts"),
        c("fk", "chain_id → attack_chains?"),
        c("fk", "host_id → hosts"),
        c("",   "decided_at : datetime"),
        c("",   "action : int (0..4)"),
        c("",   "action_name : MONITOR|LOW_ALERT|ESCALATE|"),
        c("",   "   ISOLATE_HOST|BLOCK_USER_IP"),
        c("",   "q_values : float[5]"),
        c("",   "ckc_stage_at_decision : int"),
        c("",   "requires_approval, applied : bool"),
        c("",   "applied_at : datetime?"),
        c("fk", "applied_by → users?"),
        c("",   "rejected_at : datetime?"),
        c("fk", "rejected_by → users?"),
    ]),
    "dqn_action_rollbacks": ("Detection", [
        c("pk", "rollback_id : UUID"),
        c("fk", "action_id → dqn_actions (unique)"),
        c("fk", "rolled_back_by → users"),
        c("",   "rolled_back_at : datetime"),
        c("",   "reason : str"),
    ]),
    "threat_actors": ("CTI", [
        c("pk", "actor_id : UUID"),
        c("uk", "name : str"),
        c("",   "aliases : str[]"),
        c("",   "mitre_group_id, country, motivation, description"),
    ]),
    "campaigns": ("CTI", [
        c("pk", "campaign_id : UUID"),
        c("uk", "name : str"),
        c("fk", "actor_id → threat_actors?"),
        c("",   "tactic_chain : JSONB"),
        c("",   "description : str"),
    ]),
    "ioc_lookup_cache": ("Identity", [
        c("pk", "indicator, indicator_type, source : str"),
        c("",   "reputation : str"),
        c("",   "payload : JSONB"),
        c("",   "checked_at, expires_at : datetime"),
    ]),
    "llm_insight_cache": ("Identity", [
        c("pk", "payload_hash : str"),
        c("",   "generated_at : datetime"),
        c("",   "model_version : str"),
        c("",   "insight : str"),
        c("",   "recommended_actions : JSONB"),
        c("",   "expires_at : datetime"),
    ]),
    "file_scans": ("Identity", [
        c("pk", "scan_id : UUID"),
        c("uk", "sha256 : str"),
        c("",   "filename : str  ·  size_bytes : int"),
        c("",   "uploaded_at : datetime"),
        c("fk", "uploaded_by → users"),
        c("",   "vt_result : JSONB"),
        c("",   "vt_scanned_at : datetime?  ·  status : enum"),
    ]),
    "push_devices": ("Identity", [
        c("pk", "device_id : UUID"),
        c("fk", "user_id → users  (ON DELETE CASCADE)"),
        c("",   "expo_push_token : str"),
        c("",   "platform : 'ios' | 'android'"),
        c("",   "app_version : str"),
        c("",   "registered_at, last_seen_at : datetime"),
    ]),
    "tags": ("Metadata", [
        c("pk", "tag_id : UUID"),
        c("uk", "name : str"),
        c("",   "colour, description : str"),
    ]),
    "tag_links": ("Metadata", [
        c("pk", "link_id : UUID"),
        c("",   "entity_type : 'chain'|'indicator'|'actor'|"),
        c("",   "   'campaign'|'report'"),
        c("",   "entity_id : UUID"),
        c("fk", "tag_id → tags"),
        c("fk", "created_by → users?"),
    ]),
    "chain_notes": ("Metadata", [
        c("pk", "note_id : UUID"),
        c("fk", "chain_id → attack_chains"),
        c("fk", "author_user_id → users"),
        c("",   "body_md : str"),
    ]),
    "case_audit_log": ("Metadata", [
        c("pk", "audit_id : UUID"),
        c("fk", "chain_id → attack_chains"),
        c("fk", "user_id → users"),
        c("",   "from_status, to_status, note : str"),
        c("",   "at : datetime"),
    ]),
    "hunt_saved_queries": ("Identity", [
        c("pk", "saved_id : UUID"),
        c("fk", "user_id → users"),
        c("",   "name : str  ·  q : str  ·  (user_id, name) unique"),
    ]),
    "gnn_graph_snapshots": ("Inventory-TS", [
        c("pk", "snapshot_id : UUID"),
        c("pk", "taken_at : datetime"),
        c("",   "shard_id : int"),
        c("",   "node_count, edge_count : int"),
        c("",   "nodes, edges : JSONB"),
    ]),
}

# Layout
COL_X = {
    "Identity": 40, "Inventory": 360, "Detection": 680,
    "CTI": 1340, "Metadata": 1660,
}
WIDTH = 300
HEADER_H = 28
LINE_H   = 18
GUTTER   = 24

ORDER = {
    "Identity":   ["users", "push_devices", "hunt_saved_queries", "file_scans",
                   "ioc_lookup_cache", "llm_insight_cache"],
    "Inventory":  ["hosts", "gnn_graph_snapshots"],
    "Detection":  ["attack_chains", "alerts", "detections",
                   "dqn_actions", "dqn_action_rollbacks"],
    "CTI":        ["threat_actors", "campaigns"],
    "Metadata":   ["tags", "tag_links", "chain_notes", "case_audit_log"],
}
TBL_TO_COL = {t: col for col, lst in ORDER.items() for t in lst}

FILL  = {"Identity":"#dae8fc","Inventory":"#d5e8d4","Detection":"#ffe6cc",
         "CTI":"#f8cecc","Metadata":"#e1d5e7"}
STR   = {"Identity":"#6c8ebf","Inventory":"#82b366","Detection":"#d79b00",
         "CTI":"#b85450","Metadata":"#9673a6"}

# Compute positions
pos = {}
for col, names in ORDER.items():
    x = COL_X[col]
    y = 60
    for t in names:
        cat, rows = tables[t]
        h = HEADER_H + LINE_H * len(rows) + 10
        pos[t] = (x, y, h)
        y += h + GUTTER

# FK edges (parent → child, label, parent-side, child-side)
fks = [
    ("hosts",         "attack_chains",        "host_id",                  "ERone",     "ERmany"),
    ("hosts",         "alerts",               "host_id",                  "ERone",     "ERmany"),
    ("attack_chains", "alerts",               "chain_id",                 "ERzeroOne", "ERmany"),
    ("alerts",        "detections",           "(alert_id,occurred_at)",   "ERone",     "ERone"),
    ("alerts",        "dqn_actions",          "alert_id",                 "ERone",     "ERmany"),
    ("attack_chains", "dqn_actions",          "chain_id",                 "ERzeroOne", "ERmany"),
    ("users",         "dqn_actions",          "applied_by/rejected_by",   "ERzeroOne", "ERmany"),
    ("dqn_actions",   "dqn_action_rollbacks", "action_id",                "ERone",     "ERzeroOne"),
    ("users",         "dqn_action_rollbacks", "rolled_back_by",           "ERone",     "ERmany"),
    ("campaigns",     "attack_chains",        "campaign_id",              "ERzeroOne", "ERmany"),
    ("threat_actors", "campaigns",            "actor_id",                 "ERzeroOne", "ERmany"),
    ("attack_chains", "chain_notes",          "chain_id",                 "ERone",     "ERmany"),
    ("users",         "chain_notes",          "author_user_id",           "ERone",     "ERmany"),
    ("attack_chains", "case_audit_log",       "chain_id",                 "ERone",     "ERmany"),
    ("users",         "case_audit_log",       "user_id",                  "ERone",     "ERmany"),
    ("tags",          "tag_links",            "tag_id",                   "ERone",     "ERmany"),
    ("users",         "tag_links",            "created_by",               "ERzeroOne", "ERmany"),
    ("users",         "hunt_saved_queries",   "user_id",                  "ERone",     "ERmany"),
    ("users",         "push_devices",         "user_id (cascade)",        "ERone",     "ERmany"),
    ("users",         "file_scans",           "uploaded_by",              "ERone",     "ERmany"),
    ("users",         "attack_chains",        "assignee_user_id",         "ERzeroOne", "ERmany"),
    ("users",         "alerts",               "acknowledged_by",          "ERzeroOne", "ERmany"),
]

# --- Build XML ---
cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

# Title
cells.append(
    '<mxCell id="title" value="STRIX — Database ER Diagram (3.7.6.b)" '
    'style="text;html=1;align=center;fontSize=22;fontStyle=1;" '
    'vertex="1" parent="1">'
    '<mxGeometry x="40" y="10" width="1920" height="36" as="geometry"/></mxCell>'
)

# Legend
cells.append(
    '<mxCell id="legend" '
    'value="&lt;b&gt;Legend&lt;/b&gt;&lt;br&gt;'
    '&lt;b&gt;PK&lt;/b&gt; primary key &#160;&#160; '
    '&lt;b&gt;FK&lt;/b&gt; foreign key &#160;&#160; '
    '&lt;b&gt;UK&lt;/b&gt; unique&lt;br&gt;'
    'TS suffix = TimescaleDB hypertable&lt;br&gt;'
    'Crow&apos;s foot = many&#160;·&#160;Single bar = exactly one&#160;·&#160;'
    'Circle = optional" '
    'style="text;html=1;align=left;verticalAlign=middle;fontSize=11;'
    'fillColor=#f5f5f5;strokeColor=#888;spacing=8;" '
    'vertex="1" parent="1">'
    '<mxGeometry x="1660" y="1380" width="300" height="86" as="geometry"/></mxCell>'
)

# Tables — one cell per table with HTML body
for tname, (cat, rows) in tables.items():
    x, y, h = pos[tname]
    layout = TBL_TO_COL[tname]
    fill = FILL[layout]
    stroke = STR[layout]
    ts = " &lt;sup&gt;[TS]&lt;/sup&gt;" if cat.endswith("-TS") else ""
    header = f"&lt;b&gt;{tname}&lt;/b&gt;{ts}"
    body_lines = []
    for kind, decl in rows:
        if kind == "pk":
            body_lines.append(f"&lt;b&gt;PK&lt;/b&gt; {esc(decl)}")
        elif kind == "fk":
            body_lines.append(f"&lt;i&gt;FK&lt;/i&gt; {esc(decl)}")
        elif kind == "uk":
            body_lines.append(f"UK {esc(decl)}")
        else:
            body_lines.append(f"&#160;&#160;&#160;{esc(decl)}")
    body = "&lt;br&gt;".join(body_lines)
    value = f"{header}&lt;br&gt;&lt;hr&gt;{body}"
    style = (f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
             f"fontSize=11;align=left;verticalAlign=top;spacing=6;")
    cells.append(
        f'<mxCell id="t-{tname}" value="{value}" style="{style}" '
        f'vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{WIDTH}" height="{h}" as="geometry"/>'
        f'</mxCell>'
    )

# Edges
for i, (par, ch, label, pside, cside) in enumerate(fks):
    style = (f"endArrow={cside};startArrow={pside};endFill=0;startFill=0;"
             f"html=1;edgeStyle=orthogonalEdgeStyle;orthogonalLoop=1;"
             f"jettySize=auto;strokeColor=#555;fontSize=10;")
    cells.append(
        f'<mxCell id="e-{i}" value="{esc(label)}" style="{style}" '
        f'edge="1" parent="1" source="t-{par}" target="t-{ch}">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )

inner = "\n    ".join(cells)
print(f'''<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" agent="STRIX-Chapter3" version="22.1.16">
  <diagram id="3-7-6-b-ER" name="Database ER">
    <mxGraphModel dx="1800" dy="1100" grid="1" gridSize="10" guides="1" tooltips="1"
                  connect="1" arrows="1" fold="1" page="1" pageScale="1"
                  pageWidth="2000" pageHeight="1700" math="0" shadow="0">
      <root>
    {inner}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>''')
