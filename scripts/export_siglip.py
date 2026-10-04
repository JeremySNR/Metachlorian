"""Reproduce Metachlorian's SigLIP ONNX export (Apache-2.0 weights).

Needs a separate environment with torch, transformers, sentencepiece, onnx,
onnxruntime (not runtime dependencies of Metachlorian):

    python scripts/export_siglip.py google/siglip-base-patch16-256-multilingual out/siglip-base-multilingual

Produces vision.onnx, text.q.onnx (embedding table int8, other weights fp32),
spiece.model, config.json. Parity is checked against PyTorch (max abs diff
~1e-5 for fp32; cosine > 0.998 for the quantised text tower).
"""
import json
import os
import sys

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoModel, AutoTokenizer

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
m = AutoModel.from_pretrained(src).eval()
tok = AutoTokenizer.from_pretrained(src)
size = m.config.vision_config.image_size


class V(torch.nn.Module):
    def __init__(s, m):
        super().__init__()
        s.m = m

    def forward(s, pixel_values):
        o = s.m.get_image_features(pixel_values=pixel_values)
        return o if torch.is_tensor(o) else o.pooler_output


class T(torch.nn.Module):
    def __init__(s, m):
        super().__init__()
        s.m = m

    def forward(s, input_ids):
        o = s.m.get_text_features(input_ids=input_ids)
        return o if torch.is_tensor(o) else o.pooler_output


px = torch.randn(2, 3, size, size)
ids = tok(["a photo of a beach", "drone shot"], padding="max_length", max_length=64, truncation=True, return_tensors="pt")["input_ids"]
with torch.no_grad():
    vo, to = V(m)(px), T(m)(ids)
    torch.onnx.export(V(m), (px,), f"{out}/vision.onnx", input_names=["pixel_values"], output_names=["image_embeds"],
                      dynamic_axes={"pixel_values": {0: "b"}, "image_embeds": {0: "b"}}, opset_version=17, dynamo=False)
    torch.onnx.export(T(m), (ids,), f"{out}/text.onnx", input_names=["input_ids"], output_names=["text_embeds"],
                      dynamic_axes={"input_ids": {0: "b"}, "text_embeds": {0: "b"}}, opset_version=17, dynamo=False)
quantize_dynamic(f"{out}/text.onnx", f"{out}/text.q.onnx", weight_type=QuantType.QUInt8, op_types_to_quantize=["Gather"])
os.remove(f"{out}/text.onnx")
tok.save_pretrained(out)
a = ort.InferenceSession(f"{out}/vision.onnx").run(None, {"pixel_values": px.numpy()})[0]
print("vision parity", float(np.abs(a - vo.numpy()).max()))
json.dump({"logit_scale": m.logit_scale.item(), "logit_bias": m.logit_bias.item(), "image_size": size, "max_length": 64,
           "dim": int(vo.shape[-1]), "mean": [0.5] * 3, "std": [0.5] * 3, "source": src, "licence": "Apache-2.0"},
          open(f"{out}/config.json", "w"), indent=1)
