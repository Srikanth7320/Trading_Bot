import json
import logging
from pathlib import Path

from core.models import NewsItem

try:
    from google import genai
except ImportError:
    genai = None


logger = logging.getLogger(__name__)


class AIScorer:

    def __init__(self, api_key: str, model_name: str, enabled: bool = True):

        self.enabled = enabled and bool(api_key) and genai is not None
        self.model_name = model_name

        self.client = (
            genai.Client(api_key=api_key)
            if self.enabled
            else None
        )

        self.cache_dir = Path("cache")
        self.cache_dir.mkdir(exist_ok=True)

        if enabled and genai is None:
            raise RuntimeError(
                "google-genai package not installed."
            )

        if enabled and not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY missing."
            )

    ##############################################################

    def technical_score(self, latest) -> float:

        score = 0

        close = float(latest["Close"])

        rsi = float(latest.get("RSI", 50))

        macd = float(latest.get("MACD", 0))

        signal = float(latest.get("MACD_SIGNAL", 0))

        volume_ratio = float(
            latest.get("VOLUME_RATIO", 1)
        )

        ##########################################################
        # RSI
        ##########################################################

        if 55 <= rsi <= 65:
            score += 16

        elif 50 <= rsi < 55:
            score += 8

        elif 45 <= rsi < 50:
            score += 4

        elif rsi < 35:
            score -= 18

        elif rsi > 75:
            score -= 16

        ##########################################################
        # EMA Trend
        ##########################################################

        if latest.get("ABOVE_EMA20", False):
            score += 10

        if latest.get("ABOVE_EMA50", False):
            score += 12

        if latest.get("ABOVE_EMA200", False):
            score += 14

        ##########################################################
        # Golden Cross
        ##########################################################

        if latest.get("GOLDEN_CROSS", False):
            score += 12

        ##########################################################
        # MACD
        ##########################################################

        if macd > signal:
            score += 14
            if macd > 0:
                score += 6
        elif macd < signal:
            score -= 10

        ##########################################################
        # Volume
        ##########################################################

        if volume_ratio >= 3:
            score += 18

        elif volume_ratio >= 2:
            score += 14

        elif volume_ratio >= 1.5:
            score += 8

        elif volume_ratio >= 1.2:
            score += 4
        else:
            score -= 6

        ##########################################################
        # Momentum
        ##########################################################

        momentum20 = float(
            latest.get("MOMENTUM20", 0)
        )

        momentum50 = float(
            latest.get("MOMENTUM50", 0)
        )

        if momentum20 > 5:
            score += 8
        elif momentum20 < -3:
            score -= 8

        if momentum50 > 10:
            score += 10
        elif momentum50 < -5:
            score -= 10

        ##########################################################
        # Bollinger
        ##########################################################

        bb_pos = float(
            latest.get("BB_POSITION", 0.5)
        )

        if 0.20 <= bb_pos <= 0.80:
            score += 4
        elif bb_pos < 0.10 or bb_pos > 0.90:
            score -= 6

        ##########################################################
        # ATR
        ##########################################################

        atr_percent = float(
            latest.get("ATR_PERCENT", 3)
        )

        if atr_percent > 10:
            score -= 8
        elif atr_percent < 2:
            score += 4

        ##########################################################
        # Price Trend
        ##########################################################

        if close > float(latest.get("SMA20", close)):
            score += 8
        else:
            score -= 6

        if float(latest.get("SMA20", close)) > float(
            latest.get("SMA50", close)
        ):
            score += 10
        else:
            score -= 4

        ##########################################################

        score = max(0, min(100, score))

        if score < 55 and close < float(latest.get("SMA20", close)):
            return 0.0

        return float(score)
    ##############################################################

    def _cache_file(self, symbol: str) -> Path:

        return self.cache_dir / f"{symbol.upper()}.json"

    ##############################################################

    def _load_cache(self, symbol: str):

        path = self._cache_file(symbol)

        if not path.exists():
            return None

        try:

            with open(path, "r", encoding="utf-8") as fp:
                return json.load(fp)

        except Exception:
            return None

    ##############################################################

    def _save_cache(self, symbol: str, note: str):

        path = self._cache_file(symbol)

        try:

            with open(path, "w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "note": note,
                    },
                    fp,
                    indent=4,
                )

        except Exception:
            logger.exception(
                "Unable to save AI cache for %s",
                symbol,
            )

    ##############################################################

    def summarize(
        self,
        symbol: str,
        latest,
        news_items: list[NewsItem],
        base_score: float,
    ) -> str:

        trend = "Bullish"

        if (
            float(latest.get("EMA20", 0))
            <
            float(latest.get("EMA50", 0))
        ):
            trend = "Bearish"

        fallback = (
            f"Technical Score: {base_score:.1f} | "
            f"Trend: {trend} | "
            f"RSI: {float(latest.get('RSI',0)):.1f} | "
            f"Volume: {float(latest.get('VOLUME_RATIO',1)):.2f}x"
        )

        ##########################################################

        if base_score < 60:
            return fallback

        ##########################################################

        if not self.enabled:
            return fallback

        if self.client is None:
            return fallback

        ##########################################################

        cached = self._load_cache(symbol)

        if cached:
            note = cached.get("note")

            if note:
                return note

        ##########################################################

        headlines = []

        for item in news_items[:3]:

            if item.title:
                headlines.append(item.title)

        news = "\n".join(headlines)

        if not news:
            news = "No important news."

        ##########################################################

        prompt = f"""
You are an NSE swing trading analyst.

Analyze the following stock.

Reply in less than 120 words.

Do not promise profits.

Mention:

1. Trend

2. Risk

3. Holding period

4. Why this setup is attractive

Stock : {symbol}

Technical Score : {base_score:.1f}

Close : {float(latest['Close']):.2f}

EMA20 : {float(latest.get('EMA20',0)):.2f}

EMA50 : {float(latest.get('EMA50',0)):.2f}

EMA200 : {float(latest.get('EMA200',0)):.2f}

RSI : {float(latest.get('RSI',0)):.1f}

MACD : {float(latest.get('MACD',0)):.2f}

Signal : {float(latest.get('MACD_SIGNAL',0)):.2f}

Volume Ratio : {float(latest.get('VOLUME_RATIO',1)):.2f}

Momentum20 : {float(latest.get('MOMENTUM20',0)):.2f}

Momentum50 : {float(latest.get('MOMENTUM50',0)):.2f}

News

{news}
"""

        ##########################################################

        try:

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )

            text = (
                response.text or fallback
            ).strip()

            self._save_cache(
                symbol,
                text,
            )

            return text

        except Exception as exc:

            logger.warning(
                "Gemini failed for %s : %s",
                symbol,
                exc,
            )

            return fallback