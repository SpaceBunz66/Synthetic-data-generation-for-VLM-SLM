# -*- coding: utf-8 -*-
"""Content generation with API cache and deterministic offline fallback."""

from __future__ import annotations

import hashlib
import json
import os
import random
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from synthetic_data.schema import TextBlock


CONTENT_SCHEMA_VERSION = "content_v4_rich_en_ja_zh_api_routes"
LANGUAGES = ("en", "ja", "zh")

CONTENT_PROVIDERS = ("fallback", "openai", "gemini", "groq")

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.1-8b-instant",
}

KIND_BY_CATEGORY = {
    "manga": ("dialogue", "whisper", "shout", "narration"),
    "game": ("dialogue", "hud", "quest", "floating_label", "menu"),
}

ACTION_WORD_MARKERS = (
    "bam",
    "boom",
    "crash",
    "bang",
    "rumble",
    "r\u1ea7m",
    "\u1ea7m",
    "\u0111o\u00e0ng",
    "\u0111\u00f9ng",
    "\u30c9\u30f3",
    "\u30d0\u30f3",
    "\u8f70",
    "\u7830",
    "\ucf85",
    "\uad11",
)

CONTENT_LIBRARY: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    "manga": {
        "en": [
            {"text": "I thought you had already left.", "translated_text": "T\u00f4i t\u01b0\u1edfng c\u1eadu \u0111\u00e3 r\u1eddi \u0111i r\u1ed3i."},
            {"text": "Do not look at me like that.", "translated_text": "\u0110\u1eebng nh\u00ecn t\u00f4i nh\u01b0 th\u1ebf."},
            {"text": "You knew the truth all along.", "translated_text": "C\u1eadu \u0111\u00e3 bi\u1ebft s\u1ef1 th\u1eadt t\u1eeb \u0111\u1ea7u."},
            {"text": "I only wanted to protect her.", "translated_text": "T\u00f4i ch\u1ec9 mu\u1ed1n b\u1ea3o v\u1ec7 c\u00f4 \u1ea5y."},
            {"text": "Then why are you trembling?", "translated_text": "V\u1eady t\u1ea1i sao c\u1eadu l\u1ea1i run r\u1ea9y?"},
            {"text": "This promise ends tonight.", "translated_text": "L\u1eddi h\u1ee9a n\u00e0y s\u1ebd k\u1ebft th\u00fac \u0111\u00eam nay."},
            {"text": "Please, say my name once more.", "translated_text": "Xin h\u00e3y g\u1ecdi t\u00ean t\u00f4i m\u1ed9t l\u1ea7n n\u1eefa."},
        ],
        "ja": [
            {"text": "\u3042\u306a\u305f\u306f\u6700\u521d\u304b\u3089\u77e5\u3063\u3066\u3044\u305f\u306e\u306d\u3002", "translated_text": "C\u1eadu \u0111\u00e3 bi\u1ebft ngay t\u1eeb \u0111\u1ea7u nh\u1ec9."},
            {"text": "\u79c1\u3092\u305d\u3093\u306a\u76ee\u3067\u898b\u306a\u3044\u3067\u3002", "translated_text": "\u0110\u1eebng nh\u00ecn t\u00f4i b\u1eb1ng \u00e1nh m\u1eaft \u0111\u00f3."},
            {"text": "\u672c\u5f53\u306f\u6016\u304b\u3063\u305f\u3093\u3060\u3002", "translated_text": "Th\u1eadt ra t\u00f4i \u0111\u00e3 r\u1ea5t s\u1ee3."},
            {"text": "\u3042\u306e\u65e5\u306e\u7d04\u675f\u3092\u899a\u3048\u3066\u308b\uff1f", "translated_text": "C\u1eadu c\u00f2n nh\u1edb l\u1eddi h\u1ee9a h\u00f4m \u0111\u00f3 kh\u00f4ng?"},
            {"text": "\u3082\u3046\u8ab0\u3082\u50b7\u3064\u3051\u305f\u304f\u306a\u3044\u3002", "translated_text": "T\u00f4i kh\u00f4ng mu\u1ed1n l\u00e0m ai t\u1ed5n th\u01b0\u01a1ng n\u1eefa."},
            {"text": "\u4eca\u306a\u3089\u307e\u3060\u9593\u306b\u5408\u3046\u3002", "translated_text": "B\u00e2y gi\u1edd v\u1eabn c\u00f2n k\u1ecbp."},
        ],
        "zh": [
            {"text": "\u4f60\u4ece\u4e00\u5f00\u59cb\u5c31\u77e5\u9053\u771f\u76f8\u3002", "translated_text": "C\u1eadu \u0111\u00e3 bi\u1ebft s\u1ef1 th\u1eadt ngay t\u1eeb \u0111\u1ea7u."},
            {"text": "\u522b\u7528\u90a3\u79cd\u773c\u795e\u770b\u6211\u3002", "translated_text": "\u0110\u1eebng nh\u00ecn t\u00f4i b\u1eb1ng \u00e1nh m\u1eaft \u0111\u00f3."},
            {"text": "\u6211\u53ea\u662f\u60f3\u4fdd\u62a4\u5979\u3002", "translated_text": "T\u00f4i ch\u1ec9 mu\u1ed1n b\u1ea3o v\u1ec7 c\u00f4 \u1ea5y."},
            {"text": "\u4eca\u665a\u4e4b\u540e\uff0c\u6211\u4eec\u5c31\u4e0d\u80fd\u56de\u5934\u4e86\u3002", "translated_text": "Sau \u0111\u00eam nay, ch\u00fang ta kh\u00f4ng th\u1ec3 quay \u0111\u1ea7u n\u1eefa."},
            {"text": "\u4f60\u7684\u58f0\u97f3\u5728\u53d1\u6296\u3002", "translated_text": "Gi\u1ecdng c\u1eadu \u0111ang run l\u00ean."},
            {"text": "\u8bf7\u518d\u76f8\u4fe1\u6211\u4e00\u6b21\u3002", "translated_text": "Xin h\u00e3y tin t\u00f4i th\u00eam m\u1ed9t l\u1ea7n n\u1eefa."},
        ],
        "ko": [
            {"text": "\ub108\ub294 \ucc98\uc74c\ubd80\ud130 \uc54c\uace0 \uc788\uc5c8\uc9c0.", "translated_text": "C\u1eadu \u0111\u00e3 bi\u1ebft ngay t\u1eeb \u0111\u1ea7u."},
            {"text": "\ub098\ub97c \uadf8\ub7f0 \ub208\uc73c\ub85c \ubcf4\uc9c0 \ub9c8.", "translated_text": "\u0110\u1eebng nh\u00ecn t\u00f4i b\u1eb1ng \u00e1nh m\u1eaft \u0111\u00f3."},
            {"text": "\uc0ac\uc2e4\uc740 \ub098\ub3c4 \ubb34\uc11c\uc6e0\uc5b4.", "translated_text": "Th\u1eadt ra t\u00f4i c\u0169ng \u0111\u00e3 r\u1ea5t s\u1ee3."},
            {"text": "\uadf8\ub0a0\uc758 \uc57d\uc18d\uc744 \uae30\uc5b5\ud574?", "translated_text": "C\u1eadu c\u00f2n nh\u1edb l\u1eddi h\u1ee9a h\u00f4m \u0111\u00f3 kh\u00f4ng?"},
            {"text": "\uc774\uc81c\ub294 \uc544\ubb34\ub3c4 \ub2e4\uce58\uac8c \ud558\uace0 \uc2f6\uc9c0 \uc54a\uc544.", "translated_text": "T\u00f4i kh\u00f4ng mu\u1ed1n l\u00e0m ai t\u1ed5n th\u01b0\u01a1ng n\u1eefa."},
            {"text": "\uc9c0\uae08\uc774\ub77c\uba74 \uc544\uc9c1 \ub2a6\uc9c0 \uc54a\uc558\uc5b4.", "translated_text": "B\u00e2y gi\u1edd v\u1eabn ch\u01b0a qu\u00e1 mu\u1ed9n."},
        ],
    },
    "game": {
        "en": [
            {"text": "Quest accepted: find the lost sigil.", "translated_text": "\u0110\u00e3 nh\u1eadn nhi\u1ec7m v\u1ee5: t\u00ecm \u1ea5n k\u00fd th\u1ea5t l\u1ea1c."},
            {"text": "Inventory full.", "translated_text": "T\u00fai \u0111\u1ed3 \u0111\u00e3 \u0111\u1ea7y."},
            {"text": "HP 142/200", "translated_text": "HP 142/200"},
            {"text": "Talk to the captain at the north gate.", "translated_text": "N\u00f3i chuy\u1ec7n v\u1edbi \u0111\u1ed9i tr\u01b0\u1edfng \u1edf c\u1ed5ng b\u1eafc."},
            {"text": "New skill unlocked.", "translated_text": "\u0110\u00e3 m\u1edf kh\u00f3a k\u1ef9 n\u0103ng m\u1edbi."},
            {"text": "Save point activated.", "translated_text": "\u0110\u00e3 k\u00edch ho\u1ea1t \u0111i\u1ec3m l\u01b0u."},
        ],
        "ja": [
            {"text": "\u30af\u30a8\u30b9\u30c8\u3092\u53d7\u6ce8\u3057\u307e\u3057\u305f\u3002", "translated_text": "\u0110\u00e3 nh\u1eadn nhi\u1ec7m v\u1ee5."},
            {"text": "\u6240\u6301\u54c1\u304c\u3044\u3063\u3071\u3044\u3067\u3059\u3002", "translated_text": "T\u00fai \u0111\u1ed3 \u0111\u00e3 \u0111\u1ea7y."},
            {"text": "\u5317\u306e\u9580\u3067\u968a\u9577\u3068\u8a71\u3059\u3002", "translated_text": "N\u00f3i chuy\u1ec7n v\u1edbi \u0111\u1ed9i tr\u01b0\u1edfng \u1edf c\u1ed5ng b\u1eafc."},
            {"text": "\u65b0\u3057\u3044\u30b9\u30ad\u30eb\u3092\u899a\u3048\u307e\u3057\u305f\u3002", "translated_text": "\u0110\u00e3 h\u1ecdc \u0111\u01b0\u1ee3c k\u1ef9 n\u0103ng m\u1edbi."},
            {"text": "\u30bb\u30fc\u30d6\u3057\u307e\u3059\u304b\uff1f", "translated_text": "B\u1ea1n c\u00f3 mu\u1ed1n l\u01b0u kh\u00f4ng?"},
        ],
        "zh": [
            {"text": "\u5df2\u63a5\u53d7\u4efb\u52a1\uff1a\u5bfb\u627e\u5931\u843d\u7684\u5370\u8bb0\u3002", "translated_text": "\u0110\u00e3 nh\u1eadn nhi\u1ec7m v\u1ee5: t\u00ecm \u1ea5n k\u00fd th\u1ea5t l\u1ea1c."},
            {"text": "\u80cc\u5305\u5df2\u6ee1\u3002", "translated_text": "T\u00fai \u0111\u1ed3 \u0111\u00e3 \u0111\u1ea7y."},
            {"text": "\u524d\u5f80\u5317\u95e8\u4e0e\u961f\u957f\u5bf9\u8bdd\u3002", "translated_text": "\u0110\u1ebfn c\u1ed5ng b\u1eafc n\u00f3i chuy\u1ec7n v\u1edbi \u0111\u1ed9i tr\u01b0\u1edfng."},
            {"text": "\u5df2\u89e3\u9501\u65b0\u6280\u80fd\u3002", "translated_text": "\u0110\u00e3 m\u1edf kh\u00f3a k\u1ef9 n\u0103ng m\u1edbi."},
            {"text": "\u5546\u5e97\u5c06\u5728\u5348\u591c\u5173\u95ed\u3002", "translated_text": "C\u1eeda h\u00e0ng s\u1ebd \u0111\u00f3ng v\u00e0o n\u1eeda \u0111\u00eam."},
        ],
        "ko": [
            {"text": "\ud018\uc2a4\ud2b8\ub97c \uc218\ub77d\ud588\uc2b5\ub2c8\ub2e4.", "translated_text": "\u0110\u00e3 nh\u1eadn nhi\u1ec7m v\u1ee5."},
            {"text": "\uc778\ubca4\ud1a0\ub9ac\uac00 \uac00\ub4dd \ucc3c\uc2b5\ub2c8\ub2e4.", "translated_text": "T\u00fai \u0111\u1ed3 \u0111\u00e3 \u0111\u1ea7y."},
            {"text": "\ubd81\ubb38\uc758 \ub300\uc7a5\uacfc \ub300\ud654\ud558\uc138\uc694.", "translated_text": "H\u00e3y n\u00f3i chuy\u1ec7n v\u1edbi \u0111\u1ed9i tr\u01b0\u1edfng \u1edf c\u1ed5ng b\u1eafc."},
            {"text": "\uc0c8\ub85c\uc6b4 \uae30\uc220\uc744 \ubc30\uc6e0\uc2b5\ub2c8\ub2e4.", "translated_text": "\u0110\u00e3 h\u1ecdc \u0111\u01b0\u1ee3c k\u1ef9 n\u0103ng m\u1edbi."},
            {"text": "\uc800\uc7a5\ud558\uc2dc\uaca0\uc2b5\ub2c8\uae4c?", "translated_text": "B\u1ea1n c\u00f3 mu\u1ed1n l\u01b0u kh\u00f4ng?"},
        ],
    },
}


