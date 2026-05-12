// Mirror of apps/web/lib/model-registry.ts — keep in sync.
//
// Training-time held-out test-set metrics for the active models. Live
// signals (drift, latency, last health check) come from /monitoring/models
// over the wire; everything in this file is static and reflects what each
// model is intrinsically capable of on the offline eval set.

export type ModelTint = "cyan" | "purple" | "amber" | "emerald" | "blue";

export interface ModelMetrics {
  name: string;
  architecture: string;
  description: string;
  color: ModelTint;
  status: "active" | "training" | "deprecated";
  metrics: {
    accuracy?: number;
    f1?: number;
    precision?: number;
    recall?: number;
    auc?: number;
    threshold?: number;
    extras?: Array<{ label: string; value: string }>;
  };
  source: string;
}

export const MODEL_REGISTRY: ModelMetrics[] = [
  {
    name: "AE Anomaly",
    architecture: "Autoencoder",
    description:
      "Autoencoder reconstruction-error anomaly detector. Trained on benign-only traffic; high recon-error = anomaly.",
    color: "blue",
    status: "active",
    metrics: {
      auc: 0.9849,
      f1: 0.8732,
      precision: 0.8034,
      recall: 0.9562,
      accuracy: 0.9452,
      extras: [{ label: "Balanced acc.", value: "94.52%" }],
    },
    source: "apps/notebooks/TP1_AE_FeatureSelection.ipynb",
  },
  {
    name: "VAE Anomaly",
    architecture: "Variational AE + Calibrator",
    description:
      "β-VAE with logistic-regression calibrator turning recon loss into a malicious probability.",
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
    architecture: "Graph NN (propagation)",
    description:
      "Graph neural network propagating risk across host neighborhoods. Sigmoid output = node alert risk.",
    color: "cyan",
    status: "active",
    metrics: {
      threshold: 0.7743,
      extras: [
        { label: "Threshold", value: "0.7743" },
        { label: "Output", value: "node_risk ∈ [0,1]" },
      ],
    },
    source: "apps/notebooks/GNN_Network_Propagation.ipynb",
  },
  {
    name: "Transformer CKC Predictor",
    architecture: "Transformer Encoder",
    description:
      "Transformer encoder over AE-latent sequences predicting the next Cyber Kill Chain stage.",
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
    name: "STRIX Agent",
    architecture: "Dueling DQN",
    description:
      "Deep-Q-Network policy over a 13-d state vector emitting one of 5 actions (NO_OP → BLOCK_USER_IP).",
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

export function compositeMetrics(): {
  accuracyPct: number;
  f1: number;
  modelCount: number;
} {
  const xs = MODEL_REGISTRY.filter((m) => m.status === "active");
  const accs = xs
    .map((m) => m.metrics.accuracy)
    .filter((v): v is number => typeof v === "number");
  const f1s = xs
    .map((m) => m.metrics.f1)
    .filter((v): v is number => typeof v === "number");
  const mean = (arr: number[]) =>
    arr.length === 0 ? 0 : arr.reduce((a, b) => a + b, 0) / arr.length;
  return {
    accuracyPct: Math.round(mean(accs) * 1000) / 10,
    f1: Math.round(mean(f1s) * 1000) / 1000,
    modelCount: xs.length,
  };
}

/**
 * Match a registry entry to the live `/monitoring/models` row. The API
 * uses short names ("ae", "vae", …); we look for an overlap with the
 * first token of the display name.
 */
export function findLiveRow<T extends { name: string }>(
  entry: ModelMetrics,
  liveRows: T[],
): T | undefined {
  const needle = entry.name.toLowerCase().split(" ")[0];
  return liveRows.find((r) => r.name.toLowerCase().includes(needle));
}
