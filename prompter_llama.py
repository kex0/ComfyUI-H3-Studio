"""Local llama.cpp session for H3 Studio prompt generation. No toyxyz import."""

from __future__ import annotations

import glob
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

CATALOG_LABEL = "Qwen3.8-27B-Uncensored Q4_K_M"
LOCAL_GGUF_LABEL = "Local GGUF"
CATALOG_REPO = "JonathanColetti/Qwen3.8-27B-Uncensored-GGUF"
CATALOG_FILE = "Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
CATALOG_SIZE = 16810714528
LOCAL_PREFIX = "local:"
LLM_FOLDER = "LLM"
SERVER_READY_SEC = 600.0
CHAT_TIMEOUT_SEC = 1800.0


def llm_roots() -> list[str]:
    try:
        import folder_paths
    except ImportError:
        return []
    if LLM_FOLDER not in folder_paths.folder_names_and_paths:
        folder_paths.add_model_folder_path(
            LLM_FOLDER, os.path.join(folder_paths.models_dir, LLM_FOLDER),
        )
    roots = []
    for path in folder_paths.get_folder_paths(LLM_FOLDER):
        full = os.path.abspath(path)
        os.makedirs(full, exist_ok=True)
        if full not in roots:
            roots.append(full)
    return roots


def _contained(root: str, candidate: str) -> bool:
    try:
        return os.path.commonpath((os.path.abspath(root), os.path.abspath(candidate))) == os.path.abspath(root)
    except ValueError:
        return False


def list_local_ggufs() -> list[tuple[str, str]]:
    found = []
    seen = set()
    for root in llm_roots():
        for path in glob.iglob(os.path.join(root, "**", "*.gguf"), recursive=True):
            if not os.path.isfile(path):
                continue
            full = os.path.abspath(path)
            if full in seen:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            if rel.startswith(".."):
                continue
            seen.add(full)
            found.append((f"{LOCAL_PREFIX}{rel}", rel))
    found.sort(key=lambda item: item[1].lower())
    return found


def model_combo_values() -> list[str]:
    values = [CATALOG_LABEL, LOCAL_GGUF_LABEL]
    for key, _rel in list_local_ggufs():
        if key not in values:
            values.append(key)
    return values


def find_llama_cli() -> str:
    configured = os.environ.get("H3_STUDIO_LLAMA_CLI", "").strip()
    candidates = [configured, shutil.which("llama-cli") or "", shutil.which("llama-cli.exe") or ""]
    try:
        import folder_paths
        user_root = os.path.join(folder_paths.base_path, "user")
        name = "llama-cli.exe" if os.name == "nt" else "llama-cli"
        candidates.extend(glob.glob(os.path.join(user_root, "**", name), recursive=True))
    except ImportError:
        pass
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise RuntimeError(
        "h3_studio: llama-cli was not found. Install llama.cpp or set H3_STUDIO_LLAMA_CLI."
    )


def find_llama_server(explicit="") -> str:
    configured = str(explicit or "").strip() or os.environ.get("H3_STUDIO_LLAMA_SERVER", "").strip()
    candidates = [configured, shutil.which("llama-server") or "", shutil.which("llama-server.exe") or ""]
    try:
        cli = find_llama_cli()
        sibling = "llama-server.exe" if os.name == "nt" else "llama-server"
        candidates.append(os.path.join(os.path.dirname(cli), sibling))
    except RuntimeError:
        pass
    try:
        import folder_paths
        user_root = os.path.join(folder_paths.base_path, "user")
        name = "llama-server.exe" if os.name == "nt" else "llama-server"
        candidates.extend(glob.glob(os.path.join(user_root, "**", name), recursive=True))
    except ImportError:
        pass
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise RuntimeError(
        "h3_studio: llama-server was not found. Install llama.cpp so llama-server is on PATH, "
        "or set the llama_server widget / H3_STUDIO_LLAMA_SERVER. Multi-clip jobs need llama-server."
    )


def find_catalog_gguf() -> str | None:
    for root in llm_roots():
        for path in glob.iglob(os.path.join(root, "**", CATALOG_FILE), recursive=True):
            if os.path.isfile(path):
                return os.path.abspath(path)
    return None


def _download_catalog(progress=None) -> str:
    roots = llm_roots()
    if not roots:
        raise RuntimeError("h3_studio: ComfyUI has no models/LLM directory.")
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "h3_studio: huggingface_hub is required to download the catalog GGUF."
        ) from exc
    dest = roots[0]
    os.makedirs(dest, exist_ok=True)
    stop = threading.Event()

    def monitor():
        last = -1
        while not stop.wait(0.4):
            candidates = glob.glob(os.path.join(dest, "**", "*.incomplete"), recursive=True)
            candidates.append(os.path.join(dest, CATALOG_FILE))
            size = max((os.path.getsize(p) for p in candidates if os.path.isfile(p)), default=0)
            if size != last and progress:
                progress(
                    f"Downloading {CATALOG_FILE}: {size / 1e9:.2f} / {CATALOG_SIZE / 1e9:.2f} GB"
                )
                last = size

    thread = threading.Thread(target=monitor, name="h3-studio-gguf-download", daemon=True)
    thread.start()
    try:
        if progress:
            progress(f"Starting download of {CATALOG_FILE} (~{CATALOG_SIZE / 1e9:.1f} GB)")
        path = hf_hub_download(repo_id=CATALOG_REPO, filename=CATALOG_FILE, local_dir=dest)
        if progress:
            progress("Catalog GGUF download finished")
        return os.path.abspath(path)
    finally:
        stop.set()
        thread.join(timeout=1)


