# Google Colab CLI Patch: `AttributeError: KernelClient`

## Overview

In `google-colab-cli` (v0.6.0), running code execution commands such as `colab exec` or `colab run` can fail with the following traceback:

```text
/site-packages/colab_cli/runtime.py:106 in kernel_client
    self._kernel_client = jupyter_kernel_client.KernelClient(
AttributeError: module 'jupyter_kernel_client' has no attribute 'KernelClient'
```

This occurs because `google-colab-cli` v0.6.0 has an unpinned dependency on `jupyter-kernel-client`. In `jupyter-kernel-client` (v1.0.0+), the client class is named `JupyterKernelClient` rather than `KernelClient`.

---

## Automated Patching

An automated self-healing patch script is provided in [`projects/s3-tiny-stories/patch_colab_cli.py`](file:///home/nicholas/git/nicholaswilde/esp32-sandbox/projects/s3-tiny-stories/patch_colab_cli.py).

To apply the patch at any time:

```bash
# Via Taskfile
cd projects/s3-tiny-stories
task colab-patch

# Or directly via Python
python projects/s3-tiny-stories/patch_colab_cli.py
```

[`colab_runner.py`](file:///home/nicholas/git/nicholaswilde/esp32-sandbox/projects/s3-tiny-stories/colab_runner.py) also checks and applies this fix automatically before executing any tasks.

---

## Manual Patch Instructions

If applying manually to a fresh environment (e.g. `~/.local/share/uv/tools/google-colab-cli/lib/python3.*/site-packages/`):

### 1. Patch `jupyter_kernel_client/__init__.py`

In `<site-packages>/jupyter_kernel_client/__init__.py`, locate:
```python
from jupyter_kernel_client.client import JupyterKernelClient
from jupyter_kernel_client.interfaces import IJupyterKernelClient
```

Add the alias `KernelClient = JupyterKernelClient`:
```python
from jupyter_kernel_client.client import JupyterKernelClient
KernelClient = JupyterKernelClient
from jupyter_kernel_client.interfaces import IJupyterKernelClient
```

### 2. Patch `colab_cli/runtime.py`

In `<site-packages>/colab_cli/runtime.py` (around line 106), locate:
```python
self._kernel_client = jupyter_kernel_client.KernelClient(
    server_url=self.url,
    token=self.token,
    kernel_id=self.kernel_id,
    client_kwargs=client_kwargs,
    headers={
        "X-Colab-Client-Agent": "colab-cli",
        "X-Colab-Runtime-Proxy-Token": self.token,
    },
)
```

Replace with:
```python
_kernel_client_cls = getattr(
    jupyter_kernel_client, "KernelClient", getattr(jupyter_kernel_client, "JupyterKernelClient", None)
)
self._kernel_client = _kernel_client_cls(
    server_url=self.url,
    token=self.token,
    kernel_id=self.kernel_id,
    client_kwargs=client_kwargs,
    headers={
        "X-Colab-Client-Agent": "colab-cli",
        "X-Colab-Runtime-Proxy-Token": self.token,
    },
)
```

### 3. Patch `colab_cli/common.py` (Proxy Token Expiry)

In long-running jobs (> 1 hour), Google Colab's `colab-runtime-proxy-token` (TTL 3600s) expires. Without updating `s.token` and `s.url` from `client.list_assignments()`, `colab download` commands fail with HTTP 404.

In `<site-packages>/colab_cli/common.py`, `sync_sessions()` and `resolve_session()` are patched to automatically sync and refresh expired tokens from active server assignments.

---

## Verification

Verify that the patch is working by executing a one-line test:

```bash
# Provision ephemeral test session and execute code
colab new -s s3-patch-test --gpu T4
echo "print('KernelClient patch working!')" | colab exec -s s3-patch-test
colab stop -s s3-patch-test
```
