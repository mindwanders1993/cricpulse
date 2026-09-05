import os

import httpx

from src.config import Settings, get_settings
from src.utils import setup_logging

logger = setup_logging()


class GeminiClient:
    """Client for Gemini 2.5 Flash via OpenRouter, with test mode fallback."""

    def __init__(self, settings: Settings | None = None, model: str = "google/gemini-2.5-flash"):
        self.settings = settings or get_settings()
        self.api_key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def generate_text(self, system_instruction: str, prompt: str) -> str:
        """Call Gemini 2.5 Flash via OpenRouter's chat completions API, or use mock response if no API key."""
        if not self.api_key or self.settings.app_env == "test":
            logger.info("gemini_mock_mode_active", reason="No API key or test env")
            return self._mock_generate(prompt)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(self.base_url, json=payload, headers=headers)
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