def resolve_gguf(model, gguf_path="", allow_download=False, progress=None) -> str:
    label = str(model or CATALOG_LABEL).strip() or CATALOG_LABEL
    if label.startswith(LOCAL_PREFIX):
        rel = label[len(LOCAL_PREFIX):].replace("/", os.sep)
        for root in llm_roots():
            candidate = os.path.abspath(os.path.join(root, rel))
            if _contained(root, candidate) and os.path.isfile(candidate):
                return candidate
        raise FileNotFoundError(f"h3_studio: local GGUF {rel!r} is not in models/LLM")
    if label == LOCAL_GGUF_LABEL:
        raw = str(gguf_path or "").strip()
        if not raw:
            raise ValueError("h3_studio: set gguf_path when model is Local GGUF")
        if os.path.isfile(raw):
            return os.path.abspath(raw)
        for root in llm_roots():
            candidate = os.path.abspath(os.path.join(root, raw.replace("/", os.sep)))
            if _contained(root, candidate) and os.path.isfile(candidate):
                return candidate
        raise FileNotFoundError(f"h3_studio: local GGUF not found: {raw}")
    if label != CATALOG_LABEL:
        raise ValueError(f"h3_studio: unknown prompter model {label!r}")
    existing = find_catalog_gguf()
    if existing:
        return existing
    if not allow_download:
        raise FileNotFoundError(
            f"h3_studio: {CATALOG_FILE} is not in models/LLM. Enable allow_download "
            "or pick Local GGUF / a scanned file."
        )
    return _download_catalog(progress)


def unload_comfy_models():
    try:
        import comfy.model_management as model_management
        model_management.unload_all_models()
        model_management.soft_empty_cache(force=True)
    except (ImportError, AttributeError):
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class LlamaServerSession:
    def __init__(self, executable, model_path, n_ctx=16384, n_gpu_layers=99):
        self.executable = executable
        self.model_path = model_path
        self.n_ctx = int(n_ctx)
        self.n_gpu_layers = int(n_gpu_layers)
        self.port = _free_port()
        self.process = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout=SERVER_READY_SEC, progress=None):
        command = [
            self.executable, "-m", self.model_path,
            "--host", "127.0.0.1", "--port", str(self.port),
            "-c", str(self.n_ctx), "-ngl", str(self.n_gpu_layers),
            "-np", "1", "--no-webui", "--log-disable", "--jinja",
            "--chat-template-kwargs", '{"enable_thinking":false}',
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        deadline = time.monotonic() + float(timeout)
        started = time.monotonic()
        last_status = -2
        while time.monotonic() < deadline:
            elapsed = int(time.monotonic() - started)
            if progress is not None and elapsed >= last_status + 2:
                progress(f"Loading GGUF into llama-server — {elapsed}s")
                last_status = elapsed
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"h3_studio: llama-server exited during startup with code {self.process.returncode}"
                )
            try:
                with urllib.request.urlopen(f"{self.base_url}/health", timeout=2) as resp:
                    if 200 <= int(resp.status) < 300:
                        return
            except (urllib.error.URLError, TimeoutError, OSError):
                try:
                    with urllib.request.urlopen(f"{self.base_url}/v1/models", timeout=2) as resp:
                        if 200 <= int(resp.status) < 300:
                            return
                except (urllib.error.URLError, TimeoutError, OSError):
                    pass
            time.sleep(0.4)
        self.close()
        raise RuntimeError("h3_studio: llama-server did not become ready within 10 minutes")

    def chat(self, messages, temperature=0.6, max_tokens=1800) -> str:
        payload = json.dumps({
            "model": os.path.basename(self.model_path),
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=CHAT_TIMEOUT_SEC) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"h3_studio: llama-server HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"h3_studio: llama-server request failed: {exc}") from exc
        try:
            return str(body["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("h3_studio: llama-server returned an unexpected chat response") from exc

    def close(self):
        proc = self.process
        self.process = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def llama_cli_complete(executable, model_path, system_prompt, user_prompt, n_ctx=16384,
                       n_gpu_layers=99, temperature=0.6, max_tokens=1800) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="h3_studio_prompter_") as temp_dir:
        system_file = os.path.join(temp_dir, "system.txt")
        user_file = os.path.join(temp_dir, "user.txt")
        with open(system_file, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(system_prompt)
        with open(user_file, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(user_prompt)
        command = [
            executable, "-m", model_path, "-sysf", system_file, "-f", user_file,
            "--jinja", "--chat-template-kwargs", '{"enable_thinking":false}',
            "--single-turn", "--no-display-prompt", "--no-show-timings", "--simple-io",
            "--no-context-shift", "--log-disable",
            "-c", str(int(n_ctx)), "-n", str(int(max_tokens)),
            "-ngl", str(int(n_gpu_layers)), "--temp", str(float(temperature)),
        ]
        try:
            completed = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", timeout=CHAT_TIMEOUT_SEC,
                creationflags=flags, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("h3_studio: llama-cli timed out after 30 minutes") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or "")[-800:]
            raise RuntimeError(f"h3_studio: llama-cli exited {completed.returncode}. {tail}")
        text = (completed.stdout or "").strip()
        if not text:
            raise RuntimeError("h3_studio: llama-cli returned empty output")
        return text


def register_prompter_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    instance = getattr(PromptServer, "instance", None)
    if instance is None or getattr(instance, "_h3_studio_prompter_routes", False):
        return
    instance._h3_studio_prompter_routes = True

    @instance.routes.get("/h3_studio_prompter/models")
    async def h3_studio_prompter_models(_request):
        values = model_combo_values()
        return web.json_response({"models": values})


register_prompter_routes()
