"""Minimal numpy-only Silero VAD ONNX wrapper.

The official `silero-vad` PyPI package pulls in torch + torchaudio (~1.5GB)
purely to move tensors around the ONNX call — the actual inference is
onnxruntime, which the worker already ships (transitive dep of `fastembed`
for RAG embeddings). This reimplements the same state/context bookkeeping
from `silero_vad.utils_vad.OnnxWrapper.__call__` in numpy so the GCP image
doesn't pay the torch cost for a VAD model — see
`docs/ai-streaming-voice-architecture-proposal.md` D191/D538.

Model I/O (silero_vad.onnx, verified via onnxruntime introspection):
  input:  float32 [batch, num_samples]     (256 samples for 8kHz, 512 for 16kHz)
  state:  float32 [2, batch, 128]          (recurrent state, carried across calls)
  sr:     int64    scalar
  output: float32 [batch, 1]               (speech probability)
  stateN: float32 [2, batch, 128]          (updated state)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort

_MODEL_PATH = Path(__file__).parent / "models" / "silero_vad.onnx"

_NUM_SAMPLES = {8000: 256, 16000: 512}
_CONTEXT_SIZE = {8000: 32, 16000: 64}


class SileroVADModel:
    """Stateful, single-stream Silero VAD — one instance per call/session.

    Not thread-safe and not reusable across concurrent streams (mirrors
    `VADDetector`'s own single-session-per-instance contract).
    """

    def __init__(self, sample_rate: int = 8000, model_path: Path | str = _MODEL_PATH) -> None:
        if sample_rate not in _NUM_SAMPLES:
            raise ValueError(f"Silero VAD supports 8000/16000 Hz, got {sample_rate}")
        self._sample_rate = sample_rate
        self._num_samples = _NUM_SAMPLES[sample_rate]
        self._context_size = _CONTEXT_SIZE[sample_rate]

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self._context_size), dtype=np.float32)

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self._context_size), dtype=np.float32)

    @property
    def window_samples(self) -> int:
        """Exact chunk size (in samples) this model expects per call."""
        return self._num_samples

    def predict(self, chunk: np.ndarray) -> float:
        """Return the speech probability (0..1) for exactly one window's
        worth of int16 PCM samples (`window_samples` long)."""
        if chunk.shape[-1] != self._num_samples:
            raise ValueError(
                f"expected exactly {self._num_samples} samples, got {chunk.shape[-1]}"
            )
        x = chunk.astype(np.float32) / 32768.0
        x = x.reshape(1, -1)
        x = np.concatenate([self._context, x], axis=1)

        outputs = self._session.run(
            None,
            {
                "input": x,
                "state": self._state,
                "sr": np.array(self._sample_rate, dtype=np.int64),
            },
        )
        prob, state = outputs
        self._state = state
        self._context = x[:, -self._context_size :]
        return float(prob[0][0])
