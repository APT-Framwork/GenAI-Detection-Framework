"""DQN loader (Q-network checkpoint format).

Checkpoint layout (verified against apps/models/rl_agent.pth):
    {
      'q_network_state_dict': { 'network.0.weight': ..., 'network.6.bias': ... },
      'target_network_state_dict': ...,
      'optimizer_state_dict': ...,
      'epsilon': float,
      'steps_done': int,
      'episodes_done': int,
      'hyperparameters': { 'state_dim': 13, 'action_dim': 5, ... }
    }

We only load `q_network_state_dict` and ignore optimizer/target/epsilon —
those are training-time artifacts. At inference we always do greedy
action selection (argmax over Q-values).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from strix_api.adapters.model_loaders._arch import QNetwork
from strix_api.api.errors import ModelRegistryError
from strix_api.core.constants import DQN_ACTION_SPACE, STATE_VECTOR_DIM
from strix_api.core.enums import DqnAction
from strix_api.observability import dqn_action_total, get_logger

log = get_logger("strix_api.adapters.model_loaders.dqn")


@dataclass(frozen=True)
class DqnDecision:
    action: DqnAction
    q_values: np.ndarray  # (5,)


class DqnLoader:
    """Greedy action selection — always argmax(Q). Epsilon is training-only."""

    def __init__(
        self,
        model: QNetwork,
        *,
        device: torch.device,
        version: str,
        episodes_done: int = 0,
    ) -> None:
        self._model = model
        self._device = device
        self.version = version
        self.episodes_done = episodes_done

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_state_dim: int = STATE_VECTOR_DIM,
        expected_action_dim: int = DQN_ACTION_SPACE,
        device: str = "cpu",
        version: str = "v1",
    ) -> DqnLoader:
        if not path.exists():
            raise ModelRegistryError(f"DQN checkpoint missing: {path}")

        dev = torch.device(device)
        ckpt = torch.load(path, map_location=dev, weights_only=False)
        if not isinstance(ckpt, dict):
            raise ModelRegistryError(
                f"DQN checkpoint top-level type {type(ckpt).__name__}, expected dict"
            )
        if "q_network_state_dict" not in ckpt:
            raise ModelRegistryError(
                "DQN checkpoint missing 'q_network_state_dict' — wrong format?"
            )

        sd = ckpt["q_network_state_dict"]
        first_w = sd.get("network.0.weight")
        if first_w is None:
            raise ModelRegistryError("DQN q_network state_dict missing 'network.0.weight'")
        actual_state = first_w.shape[1]
        if actual_state != expected_state_dim:
            raise ModelRegistryError(f"DQN state_dim={actual_state}, expected {expected_state_dim}")

        # Last linear layer's output gives action_dim. Find it (highest index).
        last_w_key = max(
            (k for k in sd if k.startswith("network.") and k.endswith(".weight")),
            key=lambda k: int(k.split(".")[1]),
        )
        actual_action = sd[last_w_key].shape[0]
        if actual_action != expected_action_dim:
            raise ModelRegistryError(
                f"DQN action_dim={actual_action}, expected {expected_action_dim}"
            )

        model = QNetwork(state_dim=actual_state, action_dim=actual_action)
        model.load_state_dict(sd, strict=True)
        model.to(dev).eval()

        hp = ckpt.get("hyperparameters") or {}
        episodes_done = int(ckpt.get("episodes_done", 0))

        log.info(
            "dqn_loaded",
            path=str(path),
            state_dim=actual_state,
            action_dim=actual_action,
            episodes_done=episodes_done,
            hyperparameters=hp,
            device=str(dev),
            version=version,
        )

        loader = cls(model, device=dev, version=version, episodes_done=episodes_done)
        loader._warmup()
        return loader

    @torch.inference_mode()
    def decide(self, state: np.ndarray) -> DqnDecision:
        """Greedy action over a single state vector."""
        if state.shape != (STATE_VECTOR_DIM,):
            raise ValueError(f"DQN expects state shape ({STATE_VECTOR_DIM},); got {state.shape}")
        x = torch.from_numpy(state.astype(np.float32, copy=False)).to(self._device)
        q = self._model(x.unsqueeze(0))[0]  # (5,)
        action_idx = int(torch.argmax(q).item())
        action = DqnAction(action_idx)
        dqn_action_total.labels(action_name=action.name).inc()
        return DqnDecision(
            action=action,
            q_values=q.cpu().numpy().astype(np.float32, copy=False),
        )

    @torch.inference_mode()
    def decide_batch(self, states: np.ndarray) -> list[DqnDecision]:
        """Greedy actions over a batch of state vectors. Used by the inference batcher."""
        if states.ndim != 2 or states.shape[1] != STATE_VECTOR_DIM:
            raise ValueError(f"DQN expects (B, {STATE_VECTOR_DIM}); got {states.shape}")
        x = torch.from_numpy(states.astype(np.float32, copy=False)).to(self._device)
        q = self._model(x)  # (B, 5)
        actions = torch.argmax(q, dim=-1)
        decisions: list[DqnDecision] = []
        for i in range(states.shape[0]):
            a_idx = int(actions[i].item())
            action = DqnAction(a_idx)
            dqn_action_total.labels(action_name=action.name).inc()
            decisions.append(
                DqnDecision(
                    action=action,
                    q_values=q[i].cpu().numpy().astype(np.float32, copy=False),
                )
            )
        return decisions

    def _warmup(self) -> None:
        self.decide_batch(np.zeros((2, STATE_VECTOR_DIM), dtype=np.float32))


__all__ = ["DqnDecision", "DqnLoader"]
