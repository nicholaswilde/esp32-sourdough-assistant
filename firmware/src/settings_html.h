#ifndef SETTINGS_HTML_H
#define SETTINGS_HTML_H

#ifndef NATIVE_TEST
#include <pgmspace.h>
#endif

const char settings_html[] PROGMEM = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sourdough Assistant 🤖 - Settings</title>
<style>
body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; box-sizing: border-box; }
.card { background: #181825; border-radius: 12px; padding: 28px 24px; width: 100%; max-width: 500px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; }
h2 { color: #f5c2e7; margin: 0 0 4px 0; font-weight: 600; text-align: center; }
.subtitle { text-align: center; color: #a6adc8; margin: 0 0 20px 0; font-size: 14px; }
.section-title { color: #89b4fa; font-size: 16px; font-weight: 600; margin-top: 20px; margin-bottom: 12px; border-bottom: 1px solid #313244; padding-bottom: 5px; }
label { display: block; margin-bottom: 6px; color: #a6adc8; font-size: 13px; }
select, input[type='number'] { width: 100%; padding: 10px 12px; margin-bottom: 16px; border-radius: 6px; border: 1px solid #45475a; background: #313244; color: #cdd6f4; font-size: 14px; box-sizing: border-box; }
select:focus, input:focus { outline: none; border-color: #f5c2e7; }
.slider-group { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.slider-group input[type='range'] { flex-grow: 1; margin: 0; cursor: pointer; accent-color: #cba6f7; }
.slider-group input[type='number'] { width: 75px; margin-bottom: 0; flex-shrink: 0; }
button { width: 100%; padding: 12px; background: #cba6f7; border: none; border-radius: 6px; color: #11111b; font-size: 15px; font-weight: bold; cursor: pointer; transition: background 0.2s; margin-top: 10px; }
button:hover { background: #f5c2e7; }
.info-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; font-size: 13px; }
.info-table td { padding: 6px 0; border-bottom: 1px solid #313244; }
.info-table td:first-child { color: #a6adc8; }
.info-table td:last-child { color: #cdd6f4; text-align: right; font-family: monospace; }
.btn-back { display: block; margin-top: 15px; color: #a6adc8; text-decoration: none; font-size: 13px; text-align: center; transition: color 0.2s; }
.btn-back:hover { color: #cdd6f4; }
</style>
</head>
<body>
<div class="card">
<h2>⚙️ Assistant Settings</h2>
<p class="subtitle">Inference & System Tuning</p>

<form method="POST" action="/settings/save">
<div class="section-title" style="margin-top: 0;">Inference Sampling</div>

<label for="temperature">Sampling Temperature (%TEMPERATURE%)</label>
<div class="slider-group">
  <input type="range" id="temp_slider" min="0" max="2" step="0.05" value="%TEMPERATURE%" oninput="document.getElementById('temperature').value = this.value">
  <input type="number" id="temperature" name="temperature" min="0" max="2" step="0.05" value="%TEMPERATURE%" oninput="document.getElementById('temp_slider').value = this.value">
</div>

<label for="topp">Top-p Nucleus Threshold (%TOP_P%)</label>
<div class="slider-group">
  <input type="range" id="topp_slider" min="0.05" max="1" step="0.05" value="%TOP_P%" oninput="document.getElementById('topp').value = this.value">
  <input type="number" id="topp" name="topp" min="0.05" max="1" step="0.05" value="%TOP_P%" oninput="document.getElementById('topp_slider').value = this.value">
</div>

<label for="subvocab">Sub-vocabulary Prediction</label>
<select id="subvocab" name="subvocab">
  <option value="0" %SUBVOCAB_0%>Disabled (Full 1,882 Vocab Evaluation)</option>
  <option value="2" %SUBVOCAB_2%>Top 2 Clusters (Ultra Fast)</option>
  <option value="4" %SUBVOCAB_4%>Top 4 Clusters (Default Balanced)</option>
  <option value="8" %SUBVOCAB_8%>Top 8 Clusters (High Accuracy)</option>
  <option value="16" %SUBVOCAB_16%>All 16 Clusters</option>
</select>

<div class="section-title">System & Partition Telemetry</div>
<table class="info-table">
  <tr><td>Model Partition</td><td>0x520000 (10.88 MB INT4)</td></tr>
  <tr><td>Internal SRAM</td><td>%FREE_SRAM% KB free / %TOTAL_SRAM% KB</td></tr>
  <tr><td>Octal PSRAM</td><td>%FREE_PSRAM% KB free / %TOTAL_PSRAM% KB</td></tr>
  <tr><td>Wi-Fi Network</td><td>%SSID%</td></tr>
  <tr><td>Device IP</td><td>%IP%:8080</td></tr>
  <tr><td>Signal RSSI</td><td>%RSSI% dBm</td></tr>
</table>

<button type="submit">💾 Save & Apply Settings</button>
<a href="/" class="btn-back">← Back to Assistant</a>
</form>
</div>
</body>
</html>)rawhtml";

const char settings_saved_html[] PROGMEM = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="2;url=/settings">
<title>Settings Saved</title>
<style>
body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; box-sizing: border-box; }
.card { background: #181825; border-radius: 12px; padding: 30px; width: 100%; max-width: 400px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; text-align: center; }
h2 { color: #a6e3a1; margin-top: 0; margin-bottom: 12px; }
p { color: #cdd6f4; margin: 6px 0; font-size: 14px; }
.muted { color: #a6adc8; font-size: 12px; margin-top: 16px; }
</style>
</head>
<body>
<div class="card">
<h2>✓ Settings Saved</h2>
<p>Temperature: <strong>%TEMPERATURE%</strong></p>
<p>Top-p: <strong>%TOP_P%</strong></p>
<p>Sub-vocabulary: <strong>%SUBVOCAB%</strong></p>
<p class="muted">Returning to settings in 2 seconds...</p>
</div>
</body>
</html>)rawhtml";

#endif // SETTINGS_HTML_H
