from __future__ import annotations

import os
import shutil
import time
from glob import glob
from typing import Any, Dict, Optional, Tuple

from jewelry3d.engines.base import EngineContext
from jewelry3d.engines.cli.runner import run_command


class DreamGaussianEngine:
    name = "dreamgaussian"

    def generate(self, prompt: str, out_path: str, ctx: EngineContext) -> str:
        cfg = ctx.config.get("dreamgaussian") or {}
        if not isinstance(cfg, dict):
            raise ValueError("CONFIG.yaml: dreamgaussian deve essere una mappa YAML")

        repo_dir = cfg.get("repo_dir")
        if not repo_dir:
            raise ValueError("CONFIG.yaml: dreamgaussian.repo_dir mancante")

        repo_dir = os.path.abspath(repo_dir)
        if not os.path.isdir(repo_dir):
            raise FileNotFoundError(f"dreamgaussian.repo_dir non esiste: {repo_dir}")

        dg_config = cfg.get("config", "configs/text.yaml")
        mesh_format = str(cfg.get("mesh_format", "obj")).lower()
        if mesh_format not in ("obj", "glb"):
            raise ValueError("CONFIG.yaml: dreamgaussian.mesh_format deve essere 'obj' oppure 'glb'")

        save_prefix = str(cfg.get("save_prefix", "dg"))
        elevation = cfg.get("elevation", None)

        save_path = _build_save_path(save_prefix, out_path)

        env = os.environ.copy()
        env_overrides = cfg.get("env", {}) or {}
        if not isinstance(env_overrides, dict):
            raise ValueError("CONFIG.yaml: dreamgaussian.env deve essere una mappa YAML")
        for k, v in env_overrides.items():
            env[str(k)] = str(v)

        logs_dir = os.path.join(repo_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        before_ts = time.time()

        cmd1 = [
            "python",
            "main.py",
            "--config",
            dg_config,
            "prompt=" + prompt,
            "save_path=" + save_path,
            "seed=" + str(int(ctx.seed)),
        ]
        if elevation is not None:
            cmd1.append("elevation=" + str(elevation))

        cmd2 = [
            "python",
            "main2.py",
            "--config",
            dg_config,
            "prompt=" + prompt,
            "save_path=" + save_path,
            "mesh_format=" + mesh_format,
        ]

        run_command(cmd1, cwd=repo_dir, env=env, label="DreamGaussian stage1")
        run_command(cmd2, cwd=repo_dir, env=env, label="DreamGaussian stage2")

        produced = _find_latest_mesh(logs_dir, save_path, mesh_format, after_ts=before_ts)
        if produced is None:
            raise FileNotFoundError(
                f"DreamGaussian: output mesh non trovato in {logs_dir} per save_path={save_path}"
            )

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.copyfile(produced, out_path)
        return out_path


def _build_save_path(save_prefix: str, out_path: str) -> str:
    base = os.path.splitext(os.path.basename(out_path))[0]
    base = base.replace("_raw", "")
    return f"{save_prefix}_{base}"


def _find_latest_mesh(logs_dir: str, save_path: str, mesh_format: str, after_ts: float) -> Optional[str]:
    patterns = [
        os.path.join(logs_dir, f"{save_path}*.{mesh_format}"),
        os.path.join(logs_dir, f"*{save_path}*.{mesh_format}"),
    ]

    candidates = []
    for pat in patterns:
        candidates.extend(glob(pat))

    best: Optional[Tuple[str, float]] = None
    for c in candidates:
        try:
            mt = os.path.getmtime(c)
        except OSError:
            continue
        if mt < after_ts:
            continue
        if best is None or mt > best[1]:
            best = (c, mt)

    return best[0] if best else None
