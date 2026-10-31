"""In-memory stand-in for Meko's MCP server, for integration tests (no network in CI). Search is word overlap."""
import json
import uuid


class _Text:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _Result:
    def __init__(self, payload: dict):
        self.content = [_Text(json.dumps(payload))]
        self.isError = False
        self.structuredContent = None


class FakeMeko:
    """Answers the Meko tools CrimeAI uses with plausible response shapes."""

    def __init__(self) -> None:
        self.memories: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, dict]] = []

    def add(self, dp: str, text: str, promoted: bool = False) -> str:
        mid = uuid.uuid4().hex
        self.memories.setdefault(dp, []).append({"id": mid, "memory": text, "promoted": promoted})
        return mid

    def _search(self, dp: str, query: str, limit: int) -> list[dict]:
        words = {w.lower() for w in query.replace(",", " ").replace(".", " ").split() if len(w) > 2}
        scored = []
        for m in self.memories.get(dp, []):
            text = m["memory"].lower()
            hits = sum(1 for w in words if w in text)
            if hits:
                scored.append((hits / max(len(words), 1), m))
        scored.sort(key=lambda s: -s[0])
        return [{"id": m["id"], "memory": m["memory"], "score": round(s, 3)} for s, m in scored[:limit]]

    async def call_tool(self, tool: str, args: dict) -> _Result:
        self.calls.append((tool, args))
        dp, limit = args.get("datapack_id"), args.get("limit", 8)
        if tool == "memory_add":
            mid = self.add(dp, args["text"])
            return _Result({"results": [{"id": mid, "memory": args["text"], "event": "ADD"}]})
        if tool == "memory_search":
            return _Result({"results": self._search(dp, args["query"], limit)})
        if tool == "context_search":
            return _Result({"memory": {"status": "ok", "results": self._search(dp, args["query"], limit)},
                            "knowledge_base": {"status": "ok", "results": []}, "conversation": {"status": "ok", "results": []}})
        if tool == "knowledgebase_search":
            return _Result({"results": [{"id": "kb1", "content": "Send a debit-freeze request within the golden hour.",
                                         "score": 0.7, "metadata": {"source": "online-fraud-first-response.md"}}]})
        if tool == "memory_promote":
            ids = set(args["memory_ids"])
            for m in self.memories.get(dp, []):
                if m["id"] in ids:
                    m["promoted"] = True
            return _Result({"inserted_ids": sorted(ids), "updated_ids": [], "not_found_ids": []})
        if tool == "memory_get_all":
            items = [m for m in self.memories.get(dp, []) if args.get("promoted") is None or m["promoted"] == args["promoted"]]
            return _Result({"results": items[-20:], "total": len(items)})
        if tool == "conversation_create":
            return _Result({"conversation_id": uuid.uuid4().hex})
        if tool in ("conversation_add_message", "memory_update", "memory_delete_by_id"):
            return _Result({"status": "ok"})
        raise AssertionError(f"unexpected tool {tool}")