class ContentProvider:
    """Generate source/translation blocks, preferring cached LLM responses."""

    def __init__(
        self,
        cache_dir: Path,
        use_llm: bool = False,
        model: Optional[str] = None,
        provider: str = "fallback",
        api_timeout: int = 45,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if use_llm and provider == "fallback":
            provider = os.getenv("SYNTHETIC_CONTENT_PROVIDER", "openai")
        if provider not in CONTENT_PROVIDERS:
            raise ValueError(f"provider must be one of: {', '.join(CONTENT_PROVIDERS)}")
        self.provider = provider
        self.use_llm = provider != "fallback"
        self.model = model or os.getenv("SYNTHETIC_CONTENT_MODEL") or DEFAULT_MODELS.get(provider)
        self.api_timeout = api_timeout

    def make_blocks(self, category: str, seed: int, count: int) -> List[TextBlock]:
        source_language = self._sample_language(seed)
        cache_key = self._cache_key(category, seed, count, source_language, self.provider, self.model)
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            payload = self._generate_payload(category, seed, count, source_language)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        blocks: List[TextBlock] = []
        for idx, item in enumerate(payload["items"], start=1):
            blocks.append(
                TextBlock(
                    id=idx,
                    text=item["text"],
                    translated_text=item["translated_text"],
                    source_language=payload["source_language"],
                    kind=item["kind"],
                    group_id=f"{category}_group_{idx:02d}",
                )
            )
        return blocks

    def _generate_payload(
        self,
        category: str,
        seed: int,
        count: int,
        source_language: str,
    ) -> Dict[str, Any]:
        if self.use_llm:
            try:
                return self._generate_with_api(category, seed, count, source_language)
            except Exception as exc:
                payload = self._generate_fallback(category, seed, count, source_language)
                payload["api_provider"] = self.provider
                payload["api_error"] = f"{type(exc).__name__}: {exc}"
                return payload
        return self._generate_fallback(category, seed, count, source_language)

    def _generate_with_api(
        self,
        category: str,
        seed: int,
        count: int,
        source_language: str,
    ) -> Dict[str, Any]:
        prompt = self._build_api_prompt(category, seed, count, source_language)
        if self.provider == "gemini":
            text = self._call_gemini(prompt)
        elif self.provider in {"openai", "groq"}:
            text = self._call_openai_compatible(prompt)
        else:
            raise ValueError(f"Unsupported API provider: {self.provider}")
        text = self._extract_json_text(text)
        payload = json.loads(text)
        return self._normalize_payload(payload, category, seed, count, source_language, generated_by=self.provider)

    def _build_api_prompt(self, category: str, seed: int, count: int, source_language: str) -> str:
        category_instruction = (
            "MANGA ONLY: natural comic speech and panel narration. Avoid game UI words, quests, stats, menus, HUD labels."
            if category == "manga"
            else "GAME ONLY: RPG UI, NPC dialogue, quest text, HUD, menu labels, and floating labels. Avoid manga melodrama."
        )
        allowed_kinds = "|".join(KIND_BY_CATEGORY[category])
        return (
            "Create original synthetic OCR/VLM text for a licensed manga/game dataset.\n"
            f"Category: {category}\n"
            f"Need exactly {count} items.\n"
            f"Use exactly one source language for every item: {source_language}.\n"
            "Translate every item into Vietnamese.\n"
            "Do not include sound effects or action words such as boom, bang, crash, rumble, rầm, ầm, ドン, 轰.\n"
            "Avoid repeating ideas, names, places, or object nouns within the same response.\n"
            f"{category_instruction}\n"
            "Return strict JSON only, no markdown, using this shape:\n"
            "{\"items\":[{\"text\":\"...\",\"translated_text\":\"...\",\"kind\":\""
            + allowed_kinds
            + "\"}]}\n"
            f"Seed hint: {seed}."
        )

    def _call_openai_compatible(self, prompt: str) -> str:
        if self.provider == "groq":
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            api_key = self._api_key("GROQ_API_KEY")
        else:
            endpoint = "https://api.openai.com/v1/chat/completions"
            api_key = self._api_key("OPENAI_API_KEY")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You generate compact, original JSON content only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.95,
            "response_format": {"type": "json_object"},
        }
        response = self._post_json(endpoint, payload, headers={"Authorization": f"Bearer {api_key}"})
        return response["choices"][0]["message"]["content"]

    def _call_gemini(self, prompt: str) -> str:
        api_key = self._api_key("GEMINI_API_KEY")
        model_name = str(self.model or DEFAULT_MODELS["gemini"])
        if model_name.startswith("models/"):
            model_name = model_name.split("/", 1)[1]
        model = urllib.parse.quote(model_name, safe="")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.95,
                "responseMimeType": "application/json",
            },
        }
        response = self._post_json(endpoint, payload)
        parts = response["candidates"][0]["content"].get("parts", [])
        return "".join(part.get("text", "") for part in parts)

    def _post_json(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        request = urllib.request.Request(endpoint, data=data, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.api_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider} HTTP {exc.code}: {body[:500]}") from exc

    @staticmethod
    def _api_key(env_name: str) -> str:
        api_key = os.getenv(env_name, "").strip()
        if not api_key:
            raise RuntimeError(f"Missing {env_name}")
        return api_key

    @staticmethod
    def _extract_json_text(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("API response did not contain a JSON object")
        return stripped[start : end + 1]

    def _generate_fallback(
        self,
        category: str,
        seed: int,
        count: int,
        source_language: str,
    ) -> Dict[str, Any]:
        rng = random.Random(seed)
        items: List[Dict[str, str]] = []
        seen: set[str] = set()
        kind_sequence = self._kind_sequence(category, count, rng)
        attempts = 0
        while len(items) < count and attempts < count * 40:
            attempts += 1
            item = self._generate_composed_item(category, source_language, rng, kind_sequence[len(items)])
            if self._contains_action_word(item["text"]) or self._contains_action_word(item["translated_text"]):
                continue
            key = item["text"].casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

        if len(items) < count:
            library = CONTENT_LIBRARY[category][source_language]
            sources = rng.sample(library, k=min(count - len(items), len(library)))
            for source in sources:
                if len(items) >= count:
                    break
                key = source["text"].casefold()
                if key in seen:
                    continue
                seen.add(key)
                kind = rng.choice(KIND_BY_CATEGORY[category])
                text = source["text"]
                if category == "game" and kind in {"hud", "quest", "menu"}:
                    text = self._game_style_text(text, kind, rng, source_language)
                if category == "manga" and kind == "shout":
                    text = self._manga_style_text(text, kind, source_language)
                items.append(
                    {
                        "text": text,
                        "translated_text": source["translated_text"],
                        "kind": kind,
                    }
                )
        return {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "generated_by": "rule_fallback",
            "api_provider": self.provider,
            "model": self.model if self.use_llm else None,
            "seed": seed,
            "category": category,
            "source_language": source_language,
            "items": items,
        }

    def _generate_composed_item(
        self,
        category: str,
        language: str,
        rng: random.Random,
        preferred_kind: Optional[str] = None,
    ) -> Dict[str, str]:
        if category == "manga":
            kind = preferred_kind or rng.choices(
                ["dialogue", "whisper", "shout", "narration"],
                weights=[5, 2, 2, 2],
                k=1,
            )[0]
            return self._compose_manga(language, kind, rng)

        kind = preferred_kind or rng.choices(
            ["dialogue", "hud", "quest", "floating_label", "menu"],
            weights=[3, 3, 4, 2, 2],
            k=1,
        )[0]
        return self._compose_game(language, kind, rng)

    @staticmethod
    def _kind_sequence(category: str, count: int, rng: random.Random) -> List[str]:
        base = (
            ["dialogue", "whisper", "narration", "dialogue", "shout"]
            if category == "manga"
            else ["quest", "dialogue", "hud", "menu", "floating_label"]
        )
        sequence: List[str] = []
        while len(sequence) < count:
            cycle = list(base)
            rng.shuffle(cycle)
            sequence.extend(cycle)
        return sequence[:count]

    def _compose_manga(self, language: str, kind: str, rng: random.Random) -> Dict[str, str]:
        banks = {
            "en": {
                "names": [("Mira", "Mira"), ("Ren", "Ren"), ("Aki", "Aki"), ("Sora", "Sora"), ("Lena", "Lena"), ("Noah", "Noah")],
                "places": [("the old bridge", "cây cầu cũ"), ("the empty classroom", "lớp học trống"), ("the shrine gate", "cổng đền"), ("the rainy alley", "con hẻm mưa"), ("the last train", "chuyến tàu cuối")],
                "objects": [("sealed letter", "lá thư bị niêm phong"), ("silver hairpin", "chiếc kẹp tóc bạc"), ("broken charm", "lá bùa vỡ"), ("missing photograph", "tấm ảnh thất lạc"), ("blue ribbon", "dải ruy băng xanh")],
                "feelings": [("afraid", "sợ hãi"), ("angry", "tức giận"), ("lonely", "cô đơn"), ("relieved", "nhẹ nhõm"), ("ashamed", "xấu hổ")],
            },
            "ja": {
                "names": [("ミラ", "Mira"), ("レン", "Ren"), ("アキ", "Aki"), ("ソラ", "Sora"), ("レナ", "Lena"), ("ノア", "Noah")],
                "places": [("古い橋", "cây cầu cũ"), ("誰もいない教室", "lớp học trống"), ("神社の鳥居", "cổng đền"), ("雨の路地", "con hẻm mưa"), ("終電", "chuyến tàu cuối")],
                "objects": [("封じられた手紙", "lá thư bị niêm phong"), ("銀の髪留め", "chiếc kẹp tóc bạc"), ("割れたお守り", "lá bùa vỡ"), ("なくした写真", "tấm ảnh thất lạc"), ("青いリボン", "dải ruy băng xanh")],
                "feelings": [("怖かった", "sợ hãi"), ("怒っていた", "tức giận"), ("寂しかった", "cô đơn"), ("安心した", "nhẹ nhõm"), ("恥ずかしかった", "xấu hổ")],
            },
            "zh": {
                "names": [("米拉", "Mira"), ("莲", "Ren"), ("秋", "Aki"), ("空", "Sora"), ("蕾娜", "Lena"), ("诺亚", "Noah")],
                "places": [("旧桥", "cây cầu cũ"), ("空教室", "lớp học trống"), ("神社门口", "cổng đền"), ("雨巷", "con hẻm mưa"), ("末班车", "chuyến tàu cuối")],
                "objects": [("封好的信", "lá thư bị niêm phong"), ("银发夹", "chiếc kẹp tóc bạc"), ("破裂的护符", "lá bùa vỡ"), ("遗失的照片", "tấm ảnh thất lạc"), ("蓝色缎带", "dải ruy băng xanh")],
                "feelings": [("害怕", "sợ hãi"), ("生气", "tức giận"), ("孤单", "cô đơn"), ("松了一口气", "nhẹ nhõm"), ("羞愧", "xấu hổ")],
            },
        }
        b = banks[language]
        values = {
            "name": rng.choice(b["names"]),
            "place": rng.choice(b["places"]),
            "object": rng.choice(b["objects"]),
            "feeling": rng.choice(b["feelings"]),
        }
        v = self._template_values(values)

        templates = {
            "en": {
                "dialogue": [
                    ("{name}, I found the {object} near {place}.", "{name}, tôi đã tìm thấy {object_vi} gần {place_vi}."),
                    ("You hid the {object} from me, didn't you?", "Cậu đã giấu {object_vi} khỏi tôi, đúng không?"),
                    ("I saw {name} waiting at {place}.", "Tôi thấy {name} đang đợi ở {place_vi}."),
                ],
                "whisper": [
                    ("Keep your voice down. {name} is still here.", "Nói nhỏ thôi. {name} vẫn còn ở đây."),
                    ("I was {feeling}, but I came anyway.", "Tôi đã {feeling_vi}, nhưng vẫn đến."),
                ],
                "shout": [
                    ("{name}, don't touch the {object}!", "{name}, đừng chạm vào {object_vi}!"),
                    ("Tell me why you went to {place}!", "Nói cho tôi biết vì sao cậu đến {place_vi}!"),
                ],
                "narration": [
                    ("That night, {name} returned to {place} alone.", "Đêm đó, {name} một mình quay lại {place_vi}."),
                    ("The {object} was colder than I remembered.", "{object_vi} lạnh hơn tôi nhớ."),
                ],
            },
            "ja": {
                "dialogue": [
                    ("{name}、{place}で{object}を見つけた。", "{name}, tôi đã tìm thấy {object_vi} ở {place_vi}."),
                    ("あなたが{object}を隠したんでしょう？", "Cậu đã giấu {object_vi}, đúng không?"),
                    ("{name}が{place}で待っていた。", "{name} đã đợi ở {place_vi}."),
                ],
                "whisper": [
                    ("声を落として。{name}はまだここにいる。", "Nói nhỏ thôi. {name} vẫn còn ở đây."),
                    ("本当は{feeling}けど、それでも来た。", "Thật ra tôi đã {feeling_vi}, nhưng vẫn đến."),
                ],
                "shout": [
                    ("{name}、{object}に触らないで！", "{name}, đừng chạm vào {object_vi}!"),
                    ("どうして{place}へ行ったの！", "Vì sao cậu lại đến {place_vi}!"),
                ],
                "narration": [
                    ("その夜、{name}は一人で{place}へ戻った。", "Đêm đó, {name} một mình quay lại {place_vi}."),
                    ("{object}は記憶より冷たかった。", "{object_vi} lạnh hơn trong ký ức."),
                ],
            },
            "zh": {
                "dialogue": [
                    ("{name}，我在{place}找到了{object}。", "{name}, tôi đã tìm thấy {object_vi} ở {place_vi}."),
                    ("你把{object}藏起来了，对吧？", "Cậu đã giấu {object_vi}, đúng không?"),
                    ("我看见{name}在{place}等你。", "Tôi thấy {name} đang đợi cậu ở {place_vi}."),
                ],
                "whisper": [
                    ("小声点。{name}还在这里。", "Nói nhỏ thôi. {name} vẫn còn ở đây."),
                    ("我其实很{feeling}，但还是来了。", "Thật ra tôi rất {feeling_vi}, nhưng vẫn đến."),
                ],
                "shout": [
                    ("{name}，别碰{object}！", "{name}, đừng chạm vào {object_vi}!"),
                    ("告诉我你为什么去{place}！", "Nói cho tôi biết vì sao cậu đến {place_vi}!"),
                ],
                "narration": [
                    ("那天晚上，{name}独自回到了{place}。", "Đêm đó, {name} một mình quay lại {place_vi}."),
                    ("{object}比记忆中更冰冷。", "{object_vi} lạnh hơn trong ký ức."),
                ],
            },
        }
        text_template, vi_template = rng.choice(templates[language][kind])
        return {"text": text_template.format(**v), "translated_text": vi_template.format(**v), "kind": kind}

    def _compose_game(self, language: str, kind: str, rng: random.Random) -> Dict[str, str]:
        banks = {
            "en": {
                "places": [("north gate", "cổng bắc"), ("moonlit dock", "bến tàu dưới trăng"), ("crystal mine", "mỏ pha lê"), ("western tower", "tháp phía tây"), ("forest camp", "trại trong rừng")],
                "items": [("ancient sigil", "ấn ký cổ"), ("storm key", "chìa khóa bão tố"), ("healing herb", "thảo dược hồi phục"), ("silver compass", "la bàn bạc"), ("ember shard", "mảnh than hồng")],
                "npcs": [("Captain Rhea", "đội trưởng Rhea"), ("Archivist Noll", "thủ thư Noll"), ("Merchant Vale", "thương nhân Vale"), ("Scout Ilya", "trinh sát Ilya")],
                "skills": [("Frost Guard", "Khiên băng"), ("Quick Step", "Bước nhanh"), ("Mana Bloom", "Nở mana"), ("Iron Focus", "Tập trung thép")],
            },
            "ja": {
                "places": [("北門", "cổng bắc"), ("月明かりの桟橋", "bến tàu dưới trăng"), ("水晶鉱山", "mỏ pha lê"), ("西の塔", "tháp phía tây"), ("森の野営地", "trại trong rừng")],
                "items": [("古代の印", "ấn ký cổ"), ("嵐の鍵", "chìa khóa bão tố"), ("回復草", "thảo dược hồi phục"), ("銀の羅針盤", "la bàn bạc"), ("残り火の欠片", "mảnh than hồng")],
                "npcs": [("隊長レア", "đội trưởng Rhea"), ("記録官ノル", "thủ thư Noll"), ("商人ヴェイル", "thương nhân Vale"), ("斥候イリヤ", "trinh sát Ilya")],
                "skills": [("氷の守り", "Khiên băng"), ("早足", "Bước nhanh"), ("マナ開花", "Nở mana"), ("鋼の集中", "Tập trung thép")],
            },
            "zh": {
                "places": [("北门", "cổng bắc"), ("月光码头", "bến tàu dưới trăng"), ("水晶矿洞", "mỏ pha lê"), ("西塔", "tháp phía tây"), ("森林营地", "trại trong rừng")],
                "items": [("古代印记", "ấn ký cổ"), ("风暴钥匙", "chìa khóa bão tố"), ("恢复草药", "thảo dược hồi phục"), ("银罗盘", "la bàn bạc"), ("余烬碎片", "mảnh than hồng")],
                "npcs": [("蕾雅队长", "đội trưởng Rhea"), ("档案员诺尔", "thủ thư Noll"), ("商人维尔", "thương nhân Vale"), ("斥候伊莉雅", "trinh sát Ilya")],
                "skills": [("冰霜守卫", "Khiên băng"), ("疾步", "Bước nhanh"), ("法力绽放", "Nở mana"), ("钢铁专注", "Tập trung thép")],
            },
        }
        b = banks[language]
        current = str(rng.randint(18, 180))
        max_value = str(rng.randint(190, 320))
        level = str(rng.randint(2, 48))
        combo = str(rng.randint(2, 9))
        values = {
            "place": rng.choice(b["places"]),
            "item": rng.choice(b["items"]),
            "npc": rng.choice(b["npcs"]),
            "skill": rng.choice(b["skills"]),
            "current": (current, current),
            "max": (max_value, max_value),
            "level": (level, level),
            "combo": (combo, combo),
        }
        v = self._template_values(values)

        if kind == "menu":
            labels = {
                "en": [("START", "BẮT ĐẦU"), ("SKILLS", "KỸ NĂNG"), ("INVENTORY", "TÚI ĐỒ"), ("MAP", "BẢN ĐỒ"), ("SAVE", "LƯU"), ("OPTIONS", "TÙY CHỌN")],
                "ja": [("開始", "BẮT ĐẦU"), ("スキル", "KỸ NĂNG"), ("所持品", "TÚI ĐỒ"), ("地図", "BẢN ĐỒ"), ("セーブ", "LƯU"), ("設定", "TÙY CHỌN")],
                "zh": [("开始", "BẮT ĐẦU"), ("技能", "KỸ NĂNG"), ("背包", "TÚI ĐỒ"), ("地图", "BẢN ĐỒ"), ("保存", "LƯU"), ("设置", "TÙY CHỌN")],
            }
            text, translated = rng.choice(labels[language])
            return {"text": text, "translated_text": translated, "kind": kind}

        if kind == "hud":
            labels = {
                "en": [("HP {current}/{max}", "HP {current}/{max}"), ("MP {current}/{max}", "MP {current}/{max}"), ("LV {level}", "Cấp {level}"), ("COMBO x{combo}", "Liên kích {combo}")],
                "ja": [("体力 {current}/{max}", "Thể lực {current}/{max}"), ("魔力 {current}/{max}", "Ma lực {current}/{max}"), ("レベル {level}", "Cấp {level}"), ("連携 {combo}", "Liên kích {combo}")],
                "zh": [("生命 {current}/{max}", "Sinh lực {current}/{max}"), ("魔力 {current}/{max}", "Ma lực {current}/{max}"), ("等级 {level}", "Cấp {level}"), ("连击 {combo}", "Liên kích {combo}")],
            }
            text_template, vi_template = rng.choice(labels[language])
            return {"text": text_template.format(**v), "translated_text": vi_template.format(**v), "kind": kind}

        templates = {
            "en": {
                "quest": [
                    ("QUEST: Bring the {item} to {npc}.", "NHIỆM VỤ: Mang {item_vi} đến cho {npc_vi}."),
                    ("QUEST: Investigate {place}.", "NHIỆM VỤ: Điều tra {place_vi}."),
                    ("New objective: recover the {item}.", "Mục tiêu mới: thu hồi {item_vi}."),
                ],
                "dialogue": [
                    ("{npc} says the {item} is still at {place}.", "{npc_vi} nói {item_vi} vẫn ở {place_vi}."),
                    ("Meet {npc} before entering {place}.", "Gặp {npc_vi} trước khi vào {place_vi}."),
                ],
                "floating_label": [
                    ("{npc}", "{npc_vi}"),
                    ("{skill} Ready", "{skill_vi} đã sẵn sàng"),
                    ("{item} Acquired", "Đã nhận {item_vi}"),
                ],
            },
            "ja": {
                "quest": [
                    ("クエスト: {item}を{npc}へ届ける。", "NHIỆM VỤ: Mang {item_vi} đến cho {npc_vi}."),
                    ("クエスト: {place}を調査する。", "NHIỆM VỤ: Điều tra {place_vi}."),
                    ("新目標: {item}を回収する。", "Mục tiêu mới: thu hồi {item_vi}."),
                ],
                "dialogue": [
                    ("{npc}は{item}がまだ{place}にあると言った。", "{npc_vi} nói {item_vi} vẫn ở {place_vi}."),
                    ("{place}に入る前に{npc}と話す。", "Gặp {npc_vi} trước khi vào {place_vi}."),
                ],
                "floating_label": [
                    ("{npc}", "{npc_vi}"),
                    ("{skill}準備完了", "{skill_vi} đã sẵn sàng"),
                    ("{item}入手", "Đã nhận {item_vi}"),
                ],
            },
            "zh": {
                "quest": [
                    ("任务：把{item}交给{npc}。", "NHIỆM VỤ: Mang {item_vi} đến cho {npc_vi}."),
                    ("任务：调查{place}。", "NHIỆM VỤ: Điều tra {place_vi}."),
                    ("新目标：取回{item}。", "Mục tiêu mới: thu hồi {item_vi}."),
                ],
                "dialogue": [
                    ("{npc}说{item}还在{place}。", "{npc_vi} nói {item_vi} vẫn ở {place_vi}."),
                    ("进入{place}前先找{npc}。", "Gặp {npc_vi} trước khi vào {place_vi}."),
                ],
                "floating_label": [
                    ("{npc}", "{npc_vi}"),
                    ("{skill}就绪", "{skill_vi} đã sẵn sàng"),
                    ("获得{item}", "Đã nhận {item_vi}"),
                ],
            },
        }
        text_template, vi_template = rng.choice(templates[language][kind])
        return {"text": text_template.format(**v), "translated_text": vi_template.format(**v), "kind": kind}

    @staticmethod
    def _template_values(values: Dict[str, tuple[str, str]]) -> Dict[str, str]:
        flattened: Dict[str, str] = {}
        for key, (source, translated) in values.items():
            flattened[key] = source
            flattened[f"{key}_vi"] = translated
        return flattened

    def _normalize_payload(
        self,
        payload: Dict[str, Any],
        category: str,
        seed: int,
        count: int,
        source_language: str,
        generated_by: str,
    ) -> Dict[str, Any]:
        rng = random.Random(seed)
        normalized: List[Dict[str, str]] = []
        for raw in payload.get("items", []):
            kind = str(raw.get("kind", rng.choice(KIND_BY_CATEGORY[category]))).lower()
            if kind not in KIND_BY_CATEGORY[category]:
                kind = rng.choice(KIND_BY_CATEGORY[category])
            text = str(raw.get("text", "")).strip()
            translated = str(raw.get("translated_text", "")).strip()
            if not text or not translated:
                continue
            if self._contains_action_word(text) or self._contains_action_word(translated):
                continue
            normalized.append(
                {
                    "text": text,
                    "translated_text": translated,
                    "kind": kind,
                }
            )
            if len(normalized) >= count:
                break

        if len(normalized) < count:
            fallback = self._generate_fallback(category, seed + 991, count - len(normalized), source_language)
            normalized.extend(fallback["items"])

        return {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "generated_by": generated_by,
            "model": self.model if generated_by in {"openai", "gemini", "groq"} else None,
            "seed": seed,
            "category": category,
            "source_language": source_language,
            "items": normalized[:count],
        }

    @staticmethod
    def _sample_language(seed: int) -> str:
        return LANGUAGES[seed % len(LANGUAGES)]

    @staticmethod
    def _game_style_text(text: str, kind: str, rng: random.Random, language: str) -> str:
        if kind == "quest":
            prefixes = {
                "en": "QUEST: ",
                "ja": "\u30af\u30a8\u30b9\u30c8: ",
                "zh": "\u4efb\u52a1\uff1a",
                "ko": "\ud018\uc2a4\ud2b8: ",
            }
            if language == "en" and text.lower().startswith("quest"):
                return text
            return prefixes[language] + text
        if kind == "menu":
            labels = {
                "en": ["START", "SKILLS", "INVENTORY", "MAP", "SAVE", "OPTIONS"],
                "ja": ["\u958b\u59cb", "\u30b9\u30ad\u30eb", "\u6240\u6301\u54c1", "\u5730\u56f3", "\u30bb\u30fc\u30d6", "\u8a2d\u5b9a"],
                "zh": ["\u5f00\u59cb", "\u6280\u80fd", "\u80cc\u5305", "\u5730\u56fe", "\u4fdd\u5b58", "\u8bbe\u7f6e"],
                "ko": ["\uc2dc\uc791", "\uae30\uc220", "\uc778\ubca4\ud1a0\ub9ac", "\uc9c0\ub3c4", "\uc800\uc7a5", "\uc124\uc815"],
            }
            return rng.choice(labels[language])
        if kind == "hud":
            labels = {
                "en": ["HP 142/200", "MP 38/90", "LV 17", "COMBO x4", text],
                "ja": ["\u4f53\u529b 142/200", "\u9b54\u529b 38/90", "\u30ec\u30d9\u30eb 17", "\u9023\u643a 4", text],
                "zh": ["\u751f\u547d 142/200", "\u9b54\u529b 38/90", "\u7b49\u7ea7 17", "\u8fde\u51fb 4", text],
                "ko": ["\uccb4\ub825 142/200", "\ub9c8\ub825 38/90", "\ub808\ubca8 17", "\uc5f0\uc18d 4", text],
            }
            return rng.choice(labels[language])
        return text

    @staticmethod
    def _manga_style_text(text: str, kind: str, language: str) -> str:
        if kind == "shout" and language == "en":
            return text.rstrip(".!?") + "!"
        return text

    @staticmethod
    def _contains_action_word(text: str) -> bool:
        lowered = text.casefold()
        return any(marker in lowered for marker in ACTION_WORD_MARKERS)

    @staticmethod
    def _cache_key(
        category: str,
        seed: int,
        count: int,
        source_language: str,
        provider: str,
        model: Optional[str],
    ) -> str:
        payload = json.dumps(
            {
                "schema_version": CONTENT_SCHEMA_VERSION,
                "category": category,
                "seed": seed,
                "count": count,
                "source_language": source_language,
                "provider": provider,
                "model": model,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
