import os
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image


ATOMIC_SPECIFIERS = ("self_attn_q_pre", "self_attn_kv_pre", "cross_attn_q_pre", "mlp_fc1_pre")
PRESETS = {
    "self_attn_q": ("self_attn_q_pre",),
    "self_attn_qkv": ("self_attn_q_pre", "self_attn_kv_pre"),
    "self_attn_qkv_cross_q": ("self_attn_q_pre", "self_attn_kv_pre", "cross_attn_q_pre"),
}
ASPP_DEFAULT_DILATIONS = (1, 2, 4, 8)


def _gn(channels: int) -> nn.GroupNorm:
    groups = 8
    while groups > 1 and channels % groups != 0:
        groups //= 2
    return nn.GroupNorm(groups, channels)


class _ResBlock(nn.Module):
    def __init__(self, ch: int):
        super().__init__()
        self.norm1 = _gn(ch)
        self.conv1 = nn.Conv2d(ch, ch, 3, padding=1)
        self.norm2 = _gn(ch)
        self.conv2 = nn.Conv2d(ch, ch, 3, padding=1)

    def forward(self, x):
        h = self.conv1(F.silu(self.norm1(x)))
        return x + self.conv2(F.silu(self.norm2(h)))


class _ASPP(nn.Module):
    def __init__(self, ch: int, dilations=ASPP_DEFAULT_DILATIONS):
        super().__init__()
        self.branches = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(ch, ch, 1 if d == 1 else 3, padding=0 if d == 1 else d, dilation=d),
                _gn(ch),
                nn.SiLU(),
            )
            for d in dilations
        ])
        self.global_conv = nn.Sequential(nn.Conv2d(ch, ch, 1), _gn(ch), nn.SiLU())
        self.proj = nn.Sequential(nn.Conv2d(ch * (len(dilations) + 1), ch, 1), _gn(ch), nn.SiLU())

    def forward(self, x):
        h, w = x.shape[-2:]
        outs = [branch(x) for branch in self.branches]
        pooled = self.global_conv(F.adaptive_avg_pool2d(x, 1))
        outs.append(F.interpolate(pooled, size=(h, w), mode="bilinear", align_corners=False))
        return self.proj(torch.cat(outs, dim=1))


class _Conditioning1(nn.Module):
    def __init__(self, cond_dim, cond_emb_dim, n_resblocks, use_aspp, aspp_dilations, cond_in_channels):
        super().__init__()
        half = cond_dim // 2
        self.conv1 = nn.Conv2d(cond_in_channels, half, 4, stride=4)
        self.norm1 = _gn(half)
        self.conv2 = nn.Conv2d(half, half, 3, padding=1)
        self.norm2 = _gn(half)
        self.conv3 = nn.Conv2d(half, cond_dim, 4, stride=4)
        self.norm3 = _gn(cond_dim)
        self.resblocks = nn.ModuleList([_ResBlock(cond_dim) for _ in range(n_resblocks)])
        self.aspp = _ASPP(cond_dim, aspp_dilations) if use_aspp else None
        self.proj = nn.Conv2d(cond_dim, cond_emb_dim, 1)
        self.out_norm = nn.LayerNorm(cond_emb_dim)

    def forward(self, x):
        h = F.silu(self.norm1(self.conv1(x)))
        h = F.silu(self.norm2(self.conv2(h)))
        h = F.silu(self.norm3(self.conv3(h)))
        for block in self.resblocks:
            h = block(h)
        if self.aspp is not None:
            h = self.aspp(h)
        h = self.proj(h)
        b, c, hh, ww = h.shape
        return self.out_norm(h.view(b, c, hh * ww).permute(0, 2, 1).contiguous())


