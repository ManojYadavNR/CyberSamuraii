import os

from adapters.base import BaseAdapter
from schemas.common import ToolResult


class ShodanAdapter(BaseAdapter):
    name = "shodan"
    default_timeout = 60.0

    async def _execute(self, query: str) -> ToolResult:
        api_key = os.environ.get("SHODAN_API_KEY") or os.environ.get("SHODAN_API_KEY", "")
        if not api_key:
            return ToolResult(
                tool=self.name,
                success=False,
                error="SHODAN_API_KEY environment variable not set",
            )

        try:
            import shodan

            api = shodan.Shodan(api_key)
            results: list[dict] = []

            if self._looks_like_ip(query):
                host = api.host(query)
                for item in host.get("data", []):
                    results.append(
                        self._normalize_entry(
                            platform="shodan_host",
                            url=f"https://www.shodan.io/host/{query}",
                            extra={
                                "ip": query,
                                "port": item.get("port"),
                                "transport": item.get("transport"),
                                "product": item.get("product"),
                                "banner": str(item.get("data", ""))[:500],
                                "org": host.get("org"),
                                "os": host.get("os"),
                                "country": host.get("country_name"),
                            },
                        )
                    )
                if not results:
                    results.append(
                        self._normalize_entry(
                            platform="shodan_host",
                            url=f"https://www.shodan.io/host/{query}",
                            extra={
                                "ip": query,
                                "org": host.get("org"),
                                "os": host.get("os"),
                                "ports": host.get("ports", []),
                            },
                        )
                    )
            else:
                search = api.search(query)
                for match in search.get("matches", [])[:50]:
                    ip = match.get("ip_str", "")
                    port = match.get("port", "")
                    results.append(
                        self._normalize_entry(
                            platform="shodan_search",
                            url=f"https://www.shodan.io/host/{ip}",
                            extra={
                                "ip": ip,
                                "port": port,
                                "org": match.get("org"),
                                "product": match.get("product"),
                                "hostnames": match.get("hostnames", []),
                                "transport": match.get("transport"),
                                "location": match.get("location", {}),
                            },
                        )
                    )

            return ToolResult(
                tool=self.name,
                success=True,
                data=results,
                raw_output=f"Shodan returned {len(results)} results",
            )
        except Exception as e:
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Shodan API error: {type(e).__name__}: {e}",
            )

    def _looks_like_ip(self, query: str) -> bool:
        parts = query.split(".")
        if len(parts) == 4:
            try:
                return all(0 <= int(p) <= 255 for p in parts)
            except ValueError:
                return False
        return False
