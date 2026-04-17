"""Inspect the GNN model checkpoint in detail."""
import torch

fpath = r'g:\pfe\MLA_PROJET_RL\models\gnn_propagation_best_no_rule.pth'
cp = torch.load(fpath, map_location='cpu', weights_only=False)
print(f"Type: {type(cp)}")
for k, v in cp.items():
    if hasattr(v, 'shape'):
        print(f"  {k}: {v.shape}")
    else:
        print(f"  {k}: {v}")