class _LLLiteModule(nn.Module):
    def __init__(self, name: str, org_module: nn.Linear, cond_emb_dim: int, mlp_dim: int, multiplier: float):
        super().__init__()
        self.lllite_name = name
        self.org_module = [org_module]
        self.multiplier = multiplier
        self.down = nn.Linear(org_module.in_features, mlp_dim)
        self.mid = nn.Linear(mlp_dim + cond_emb_dim, mlp_dim)
        self.cond_to_film = nn.Linear(cond_emb_dim, mlp_dim * 2)
        self.up = nn.Linear(mlp_dim, org_module.in_features)
        self.cond_emb = None
        self.org_forward = None
        self.layer_idx = -1
        self._depth_embeds_ref = []

    def apply_to(self):
        if self.org_forward is None:
            self.org_forward = self.org_module[0].forward
            self.org_module[0].forward = self.forward

    def restore(self):
        if self.org_forward is not None:
            self.org_module[0].forward = self.org_forward
            self.org_forward = None

    def forward(self, x):
        if self.multiplier == 0.0 or self.cond_emb is None:
            return self.org_forward(x)
        orig_shape = x.shape
        is_5d = x.dim() == 5
        if is_5d:
            x = x.reshape(orig_shape[0], orig_shape[1] * orig_shape[2] * orig_shape[3], orig_shape[4])

        cond = self.cond_emb
        if x.shape[0] != cond.shape[0]:
            if x.shape[0] % cond.shape[0] != 0:
                return self.org_forward(x.reshape(orig_shape) if is_5d else x)
            cond = cond.repeat(x.shape[0] // cond.shape[0], 1, 1)
        if x.shape[1] != cond.shape[1]:
            return self.org_forward(x.reshape(orig_shape) if is_5d else x)

        dtype = self.down.weight.dtype
        x_proc = x.to(dtype) if x.dtype != dtype else x
        cond = cond.to(device=x.device, dtype=dtype)
        if self._depth_embeds_ref:
            cond = cond + self._depth_embeds_ref[0][self.layer_idx].to(device=x.device, dtype=dtype)

        h = F.silu(self.down(x_proc))
        gamma, beta = self.cond_to_film(cond).chunk(2, dim=-1)
        h = self.mid(torch.cat([cond, h], dim=-1))
        out = self.up(F.silu(h * (1 + gamma) + beta)) * self.multiplier
        y = self.org_forward(x + out.to(x.dtype))
        if is_5d:
            y = y.reshape(orig_shape[0], orig_shape[1], orig_shape[2], orig_shape[3], -1)
        return y


class _ControlNetLLLiteDiT(nn.Module):
    def __init__(
        self,
        dit,
        cond_emb_dim,
        mlp_dim,
        target_layers,
        multiplier,
        cond_dim,
        cond_resblocks,
        use_aspp,
        aspp_dilations,
        cond_in_channels,
        inpaint_masked_input,
    ):
        super().__init__()
        self.multiplier = multiplier
        self.cond_in_channels = cond_in_channels
        self.inpaint_masked_input = inpaint_masked_input
        self.conditioning1 = _Conditioning1(
            cond_dim, cond_emb_dim, cond_resblocks, use_aspp, aspp_dilations, cond_in_channels
        )
        self.lllite_modules = nn.ModuleList(
            self._create_modules(dit, cond_emb_dim, mlp_dim, _parse_target_layers(target_layers), multiplier)
        )
        if not self.lllite_modules:
            raise ValueError("No matching Anima DiT layers found for LLLite")
        self.depth_embeds = nn.Parameter(torch.zeros(len(self.lllite_modules), cond_emb_dim))
        for i, module in enumerate(self.lllite_modules):
            module.layer_idx = i
            module._depth_embeds_ref = [self.depth_embeds]

    def _create_modules(self, dit, cond_emb_dim, mlp_dim, atomics, multiplier):
        modules = []
        for name, module in dit.named_modules():
            if "llm_adapter" in name:
                continue
            cls = module.__class__.__name__
            if cls == "Attention" and hasattr(module, "is_selfattn"):
                for child_name, child in module.named_children():
                    if not isinstance(child, nn.Linear) or "output_proj" in child_name:
                        continue
                    is_self = bool(module.is_selfattn)
                    wanted = (
                        (is_self and child_name == "q_proj" and "self_attn_q_pre" in atomics)
                        or (is_self and child_name in ("k_proj", "v_proj") and "self_attn_kv_pre" in atomics)
                        or (not is_self and child_name == "q_proj" and "cross_attn_q_pre" in atomics)
                    )
                    if wanted:
                        modules.append(_LLLiteModule(f"lllite_dit.{name}.{child_name}".replace(".", "_"), child, cond_emb_dim, mlp_dim, multiplier))
            elif cls == "GPT2FeedForward" and "mlp_fc1_pre" in atomics:
                child = getattr(module, "layer1", None)
                if isinstance(child, nn.Linear):
                    modules.append(_LLLiteModule(f"lllite_dit.{name}.layer1".replace(".", "_"), child, cond_emb_dim, mlp_dim, multiplier))
        return modules

    def set_cond_image(self, cond_image):
        cond = self.conditioning1(cond_image)
        for module in self.lllite_modules:
            module.cond_emb = cond

    def clear_cond_image(self):
        for module in self.lllite_modules:
            module.cond_emb = None

    def set_multiplier(self, multiplier: float):
        self.multiplier = multiplier
        for module in self.lllite_modules:
            module.multiplier = multiplier

    def apply_to(self):
        for module in self.lllite_modules:
            module.apply_to()

    def restore(self):
        for module in self.lllite_modules:
            module.restore()


def _parse_target_layers(spec: str):
    parts = PRESETS.get(spec, tuple(p.strip() for p in spec.split(",") if p.strip()))
    bad = [p for p in parts if p not in ATOMIC_SPECIFIERS]
    if bad:
        raise ValueError(f"Unsupported LLLite target layers: {bad}")
    return tuple(a for a in ATOMIC_SPECIFIERS if a in parts)


def _read_metadata(path: str) -> dict:
    if os.path.splitext(path)[1] != ".safetensors":
        return {}
    from safetensors import safe_open

    with safe_open(path, framework="pt") as f:
        return f.metadata() or {}


def _load_weights(lllite: _ControlNetLLLiteDiT, path: str):
    from safetensors.torch import load_file

    sd = load_file(path, device="cpu") if path.endswith(".safetensors") else torch.load(path, map_location="cpu")
    if any(k.startswith("lllite_modules.") for k in sd):
        raise ValueError("Legacy LLLite weights are not supported")

    name_to_idx = {m.lllite_name: i for i, m in enumerate(lllite.lllite_modules)}
    converted = {}
    depth = {}
    for k, v in sd.items():
        if k.startswith("lllite_conditioning1."):
            converted["conditioning1." + k[len("lllite_conditioning1."):]] = v
        elif k.endswith(".depth_embed"):
            name = k[:-len(".depth_embed")]
            if name in name_to_idx:
                depth[name_to_idx[name]] = v
        else:
            head, dot, tail = k.partition(".")
            if dot and head in name_to_idx:
                converted[f"lllite_modules.{name_to_idx[head]}.{tail}"] = v

    if depth:
        if len(depth) != len(name_to_idx):
            raise ValueError("LLLite depth embeddings do not match this Anima DiT")
        converted["depth_embeds"] = torch.stack([depth[i] for i in range(len(depth))], dim=0)
    if not converted:
        raise ValueError("Invalid Anima LLLite weights")
    info = lllite.load_state_dict(converted, strict=False)
    if info.missing_keys:
        raise ValueError("LLLite weights do not match this Anima DiT")


def _target_cond_hw(latent_h: int, latent_w: int, patch_spatial: int):
    padded_h = ((latent_h + patch_spatial - 1) // patch_spatial) * patch_spatial
    padded_w = ((latent_w + patch_spatial - 1) // patch_spatial) * patch_spatial
    return padded_h * 8, padded_w * 8


def _pil_rgb_tensor(image: Image.Image) -> torch.Tensor:
    import numpy as np

    arr = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)


def _pil_mask_tensor(mask: Image.Image) -> torch.Tensor:
    import numpy as np

    arr = np.array(mask.convert("L"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0).unsqueeze(0)


def _build_cond(rgb_source, mask_source, latent_h, latent_w, device, dtype, patch_spatial, masked_input):
    target_h, target_w = _target_cond_hw(latent_h, latent_w, patch_spatial)
    rgb = F.interpolate(rgb_source.to(device=device), size=(target_h, target_w), mode="bicubic", align_corners=False)
    rgb = rgb.clamp(0, 1).to(dtype=dtype) * 2.0 - 1.0
    mask = F.interpolate(mask_source.to(device=device), size=(target_h, target_w), mode="nearest")
    mask = (mask >= 0.5).to(dtype=dtype)
    if masked_input:
        rgb = rgb * (mask < 0.5).to(dtype)
    return torch.cat([rgb, mask * 2.0 - 1.0], dim=1)


def apply_lllite_inpaint(
    pipe,
    lllite_path: str,
    control_image: Image.Image,
    mask_image: Image.Image,
    strength: float = 1.0,
    start_percent: float = 0.0,
    end_percent: float = 1.0,
):
    if mask_image is None:
        raise ValueError("mask_image is required for LLLite inpainting")
    if not os.path.isfile(lllite_path):
        raise FileNotFoundError(f"LLLite weights not found: {lllite_path}")
    if not 0.0 <= start_percent <= end_percent <= 1.0:
        raise ValueError("LLLite percent range must be 0.0 <= start <= end <= 1.0")

    meta = _read_metadata(lllite_path)
    if meta.get("lllite.version") != "2" or int(meta.get("lllite.cond_in_channels", 3)) != 4:
        raise ValueError("Use Anima LLLite v2 inpainting weights")

    use_aspp = str(meta.get("lllite.use_aspp", "false")).lower() == "true"
    aspp_dilations = tuple(int(d) for d in meta.get("lllite.aspp_dilations", "").split(",") if d.strip())
    lllite = _ControlNetLLLiteDiT(
        pipe.dit,
        cond_emb_dim=int(meta.get("lllite.cond_emb_dim", 32)),
        mlp_dim=int(meta.get("lllite.mlp_dim", 64)),
        target_layers=meta.get("lllite.target_atomics", meta.get("lllite.target_layers", "self_attn_q")),
        multiplier=strength,
        cond_dim=int(meta.get("lllite.cond_dim", 64)),
        cond_resblocks=int(meta.get("lllite.cond_resblocks", 1)),
        use_aspp=use_aspp,
        aspp_dilations=aspp_dilations or ASPP_DEFAULT_DILATIONS,
        cond_in_channels=4,
        inpaint_masked_input=str(meta.get("lllite.inpaint_masked_input", "false")).lower() == "true",
    )
    _load_weights(lllite, lllite_path)
    lllite.eval().requires_grad_(False)

    original_model_fn = pipe.model_fn
    rgb_source = _pil_rgb_tensor(control_image)
    mask_source = _pil_mask_tensor(mask_image)
    patch_spatial = int(getattr(pipe.dit, "patch_spatial", 2))
    cache = {"key": None, "cond": None}

    def patched_model_fn(*args, **kwargs):
        progress_id = int(kwargs.get("progress_id", 0))
        total = max(int(kwargs.get("num_inference_steps", 1)) - 1, 1)
        percent = progress_id / total
        if percent < start_percent or percent > end_percent:
            return original_model_fn(*args, **kwargs)

        latents = kwargs.get("latents")
        latent_h, latent_w = int(latents.shape[-2]), int(latents.shape[-1])
        device = latents.device
        if device.type != "cuda":
            raise RuntimeError("LLLite inpainting requires CUDA")
        dtype = torch.bfloat16
        key = (latent_h, latent_w, device, dtype)
        if cache["key"] != key:
            cache["cond"] = _build_cond(
                rgb_source,
                mask_source,
                latent_h,
                latent_w,
                device,
                dtype,
                patch_spatial,
                lllite.inpaint_masked_input,
            )
            cache["key"] = key

        lllite.to(device=device, dtype=dtype)
        lllite.set_multiplier(strength)
        lllite.set_cond_image(cache["cond"])
        lllite.apply_to()
        try:
            return original_model_fn(*args, **kwargs)
        finally:
            lllite.restore()
            lllite.clear_cond_image()

    pipe.model_fn = patched_model_fn

    def unpatch():
        lllite.restore()
        lllite.clear_cond_image()
        if pipe.model_fn is patched_model_fn:
            pipe.model_fn = original_model_fn

    return unpatch
