from __future__ import annotations

"""HTTP client for the ComfyUI API.

Communicates with a running ComfyUI instance to submit workflows,
poll for results, and fetch generated images. Uses only stdlib.
"""

import json
import time
import urllib.request
import urllib.error
import uuid


class ComfyUIClient:
    """Client for the ComfyUI HTTP API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    def is_available(self) -> bool:
        """Check if ComfyUI is reachable."""
        try:
            self.get_system_stats()
            return True
        except Exception:
            return False

    def get_system_stats(self) -> dict:
        """GET /system_stats — system info, VRAM usage, queue depth."""
        return self._get("/system_stats")

    def get_object_info(self) -> dict:
        """GET /object_info — list all available ComfyUI nodes."""
        return self._get("/object_info")

    def get_queue(self) -> dict:
        """GET /queue — current queue state (running + pending)."""
        return self._get("/queue")

    def submit_workflow(self, workflow: dict) -> str:
        """POST /prompt — queue a workflow for execution.

        Args:
            workflow: The ComfyUI workflow JSON (node graph).

        Returns:
            The prompt_id for tracking this execution.
        """
        body = {
            "prompt": workflow,
            "client_id": self.client_id,
        }
        result = self._post("/prompt", body)
        return result.get("prompt_id", "")

    def get_history(self, prompt_id: str) -> dict:
        """GET /history/{prompt_id} — get execution result for a prompt."""
        return self._get(f"/history/{prompt_id}")

    def poll_result(self, prompt_id: str, timeout: float = 300.0, interval: float = 1.0) -> dict:
        """Poll ComfyUI until workflow completes or times out.

        Returns the history entry for the prompt, or raises TimeoutError.
        """
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            history = self.get_history(prompt_id)
            if prompt_id in history:
                entry = history[prompt_id]
                # Check if execution is complete
                status = entry.get("status", {})
                if status.get("completed", False) or status.get("status_str") == "success":
                    return entry
                # Also check if outputs exist (older ComfyUI versions)
                if entry.get("outputs"):
                    return entry
            time.sleep(interval)
        raise TimeoutError(f"Workflow {prompt_id} did not complete within {timeout}s")

    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        """GET /view — fetch a generated image by filename.

        Returns raw image bytes.
        """
        params = f"filename={urllib.request.quote(filename)}&type={image_type}"
        if subfolder:
            params += f"&subfolder={urllib.request.quote(subfolder)}"
        url = f"{self.base_url}/view?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def upload_image(self, filepath: str, image_type: str = "input") -> dict:
        """POST /upload/image — upload an image for use in workflows.

        Returns the upload result with filename.
        """
        import mimetypes
        import os

        filename = os.path.basename(filepath)
        content_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"

        with open(filepath, "rb") as f:
            file_data = f.read()

        # Build multipart/form-data manually (stdlib only)
        boundary = uuid.uuid4().hex
        body = bytearray()

        # Image file part
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode())
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(file_data)
        body.extend(b"\r\n")

        # Type part
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="type"\r\n\r\n'.encode())
        body.extend(image_type.encode())
        body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -- Internal ------------------------------------------------------------

    def _get(self, path: str) -> dict:
        """Perform a GET request and return parsed JSON."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, body: dict) -> dict:
        """Perform a POST request with JSON body and return parsed JSON."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
