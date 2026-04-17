import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

df = pd.read_excel(r'g:\pfe\MLA_PROJET_RL\combined_dataset_final_mal_sum.xlsx')

# Timestamp format
print('Timestamp sample:', df['_source.@timestamp'].iloc[0])
print('Timestamp sample:', df['_source.@timestamp'].iloc[100])
print('Timestamp sample:', df['_source.@timestamp'].iloc[-1])

# Check for our 55 features
from synthetic.data_loader import FEATURE_COLUMNS
found = [c for c in FEATURE_COLUMNS if c in df.columns]
missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
print(f'\nOur 55 features: found {len(found)}, missing {len(missing)}')
if missing:
    print(f'Missing: {missing[:10]}...')

# Machine/agent column
print(f'\nAgent names:', df['_source.agent.name'].unique()[:10] if '_source.agent.name' in df.columns else 'N/A')

# CKC stage distribution
print(f'\nCKC summary:', df['cyber_kill_chain_summary'].value_counts().to_dict())

# Check if data is already sorted by timestamp
ts = pd.to_datetime(df['_source.@timestamp'], format='mixed', dayfirst=False)
print(f'\nTimestamp range: {ts.min()} -> {ts.max()}')
print(f'Is sorted ascending:', ts.is_monotonic_increasing)
print(f'Is sorted descending:', ts.is_monotonic_decreasing)

# How many S7 alerts
s7_count = (df['cyber_kill_chain_summary'] == 'S7').sum()
print(f'\nS7 alerts: {s7_count}')
print(f'So max sequences ending with S7: {s7_count}')
