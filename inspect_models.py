"""Inspect the new model checkpoints."""
import torch
import os

models_dir = r'g:\pfe\MLA_PROJET_RL\models'

for fname in os.listdir(models_dir):
    if fname.endswith('.pth'):
        fpath = os.path.join(models_dir, fname)
        print(f"\n{'='*60}")
        print(f"MODEL: {fname}")
        print(f"{'='*60}")
        cp = torch.load(fpath, map_location='cpu', weights_only=False)
        print(f"Type: {type(cp)}")
        if isinstance(cp, dict):
            for k, v in cp.items():
                if hasattr(v, 'shape'):
                    print(f"  {k}: {v.shape}")
                elif isinstance(v, dict):
                    print(f"  {k}: (dict with {len(v)} keys)")
                    for kk, vv in v.items():
                        if hasattr(vv, 'shape'):
                            print(f"    {kk}: {vv.shape}")
                        else:
                            print(f"    {kk}: {vv}")
                else:
                    print(f"  {k}: {v}")
