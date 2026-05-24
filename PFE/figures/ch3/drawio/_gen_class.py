#!/usr/bin/env python3
"""Generate 3.7.4 UML Class Diagram (drawio XML, compact)."""
from html import escape as esc

# (stereotype, "ClassName", [attr_lines], [method_lines])
def C(stereo, name, attrs, methods=None):
    return (stereo, name, attrs, methods or [])

# Cluster 1 — Domain entities
domain = {
    "User": C("entity", "User", [
        "+ user_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ email : str  &lt;i&gt;(unique)&lt;/i&gt;",
        "- password_hash : str",
        "+ role : 'admin' | 'analyst'",
        "+ is_active : bool",
        "+ designation : str?",
    ], [
        "+ set_password(plain) : None  [Argon2]",
        "+ verify_password(plain) : bool",
    ]),
    "Host": C("entity", "Host", [
        "+ host_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ agent_id : str  &lt;i&gt;(unique)&lt;/i&gt;",
        "+ agent_name, ip_address : str",
        "+ is_manager : bool",
        "+ first_seen_at, last_seen_at",
    ]),
    "AttackChain": C("entity", "AttackChain", [
        "+ chain_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ host_id : UUID → Host",
        "+ opened_at, closed_at?",
        "+ first_malicious_at? : datetime",
        "+ max_ckc_stage : int",
        "+ max_vae_prob : float",
        "+ status : 'open'|'closed'",
        "+ triage_status : enum (4 states)",
        "+ campaign_id? → Campaign",
        "+ tlp : enum  ·  assignee_user_id?",
    ], [
        "+ close(reason) : None",
        "+ bump_stage(stage) : None",
        "+ attribute_to(campaign) : None",
    ]),
    "Alert": C("entity", "Alert «hypertable»", [
        "+ alert_id : str  &lt;b&gt;(PK pt1)&lt;/b&gt;",
        "+ occurred_at : datetime  &lt;b&gt;(PK pt2)&lt;/b&gt;",
        "+ host_id, chain_id?",
        "+ decoder_name, location, full_log",
        "+ rule_id, rule_firedtimes : int",
        "+ mitre_tactics/techniques : str[]",
        "+ ckc_stage : int",
        "+ raw_jsonb : JSONB",
        "+ acknowledged_at?, acknowledged_by?",
    ], [
        "+ acknowledge(user) : None",
    ]),
    "Detection": C("entity", "Detection «hypertable»", [
        "+ alert_id, occurred_at  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ host_id, chain_id?",
        "+ step_in_chain : int",
        "+ ae_anomaly_score, ae_recon_error",
        "+ vae_malicious_prob, vae_uncertainty",
        "+ transformer_pred_ckc, _confidence",
        "+ transformer_probabilities : float[8]",
        "+ gnn_node_risk, _neighbor_risk, _growth",
        "+ state_vector : float[13]",
        "+ model_versions : JSONB",
    ]),
    "DQNAction": C("entity", "DQNAction", [
        "+ action_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ alert_id → Alert",
        "+ chain_id? → AttackChain",
        "+ host_id → Host",
        "+ decided_at : datetime",
        "+ action : int (0..4)",
        "+ action_name : enum (5 values)",
        "+ q_values : float[5]",
        "+ ckc_stage_at_decision : int",
        "+ requires_approval, applied : bool",
        "+ applied_at?, applied_by? → User",
        "+ rejected_at?, rejected_by? → User",
    ], [
        "+ approve(user) : None",
        "+ reject(user, reason) : None",
        "+ rollback(user, reason)",
    ]),
    "DqnActionRollback": C("entity", "DqnActionRollback", [
        "+ rollback_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ action_id → DQNAction &lt;i&gt;(unique)&lt;/i&gt;",
        "+ rolled_back_by → User",
        "+ rolled_back_at : datetime",
        "+ reason : str",
    ]),
    "Campaign": C("entity", "Campaign", [
        "+ campaign_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ name : str  &lt;i&gt;(unique)&lt;/i&gt;",
        "+ actor_id? → ThreatActor",
        "+ tactic_chain : JSONB",
        "+ description : str",
    ]),
    "ThreatActor": C("entity", "ThreatActor", [
        "+ actor_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ name : str  &lt;i&gt;(unique)&lt;/i&gt;",
        "+ aliases : str[]",
        "+ mitre_group_id, country, motivation",
        "+ description : str",
    ]),
    "IocLookupCache": C("entity", "IocLookupCache", [
        "+ indicator, indicator_type, source  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ reputation : str",
        "+ payload : JSONB",
        "+ checked_at, expires_at",
    ]),
    "LlmInsightCache": C("entity", "LlmInsightCache", [
        "+ payload_hash : str  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ generated_at : datetime",
        "+ model_version : str",
        "+ insight : str",
        "+ recommended_actions : JSONB",
        "+ expires_at : datetime",
    ]),
    "FileScan": C("entity", "FileScan", [
        "+ scan_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ sha256 : str  &lt;i&gt;(unique)&lt;/i&gt;",
        "+ filename, size_bytes",
        "+ uploaded_at, uploaded_by → User",
        "+ vt_result : JSONB",
        "+ vt_scanned_at?, status : enum",
    ]),
    "PushDevice": C("entity", "PushDevice", [
        "+ device_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ user_id → User &lt;i&gt;(cascade)&lt;/i&gt;",
        "+ expo_push_token : str",
        "+ platform : 'ios' | 'android'",
        "+ app_version : str",
        "+ registered_at, last_seen_at",
    ]),
    "Tag": C("entity", "Tag", [
        "+ tag_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ name : str  &lt;i&gt;(unique)&lt;/i&gt;",
        "+ colour, description : str",
    ]),
    "TagLink": C("entity", "TagLink «polymorphic»", [
        "+ link_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ entity_type : enum (5 values)",
        "+ entity_id : UUID",
        "+ tag_id → Tag",
        "+ created_by? → User",
    ]),
    "ChainNote": C("entity", "ChainNote", [
        "+ note_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ chain_id → AttackChain",
        "+ author_user_id → User",
        "+ body_md : str",
    ]),
    "CaseAuditLog": C("entity", "CaseAuditLog", [
        "+ audit_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ chain_id → AttackChain",
        "+ user_id → User",
        "+ from_status, to_status, note : str",
        "+ at : datetime",
    ]),
    "HuntSavedQuery": C("entity", "HuntSavedQuery", [
        "+ saved_id : UUID  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ user_id → User",
        "+ name, q : str",
        "+ (user_id, name) unique",
    ]),
    "GnnGraphSnapshot": C("entity", "GnnGraphSnapshot «hypertable»", [
        "+ snapshot_id, taken_at  &lt;b&gt;(PK)&lt;/b&gt;",
        "+ shard_id : int",
        "+ node_count, edge_count : int",
        "+ nodes, edges : JSONB",
    ]),
}

