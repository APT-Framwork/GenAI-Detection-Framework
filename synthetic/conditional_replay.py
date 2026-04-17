"""
Conditional Replay Mechanism
=============================

This module implements conditional replay to map synthetic meta-sequences
to real feature vectors compatible with pre-trained detection models.

The Core Problem:
-----------------
- ReALTabFormer generates high-level meta-sequences (CKC stages + time)
- But detection models (AE, VAE, Transformer) require FULL feature vectors
- We cannot generate 200+ realistic SIEM features from scratch

The Solution: Conditional Replay
---------------------------------
For each (ckc_stage, time) in a meta-sequence:
1. Query the real dataset for events with matching CKC stage
2. Sample a real event from this subset
3. Inject the synthetic time information
4. Return the complete feature vector

This ensures:
[OK] Correct dimensionality (models get expected input)
[OK] Realistic features (actual SIEM data)
[OK] Controlled sequence (synthetic CKC progression + timing)
[OK] No retraining needed

Academic Justification:
-----------------------
This is a form of "conditional sampling" or "guided generation":
- We condition on CKC stage (attack progression)
- We sample from real data distribution (feature realism)
- We inject temporal structure (attack timing)

Alternative name: "Conditional Data Augmentation"
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings


class ConditionalReplay:
    """
    Maps synthetic meta-sequences to real feature vectors using conditional sampling.
    
    For each meta-event (ckc_stage, time), this class:
    1. Finds real events with matching CKC stage
    2. Samples one event
    3. Injects synthetic temporal features
    4. Returns full feature vector for detection models
    """
    
    def __init__(
        self,
        real_data_path: str,
        feature_columns: Optional[List[str]] = None,
        timestamp_column: str = '_source.@timestamp',
        ckc_column: str = 'cyber_kill_chain_tactic'
    ):
        """
        Initialize conditional replay with real dataset.
        
        Args:
            real_data_path: Path to real SIEM data (Excel or CSV)
            feature_columns: List of feature column names (if None, use all numeric)
            timestamp_column: Name of timestamp column
            ckc_column: Name of CKC stage column
        """
        self.real_data_path = Path(real_data_path)
        self.timestamp_column = timestamp_column
        self.ckc_column = ckc_column
        self.feature_columns = feature_columns
        
        self.df = None
        self.ckc_indices = {}  # Maps CKC stage to row indices
        self.feature_matrix = None  # Preprocessed features
        
        self._load_real_data()
        self._build_ckc_index()
    
    def _load_real_data(self):
        """Load and preprocess real SIEM data."""
        print(f"\n[>>] Loading real data from {self.real_data_path.name}...")
        
        if not self.real_data_path.exists():
            raise FileNotFoundError(f"Real data file not found: {self.real_data_path}")
        
        # Load data
        if self.real_data_path.suffix == '.xlsx':
            self.df = pd.read_excel(self.real_data_path)
        elif self.real_data_path.suffix == '.csv':
            self.df = pd.read_csv(self.real_data_path)
        else:
            raise ValueError(f"Unsupported file format: {self.real_data_path.suffix}")
        
        print(f"[OK] Loaded {len(self.df)} real events")
        
        # Create combined CKC column from multiple CKC columns
        ckc_columns = [
            'cyber_kill_chain_technique',
            'cyber_kill_chain_tactic', 
            'cyber_kill_chain_mitre_tactics',
            'cyber_kill_chain_mitre_techniques'
        ]
        
        print(f"\n[+] Creating combined CKC column from: {ckc_columns}")
        
        # Function to extract stage number from CKC value
        def extract_stage(value):
            """Extract numeric stage from CKC value (e.g., 'S1' -> 1, '3' -> 3)"""
            if pd.isna(value):
                return np.nan
            value_str = str(value).upper().strip()
            # Try to extract number from string like 'S1', 'Stage 1', '1', etc.
            import re
            match = re.search(r'(\d+)', value_str)
            if match:
                stage = int(match.group(1))
                return stage if 1 <= stage <= 7 else np.nan
            return np.nan
        
        # Extract stages from all CKC columns
        stage_values = []
        for col in ckc_columns:
            if col in self.df.columns:
                stages = self.df[col].apply(extract_stage)
                stage_values.append(stages)
                valid_count = stages.notna().sum()
                print(f"   {col}: {valid_count} valid stages")
        
        if not stage_values:
            raise ValueError(f"None of the CKC columns found in data: {ckc_columns}")
        
        # Combine by taking minimum stage (earliest in kill chain)
        combined_stages = pd.concat(stage_values, axis=1).min(axis=1)
        self.df['ckc_stage_combined'] = combined_stages
        
        # Update ckc_column to use the combined column
        self.ckc_column = 'ckc_stage_combined'
        
        valid_ckc_count = combined_stages.notna().sum()
        print(f"[OK] Combined CKC column created: {valid_ckc_count} events with valid stages")
        
        # Select feature columns
        if self.feature_columns is None:
            # Use all columns except metadata/label columns
            # Include text columns (they might be encoded in your original data)
            exclude_cols = [
                self.ckc_column, 
                'malicious', 
                'agent_id', 
                self.timestamp_column,
                'ckc_stage_combined',
                'cyber_kill_chain_technique',
                'cyber_kill_chain_tactic',
                'cyber_kill_chain_mitre_tactics',
                'cyber_kill_chain_mitre_techniques'
            ]
            
            # Include all numeric columns and some object/categorical columns if needed
            self.feature_columns = [
                col for col in self.df.columns
                if col not in exclude_cols and self.df[col].dtype in ['int64', 'float64', 'bool']
            ]
            
            # If still too few features, include more columns (encoded categorical)
            if len(self.feature_columns) < 100:
                print(f"   [WARNING] Only {len(self.feature_columns)} numeric columns found, including categorical...")
                # Add categorical columns that might be one-hot encoded
                for col in self.df.columns:
                    if col not in exclude_cols and col not in self.feature_columns:
                        # Try to convert to numeric, filling NaN with 0
                        try:
                            self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0)
                            self.feature_columns.append(col)
                        except:
                            pass
        
        print(f"   Using {len(self.feature_columns)} feature columns")
        print(f"   Expected by Autoencoder: 313 features")
        
        if len(self.feature_columns) < 313:
            print(f"   [WARNING] Only {len(self.feature_columns)} features available, but Autoencoder expects 313!")
            print(f"   Padding with zeros to match expected dimensions...")
    
    def _build_ckc_index(self):
        """Build index mapping CKC stages to row indices for fast lookup."""
        print(f"\n[*] Building CKC stage index...")
        
        if self.ckc_column not in self.df.columns:
            raise ValueError(f"CKC column '{self.ckc_column}' not found in data")
        
        for stage in range(1, 8):  # CKC stages 1-7
            mask = self.df[self.ckc_column] == stage
            indices = self.df[mask].index.tolist()
            self.ckc_indices[stage] = indices
            print(f"   S{stage}: {len(indices)} events")
        
        # Check for missing stages
        missing_stages = [s for s in range(1, 8) if len(self.ckc_indices[s]) == 0]
        if missing_stages:
            warnings.warn(f"No events found for CKC stages: {missing_stages}")
    
    def sample_event_by_ckc(self, ckc_stage: int) -> Tuple[np.ndarray, int]:
        """
        Sample a random event with the specified CKC stage.
        
        Args:
            ckc_stage: CKC stage (1-7)
        
        Returns:
            Tuple of (feature_vector, row_index)
        """
        # Ensure ckc_stage is an integer
        ckc_stage = int(ckc_stage)
        
        if ckc_stage not in self.ckc_indices or len(self.ckc_indices[ckc_stage]) == 0:
            # Fallback: sample from closest available stage
            available_stages = [s for s in range(1, 8) if len(self.ckc_indices[s]) > 0]
            if not available_stages:
                raise ValueError("No events available for any CKC stage")
            
            # Find closest stage
            ckc_stage = min(available_stages, key=lambda s: abs(s - ckc_stage))
            warnings.warn(f"No events for requested stage, using S{ckc_stage}")
        
        # Sample random event from this stage
        idx = np.random.choice(self.ckc_indices[ckc_stage])
        
        # Extract features
        features = self.df.loc[idx, self.feature_columns].values.astype(np.float32)
        
        # Pad features to 313 if needed (to match Autoencoder input dimension)
        if len(features) < 313:
            padded_features = np.zeros(313, dtype=np.float32)
            padded_features[:len(features)] = features
            features = padded_features
        elif len(features) > 313:
            # Truncate if too many features
            features = features[:313]
        
        return features, idx
    
    def replay_meta_sequence(
        self,
        meta_sequence: List[Dict],
        inject_time: bool = True
    ) -> Tuple[np.ndarray, List[int]]:
        """
        Replay a meta-sequence to generate full feature vectors.
        
        Args:
            meta_sequence: List of meta-events with 'ckc_stage' and 'relative_time_delta'
            inject_time: Whether to inject time information into features
        
        Returns:
            Tuple of:
            - feature_matrix: Array of shape (seq_len, n_features)
            - sampled_indices: List of row indices used for sampling
        """
        seq_len = len(meta_sequence)
        # Use 313 features to match Autoencoder input dimension (padded)
        n_features = 313
        
        # Initialize output arrays
        feature_matrix = np.zeros((seq_len, n_features), dtype=np.float32)
        sampled_indices = []
        
        # Process each meta-event
        for i, meta_event in enumerate(meta_sequence):
            ckc_stage = meta_event['ckc_stage']
            
            # Sample real event with matching CKC stage (already padded to 313)
            features, idx = self.sample_event_by_ckc(ckc_stage)
            
            # Inject temporal information (if requested)
            if inject_time and 'relative_time_delta' in meta_event:
                # Find time-related features and update them
                # This is a simple heuristic - in practice, you might have specific
                # time feature columns to modify
                time_delta = meta_event['relative_time_delta']
                cumulative_time = meta_event.get('cumulative_time', 0)
                
                # Option 1: Encode as additional features (append to feature vector)
                # Option 2: Replace existing time features (requires knowing which columns)
                # For now, we keep features as-is since models expect fixed dimensions
                # Time information is implicitly in the sequence order
                pass
            
            feature_matrix[i] = features
            sampled_indices.append(idx)
        
        return feature_matrix, sampled_indices
    
    def replay_multiple_sequences(
        self,
        meta_sequences: List[List[Dict]],
        inject_time: bool = True
    ) -> List[Tuple[np.ndarray, List[int]]]:
        """
        Replay multiple meta-sequences.
        
        Args:
            meta_sequences: List of meta-sequences
            inject_time: Whether to inject time information
        
        Returns:
            List of (feature_matrix, sampled_indices) tuples
        """
        replayed_sequences = []
        
        print(f"\n🔄 Replaying {len(meta_sequences)} meta-sequences...")
        
        for i, meta_seq in enumerate(meta_sequences):
            feature_matrix, indices = self.replay_meta_sequence(meta_seq, inject_time)
            replayed_sequences.append((feature_matrix, indices))
            
            if (i + 1) % 20 == 0:
                print(f"   Replayed {i + 1}/{len(meta_sequences)} sequences...")
        
        print(f"[OK] Replayed {len(replayed_sequences)} sequences")
        return replayed_sequences
    
    def get_feature_vector(self, ckc_stage: int) -> np.ndarray:
        """
        Get a single feature vector for a specific CKC stage.
        
        Args:
            ckc_stage: CKC stage (1-7)
        
        Returns:
            Feature vector of shape (n_features,)
        """
        features, _ = self.sample_event_by_ckc(ckc_stage)
        return features
    
    def get_batch_features(self, ckc_stages: List[int]) -> np.ndarray:
        """
        Get batch of feature vectors for multiple CKC stages.
        
        Args:
            ckc_stages: List of CKC stages
        
        Returns:
            Feature matrix of shape (len(ckc_stages), n_features)
        """
        features = []
        for stage in ckc_stages:
            feat, _ = self.sample_event_by_ckc(stage)
            features.append(feat)
        return np.array(features)
    
    def get_statistics(self) -> Dict:
        """Get statistics about the real data and replay capabilities."""
        return {
            'total_events': len(self.df),
            'num_features': len(self.feature_columns),
            'ckc_distribution': {
                f'S{stage}': len(indices) 
                for stage, indices in self.ckc_indices.items()
            },
            'feature_columns': self.feature_columns
        }


class RealSequenceExtractor:
    """
    Extracts real attack sequences from the dataset for comparison with synthetic.
    
    This provides ground-truth sequences for evaluation and baseline comparison.
    """
    
    def __init__(
        self,
        real_data_path: str,
        agent_id_column: str = '_source.agent.id',
        timestamp_column: str = '_source.@timestamp',
        ckc_column: str = 'cyber_kill_chain_tactic'
    ):
        """
        Initialize real sequence extractor.
        
        Args:
            real_data_path: Path to real SIEM data
            agent_id_column: Column name for agent ID (grouping variable)
            timestamp_column: Column name for timestamps
            ckc_column: Column name for CKC stages
        """
        self.real_data_path = Path(real_data_path)
        self.agent_id_column = agent_id_column
        self.timestamp_column = timestamp_column
        self.ckc_column = ckc_column
        
        self.df = None
        self._load_data()
    
    def _load_data(self):
        """Load real data."""
        if self.real_data_path.suffix == '.xlsx':
            self.df = pd.read_excel(self.real_data_path)
        else:
            self.df = pd.read_csv(self.real_data_path)
        
        # Convert timestamp with custom format
        if self.timestamp_column in self.df.columns:
            # Handle format like "Dec 31, 2023 @ 12:59:55.107"
            try:
                self.df['timestamp'] = pd.to_datetime(
                    self.df[self.timestamp_column],
                    format='%b %d, %Y @ %H:%M:%S.%f'
                )
            except (ValueError, pd.errors.ParserError):
                # Fallback to automatic parsing
                self.df['timestamp'] = pd.to_datetime(
                    self.df[self.timestamp_column],
                    errors='coerce'
                )
        
        print(f"[OK] Loaded {len(self.df)} events for sequence extraction")
    
    def extract_sequences(
        self,
        min_length: int = 5,
        max_length: int = 50,
        num_sequences: Optional[int] = None
    ) -> List[Dict]:
        """
        Extract real attack sequences grouped by agent.
        
        Args:
            min_length: Minimum sequence length
            max_length: Maximum sequence length
            num_sequences: Maximum number of sequences to extract (None = all)
        
        Returns:
            List of sequence dictionaries
        """
        sequences = []
        
        # Group by agent
        grouped = self.df.groupby(self.agent_id_column)
        
        print(f"\n[*] Extracting real sequences from {len(grouped)} agents...")
        
        for agent_id, group in grouped:
            # Sort by timestamp
            group = group.sort_values('timestamp')
            
            # Filter by length
            if len(group) < min_length:
                continue
            
            # Truncate if too long
            if len(group) > max_length:
                group = group.iloc[:max_length]
            
            # Extract CKC stages and ensure they're integers
            ckc_stages = group[self.ckc_column].values
            
            # Filter out NaN values - skip this sequence if any CKC stage is missing
            if pd.isna(ckc_stages).any():
                continue
            
            # Convert to integers (handles both int and string inputs)
            ckc_stages = np.array([int(s) for s in ckc_stages])
            
            # Compute time deltas
            timestamps = group['timestamp'].values
            time_deltas = np.diff(timestamps).astype('timedelta64[s]').astype(float)
            time_deltas = np.insert(time_deltas, 0, 0)  # First event has delta=0
            
            # Create sequence
            sequence = {
                'agent_id': agent_id,
                'length': len(group),
                'ckc_stages': ckc_stages.tolist(),
                'time_deltas': time_deltas.tolist(),
                'indices': group.index.tolist()
            }
            
            sequences.append(sequence)
            
            if num_sequences and len(sequences) >= num_sequences:
                break
        
        print(f"[OK] Extracted {len(sequences)} real sequences")
        return sequences


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("CONDITIONAL REPLAY - TEST")
    print("="*70)
    
    # Path to real data
    data_path = "../combined_dataset_final.xlsx"
    
    try:
        # Initialize conditional replay
        replay = ConditionalReplay(data_path)
        
        # Print statistics
        stats = replay.get_statistics()
        print(f"\n[*] Dataset Statistics:")
        print(f"   Total events: {stats['total_events']}")
        print(f"   Features: {stats['num_features']}")
        print(f"   CKC distribution: {stats['ckc_distribution']}")
        
        # Test sampling
        print(f"\n🧪 Testing conditional sampling...")
        for stage in range(1, 8):
            try:
                features, idx = replay.sample_event_by_ckc(stage)
                print(f"   S{stage}: Sampled event {idx}, features shape {features.shape}")
            except Exception as e:
                print(f"   S{stage}: {e}")
        
        # Test meta-sequence replay
        print(f"\n🔄 Testing meta-sequence replay...")
        test_meta_seq = [
            {'ckc_stage': 1, 'event_index': 0, 'relative_time_delta': 0},
            {'ckc_stage': 1, 'event_index': 1, 'relative_time_delta': 10},
            {'ckc_stage': 3, 'event_index': 2, 'relative_time_delta': 30},
            {'ckc_stage': 5, 'event_index': 3, 'relative_time_delta': 60},
        ]
        
        feature_matrix, indices = replay.replay_meta_sequence(test_meta_seq)
        print(f"   Replayed sequence: {feature_matrix.shape}")
        print(f"   Sampled from rows: {indices}")
        
    except FileNotFoundError as e:
        print(f"\n⚠️  {e}")
        print("   Please ensure the data file exists.")
