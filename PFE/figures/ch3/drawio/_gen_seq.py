#!/usr/bin/env python3
"""Generate 3.7.7 Sequence Diagram (drawio XML)."""
from html import escape as esc

LIFELINES = [
    ("caldera",    "Caldera",            "external"),
    ("sandcat",    "Sandcat (victim)",   "external"),
    ("auditd",     "auditd",             "external"),
    ("wagent",     "Wazuh agent",        "external"),
    ("wmgr",       "Wazuh manager",      "external"),
    ("filebeat",   "Filebeat",           "external"),
    ("redis",      "Redis Streams",      "store"),
    ("wbridge",    "wazuh_bridge",       "worker"),
    ("normalizer", "normalizer",         "worker"),
    ("inference",  "inference (AE·VAE·Tx·GNN·DQN)", "worker"),
    ("vwriter",    "verdicts_writer",    "worker"),
    ("postgres",   "Postgres",           "store"),
    ("web",        "Web client",         "external"),
]

# y origin and message spacing
LL_X0 = 40           # left margin
LL_W  = 130          # lifeline column width
LL_Y  = 80           # top of lifeline head
LL_HEAD_H = 56
LL_H  = 800          # total lifeline height (head + dashed line)
MSG_Y0 = 160         # y of first message
DY     = 26          # row height per message

FILLS = {
    "external": ("#f5f5f5", "#444"),
    "store":    ("#fff2cc", "#d6b656"),
    "worker":   ("#dae8fc", "#6c8ebf"),
}

def center(idx):
    return LL_X0 + idx * LL_W + LL_W // 2

messages = [
    # (from_idx, to_idx, label, kind)
    # kind: "" normal, "self" self-call (loop arrow), "return" dashed return
    (0,  1, "run_ability('whoami')",                  ""),
    (1,  2, "exec syscall (SYS_execve)",              ""),
    (2,  3, "audit-wazuh-x record",                   ""),
    (3,  4, "TCP/1514 encrypted event",               ""),
    (4,  5, "append to alerts.json",                  ""),
    (5,  6, "RPUSH strix:alerts:raw:list",            ""),
    (7,  6, "BLPOP strix:alerts:raw:list",            ""),
    (7,  6, "XADD strix:alerts:raw {…}",              ""),
    (8,  6, "XREAD strix:alerts:raw",                 ""),
    (8,  8, "feature engineering (55-d)",             "self"),
    (8,  6, "XADD strix:features:shard0",             ""),
    (9,  6, "XREAD features (batch=32)",              ""),
    (9,  9, "AE forward → anomaly_score",             "self"),
    (9,  9, "β-VAE forward → malicious_prob, uncert.","self"),
    (9,  9, "Transformer forward → pred_ckc",         "self"),
    (9,  9, "GraphSAGE forward → node_risk",          "self"),
    (9,  9, "DQN select_action → action_idx",         "self"),
    (9,  9, "apply gate (deterministic thresholds)",  "self"),
    (9,  6, "XADD strix:verdicts {verdict + action}", ""),
    (10, 6, "XREAD verdicts (5 s window)",            ""),
    (10,11, "INSERT alerts, detections, dqn_actions", ""),
    (10,11, "UPSERT attack_chains (open / bump)",     ""),
    (10,12, "SSE event on /api/v1/streams/live-feed", ""),
    (12,12, "render verdict + chain timeline",        "self"),
]

cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

# Title
cells.append(
    '<mxCell id="title" value="STRIX — Sequence Diagram (3.7.7)&lt;br&gt;'
    '&lt;span style=&quot;font-size:13px;font-weight:normal&quot;&gt;'
    'Caldera fires Discovery tactic against a victim host&lt;/span&gt;" '
    'style="text;html=1;align=center;fontSize=20;fontStyle=1;" '
    'vertex="1" parent="1">'
    f'<mxGeometry x="40" y="10" width="{LL_X0 + len(LIFELINES)*LL_W}" height="60" as="geometry"/></mxCell>'
)

