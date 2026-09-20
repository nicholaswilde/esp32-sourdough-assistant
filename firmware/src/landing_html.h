#ifndef LANDING_HTML_H
#define LANDING_HTML_H

#ifndef NATIVE_TEST
#include <pgmspace.h>
#endif

const char landing_html[] PROGMEM = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sourdough Assistant 🤖</title>
<style>
body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; box-sizing: border-box; }
.card { background: #181825; border-radius: 12px; padding: 28px 24px; width: 100%; max-width: 580px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; }
h1 { color: #f5c2e7; margin: 0 0 4px 0; font-size: 24px; text-align: center; }
.subtitle { text-align: center; color: #a6adc8; margin: 0 0 18px 0; font-size: 14px; }
.status-bar { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 20px; }
.badge { background: #11111b; border: 1px solid #313244; border-radius: 20px; padding: 4px 12px; font-size: 12px; color: #cdd6f4; }
.badge span { color: #89b4fa; font-weight: 600; }
.chat-container { background: #11111b; border: 1px solid #313244; border-radius: 10px; padding: 14px; min-height: 220px; max-height: 380px; overflow-y: auto; margin-bottom: 16px; display: flex; flex-direction: column; gap: 12px; }
.msg { padding: 10px 14px; border-radius: 10px; max-width: 85%; font-size: 14px; line-height: 1.5; word-break: break-word; }
.msg-user { background: #313244; color: #cdd6f4; align-self: flex-end; border-bottom-right-radius: 2px; }
.msg-assistant { background: #181825; border: 1px solid #cba6f7; color: #cdd6f4; align-self: flex-start; border-bottom-left-radius: 2px; }
.msg-meta { font-size: 11px; color: #a6adc8; margin-top: 4px; text-align: right; }
.input-group { display: flex; gap: 8px; margin-bottom: 20px; }
textarea { flex-grow: 1; height: 54px; padding: 10px 12px; border-radius: 8px; border: 1px solid #45475a; background: #313244; color: #cdd6f4; font-size: 14px; font-family: inherit; resize: none; box-sizing: border-box; }
textarea:focus { outline: none; border-color: #f5c2e7; }
.btn-send { padding: 0 20px; background: #cba6f7; border: none; border-radius: 8px; color: #11111b; font-size: 15px; font-weight: bold; cursor: pointer; transition: background 0.2s; display: flex; align-items: center; justify-content: center; }
.btn-send:hover { background: #f5c2e7; }
.btn-send:disabled { background: #45475a; color: #a6adc8; cursor: not-allowed; }
.nav-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
.btn-nav { text-decoration: none; text-align: center; padding: 10px; border-radius: 6px; font-size: 13px; font-weight: 600; color: #11111b; transition: opacity 0.2s; }
.btn-nav:hover { opacity: 0.9; }
.btn-settings { background: #89b4fa; }
.btn-update { background: #a6e3a1; }
.btn-reset { grid-column: span 2; background: #f38ba8; }
.footer { margin: 15px 0 0 0; font-size: 12px; color: #6c7086; text-align: center; }
.footer a { color: #89b4fa; text-decoration: none; }
</style>
</head>
<body>
<div class="card">
<h1>🍞 Sourdough Assistant 🤖</h1>
<p class="subtitle">On-Device PLE INT4 Inference REPL</p>

<div class="status-bar">
<div class="badge">Wi-Fi: <span>%SSID% (%RSSI% dBm)</span></div>
<div class="badge">IP: <span>%IP%:8080</span></div>
<div class="badge">PSRAM: <span>%FREE_PSRAM% KB free</span></div>
<div class="badge">SRAM: <span>%FREE_SRAM% KB free</span></div>
</div>

<div id="chat" class="chat-container">
<div class="msg msg-assistant">
Hello! I am your on-device Sourdough Baker Assistant. Ask me anything about feeding schedules, hydration, proofing, dough strength, or diagnosing bread baking problems!
</div>
</div>

<div class="input-group">
<textarea id="prompt" placeholder="Ask a sourdough question (e.g. Why is my crumb dense?)..." onkeydown="handleKey(event)"></textarea>
<button id="sendBtn" class="btn-send" onclick="sendQuery()">Ask</button>
</div>

<div class="nav-grid">
<a href="/settings" class="btn-nav btn-settings">⚙️ Inference Settings</a>
<a href="/update" class="btn-nav btn-update">🔄 Firmware Update (OTA)</a>
<a href="/reset" class="btn-nav btn-reset" onclick="return confirm('Reboot into Wi-Fi captive portal setup?');">📶 Reconfigure Wi-Fi</a>
</div>

<p class="footer">Built for ESP32-S3 Sourdough Assistant | <a href="https://github.com/nicholaswilde/esp32-sourdough-assistant" target="_blank">GitHub</a></p>
</div>

<script>
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQuery();
  }
}

async function sendQuery() {
  const promptInput = document.getElementById('prompt');
  const sendBtn = document.getElementById('sendBtn');
  const chat = document.getElementById('chat');
  const text = promptInput.value.trim();
  if (!text) return;

  promptInput.value = '';
  sendBtn.disabled = true;

  const userBubble = document.createElement('div');
  userBubble.className = 'msg msg-user';
  userBubble.textContent = text;
  chat.appendChild(userBubble);

  const assistantBubble = document.createElement('div');
  assistantBubble.className = 'msg msg-assistant';
  assistantBubble.textContent = 'Thinking...';
  chat.appendChild(assistantBubble);
  chat.scrollTop = chat.scrollHeight;

  const startTime = performance.now();
  try {
    const res = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'esp32-sourdough',
        messages: [{ role: 'user', content: text }]
      })
    });
    const data = await res.json();
    const elapsedSec = ((performance.now() - startTime) / 1000).toFixed(2);

    if (data.choices && data.choices[0] && data.choices[0].message) {
      const content = data.choices[0].message.content.trim();
      const nTokens = data.usage ? data.usage.completion_tokens : 0;
      const tokSec = nTokens > 0 && elapsedSec > 0 ? (nTokens / elapsedSec).toFixed(1) : 0;
      assistantBubble.textContent = content;
      const meta = document.createElement('div');
      meta.className = 'msg-meta';
      meta.textContent = `${nTokens} tokens in ${elapsedSec}s (${tokSec} tok/s)`;
      assistantBubble.appendChild(meta);
    } else {
      assistantBubble.textContent = 'Error: ' + JSON.stringify(data);
    }
  } catch (err) {
    assistantBubble.textContent = 'Network or inference error: ' + err.message;
  }

  sendBtn.disabled = false;
  chat.scrollTop = chat.scrollHeight;
}
</script>
</body>
</html>)rawhtml";

#endif // LANDING_HTML_H
