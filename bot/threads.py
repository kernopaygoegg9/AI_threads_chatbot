"""Thin client for the official Threads API (graph.threads.net).

Adapted from linzoie/threads-bot-template (MIT) and extended with image posts,
container status polling, publishing-limit checks and token exchange/refresh.
"""
from __future__ import annotations

import time

import requests

from . import settings

API_BASE = "https://graph.threads.net/v1.0"
TOKEN_BASE = "https://graph.threads.net"
TIMEOUT = 30


class ThreadsError(RuntimeError):
    pass


def _token() -> str:
    token = settings.load_secrets().threads_token
    if not token:
        raise ThreadsError("THREADS_ACCESS_TOKEN is not set")
    return token


def _user_id() -> str:
    uid = settings.load_secrets().threads_user_id
    if not uid:
        raise ThreadsError("THREADS_USER_ID is not set")
    return uid


def _check(r: requests.Response) -> dict:
    if r.status_code >= 400:
        raise ThreadsError(f"{r.request.method} {r.url.split('?')[0]} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def _get(path: str, **params) -> dict:
    params["access_token"] = _token()
    return _check(requests.get(f"{API_BASE}/{path}", params=params, timeout=TIMEOUT))


def _post(path: str, **data) -> dict:
    data["access_token"] = _token()
    return _check(requests.post(f"{API_BASE}/{path}", data=data, timeout=TIMEOUT))


# ---- account ---------------------------------------------------------------
def me() -> dict:
    return _get("me", fields="id,username,name,threads_biography")


def publishing_limit() -> dict:
    fields = "quota_usage,config,reply_quota_usage,reply_config"
    data = _get(f"{_user_id()}/threads_publishing_limit", fields=fields).get("data") or [{}]
    return data[0]


# ---- reading ---------------------------------------------------------------
def my_recent_threads(limit: int = 10) -> list[dict]:
    return _get("me/threads", fields="id,text,timestamp,permalink", limit=limit).get("data", [])


def replies(thread_id: str, limit: int = 100) -> list[dict]:
    fields = "id,text,username,timestamp,replied_to,is_reply_owned_by_me"
    return _get(f"{thread_id}/replies", fields=fields, limit=limit).get("data", [])


# ---- publishing ------------------------------------------------------------
def _wait_container(container_id: str, timeout_s: int = 120) -> None:
    """Media containers need processing before publish; poll status until FINISHED."""
    deadline = time.monotonic() + timeout_s
    while True:
        status = _get(container_id, fields="status,error_message")
        state = status.get("status")
        if state in (None, "FINISHED", "PUBLISHED"):
            return
        if state in ("ERROR", "EXPIRED"):
            raise ThreadsError(f"container {container_id} {state}: {status.get('error_message')}")
        if time.monotonic() > deadline:
            raise ThreadsError(f"container {container_id} not ready after {timeout_s}s (status={state})")
        time.sleep(5)


def publish(text: str, image_url: str | None = None, reply_to_id: str | None = None) -> dict:
    """Two-step publish: create a container, wait until ready, then publish it."""
    data: dict = {"text": text}
    if image_url:
        data.update(media_type="IMAGE", image_url=image_url)
    else:
        data["media_type"] = "TEXT"
    if reply_to_id:
        data["reply_to_id"] = reply_to_id
    container = _post(f"{_user_id()}/threads", **data)
    creation_id = container["id"]
    _wait_container(creation_id)
    published = _post(f"{_user_id()}/threads_publish", creation_id=creation_id)
    return {"creation_id": creation_id, "id": published.get("id")}


def permalink(media_id: str) -> str | None:
    try:
        return _get(media_id, fields="permalink").get("permalink")
    except ThreadsError:
        return None


# ---- tokens ----------------------------------------------------------------
def exchange_long_lived(short_token: str, app_secret: str) -> dict:
    r = requests.get(
        f"{TOKEN_BASE}/access_token",
        params={"grant_type": "th_exchange_token", "client_secret": app_secret, "access_token": short_token},
        timeout=TIMEOUT,
    )
    return _check(r)


def refresh_long_lived(token: str) -> dict:
    r = requests.get(
        f"{TOKEN_BASE}/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": token},
        timeout=TIMEOUT,
    )
    return _check(r)
