"""One place that knows how to obtain a TFLite interpreter on edge (tflite-runtime / ai-edge-litert) and on a PC (tensorflow)."""
from __future__ import annotations

import importlib


def load_interpreter(model_path: str):
    """Return a TFLite Interpreter for model_path, or raise ImportError if no runtime is installed.
    Other errors (corrupt / incompatible model file) propagate so the caller can decide how to degrade."""
    tried = []
    for mod in ("tflite_runtime.interpreter", "ai_edge_litert.interpreter"):
        try:
            return importlib.import_module(mod).Interpreter(model_path=model_path)
        except ImportError as e:
            tried.append(f"{mod}: {e}")
    try:
        import tensorflow as tf
        return tf.lite.Interpreter(model_path=model_path)
    except (ImportError, AttributeError) as e:     # TF >= 2.20 may not ship tf.lite.Interpreter
        tried.append(f"tensorflow.lite: {e}")
    raise ImportError("No TFLite runtime available. Install tflite-runtime or ai-edge-litert (edge) or tensorflow (PC). Tried: "
                      + "; ".join(tried))
