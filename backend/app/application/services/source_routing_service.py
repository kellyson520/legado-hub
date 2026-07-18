from __future__ import annotations


class SourceRoutingService:
    def __init__(self, health_repo=None):
        self._health_repo = health_repo

    def snapshot_map(self, source_ids: list[int]) -> dict[int, object | None]:
        if self._health_repo is None:
            return {source_id: None for source_id in source_ids}
        return {source_id: self._health_repo.get_snapshot(source_id) for source_id in source_ids}

    def rank_search_sources(
        self,
        sources: list[dict],
        snapshots: dict[int, object | None],
        routing_mode: str = "auto",
    ) -> list[dict]:
        ranked = []
        for source in sources:
            snapshot = snapshots.get(source["id"])
            health_status = getattr(snapshot, "health_status", "unknown") if snapshot else "unknown"
            failure_reason = getattr(snapshot, "failure_reason", "") if snapshot else ""
            route_policy = getattr(snapshot, "route_policy", "probe_only") if snapshot else "probe_only"
            route_score = float(getattr(snapshot, "route_score", 10.0) if snapshot else 10.0)

            if routing_mode == "auto" and health_status in {"dead", "blocked", "disabled"}:
                continue

            is_js = str(source.get("searchUrl", "") or "").strip().startswith("@js:")
            score = route_score
            if health_status == "healthy":
                score += 100
            elif health_status == "degraded":
                score += 25
            elif health_status == "unknown":
                score += 5
            if not is_js:
                score += 20

            decision = {
                "health_status": health_status,
                "failure_reason": failure_reason,
                "route_decision": (
                    "allow"
                    if health_status == "healthy"
                    else ("deprioritize" if health_status == "degraded" else route_policy)
                ),
                "route_score": score,
            }
            ranked.append({"source": source, "decision": decision})

        ranked.sort(key=lambda item: item["decision"]["route_score"], reverse=True)
        return ranked

    async def resolve_book_candidates(
        self,
        repo,
        keyword: str,
        author_hint: str | None,
        fetcher,
        routing_mode: str = "auto",
        tenant_id: str | None = None,
    ) -> list[dict]:
        if tenant_id and hasattr(repo, "list_ephemeral_book_sources"):
            sources = await repo.list_ephemeral_book_sources(tenant_id)
        else:
            sources = await repo.list_book_sources_full(enabled_only=True)
        ranked = self.rank_search_sources(
            sources,
            self.snapshot_map([source["id"] for source in sources]),
            routing_mode=routing_mode,
        )
        candidates = []
        for routed in ranked:
            source = routed["source"]
            results = await fetcher.search(source, keyword, page=1)
            if results:
                candidates.append(
                    {
                        "source": source,
                        "book": results[0],
                        "decision": routed["decision"],
                    }
                )
        return candidates
