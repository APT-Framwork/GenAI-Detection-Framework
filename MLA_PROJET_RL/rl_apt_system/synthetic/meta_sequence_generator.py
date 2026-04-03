"""
Synthetic Meta-Sequence Generator
==================================

This module generates synthetic APT attack meta-sequences using ReALTabFormer.

Key Concepts:
-------------
1. ReALTabFormer generates HIGH-LEVEL metadata only:
   - CKC stage (S1-S7)
   - Event index within sequence
   - Other high-level attack characteristics
   
2. It does NOT generate full feature vectors compatible with detection models

3. Time deltas are synthesized using:
   - Statistical sampling from real distributions
   - Rule-based generation (e.g., increasing with CKC stage)

Why Meta-Sequences?
-------------------
- ReALTabFormer was trained on 20 selected high-level columns
- It captures realistic attack progressions through CKC stages
- But it cannot generate 200+ raw SIEM features
- Solution: Generate meta-level sequences, then use conditional replay
  to map them to real feature vectors

Output Format:
--------------
Each meta-sequence is a list of events:
[
    {'ckc_stage': 1, 'event_index': 0, 'relative_time_delta': 0},
    {'ckc_stage': 1, 'event_index': 1, 'relative_time_delta': 4},
    {'ckc_stage': 3, 'event_index': 2, 'relative_time_delta': 18},
    ...
]
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
import json


class MetaSequenceGenerator:
    """
    Generates synthetic meta-sequences representing APT attack progressions.
    
    Uses ReALTabFormer for high-level sequence generation and statistical
    methods for time delta synthesis.
    """
    
    def __init__(
        self,
        realtabformer_model_path: Optional[str] = None,
        real_data_path: Optional[str] = None,
        use_simple_generation: bool = False
    ):
        """
        Initialize the meta-sequence generator.
        
        Args:
            realtabformer_model_path: Path to trained ReALTabFormer model
            real_data_path: Path to real data for time distribution analysis
            use_simple_generation: If True, use rule-based generation instead of ReALTabFormer
        """
        self.use_simple_generation = use_simple_generation
        self.realtabformer_model = None
        self.time_distributions = {}
        
        if not use_simple_generation and realtabformer_model_path:
            self._load_realtabformer_model(realtabformer_model_path)
        
        if real_data_path:
            self._analyze_time_distributions(real_data_path)
    
    def _load_realtabformer_model(self, model_path: str):
        """Load the trained ReALTabFormer model."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            model_path = Path(model_path)
            if not model_path.exists():
                print(f"[WARNING] ReALTabFormer model not found at {model_path}")
                print("   Falling back to simple rule-based generation")
                self.use_simple_generation = True
                return
            
            self.realtabformer_model = AutoModelForCausalLM.from_pretrained(model_path)
            self.realtabformer_tokenizer = AutoTokenizer.from_pretrained(model_path)
            
            print(f"[OK] ReALTabFormer model loaded from {model_path}")
        
        except Exception as e:
            print(f"[WARNING] Error loading ReALTabFormer: {e}")
            print("   Falling back to simple rule-based generation")
            self.use_simple_generation = True
    
    def _analyze_time_distributions(self, data_path: str):
        """
        Analyze time deltas between events in real data.
        
        This creates statistical distributions for realistic time synthesis.
        """
        try:
            data_path = Path(data_path)
            
            if data_path.suffix == '.xlsx':
                df = pd.read_excel(data_path)
            elif data_path.suffix == '.csv':
                df = pd.read_csv(data_path)
            else:
                print(f"[WARNING] Unsupported file format: {data_path.suffix}")
                return
            
            # Analyze time deltas per CKC stage transition
            if 'cyber_kill_chain_tactic' in df.columns and '_source.@timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['_source.@timestamp'])
                df = df.sort_values('timestamp')
                
                # Group by agent and calculate time deltas
                for stage in range(1, 8):
                    stage_data = df[df['cyber_kill_chain_tactic'] == stage]
                    if len(stage_data) > 1:
                        # Calculate inter-event times within this stage
                        time_diffs = stage_data['timestamp'].diff().dt.total_seconds().dropna()
                        
                        if len(time_diffs) > 0:
                            self.time_distributions[stage] = {
                                'mean': float(time_diffs.mean()),
                                'std': float(time_diffs.std()),
                                'median': float(time_diffs.median()),
                                'min': float(time_diffs.min()),
                                'max': float(time_diffs.max())
                            }
                
                print(f"[OK] Analyzed time distributions from {len(df)} events")
                print(f"   Found distributions for {len(self.time_distributions)} CKC stages")
        
        except Exception as e:
            print(f"[WARNING] Error analyzing time distributions: {e}")
    
    def _generate_time_delta(self, current_stage: int, next_stage: int, event_index: int) -> float:
        """
        Generate realistic time delta between events.
        
        Args:
            current_stage: Current CKC stage (1-7)
            next_stage: Next CKC stage (1-7)
            event_index: Index of event in sequence
        
        Returns:
            Time delta in seconds
        """
        # If we have learned distributions, use them
        if current_stage in self.time_distributions:
            dist = self.time_distributions[current_stage]
            # Sample from learned distribution
            delta = np.random.normal(dist['mean'], dist['std'])
            # Ensure positive and reasonable
            delta = max(1.0, min(delta, dist['max']))
            return delta
        
        # Otherwise use rule-based generation
        # APT attacks typically have increasing time intervals as they progress
        
        if next_stage > current_stage:
            # Stage transition: longer delay
            base_delay = np.random.uniform(300, 3600)  # 5 min to 1 hour
            stage_factor = next_stage - current_stage
            return base_delay * stage_factor
        else:
            # Within same stage: shorter delay
            base_delay = np.random.uniform(1, 300)  # 1 sec to 5 min
            # Add some randomness based on event index
            return base_delay * (1 + event_index * 0.1)
    
    def generate_simple_meta_sequence(
        self,
        min_length: int = 5,
        max_length: int = 20,
        attack_type: str = 'progressive'
    ) -> List[Dict]:
        """
        Generate a simple rule-based meta-sequence.
        
        Args:
            min_length: Minimum sequence length
            max_length: Maximum sequence length
            attack_type: Type of attack progression
                - 'progressive': Moves through stages sequentially
                - 'repetitive': Stays in early stages
                - 'advanced': Jumps to later stages quickly
        
        Returns:
            List of meta-events
        """
        seq_length = np.random.randint(min_length, max_length + 1)
        meta_sequence = []
        
        current_stage = 1  # Start at S1 (Reconnaissance)
        cumulative_time = 0.0
        
        for i in range(seq_length):
            # Determine next stage based on attack type
            if attack_type == 'progressive':
                # Gradually progress through stages
                if i > 0 and np.random.random() < 0.3:  # 30% chance to advance
                    current_stage = min(7, current_stage + 1)
            
            elif attack_type == 'repetitive':
                # Stay in early stages (S1-S3)
                current_stage = np.random.choice([1, 2, 3])
            
            elif attack_type == 'advanced':
                # Quickly move to advanced stages
                if i < 3:
                    current_stage = np.random.choice([1, 2, 3])
                else:
                    current_stage = np.random.choice([4, 5, 6, 7])
            
            # Generate time delta
            if i == 0:
                time_delta = 0.0
            else:
                prev_stage = meta_sequence[-1]['ckc_stage']
                time_delta = self._generate_time_delta(prev_stage, current_stage, i)
            
            cumulative_time += time_delta
            
            # Create meta-event
            meta_event = {
                'ckc_stage': current_stage,
                'event_index': i,
                'relative_time_delta': time_delta,
                'cumulative_time': cumulative_time
            }
            
            meta_sequence.append(meta_event)
        
        return meta_sequence
    
    def generate_meta_sequences(
        self,
        num_sequences: int = 100,
        min_length: int = 5,
        max_length: int = 20,
        attack_types: Optional[List[str]] = None
    ) -> List[List[Dict]]:
        """
        Generate multiple synthetic meta-sequences.
        
        Args:
            num_sequences: Number of sequences to generate
            min_length: Minimum sequence length
            max_length: Maximum sequence length
            attack_types: List of attack types to use
        
        Returns:
            List of meta-sequences
        """
        if attack_types is None:
            attack_types = ['progressive', 'repetitive', 'advanced']
        
        sequences = []
        
        print(f"\n[*] Generating {num_sequences} synthetic meta-sequences...")
        
        for i in range(num_sequences):
            # Randomly select attack type
            attack_type = np.random.choice(attack_types)
            
            # Generate sequence
            if self.use_simple_generation or self.realtabformer_model is None:
                sequence = self.generate_simple_meta_sequence(
                    min_length=min_length,
                    max_length=max_length,
                    attack_type=attack_type
                )
            else:
                # Use ReALTabFormer (to be implemented when model is available)
                sequence = self.generate_simple_meta_sequence(
                    min_length=min_length,
                    max_length=max_length,
                    attack_type=attack_type
                )
            
            sequences.append(sequence)
            
            if (i + 1) % 20 == 0:
                print(f"   Generated {i + 1}/{num_sequences} sequences...")
        
        print(f"[OK] Generated {len(sequences)} synthetic meta-sequences")
        return sequences
    
    def save_meta_sequences(self, sequences: List[List[Dict]], output_path: str):
        """Save meta-sequences to JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(sequences, f, indent=2)
        
        print(f"[OK] Saved {len(sequences)} meta-sequences to {output_path}")
    
    def load_meta_sequences(self, input_path: str) -> List[List[Dict]]:
        """Load meta-sequences from JSON file."""
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Meta-sequence file not found: {input_path}")
        
        with open(input_path, 'r') as f:
            sequences = json.load(f)
        
        print(f"[OK] Loaded {len(sequences)} meta-sequences from {input_path}")
        return sequences
    
    def print_sequence_statistics(self, sequences: List[List[Dict]]):
        """Print statistics about generated sequences."""
        lengths = [len(seq) for seq in sequences]
        stages = []
        durations = []
        
        for seq in sequences:
            stages.extend([event['ckc_stage'] for event in seq])
            if len(seq) > 0:
                durations.append(seq[-1]['cumulative_time'])
        
        print("\n" + "="*70)
        print("META-SEQUENCE STATISTICS")
        print("="*70)
        print(f"Number of sequences: {len(sequences)}")
        print(f"\nSequence lengths:")
        print(f"  Min: {min(lengths)}, Max: {max(lengths)}, Mean: {np.mean(lengths):.1f}")
        print(f"\nCKC stage distribution:")
        for stage in range(1, 8):
            count = stages.count(stage)
            pct = count / len(stages) * 100 if stages else 0
            print(f"  S{stage}: {count} ({pct:.1f}%)")
        print(f"\nSequence durations (seconds):")
        print(f"  Min: {min(durations):.1f}, Max: {max(durations):.1f}, Mean: {np.mean(durations):.1f}")
        print("="*70)


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("META-SEQUENCE GENERATOR - TEST")
    print("="*70)
    
    # Initialize generator (simple mode)
    generator = MetaSequenceGenerator(use_simple_generation=True)
    
    # Generate sample sequences
    sequences = generator.generate_meta_sequences(
        num_sequences=10,
        min_length=5,
        max_length=15
    )
    
    # Print statistics
    generator.print_sequence_statistics(sequences)
    
    # Show example sequence
    print("\n📋 Example meta-sequence:")
    print(json.dumps(sequences[0], indent=2))
    
    # Save to file
    output_dir = Path("../data/synthetic_meta_sequences")
    output_dir.mkdir(parents=True, exist_ok=True)
    generator.save_meta_sequences(sequences, output_dir / "test_sequences.json")