# Cluster 2 — ML model layer
ml = {
    "ModelRegistry": C("service", "ModelRegistry", [
        "+ active_calibrator : str =",
        "&#160;&#160;&#x27;Beta-VAE (Top 25) lab-refit&#x27;",
    ], [
        "+ load(name, version) : nn.Module",
        "+ verify_sha256(path, expected) : bool",
    ]),
    "RegularizedAutoencoder": C("model", "RegularizedAutoencoder", [
        "- encoder : nn.Sequential",
        "- fc_mu : Linear(128 → 64)",
        "- fc_logvar : Linear(128 → 64)",
        "- decoder : nn.Sequential",
        "- center : Parameter(zeros(64))",
    ], [
        "+ forward(x) → dict {mu, logvar,",
        "&#160;&#160;recon, recon_error, anomaly_score}",
        "+ encode(x), decode(z)",
    ]),
    "BetaVAE": C("model", "BetaVAE", [
        "- encoder : Sequential 55→512→256→128",
        "- fc_z_mean : Linear(128 → 32)",
        "- fc_z_log_var : Linear(128 → 32)",
        "- decoder : Sequential 32→128→256→512→55",
        "- center : Parameter(zeros(32))",
    ], [
        "+ forward(x) → dict {z_mean, z_log_var,",
        "&#160;&#160;recon_loss, malicious_prob, uncertainty}",
    ]),
    "Transformer": C("model", "Transformer", [
        "- input_projection : Linear(64 → 128)",
        "&#160;&#160;+ LayerNorm + ReLU",
        "- pos_encoder : Sinusoidal (d=128, len=500)",
        "- transformer_encoder : 4 × EncoderLayer",
        "&#160;&#160;(8 heads, d_ff=512, GELU, PreLN)",
        "- output_head : Linear(128 → 64)",
        "&#160;&#160;+ ReLU + Linear(64 → 8)",
    ], [
        "+ forward(seq : Tensor[T, 64]) →",
        "&#160;&#160;{logits, pred_ckc, confidence,",
        "&#160;&#160;probabilities}",
    ]),
    "GraphSAGE": C("model", "GraphSAGE", [
        "- convs : ModuleList[",
        "&#160;&#160;SAGEConv(55 → 128),",
        "&#160;&#160;SAGEConv(128 → 128) × 2]",
        "- bns : BatchNorm(128) × 3",
        "- head : Linear(128 → 64)",
        "&#160;&#160;+ ReLU + Linear(64 → 1) + Sigmoid",
    ], [
        "+ forward(x, edge_index) → Tensor[N]",
        "&#160;&#160;(per-node risk ∈ [0, 1])",
    ]),
    "DQN": C("model", "DQN", [
        "- network : nn.Sequential",
        "&#160;&#160;Linear(13 → 128) + ReLU + Dropout",
        "&#160;&#160;Linear(128 → 64) + ReLU + Dropout",
        "&#160;&#160;Linear(64 → 5)",
    ], [
        "+ forward(state : Tensor[13]) →",
        "&#160;&#160;Tensor[5]  (Q-values)",
        "+ select_action(state) : int",
    ]),
}

