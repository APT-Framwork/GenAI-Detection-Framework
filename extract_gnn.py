"""Extract GNN model class and feature prep from GNN_Network_Propagation notebook."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'g:\pfe\MLA_PROJET_RL\GNN_Network_Propagation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'class APTPropagationGNN' in src or 'class APT' in src:
            print(f"=== Cell {i} (GNN Model Class) ===")
            for line in cell['source']:
                print(line, end='')
            print("\n===END===\n")
        # Also find feature preparation
        if 'X_sel' in src and ('FEATURE_COLS' in src or 'feature_cols' in src.lower() or 'top_25' in src.lower()):
            print(f"=== Cell {i} (Feature Prep) ===")
            for line in cell['source'][:50]:
                print(line, end='')
            print("\n===END===\n")
        # Also find the configuration cell with window sizes
        if 'INTRA_WINDOW' in src and 'CROSS_WINDOW' in src:
            print(f"=== Cell {i} (Config) ===")
            for line in cell['source']:
                print(line, end='')
            print("\n===END===\n")
