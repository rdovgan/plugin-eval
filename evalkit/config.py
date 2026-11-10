"""Loads config.yaml, substituting ${VAR} from the environment and .env."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


def load_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _expand(value: Any, env: Dict[str, str]) -> Any:
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            name = m.group(1)
            if name not in env:
                raise SystemExit(f"config: variable ${{{name}}} is set neither in the environment nor in .env")
            return env[name]
        return _VAR.sub(sub, value)
    if isinstance(value, dict):
        return {k: _expand(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, env) for v in value]
    return value


def _path(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


@dataclass
class ModelProfile:
    name: str
    model: str
    env: Dict[str, str] = field(default_factory=dict)

    def public_fingerprint(self) -> Dict[str, str]:
        """What may be written to the manifest and cache key: no tokens."""
        return {"model": self.model, "base_url": self.env.get("ANTHROPIC_BASE_URL", "")}


@dataclass
class PluginProfile:
    name: str
    repo: Path              # git repository the versions come from
    subdir: str             # plugin directory inside the repository
    allow_tools: List[str]  # --allow-tools for this plugin

    @property
    def local_dir(self) -> Path:
        """The current (unversioned) copy of the plugin: for preview and MCP server names."""
        return (self.repo / self.subdir).resolve()


@dataclass
class Config:
    plugins: Dict[str, PluginProfile]
    eval_dir_name: str
    runs: int
    judge_model: str
    timeout_sec: int
    budget_per_invocation: float
    budget_per_day: float
    maven_repo: str
    raw_models: Dict[str, Dict[str, Any]]
    smoke_tags: List[str]
    smoke_runs: int
    concurrency: int = 1

    def plugin(self, name: str) -> PluginProfile:
        if name not in self.plugins:
            raise SystemExit(f"config: plugin '{name}' is not defined. Available: {', '.join(self.plugins)}")
        return self.plugins[name]

    def model(self, name: str) -> ModelProfile:
        """Substitutes ${VAR} only for the selected model, so a missing GLM key does not break a Sonnet run."""
        if name not in self.raw_models:
            raise SystemExit(f"config: model '{name}' is not defined. Available: {', '.join(self.raw_models)}")
        env = {**load_dotenv(ROOT / ".env"), **os.environ}
        m = _expand(self.raw_models[name], env)
        return ModelProfile(name=name, model=m["model"], env={k: str(v) for k, v in (m.get("env") or {}).items()})


def load(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get("PE_CONFIG", ROOT / "config.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    budget = data.get("budget") or {}
    smoke = data.get("smoke") or {}
    default_tools = list(data.get("allow_tools") or [])
    plugins = {
        name: PluginProfile(name=name, repo=_path(p["repo"]), subdir=p.get("subdir", "."),
                            allow_tools=list(p.get("allow_tools", default_tools)))
        for name, p in (data.get("plugins") or {}).items()
    }
    return Config(
        plugins=plugins,
        eval_dir_name=data.get("eval_dir_name", "pe-evals"),
        runs=int(data.get("runs", 3)),
        judge_model=data.get("judge_model", "haiku"),
        timeout_sec=int(data.get("timeout_per_invocation_sec", 7200)),
        budget_per_invocation=float(budget.get("per_invocation_usd", 20)),
        budget_per_day=float(budget.get("per_day_usd", 50)),
        maven_repo=str(_path(data.get("maven_repo_local", "~/.m2/repository"))),
        raw_models=data.get("models") or {},
        smoke_tags=list(smoke.get("tags") or ["smoke"]),
        smoke_runs=int(smoke.get("runs", 1)),
        concurrency=int(data.get("concurrency", 1)),
    )