# Colours
COLOR = {
    "entity":  ("#dae8fc", "#6c8ebf"),
    "model":   ("#fff2cc", "#d6b656"),
    "service": ("#d5e8d4", "#82b366"),
}

LINE_H = 14
HEADER_H = 36

def class_height(c):
    _, _, attrs, methods = c
    h = HEADER_H + LINE_H * len(attrs) + 8
    if methods:
        h += 6 + LINE_H * len(methods) + 8
    return h

# Layout: domain 4 columns × N rows, ML 6 in one row at bottom
W = 260
GUTTER_Y = 18
DOMAIN_LAYOUT = [
    (0, "User"), (0, "PushDevice"), (0, "HuntSavedQuery"), (0, "FileScan"),
    (1, "Host"), (1, "GnnGraphSnapshot"), (1, "Tag"), (1, "TagLink"),
    (2, "AttackChain"), (2, "ChainNote"), (2, "CaseAuditLog"),
    (3, "Alert"), (3, "Detection"),
    (4, "DQNAction"), (4, "DqnActionRollback"),
    (5, "Campaign"), (5, "ThreatActor"),
    (5, "IocLookupCache"), (5, "LlmInsightCache"),
]
COL_X = [40, 320, 600, 880, 1160, 1440]

domain_pos = {}
col_y = [70] * 6
for col_idx, name in DOMAIN_LAYOUT:
    h = class_height(domain[name])
    domain_pos[name] = (COL_X[col_idx], col_y[col_idx], W, h)
    col_y[col_idx] += h + GUTTER_Y

# ML row at bottom of domain lane
ml_top = max(col_y) + 60
ml_pos = {}
ml_names = ["ModelRegistry", "RegularizedAutoencoder", "BetaVAE",
            "Transformer", "GraphSAGE", "DQN"]
for i, name in enumerate(ml_names):
    h = class_height(ml[name])
    ml_pos[name] = (40 + i * 280, ml_top + 60, W, h)

ml_lane_h = max(class_height(ml[n]) for n in ml_names) + 100

