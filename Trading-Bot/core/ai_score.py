import logging

from core.models import NewsItem

try:
    from google import genai
except ImportError:  # pragma: no cover - dependency is installed by requirements
    genai = None


logger = logging.getLogger(__name__)


class AIScorer:
    def __init__(self, api_key: str, model_name: str, enabled: bool = True):
        self.enabled = enabled and bool(api_key) and genai is not None
        self.client = genai.Client(api_key=api_key) if self.enabled else None
        self.model_name = model_name
        if enabled and genai is None:
            raise RuntimeError("google-genai is required for mandatory Gemini scoring.")
        if enabled and not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for mandatory Gemini scoring.")

    def technical_score(self, latest) -> float:
        score = 0.0
        close = float(latest["Close"])
        rsi = float(latest.get("RSI", 50))
        macd = float(latest.get("MACD", 0))
        signal = float(latest.get("MACD_SIGNAL", 0))
        sma20 = float(latest.get("SMA20", close))
        sma50 = float(latest.get("SMA50", close))
        volume_ratio = float(latest.get("VOLUME_RATIO", 1))

        if 45 <= rsi <= 65:
            score += 18
        elif 35 <= rsi < 45:
            score += 10
        elif rsi > 75:
            score -= 15

        if macd > signal:
            score += 18
        if close > sma20:
            score += 16
        if sma20 > sma50:
            score += 16
        if volume_ratio >= 1.2:
            score += 12
        if close <= float(latest.get("BB_LOWER", close)) * 1.03:
            score += 8

        return max(0.0, min(100.0, score))

    def summarize(self, symbol: str, latest, news_items: list[NewsItem], base_score: float) -> str:
        fallback = (
            f"Technical score {base_score:.1f}; RSI {float(latest.get('RSI', 0)):.1f}; "
            f"MACD {'bullish' if float(latest.get('MACD', 0)) > float(latest.get('MACD_SIGNAL', 0)) else 'neutral'}."
        )
        if not self.enabled or self.client is None:
            return fallback

        news_text = "; ".join(item.title for item in news_items[:3]) or "No recent news headlines."
        prompt = (
            "Give one concise trading note for an NSE stock. Do not promise returns. "
            f"Symbol: {symbol}. Score: {base_score:.1f}. "
            f"RSI: {float(latest.get('RSI', 0)):.1f}. MACD: {float(latest.get('MACD', 0)):.2f}. "
            f"News: {news_text}"
        )
        try:
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            return (response.text or fallback).strip()
        except Exception as exc:  # Gemini failures should never block scans
            logger.warning("Gemini scoring failed for %s: %s", symbol, exc)
            return fallback
