"""Priority lead queue for auto-pivot investigations."""

from __future__ import annotations

import heapq

from schemas.discovery import DiscoveryLead


def visit_key(lead_type: str, query: str) -> str:
    return f"{lead_type}:{query.strip().lower()}"


class LeadQueue:
    """Generic priority queue with deduplication."""

    def __init__(self):
        self._heap: list[tuple[float, int, DiscoveryLead]] = []
        self._counter = 0
        self._visited: set[str] = set()
        self._queued: set[str] = set()

    @property
    def visited(self) -> set[str]:
        return self._visited

    def mark_visited(self, lead_type: str, query: str) -> None:
        self._visited.add(visit_key(lead_type, query))

    def is_visited(self, lead: DiscoveryLead) -> bool:
        return visit_key(lead.lead_type, lead.query) in self._visited

    def enqueue(self, lead: DiscoveryLead) -> bool:
        key = visit_key(lead.lead_type, lead.query)
        if key in self._visited or key in self._queued:
            return False
        heapq.heappush(self._heap, (-lead.priority, self._counter, lead))
        self._counter += 1
        self._queued.add(key)
        return True

    def enqueue_many(self, leads: list[DiscoveryLead]) -> int:
        added = 0
        for lead in leads:
            if self.enqueue(lead):
                added += 1
        return added

    def pop(self) -> DiscoveryLead | None:
        if not self._heap:
            return None
        _, _, lead = heapq.heappop(self._heap)
        self._queued.discard(visit_key(lead.lead_type, lead.query))
        return lead

    def pending(self) -> list[DiscoveryLead]:
        return [item[2] for item in sorted(self._heap, key=lambda entry: entry[0])]

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)
