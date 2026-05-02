// model-registry.ts — canonical training-time evaluation metrics.
//
// These are NOT live runtime values. They are the held-out test-set
// numbers reported by the training notebooks under apps/notebooks/ and
// the offline RL evaluation runs under RL_agent/evaluation/. They
// represent what the model is *intrinsically* capable of, independent
// of distribution shift on lab traffic — that's what the drift signal
// in /api/v1/monitoring/models is for.
//
// Sources are cited per-model so an analyst can trace each number
// back to the artefact it came from. If you retrain a model, update
// this file alongside the weights.

export interface ModelMetrics {
  /** UI-facing name. */
  name: string;
  /** Short version tag — bump when weights change. */
  version: string;
  /** What the model does in one short sentence. */
  description: string;
  /** Held-out test-set metrics. */
  metrics: {
    accuracy?: number;       // 0..1
    f1?: number;             // 0..1
    precision?: number;      // 0..1
    recall?: number;         // 0..1
    auc?: number;            // 0..1
    threshold?: number;      // decision threshold (model-specific)
    extras?: Array<{ label: string; value: string }>;
  };
  /** Where these numbers came from — relative to repo root. */
  source: string;
  /** Architecture short tag for UI badging. */
  architecture: string;
  /** UI tint key. */
  color:
    | "cyan"
    | "purple"
    | "amber"
    | "emerald"
    | "blue";
  /** Lifecycle state. */
  status: "active" | "training" | "deprecated";
}

/** Display-only — the dashboard's list of "active models" pulls from here. */
export const MODEL_REGISTRY: ModelMetrics[] = [
  {
    name: "AE Anomaly",
    version: "regularized-top25",
    description:
      "Autoencoder reconstruction-error anomaly detector. Trained on benign-only traffic; high recon-error = anomaly.",
    architecture: "Autoencoder",
    color: "blue",
    status: "active",
    metrics: {
      auc: 0.9849,
      f1: 0.8732,
      precision: 0.8034,
      recall: 0.9562,
      accuracy: 0.9452, // balanced accuracy
      extras: [{ label: "Balanced acc.", value: "94.52%" }],
    },
    source: "apps/notebooks/TP1_AE_FeatureSelection.ipynb",
  },
  {
    name: "VAE Anomaly",
    version: "beta-vae-top25-l32",
    description:
      "β-VAE with logistic-regression calibrator turning recon loss into a malicious probability.",
    architecture: "Variational AE + Calibrator",
    color: "purple",
    status: "active",
    metrics: {
      auc: 0.9740,
      f1: 0.8636,
      precision: 0.8298,
      recall: 0.9002,
      accuracy: 0.9241,
      extras: [{ label: "Latent dim", value: "32" }],
    },
    source: "apps/notebooks/TP2_VAE_FeatureSelection.ipynb",
  },
  {
    name: "GNN Classifier",
    version: "propagation-no-rule-level",
    description:
      "Graph neural network propagating risk across host neighborhoods. Sigmoid output = node alert risk.",
    architecture: "Graph NN (propagation)",
    color: "cyan",
    status: "active",
    metrics: {
      threshold: 0.7743,
      extras: [
        { label: "Threshold", value: "0.7743" },
        { label: "Output", value: "node_risk ∈ [0,1]" },
      ],
    },
    source:
      "apps/notebooks/GNN_Network_Propagation.ipynb · apps/models/gnn_metadata.pkl",
  },
  {
    name: "Transformer CKC Predictor",
    version: "te-on-ae-latents",
    description:
      "Transformer encoder over AE-latent sequences predicting the next Cyber Kill Chain stage.",
    architecture: "Transformer Encoder",
    color: "emerald",
    status: "active",
    metrics: {
      accuracy: 0.8602,
      f1: 0.8854,
      precision: 0.9231,
      recall: 0.8602,
      extras: [
        { label: "Test seqs", value: "17,359" },
        { label: "Held-out top-1", value: "83.3%" },
      ],
    },
    source: "apps/notebooks/TP2_MLA_TE.ipynb",
  },
  {
    name: "DQN Agent",
    version: "real-data-2k",
    description:
      "Deep-Q-Network policy over a 13-d state vector emitting one of 5 actions (NO_OP → BLOCK_USER_IP).",
    architecture: "Dueling DQN",
    color: "amber",
    status: "active",
    metrics: {
      accuracy: 0.839,
      f1: 0.8418,
      precision: 0.8272,
      recall: 0.857,
      extras: [
        { label: "FPR", value: "17.9%" },
        { label: "Avg reward", value: "6.728" },
        { label: "Pre-detection rate", value: "80.4%" },
      ],
    },
    source: "RL_agent/evaluation/real_data_evaluation.json",
  },
];

/** Convenience — composite (mean) metrics across the active models that
 *  expose accuracy / F1. Used by the AI Engine page's KPI strip so we
 *  don't show a bogus 100% derived from a null drift signal. */
export function compositeMetrics(): {
  accuracyPct: number;
  f1: number;
  modelCount: number;
} {
  const xs = MODEL_REGISTRY.filter((m) => m.status === "active");
  const accs = xs.map((m) => m.metrics.accuracy).filter((v): v is number => typeof v === "number");
  const f1s = xs.map((m) => m.metrics.f1).filter((v): v is number => typeof v === "number");
  const mean = (arr: number[]) =>
    arr.length === 0 ? 0 : arr.reduce((a, b) => a + b, 0) / arr.length;
  return {
    accuracyPct: Math.round(mean(accs) * 1000) / 10, // one decimal
    f1: Math.round(mean(f1s) * 1000) / 1000,
    modelCount: xs.length,
  };
}
