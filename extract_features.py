"""Extract TOP_25_FEATURES from CKC_Generation notebook."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'g:\pfe\MLA_PROJET_RL\CKC_Generation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        if 'TOP_25_FEATURES = [' in src:
            for line in cell['source']:
                print(line, end='')
            print()
            break
