"""AI API 客户端 - 支持 OpenAI 兼容格式的多厂商调用"""

import requests


class AIClient:
    def __init__(self, base_url, api_key, model):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # 检测是否为 Google Gemini API
        self.is_gemini = "generativelanguage.googleapis.com" in base_url

    def chat(self, messages, temperature=0.8, max_tokens=4096):
        """调用 AI 聊天接口，返回纯文本响应"""
        if self.is_gemini:
            return self._chat_gemini(messages, temperature, max_tokens)
        else:
            return self._chat_openai(messages, temperature, max_tokens)

    def _chat_openai(self, messages, temperature, max_tokens):
        """OpenAI 兼容格式的调用"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        print(f"--- AI 请求 [{self.model}] ---")
        print(f"URL: {url}")
        print(f"Messages: {messages[-1]['content'][:100]}...")

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        print(f"--- AI 响应 ---")
        result = self._extract_text(data)
        print(f"Response (提取后): {result[:100]}...")
        return result

    def _chat_gemini(self, messages, temperature, max_tokens):
        """Google Gemini API 格式的调用"""
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        # 转换消息格式：OpenAI -> Gemini
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        print(f"--- AI 请求 [Gemini: {self.model}] ---")
        print(f"URL: {url[:80]}...")
        print(f"Messages: {messages[-1]['content'][:100]}...")

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        print(f"--- AI 响应 ---")
        result = self._extract_gemini_text(data)
        print(f"Response (提取后): {result[:100]}...")
        return result

    def _extract_gemini_text(self, data):
        """从 Gemini API 响应中提取文本"""
        try:
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            raise ValueError("Gemini 响应中未找到文本内容")
        except (KeyError, IndexError) as e:
            raise ValueError(f"无法解析 Gemini API 响应: {e}")

    def _extract_text(self, data):
        """从响应中提取纯文本，兼容多种格式"""
        # OpenAI 标准格式
        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        # Anthropic / SiliconFlow messages 格式
        if "content" in data and isinstance(data["content"], list):
            parts = []
            for block in data["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block["text"])
            return "\n".join(parts) if parts else str(data["content"])

        raise ValueError(f"无法解析 API 响应格式: {list(data.keys())}")

    def test_connection(self):
        """测试 API 连接是否正常"""
        try:
            result = self.chat(
                [{"role": "user", "content": "回复'连接成功'四个字"}],
                max_tokens=20,
            )
            return True, result.strip()
        except Exception as e:
            return False, str(e)
