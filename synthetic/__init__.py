"""
Synthetic Data Package
======================

Provides data loading and sequence generation for the RL APT system.

Components:
- APTDataLoader: Loads real + synthetic datasets, generates timestamps
- MetaSequenceGenerator: Creates attack meta-sequences for training
"""

from .data_loader import APTDataLoader, FEATURE_COLUMNS, CKC_STAGE_MAP
from .meta_sequence_generator import MetaSequenceGenerator

__all__ = [
    'APTDataLoader',
    'MetaSequenceGenerator',
    'FEATURE_COLUMNS',
    'CKC_STAGE_MAP',
]
