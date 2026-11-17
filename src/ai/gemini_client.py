import httpx

from src.config import Settings, get_settings
from src.utils import setup_logging

logger = setup_logging()

# Local OSS plan, card R.2: what the user reads when the local model cannot answer
LOCAL_MODEL_DOWN = "Local model not running — run `make start` in Moonhopper"


class LocalModelUnavailable(RuntimeError):
    """Moonhopper's gateway, or the local model behind it, did not answer."""


# Local OSS plan, card R.2: keeps the name GeminiClient, instead of a rename, because six files import it
class GeminiClient:
    """Client for the local model behind Moonhopper's LiteLLM gateway, with a test-mode mock."""

    def __init__(
        self,
        settings: Settings | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings or get_settings()
        self.api_key = self.settings.llm_api_key
        self.model = model or self.settings.llm_model
        self.base_url = self.settings.llm_base_url.rstrip("/")
        self.transport = transport

    def generate_text(self, system_instruction: str, prompt: str) -> str:
        """Call the local model through the gateway's chat completions API; the mock runs in tests only."""
        # Local OSS plan, card R.2: the mock runs only when app_env == test, instead of whenever no key is set
        if self.settings.app_env == "test":
            logger.info("llm_mock_mode_active", reason="test env")
            return self._mock_generate(prompt)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        url = f"{self.base_url}/chat/completions"

        try:
            with httpx.Client(timeout=30.0, transport=self.transport) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TransportError as err:
            # The gateway is down (connection refused) or gave no answer in time
            logger.error("local_model_unreachable", url=url, error=str(err))
            raise LocalModelUnavailable(LOCAL_MODEL_DOWN) from err
        if response.status_code >= 500:
            # The gateway is up but the model server is not: LiteLLM answers 500 "Connection error"
            logger.error(
                "local_model_unavailable",
                url=url,
                status=response.status_code,
                body=response.text[:500],
            )
            raise LocalModelUnavailable(LOCAL_MODEL_DOWN)

        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0]["message"]["content"]
        return ""

    def _mock_generate(self, prompt: str) -> str:
        """Deterministic mock responses for unit & integration testing."""
        prompt_lower = prompt.lower()

        # 1. Insight synthesis prompt
        if "synthesize a concise" in prompt_lower or "rows returned" in prompt_lower:
            return (
                "Heinrich Klaasen and Nicholas Pooran dominate death overs in white-ball cricket."
            )

        # 2. Tactical Scouting prompt
        if "tactical scouting request" in prompt_lower:
            return "Virat Kohli displays high resilience against left-arm pacers but has a 38% dot ball rate in Powerplay overs. Recommendation: bowl tight back of a length outside off-stump."

        # 3. Reflection / Error Repair prompt
        if "repaired sql" in prompt_lower or "failed with error" in prompt_lower:
            return "```sql\nSELECT p.full_name, SUM(fd.runs_batter) AS total_runs FROM gold.fact_delivery fd JOIN gold.dim_player p ON fd.batter_id = p.player_id GROUP BY p.full_name ORDER BY total_runs DESC LIMIT 5;\n```"

        # 4. Text-to-SQL prompt
        if "death" in prompt_lower:
            return """
```sql
SELECT 
    p.full_name,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS death_strike_rate,
    SUM(fd.runs_batter) AS death_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
WHERE fd.phase = 'death'
GROUP BY p.full_name
ORDER BY death_strike_rate DESC
LIMIT 5;
```
            """.strip()

        return """
```sql
SELECT 
    p.full_name,
    SUM(fd.runs_batter) AS total_runs,
    COUNT(DISTINCT fd.match_id) AS matches_played
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
GROUP BY p.full_name
ORDER BY total_runs DESC
LIMIT 5;
```
        """.strip()