# Edges
edges = [
    ("Host", "AttackChain", "1—* chains"),
    ("AttackChain", "Alert", "1—* alerts"),
    ("Alert", "Detection", "1—1"),
    ("Alert", "DQNAction", "1—* actions"),
    ("AttackChain", "Campaign", "0..1 → 0..*"),
    ("Campaign", "ThreatActor", "0..* → 0..1"),
    ("AttackChain", "ChainNote", "1—*"),
    ("AttackChain", "CaseAuditLog", "1—*"),
    ("User", "DQNAction", "approves/rejects"),
    ("DQNAction", "DqnActionRollback", "0..1"),
    ("User", "PushDevice", "1—*"),
    ("User", "HuntSavedQuery", "1—*"),
    ("User", "FileScan", "uploads"),
    ("Tag", "TagLink", "1—*  &lt;i&gt;poly&lt;/i&gt;"),
    # ML
    ("ModelRegistry", "RegularizedAutoencoder", "«loads»"),
    ("ModelRegistry", "BetaVAE", "«loads»"),
    ("ModelRegistry", "Transformer", "«loads»"),
    ("ModelRegistry", "GraphSAGE", "«loads»"),
    ("ModelRegistry", "DQN", "«loads»"),
    ("Detection", "ModelRegistry", "«produced by»"),
]

# Build XML
cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

# Title
cells.append(
    '<mxCell id="title" value="STRIX — Class Diagram (3.7.4)" '
    'style="text;html=1;align=center;fontSize=22;fontStyle=1;" '
    'vertex="1" parent="1">'
    '<mxGeometry x="40" y="14" width="1660" height="36" as="geometry"/></mxCell>'
)

# Lane labels
cells.append(
    f'<mxCell id="lab-domain" value="Cluster 1 — Domain entities (SQLAlchemy ORM)" '
    f'style="text;html=1;align=left;fontSize=16;fontStyle=1;fillColor=#f5f5f5;'
    f'strokeColor=#666;spacing=8;" vertex="1" parent="1">'
    f'<mxGeometry x="40" y="56" width="1660" height="20" as="geometry"/></mxCell>'
)
cells.append(
    f'<mxCell id="lab-ml" value="Cluster 2 — ML model layer (torch.nn.Module + registry)" '
    f'style="text;html=1;align=left;fontSize=16;fontStyle=1;fillColor=#fffaf0;'
    f'strokeColor=#d6b656;spacing=8;" vertex="1" parent="1">'
    f'<mxGeometry x="40" y="{ml_top}" width="1660" height="20" as="geometry"/></mxCell>'
)

# Class cells
def emit(cid, cdef, x, y, w, h, parent="1"):
    stereo, name, attrs, methods = cdef
    fill, stroke = COLOR[stereo]
    header = f"&lt;i&gt;«{stereo}»&lt;/i&gt;&lt;br&gt;&lt;b&gt;{name}&lt;/b&gt;"
    attr_block = "&lt;br&gt;".join(attrs)
    meth_block = "&lt;br&gt;".join(methods)
    parts = [header, "&lt;hr&gt;", attr_block]
    if methods:
        parts += ["&lt;hr&gt;", meth_block]
    value = "&lt;br&gt;".join(parts)
    style = (f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
             f"fontSize=10;align=left;verticalAlign=top;spacing=4;")
    cells.append(
        f'<mxCell id="cls-{cid}" value="{value}" style="{style}" '
        f'vertex="1" parent="{parent}">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )

for name, (x, y, w, h) in domain_pos.items():
    emit(name, domain[name], x, y, w, h)
for name, (x, y, w, h) in ml_pos.items():
    emit(name, ml[name], x, y, w, h)

# Edges
for i, (src, tgt, label) in enumerate(edges):
    dashed = "dashed=1;dashPattern=8 4;" if "«" in label else ""
    style = (f"endArrow=open;startArrow=none;html=1;edgeStyle=orthogonalEdgeStyle;"
             f"orthogonalLoop=1;jettySize=auto;strokeColor=#444;fontSize=10;{dashed}")
    cells.append(
        f'<mxCell id="e-{i}" value="{label}" style="{style}" edge="1" parent="1" '
        f'source="cls-{src}" target="cls-{tgt}">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )

inner = "\n    ".join(cells)
page_h = ml_top + ml_lane_h + 80
print(f'''<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" agent="STRIX-Chapter3" version="22.1.16">
  <diagram id="3-7-4-CLASS" name="Class Diagram">
    <mxGraphModel dx="1800" dy="1100" grid="1" gridSize="10" guides="1" tooltips="1"
                  connect="1" arrows="1" fold="1" page="1" pageScale="1"
                  pageWidth="1740" pageHeight="{page_h}" math="0" shadow="0">
      <root>
    {inner}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>''')
