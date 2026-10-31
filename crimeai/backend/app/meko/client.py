"""
Meko access for CrimeAI's agents.

Agents talk to Meko's MCP server with the MCP Python client over Streamable HTTP. One run (an FIR check, a
case share, an officer decision) opens one session; every tool call is timed and kept, and the caller
persists the calls to the meko_calls table so the UI can show exactly what Meko was asked and returned.
Every Meko tool except conversation_create takes a conversation_id, so a run opens one conversation per agent
and datapack on first use and passes it along. The REST Datapack API is used only for setup chores (listing
and creating datapacks) and as a fallback for promotion; knowledge-base files go to the presigned S3 form
that knowledgebase_upload_document returns.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.meko.models import MekoCall, MekoDatapack

logger = get_logger(__name__)

USER_AGENT = "crimeai-meko/1.0 (hackCBS 9.0)"
AGENT_TOOLS = {
    "memory_add", "memory_search", "memory_get_all", "memory_get_by_id", "memory_update",
    "memory_delete_by_id", "memory_delete_all", "memory_promote", "context_search",
    "knowledgebase_search", "conversation_create", "conversation_add_message", "conversation_get",
    "conversation_list", "conversation_update", "conversation_delete", "artifact_put", "artifact_get",
    "knowledgebase_upload_document", "knowledgebase_document_status",
}
# Tools whose calls Meko nests under a conversation (conversation_id is a required argument).
CONVERSATION_TOOLS = AGENT_TOOLS - {"conversation_create", "conversation_list"}
CATEGORY = {
    **dict.fromkeys(["memory_add", "memory_update", "conversation_create", "conversation_add_message",
                     "track_token_usage", "knowledgebase_upload_document", "rest:kb-s3-upload", "artifact_put"], "write"),
    **dict.fromkeys(["memory_search", "context_search", "knowledgebase_search", "memory_get_all",
                     "memory_get_by_id", "conversation_get", "conversation_list", "artifact_get",
                     "knowledgebase_document_status"], "recall"),
    **dict.fromkeys(["memory_promote", "rest:promote-memories"], "promote"),
    **dict.fromkeys(["memory_delete_by_id", "memory_delete_all", "conversation_delete"], "delete"),
    "connect": "session",
}
# memory_get_all returns each memory's text under "data".
TEXT_KEYS = ("memory", "text", "content", "fact", "chunk", "snippet", "page_content", "chunk_text", "document", "data")
ID_KEYS = ("id", "memory_id", "document_id", "chunk_id", "uuid")
LIST_KEYS = ("results", "memories", "items", "hits", "chunks", "documents", "data", "matches")
BUCKETS = ("memory", "knowledge_base", "conversation")


# (agent, datapack id) -> Meko conversation id, shared by every run in this process.
_CONVERSATIONS: dict[tuple[str, str | None], str] = {}


class MekoError(RuntimeError):
    def __init__(self, message: str, run: MekoRun | None = None):
        super().__init__(message)
        self.run = run


def agent_id(name: str) -> str:
    return f"crimeai-{name}"


@dataclass
class Hit:
    id: str | None
    text: str
    score: float | None
    source: str
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "score": self.score, "source": self.source, "metadata": self.metadata}


@dataclass
class Result:
    tool: str
    datapack: str | None
    ok: bool
    data: Any
    error: str | None
    latency_ms: int
    call_id: str | None = None

    def hits(self, source: str = "memory") -> list[Hit]:
        return to_hits(self.data, source) if self.ok else []

    def first(self, *keys: str) -> Any:
        return find_value(self.data, keys) if self.ok else None


# --- response normalisation: Meko's docs do not fix MCP response shapes, so read them defensively ----------

def parse_tool_result(res: Any) -> tuple[Any, str | None]:
    texts = [getattr(c, "text", "") for c in (getattr(res, "content", None) or []) if getattr(c, "type", "") == "text"]
    joined = "\n".join(t for t in texts if t)
    if getattr(res, "isError", False) or getattr(res, "is_error", False):
        return None, (joined or "tool returned an error")[:600]
    structured = getattr(res, "structuredContent", None)
    if structured is None:
        structured = getattr(res, "structured_content", None)
    if structured is not None:
        data = structured
    else:
        try:
            data = json.loads(joined) if joined else {}
        except json.JSONDecodeError:
            data = {"text": joined}
    # Meko's tools return their payload as a JSON string, which MCP wraps as {"result": "<json>"}.
    if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], str):
        try:
            data = json.loads(data["result"])
        except json.JSONDecodeError:
            data = {"text": data["result"]}
    if isinstance(data, dict):
        if data.get("error"):
            return data, str(data["error"])[:600]
        if data.get("status") == "error":
            return data, str(data.get("message") or data.get("detail") or data)[:600]
        if "detail" in data and not any(k in data for k in LIST_KEYS + BUCKETS):
            return data, str(data["detail"])[:600]
    return data, None


def _text_of(item: dict) -> str:
    for k in TEXT_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _id_of(item: dict) -> str | None:
    for k in ID_KEYS:
        v = item.get(k)
        if isinstance(v, str | int) and str(v):
            return str(v)
    return None


def _items(data: Any) -> list[dict]:
    if isinstance(data, list):
        dicts = [x for x in data if isinstance(x, dict)]
        if any(_text_of(x) for x in dicts):
            return dicts
        out: list[dict] = []
        for x in data:
            out += _items(x)
        return out
    if isinstance(data, dict):
        for k in LIST_KEYS:
            if k in data and (found := _items(data[k])):
                return found
        if _text_of(data) and _id_of(data):
            return [data]
    return []


def to_hits(data: Any, source: str = "memory") -> list[Hit]:
    hits = []
    for item in _items(data):
        text = _text_of(item)
        if not text:
            continue
        score = item.get("score", item.get("similarity", item.get("relevance")))
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        hits.append(Hit(_id_of(item), text, float(score) if isinstance(score, int | float) else None, source, meta))
    return hits


def context_buckets(data: Any) -> dict[str, dict]:
    root = data["results"] if isinstance(data, dict) and isinstance(data.get("results"), dict) else data
    out = {}
    for b in BUCKETS:
        node = root.get(b) if isinstance(root, dict) else None
        status = (node.get("status") or node.get("source_status")) if isinstance(node, dict) else None
        out[b] = {"hits": to_hits(node, b) if node is not None else [], "status": status, "present": node is not None}
    return out


def find_value(data: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k] not in (None, "", []):
                return data[k]
        for v in data.values():
            if (found := find_value(v, keys)) is not None:
                return found
    elif isinstance(data, list):
        for v in data:
            if (found := find_value(v, keys)) is not None:
                return found
    return None


def summarize(tool: str, data: Any, err: str | None) -> str:
    if err:
        return f"error: {err[:200]}"
    if tool == "context_search":
        return ", ".join(f"{k}: {len(v['hits'])}" for k, v in context_buckets(data).items())
    if hits := to_hits(data):
        return f"{len(hits)} item(s)"
    ident = find_value(data, ("conversation_id", "datapack_id", "key", "document_key", "inserted_ids", "id"))
    return f"ok ({str(ident)[:60]})" if ident is not None else "ok"


def _trim(value: Any, limit: int = 600) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, dict):
        return {k: _trim(v, limit) for k, v in value.items() if k != "content_base64"}
    if isinstance(value, list):
        return [_trim(v, limit) for v in value[:40]]
    return value


def _flatten(e: BaseException) -> str:
    if isinstance(e, BaseExceptionGroup):
        return "; ".join(_flatten(x) for x in e.exceptions)
    return f"{type(e).__name__}: {e}"


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


# --- runs -------------------------------------------------------------------------------------------------

class MekoRun:
    """One agent run: an open MCP session plus the calls it made (persisted with `save`)."""

    transport = "mcp"

    def __init__(self, datapacks: dict[str, str], run_id: str, session: Any = None):
        self.datapacks = datapacks
        self.run_id = run_id
        self.session = session
        self.calls: list[dict] = []

    def dp_id(self, key: str) -> str:
        if key not in self.datapacks:
            raise MekoError(f"Meko datapack '{key}' is not set up; run scripts/meko_setup.py")
        return self.datapacks[key]

    def _log(self, *, agent: str, tool: str, datapack: str | None, args: dict, ok: bool, latency: int,
             summary: str, result: Any, transport: str | None = None) -> str:
        call_id = str(uuid.uuid4())
        self.calls.append({
            "id": call_id, "run_id": self.run_id, "agent": agent, "tool": tool, "category": CATEGORY.get(tool, "admin"),
            "datapack": datapack, "transport": transport or self.transport, "ok": ok, "latency_ms": latency,
            "summary": summary[:300], "args": _trim(args), "result": _trim(result, 1500),
        })
        return call_id

    async def _invoke(self, tool: str, args: dict) -> tuple[Any, str | None]:
        try:
            res = await self.session.call_tool(tool, args)
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt | SystemExit | asyncio.CancelledError):
                raise
            return None, _flatten(e)
        return parse_tool_result(res)

    async def _conversation(self, agent: str, dp: str | None) -> str | None:
        """This agent's conversation in this datapack, created on first use and kept for the process: Meko asks
        for a consistent conversation per agent, and creating one costs seconds."""
        key = (agent, self.datapacks.get(dp) if dp else None)
        if key not in _CONVERSATIONS:
            res = await self.conversation_create(agent, dp, f"CrimeAI {agent}")
            conv = res.first("conversation_id", "id") if res.ok else None
            if not conv:
                return None
            _CONVERSATIONS[key] = str(conv)
        return _CONVERSATIONS[key]

    async def open_conversations(self, pairs: list[tuple[str, str]]) -> None:
        """Create the conversations a set of parallel calls will need, before they start."""
        await asyncio.gather(*(self._conversation(agent, dp) for agent, dp in dict.fromkeys(pairs)))

    async def call(self, agent: str, tool: str, args: dict, dp: str | None = None) -> Result:
        args = {k: v for k, v in args.items() if v is not None}
        if isinstance(args.get("metadata"), dict | list):
            args["metadata"] = json.dumps(args["metadata"], ensure_ascii=False)
        if tool in CONVERSATION_TOOLS and "conversation_id" not in args:
            conv = await self._conversation(agent, dp)
            if conv:
                args["conversation_id"] = conv
        if dp:
            args["datapack_id"] = self.dp_id(dp)
        if tool in AGENT_TOOLS and "agent_id" not in args:
            args["agent_id"] = agent_id(agent)
        t0 = time.perf_counter()
        data, err = await self._invoke(tool, args)
        latency = _ms(t0)
        call_id = self._log(agent=agent, tool=tool, datapack=dp, args=args, ok=err is None, latency=latency,
                            summary=summarize(tool, data, err), result=data)
        return Result(tool, dp, err is None, data, err, latency, call_id)

    # typed helpers
    async def memory_add(self, agent: str, dp: str, text: str, metadata: dict | None = None,
                         conversation_id: str | None = None) -> Result:
        return await self.call(agent, "memory_add", {"text": text, "metadata": metadata, "conversation_id": conversation_id}, dp)

    async def memory_search(self, agent: str, dp: str, query: str, limit: int = 8) -> Result:
        return await self.call(agent, "memory_search", {"query": query, "limit": limit}, dp)

    async def memory_get_all(self, agent: str, dp: str, promoted: bool | None = None) -> Result:
        return await self.call(agent, "memory_get_all", {"promoted": promoted}, dp)

    async def context_search(self, agent: str, dp: str, query: str, limit: int = 8) -> Result:
        return await self.call(agent, "context_search", {"query": query, "limit": limit}, dp)

    async def kb_search(self, agent: str, dp: str, query: str, limit: int = 4) -> Result:
        return await self.call(agent, "knowledgebase_search", {"query": query, "limit": limit}, dp)

    async def memory_update(self, agent: str, dp: str, memory_id: str, text: str) -> Result:
        return await self.call(agent, "memory_update", {"memory_id": memory_id, "text": text}, dp)

    async def memory_delete(self, agent: str, dp: str, memory_id: str) -> Result:
        return await self.call(agent, "memory_delete_by_id", {"memory_id": memory_id}, dp)

    async def kb_upload(self, agent: str, dp: str, filename: str, content: bytes) -> tuple[Result, str | None]:
        """Ask Meko for a presigned S3 form and post the file to it. Returns the tool result and the document key."""
        res = await self.call(agent, "knowledgebase_upload_document", {
            "filename": filename, "size": len(content), "content_hash": hashlib.sha256(content).hexdigest(),
            "content_head_base64": base64.b64encode(content[:3072]).decode(),
        }, dp)
        key = res.first("key", "document_key")
        url, fields = res.first("url"), res.first("fields")
        if not res.ok or res.first("already_uploaded") or not url:
            return res, key
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as http:
                resp = await http.post(url, data=fields or {}, files={"file": (filename, content)})
            err = None if resp.status_code < 400 else f"S3 HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {e}"
        self._log(agent=agent, tool="rest:kb-s3-upload", datapack=dp, args={"filename": filename, "size": len(content)},
                  ok=err is None, latency=_ms(t0), summary=err or f"{filename} uploaded", result=None, transport="rest")
        return Result("rest:kb-s3-upload", dp, err is None, res.data, err, _ms(t0)), key

    async def kb_status(self, agent: str, dp: str, document_key: str) -> Result:
        return await self.call(agent, "knowledgebase_document_status", {"document_key": document_key}, dp)

    async def conversation_create(self, agent: str, dp: str | None, title: str, metadata: dict | None = None) -> Result:
        return await self.call(agent, "conversation_create", {"title": title, "metadata": metadata, "run_id": self.run_id}, dp)

    async def conversation_add_message(self, agent: str, dp: str, conversation_id: str, user_input: str, output: str,
                                       plan: list[str] | None = None, reasoning: str | None = None) -> Result:
        return await self.call(agent, "conversation_add_message", {
            "conversation_id": conversation_id, "input": user_input, "output": output, "plan": plan,
            "reasoning": reasoning,
        }, dp)

    async def memory_promote(self, agent: str, dp: str, memory_ids: list[str]) -> Result:
        res = await self.call(agent, "memory_promote", {"memory_ids": memory_ids}, dp)
        if res.ok or self.transport != "mcp":
            return res
        body, err = await rest(self, "POST", "/promote-memories", agent=agent, label="promote-memories", datapack=dp,
                               json_body={"datapack_id": self.dp_id(dp), "memory_ids": memory_ids})
        return Result("rest:promote-memories", dp, err is None, body, err, 0)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.MEKO_API_KEY}", "User-Agent": USER_AGENT}


async def load_datapacks(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(MekoDatapack.key, MekoDatapack.datapack_id))).all()
    return dict(rows)


@asynccontextmanager
async def open_run(datapacks: dict[str, str], agent: str = "system"):
    """Open one MCP session to Meko. Raises MekoError (with the attempt logged on the run) when it cannot."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    run = MekoRun(datapacks, uuid.uuid4().hex[:12])
    if not settings.MEKO_API_KEY:
        raise MekoError("Meko is not configured: set MEKO_API_KEY")
    t0 = time.perf_counter()
    async with AsyncExitStack() as stack:
        try:
            read, write, _ = await stack.enter_async_context(streamablehttp_client(
                settings.MEKO_MCP_URL, headers=_headers(), timeout=30, sse_read_timeout=settings.MEKO_TIMEOUT_SECONDS))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt | SystemExit | asyncio.CancelledError):
                raise
            msg = _flatten(e)
            run._log(agent=agent, tool="connect", datapack=None, args={"url": settings.MEKO_MCP_URL}, ok=False,
                     latency=_ms(t0), summary=f"error: {msg[:200]}", result=None)
            raise MekoError(f"Could not connect to Meko: {msg}", run) from None
        run._log(agent=agent, tool="connect", datapack=None, args={"url": settings.MEKO_MCP_URL}, ok=True,
                 latency=_ms(t0), summary="MCP session open", result=None)
        run.session = session
        yield run


async def save_calls(db: AsyncSession, calls: list[dict]) -> None:
    for c in calls:
        db.add(MekoCall(id=uuid.UUID(c["id"]), **{k: v for k, v in c.items() if k != "id"}))
    await db.flush()


async def rest(run: MekoRun | None, method: str, path: str, *, agent: str, label: str, datapack: str | None = None,
               json_body: dict | None = None, params: dict | None = None, files: dict | None = None) -> tuple[Any, str | None]:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(headers=_headers(), timeout=60) as http:
            resp = await http.request(method, f"{settings.MEKO_API_URL}{path}", json=json_body, params=params, files=files)
        try:
            body: Any = resp.json()
        except ValueError:
            body = {"text": resp.text[:500]}
        err = None if resp.status_code < 400 else f"HTTP {resp.status_code}: {json.dumps(body)[:300]}"
    except httpx.HTTPError as e:
        body, err = None, f"{type(e).__name__}: {e}"
    if run is not None:
        run._log(agent=agent, tool=f"rest:{label}", datapack=datapack,
                 args={"method": method, "path": path, **({"body": json_body} if json_body else {})}, ok=err is None,
                 latency=_ms(t0), summary=err or summarize(label, body, None), result=body, transport="rest")
    return body, err