# Timing annotation
cells.append(
    '<mxCell id="timing" value="&lt;b&gt;Timing reference&lt;/b&gt;&lt;br&gt;'
    'T=0 ms&#160;&#160;Caldera fires ability&lt;br&gt;'
    'T≈50 ms&#160;&#160;Wazuh manager writes alerts.json&lt;br&gt;'
    'T≈250 ms&#160;&#160;filebeat picks up · RPUSH&lt;br&gt;'
    'T≈400 ms&#160;&#160;wazuh_bridge XADD&lt;br&gt;'
    'T≈700 ms&#160;&#160;normalizer features built&lt;br&gt;'
    'T≈1.3 s&#160;&#160;inference batch flushes&lt;br&gt;'
    'T≈1.5 s&#160;&#160;Postgres INSERT + SSE&lt;br&gt;'
    'T≈1.7 s&#160;&#160;Web client renders" '
    'style="text;html=1;align=left;verticalAlign=top;fontSize=10;'
    'fillColor=#f5f5f5;strokeColor=#888;spacing=6;" '
    'vertex="1" parent="1">'
    '<mxGeometry x="40" y="900" width="320" height="140" as="geometry"/></mxCell>'
)

# Lifelines: head box + vertical dashed line
for i, (lid, name, kind) in enumerate(LIFELINES):
    fill, stroke = FILLS[kind]
    x = LL_X0 + i * LL_W
    cx = center(i)
    # Head
    cells.append(
        f'<mxCell id="ll-{lid}-head" value="&lt;b&gt;{esc(name)}&lt;/b&gt;" '
        f'style="rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};'
        f'strokeWidth=2;fontSize=11;align=center;verticalAlign=middle;" '
        f'vertex="1" parent="1">'
        f'<mxGeometry x="{x+8}" y="{LL_Y}" width="{LL_W-16}" height="{LL_HEAD_H}" as="geometry"/></mxCell>'
    )
    # Lifeline dashed line (a vertical edge)
    cells.append(
        f'<mxCell id="ll-{lid}-line" value="" '
        f'style="endArrow=none;html=1;dashed=1;strokeColor={stroke};strokeWidth=1;" '
        f'edge="1" parent="1">'
        f'<mxGeometry relative="1" as="geometry">'
        f'<mxPoint x="{cx}" y="{LL_Y + LL_HEAD_H}" as="sourcePoint"/>'
        f'<mxPoint x="{cx}" y="{LL_Y + LL_H}" as="targetPoint"/>'
        f'</mxGeometry></mxCell>'
    )

# Messages
for i, (fr, to, label, kind) in enumerate(messages):
    y = MSG_Y0 + i * DY
    xf = center(fr)
    xt = center(to)
    if kind == "self":
        # small loop on same lifeline: right-going then back
        loop_w = 90
        cells.append(
            f'<mxCell id="msg-{i}" value="{esc(label)}" '
            f'style="endArrow=open;html=1;rounded=0;strokeColor=#222;fontSize=10;'
            f'edgeStyle=orthogonalEdgeStyle;exitX=1;exitY=0.5;entryX=1;entryY=0.5;dashed=1;dashPattern=4 4;" '
            f'edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{xf}" y="{y-6}" as="sourcePoint"/>'
            f'<mxPoint x="{xf}" y="{y+6}" as="targetPoint"/>'
            f'<Array as="points">'
            f'<mxPoint x="{xf+loop_w}" y="{y-6}"/>'
            f'<mxPoint x="{xf+loop_w}" y="{y+6}"/>'
            f'</Array>'
            f'</mxGeometry></mxCell>'
        )
    else:
        cells.append(
            f'<mxCell id="msg-{i}" value="{esc(label)}" '
            f'style="endArrow=open;html=1;rounded=0;strokeColor=#222;fontSize=10;'
            f'startSize=8;endSize=8;" '
            f'edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{xf}" y="{y}" as="sourcePoint"/>'
            f'<mxPoint x="{xt}" y="{y}" as="targetPoint"/>'
            f'</mxGeometry></mxCell>'
        )

inner = "\n    ".join(cells)
width = LL_X0 + len(LIFELINES)*LL_W + 40
print(f'''<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" agent="STRIX-Chapter3" version="22.1.16">
  <diagram id="3-7-7-SEQ" name="Sequence Diagram">
    <mxGraphModel dx="1800" dy="1100" grid="1" gridSize="10" guides="1" tooltips="1"
                  connect="1" arrows="1" fold="1" page="1" pageScale="1"
                  pageWidth="{width}" pageHeight="1060" math="0" shadow="0">
      <root>
    {inner}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>''')
