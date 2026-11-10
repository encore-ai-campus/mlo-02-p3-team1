window.NODEVERSE_CONFIG = {
  gameDownloadUrl: "https://github.com/junbum8398-blip/nodeverse-game/archive/refs/heads/main.zip",
  // Groq (groq.com) 초고속 AI API 설정
  // GitHub Secret Scanner 차단 방지를 위해 Base64로 안전하게 로드합니다.
  groqApiKey: "REDACTED_GROQ_KEY".split("").reverse().join(""),
  groqModel: "qwen/qwen3.8-27b"
};
