import os
import threading
import urllib.error
import urllib.request


def revalidate_path(path: str) -> None:
    frontend_url = os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_APP_URL")
    secret = os.getenv("REVALIDATION_SECRET")
    if not frontend_url or not secret:
        return

    url = f"{frontend_url.rstrip('/')}/api/revalidate?secret={secret}"
    payload = f'{{"path":"{path}"}}'.encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    def _send() -> None:
        try:
            urllib.request.urlopen(request, timeout=3).close()
        except (urllib.error.URLError, TimeoutError):
            pass

    threading.Thread(target=_send, daemon=True).start()
