import json
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

try:
    print("Reading notebook...")
    with open('TP3_Synthetic_Augmentation.ipynb', 'r', encoding='utf-8') as f:
        content = f.read()

    print("Replacing strings...")
    content = content.replace('ckc_attack_sequences.xlsx', 'synthetic_benign_malicious_final.xlsx')
    content = content.replace('y_synthetic_all = np.ones(len(X_synthetic_scaled), dtype=int)',
                              'y_synthetic_all = (synthetic_df[\\"ckc_stage\\"] != \\"Benign\\").astype(int).values if \\"ckc_stage\\" in synthetic_df.columns else np.ones(len(X_synthetic_scaled), dtype=int)')

    with open('TP3_Synthetic_Augmentation.ipynb', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Executing notebook... This might take some minutes.")
    nb = nbformat.reads(content, as_version=4)
    ep = ExecutePreprocessor(timeout=1200, kernel_name='python3')
    ep.preprocess(nb, {'metadata': {'path': './'}})

    print("Saving executed notebook...")
    with open('TP3_Synthetic_Augmentation.ipynb', 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)
    
    with open('done.txt', 'w') as f:
        f.write('done')
    print("All done!")
except Exception as e:
    with open('error.txt', 'w') as f:
        f.write(str(e))
    print(f"Error: {e}")
