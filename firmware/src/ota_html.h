#ifndef OTA_HTML_H
#define OTA_HTML_H

#ifndef NATIVE_TEST
#include <pgmspace.h>
#endif

const char ota_html[] PROGMEM = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sourdough Assistant 🤖 - Firmware Update</title>
<style>
body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; box-sizing: border-box; }
.card { background: #181825; border-radius: 12px; padding: 30px; width: 100%; max-width: 440px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; text-align: center; }
h2 { color: #f5c2e7; margin-top: 0; margin-bottom: 6px; font-weight: 600; }
.subtitle { color: #a6adc8; margin-top: 0; margin-bottom: 20px; font-size: 14px; }
.drop-zone { border: 2px dashed #45475a; border-radius: 8px; padding: 28px 10px; margin-bottom: 18px; cursor: pointer; transition: border-color 0.2s, background-color 0.2s; }
.drop-zone:hover, .drop-zone.dragover { border-color: #89b4fa; background: #313244; }
.drop-zone p { margin: 0; color: #a6adc8; font-size: 14px; }
input[type="file"] { display: none; }
button { width: 100%; padding: 12px; background: #cba6f7; border: none; border-radius: 6px; color: #11111b; font-size: 15px; font-weight: bold; cursor: pointer; transition: background-color 0.2s; }
button:hover { background: #f5c2e7; }
button:disabled { background: #45475a; color: #a6adc8; cursor: not-allowed; }
.progress-container { margin-top: 18px; display: none; }
.progress-bar-bg { background: #313244; border-radius: 6px; height: 12px; overflow: hidden; }
.progress-bar { background: #a6e3a1; width: 0%; height: 100%; transition: width 0.2s; }
.status-text { margin-top: 10px; font-size: 13px; color: #cdd6f4; }
.btn-back { display: block; margin-top: 18px; color: #a6adc8; text-decoration: none; font-size: 13px; text-align: center; }
.btn-back:hover { color: #cdd6f4; }
</style>
</head>
<body>
<div class="card">
<h2>🔄 Firmware Update</h2>
<p class="subtitle">Select or drop a compiled firmware.bin</p>

<div class="drop-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
  <p id="fileLabel">📁 Click to browse or drag & drop .bin file</p>
  <input type="file" id="fileInput" accept=".bin">
</div>

<button id="uploadBtn" disabled onclick="uploadFirmware()">Upload & Flash</button>

<div class="progress-container" id="progressContainer">
  <div class="progress-bar-bg">
    <div class="progress-bar" id="progressBar"></div>
  </div>
  <div class="status-text" id="statusText">0%</div>
</div>

<a href="/" class="btn-back">← Back to Assistant</a>
</div>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileLabel = document.getElementById('fileLabel');
const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const statusText = document.getElementById('statusText');

let selectedFile = null;

['dragenter', 'dragover'].forEach(name => {
  dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.add('dragover'); }, false);
});
['dragleave', 'drop'].forEach(name => {
  dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); }, false);
});
dropZone.addEventListener('drop', (e) => {
  if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
}, false);
fileInput.addEventListener('change', (e) => {
  if (e.target.files.length > 0) handleFile(e.target.files[0]);
});

function handleFile(file) {
  if (!file.name.endsWith('.bin')) {
    alert('Please select a valid .bin firmware file');
    return;
  }
  selectedFile = file;
  fileLabel.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  uploadBtn.disabled = false;
}

function uploadFirmware() {
  if (!selectedFile) return;
  uploadBtn.disabled = true;
  dropZone.style.pointerEvents = 'none';
  progressContainer.style.display = 'block';

  const xhr = new XMLHttpRequest();
  const formData = new FormData();
  formData.append('firmware', selectedFile, selectedFile.name);

  xhr.upload.addEventListener('progress', (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressBar.style.width = pct + '%';
      statusText.textContent = `Uploading: ${pct}%`;
    }
  });

  xhr.addEventListener('load', () => {
    if (xhr.status === 200) {
      progressBar.style.width = '100%';
      statusText.textContent = 'Update successful! Rebooting device in 5 seconds...';
      statusText.style.color = '#a6e3a1';
      setTimeout(() => { window.location.href = '/'; }, 6000);
    } else {
      statusText.textContent = `Upload failed (Status ${xhr.status}): ${xhr.responseText}`;
      statusText.style.color = '#f38ba8';
    }
  });

  xhr.addEventListener('error', () => {
    statusText.textContent = 'Upload encountered a network error.';
    statusText.style.color = '#f38ba8';
  });

  xhr.open('POST', '/v1/update');
  xhr.send(formData);
}
</script>
</body>
</html>)rawhtml";

#endif // OTA_HTML_H
