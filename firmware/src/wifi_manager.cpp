#include "wifi_manager.h"

WifiManager::WifiManager(const char* defaultSSID, const char* defaultPassword)
    : _defaultSSID(defaultSSID),
      _defaultPassword(defaultPassword),
      _ssid(defaultSSID),
      _password(defaultPassword),
      _state(WIFI_STATE_DISCONNECTED),
      _lastReconnectAttempt(0),
      _connectionStartTime(0) {}


void WifiManager::begin() {
    Serial.println("[WiFi] Starting Wi-Fi Manager...");
    loadCredentials();

#ifndef NATIVE_TEST
    WiFi.mode(WIFI_STA);

    if (_ssid.length() == 0 || _ssid == "your_wifi_network") {
        Serial.println("[WiFi] No valid credentials configured. Launching AP mode directly...");
        startAPMode();
    } else {
        WiFi.setHostname("esp32-sourdough");
        WiFi.begin(_ssid.c_str(), _password.c_str());
        _state = WIFI_STATE_CONNECTING;
        _connectionStartTime = millis();
        Serial.printf("[WiFi] Connecting to %s...\n", _ssid.c_str());
    }
#endif
}

void WifiManager::update() {
#ifndef NATIVE_TEST
    wl_status_t status = WiFi.status();

    switch (_state) {
        case WIFI_STATE_DISCONNECTED:
            if (millis() - _lastReconnectAttempt > _reconnectInterval) {
                _lastReconnectAttempt = millis();
                Serial.println("[WiFi] Reconnecting...");
                WiFi.setHostname("esp32-sourdough");
                WiFi.begin(_ssid.c_str(), _password.c_str());
                _state = WIFI_STATE_CONNECTING;
                _connectionStartTime = millis();
            }
            break;

        case WIFI_STATE_CONNECTING:
            if (status == WL_CONNECTED) {
                _state = WIFI_STATE_CONNECTED;
                Serial.print("[WiFi] Connected! IP address: ");
                Serial.println(WiFi.localIP());
            } else if (status == WL_CONNECT_FAILED || status == WL_NO_SSID_AVAIL || (millis() - _connectionStartTime > _connectionTimeout)) {
                Serial.println("[WiFi] Connection failed or timed out. Transitioning to AP Mode...");
                startAPMode();
            }
            break;

        case WIFI_STATE_CONNECTED:
            if (status != WL_CONNECTED) {
                _state = WIFI_STATE_DISCONNECTED;
                _lastReconnectAttempt = millis();
                Serial.println("[WiFi] Connection lost.");
            }
            break;

        case WIFI_STATE_AP_MODE:
            if (WiFi.status() == WL_CONNECTED) {
                Serial.println("[WiFi] Wi-Fi connected in background. Stopping AP Mode...");
                stopAPMode();
                _state = WIFI_STATE_CONNECTED;
                Serial.print("[WiFi] Connected! IP address: ");
                Serial.println(WiFi.localIP());
            } else {
                if (_dnsServer) _dnsServer->processNextRequest();
                if (_webServer) _webServer->handleClient();
            }
            break;
    }
#endif
}

WifiState WifiManager::getState() const {
    return _state;
}

String WifiManager::getIPAddress() const {
#ifndef NATIVE_TEST
    if (_state == WIFI_STATE_CONNECTED) {
        return WiFi.localIP().toString();
    } else if (_state == WIFI_STATE_AP_MODE) {
        return "192.168.4.1";
    }
#endif
    return "0.0.0.0";
}

int8_t WifiManager::getRSSI() const {
#ifndef NATIVE_TEST
    if (_state == WIFI_STATE_CONNECTED) {
        return WiFi.RSSI();
    }
#endif
    return -100;
}

String WifiManager::getSSID() const {
    return _ssid;
}

void WifiManager::setCredentials(const String& ssid, const String& password) {
    _ssid = ssid;
    _password = password;
}

String WifiManager::getAPSSID() {
#ifndef NATIVE_TEST
    String mac = WiFi.macAddress();
    String cleanMac = "";
    for (size_t i = 0; i < mac.length(); i++) {
        if (mac[i] != ':') {
            cleanMac += mac[i];
        }
    }
    String suffix = "";
    if (cleanMac.length() >= 4) {
        suffix = String(cleanMac.c_str() + cleanMac.length() - 4);
    } else {
        suffix = "ESP32";
    }
    for (size_t i = 0; i < suffix.length(); i++) {
        suffix[i] = toupper(suffix[i]);
    }
    return "sourdough-assistant-" + suffix;
#else
    return "sourdough-assistant-TEST";
#endif
}

void WifiManager::startAPMode() {
    _state = WIFI_STATE_AP_MODE;
    String apSSID = getAPSSID();
    Serial.printf("[WiFi] Entering AP Mode. SSID: %s\n", apSSID.c_str());

#ifndef NATIVE_TEST
    WiFi.persistent(false);
    WiFi.setAutoReconnect(false);
    WiFi.disconnect();
    delay(200);

    WiFi.mode(WIFI_AP_STA);
    delay(100);

    IPAddress apIP(192, 168, 4, 1);
    WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
    delay(100);

    WiFi.softAP(apSSID.c_str());
    delay(200);

    _cachedNetworksHTML = "<div class='net-item' style='color: #a6adc8;'>Scanning in progress... Please refresh.</div>";

    if (_dnsServer) {
        _dnsServer->stop();
        delete _dnsServer;
        _dnsServer = nullptr;
    }
    _dnsServer = new DNSServer();
    _dnsServer->setErrorReplyCode(DNSReplyCode::NoError);
    _dnsServer->start(53, "*", apIP);

    if (_webServer) {
        _webServer->stop();
        delete _webServer;
        _webServer = nullptr;
    }
    _webServer = new WebServer(80);

    _webServer->on("/", [this]() { handleRoot(); });
    _webServer->on("/save", HTTP_POST, [this]() { handleSave(); });
    _webServer->on("/scan", [this]() { handleScan(); });
    // Captive portal probes
    _webServer->on("/generate_204", [this]() { handleNotFound(); });
    _webServer->on("/hotspot-detect.html", [this]() { handleNotFound(); });
    _webServer->on("/canonical.html", [this]() { handleNotFound(); });
    _webServer->on("/connecttest.txt", [this]() { handleNotFound(); });
    _webServer->onNotFound([this]() { handleNotFound(); });

    _webServer->begin();
    Serial.println("[WiFi] AP Mode Web Server and DNS Server started.");

    // Trigger initial asynchronous scan
    WiFi.scanNetworks(true, false, false, 150);
#endif
}

void WifiManager::stopAPMode() {
#ifndef NATIVE_TEST
    if (_dnsServer) {
        _dnsServer->stop();
        delete _dnsServer;
        _dnsServer = nullptr;
    }
    if (_webServer) {
        _webServer->stop();
        delete _webServer;
        _webServer = nullptr;
    }
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_STA);
#endif
}

void WifiManager::handleRoot() {
#ifndef NATIVE_TEST
    int16_t scanStatus = WiFi.scanComplete();
    if (scanStatus >= 0) {
        _cachedNetworksHTML = "";
        for (int i = 0; i < scanStatus; ++i) {
            String ssidName = WiFi.SSID(i);
            int32_t rssi = WiFi.RSSI(i);
            _cachedNetworksHTML += "<div class='net-item' onclick='selectSSID(\"" + ssidName + "\")'>";
            _cachedNetworksHTML += "<span>" + ssidName + "</span>";
            _cachedNetworksHTML += "<span style='color: #a6adc8; font-size: 12px;'>" + String(rssi) + " dBm</span>";
            _cachedNetworksHTML += "</div>";
        }
        WiFi.scanDelete();
    } else if (scanStatus == WIFI_SCAN_FAILED) {
        WiFi.scanNetworks(true, false, false, 150);
        if (_cachedNetworksHTML.length() == 0 || _cachedNetworksHTML.indexOf("Scanning in progress") != -1) {
            _cachedNetworksHTML = "<div class='net-item' style='color: #a6adc8;'>Scanning in progress... Please refresh.</div>";
        }
    }

    String html = generatePortalHTML(scanStatus, _cachedNetworksHTML, _ssid);
    _webServer->send(200, "text/html", html);
#endif
}

void WifiManager::handleScan() {
#ifndef NATIVE_TEST
    WiFi.scanNetworks(true, false, false, 150);
    String html = generateScanningHTML();
    _webServer->send(200, "text/html", html);
#endif
}

void WifiManager::handleSave() {
#ifndef NATIVE_TEST
    String ssid = _webServer->arg("ssid");
    String pass = _webServer->arg("pass");

    Serial.printf("[WiFi] Saved new credentials via captive portal: %s\n", ssid.c_str());

    String html = generateSavedHTML(ssid);
    saveCredentials(ssid, pass);

    _webServer->send(200, "text/html", html);
    delay(1000);

    ESP.restart();
#endif
}

void WifiManager::handleNotFound() {
#ifndef NATIVE_TEST
    _webServer->sendHeader("Location", "http://192.168.4.1/", true);
    _webServer->send(302, "text/plain", "");
#endif
}

void WifiManager::loadCredentials() {
#ifndef NATIVE_TEST
    Preferences prefs;
    if (prefs.begin("wifi", true)) {
        _ssid = prefs.getString("ssid", _defaultSSID.c_str());
        _password = prefs.getString("pass", _defaultPassword.c_str());
        prefs.end();
    } else {
        _ssid = _defaultSSID;
        _password = _defaultPassword;
    }
#endif
}

void WifiManager::saveCredentials(const String& ssid, const String& password) {
    _ssid = ssid;
    _password = password;
#ifndef NATIVE_TEST
    Preferences prefs;
    if (prefs.begin("wifi", false)) {
        prefs.putString("ssid", ssid);
        prefs.putString("pass", password);
        prefs.end();
    }
#endif
}

void WifiManager::resetSettings() {
#ifndef NATIVE_TEST
    Preferences prefs;
    if (prefs.begin("wifi", false)) {
        prefs.clear();
        prefs.end();
    }
#endif
    _ssid = _defaultSSID;
    _password = _defaultPassword;
}


String WifiManager::generatePortalHTML(int16_t scanStatus, const String& networksHTML, const String& currentSSID) {
    String html = "<!DOCTYPE html><html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">";
#ifndef NATIVE_TEST
    if (scanStatus == WIFI_SCAN_RUNNING || scanStatus == WIFI_SCAN_FAILED) {
        html += "<meta http-equiv='refresh' content='3'>";
    }
#endif
    html += "<title>Sourdough Assistant 🤖 Setup</title>";
    html += "<style>";
    html += "body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; box-sizing: border-box; }";
    html += ".card { background: #181825; border-radius: 12px; padding: 30px; width: 100%; max-width: 400px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; }";
    html += "h2 { color: #f5c2e7; margin-top: 0; margin-bottom: 5px; font-weight: 600; text-align: center; }";
    html += ".subtitle { text-align: center; color: #a6adc8; margin-top: 0; margin-bottom: 20px; font-size: 14px; }";
    html += "label { display: block; margin-bottom: 8px; color: #a6adc8; font-size: 14px; }";
    html += "select, input[type='text'], input[type='password'] { width: 100%; padding: 12px; margin-bottom: 20px; border-radius: 6px; border: 1px solid #45475a; background: #313244; color: #cdd6f4; font-size: 16px; box-sizing: border-box; }";
    html += "select:focus, input:focus { outline: none; border-color: #f5c2e7; }";
    html += "button { width: 100%; padding: 12px; background: #cba6f7; border: none; border-radius: 6px; color: #11111b; font-size: 16px; font-weight: bold; cursor: pointer; transition: background 0.2s; }";
    html += "button:hover { background: #f5c2e7; }";
    html += ".section-title { color: #89b4fa; font-size: 18px; margin-top: 0; margin-bottom: 15px; border-bottom: 1px solid #313244; padding-bottom: 5px; }";
    html += ".net-list { margin-bottom: 20px; max-height: 150px; overflow-y: auto; border: 1px solid #313244; border-radius: 6px; padding: 10px; background: #11111b; }";
    html += ".net-item { display: flex; justify-content: space-between; padding: 8px; cursor: pointer; border-bottom: 1px solid #1e1e2e; }";
    html += ".net-item:last-child { border-bottom: none; }";
    html += ".net-item:hover { background: #313244; color: #f5c2e7; }";
    html += ".password-wrapper { position: relative; display: block; margin-bottom: 20px; }";
    html += ".toggle-password { position: absolute; right: 12px; top: 12px; cursor: pointer; color: #a6adc8; }";
    html += ".footer { margin-top: 25px; margin-bottom: 0; font-size: 13px; color: #6c7086; text-align: center; }";
    html += ".footer a { color: #89b4fa; text-decoration: none; }";
    html += "</style>";
    html += "<script>";
    html += "function selectSSID(ssid) { document.getElementById('ssid').value = ssid; }";
    html += "function togglePwd(id, el) {";
    html += "    var eyeSvg = '<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z\"></path><circle cx=\"12\" cy=\"12\" r=\"3\"></circle></svg>';";
    html += "    var eyeOffSvg = '<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24\"></path><line x1=\"1\" y1=\"1\" x2=\"23\" y2=\"23\"></line></svg>';";
    html += "    var input = document.getElementById(id);";
    html += "    if (input.type === \"password\") {";
    html += "        input.type = \"text\";";
    html += "        el.innerHTML = eyeOffSvg;";
    html += "    } else {";
    html += "        input.type = \"password\";";
    html += "        el.innerHTML = eyeSvg;";
    html += "    }";
    html += "}";
    html += "</script>";
    html += "</head><body>";
    html += "<div class='card'>";
    html += "<h2>Sourdough Assistant 🤖</h2>";
    html += "<p class='subtitle'>Wi-Fi Setup</p>";
    html += "<form method='POST' action='/save'>";
    html += "<div class='section-title'>Wi-Fi Connection</div>";
    html += "<div style='display: flex; justify-content: space-between; align-items: center;'>";
    html += "<label style='margin-bottom: 0;'>Select Network</label>";
    html += "<a href='/scan' style='color: #cba6f7; font-size: 12px; text-decoration: none;'>&#x21bb; Refresh List</a>";
    html += "</div>";
    html += "<div style='height: 8px;'></div>";
    html += "<div class='net-list'>";
    html += networksHTML;
    html += "</div>";
    String formSSID = (currentSSID == "your_wifi_network") ? "" : currentSSID;
    html += "<label for='ssid'>SSID</label>";
    html += "<input type='text' id='ssid' name='ssid' placeholder='SSID name' value='" + formSSID + "' required>";

    html += "<label for='pass'>Password</label>";
    html += "<div class='password-wrapper'>";
    html += "<input type='password' id='pass' name='pass' placeholder='Password'>";
    html += "<span class='toggle-password' onclick='togglePwd(\"pass\", this)'><svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z\"></path><circle cx=\"12\" cy=\"12\" r=\"3\"></circle></svg></span>";
    html += "</div>";
    html += "<button type='submit'>Save & Connect</button>";
    html += "</form>";
    html += "<p class='footer'>Built for ESP32-S3 Sourdough Assistant | <a href=\"https://github.com/nicholaswilde/esp32-sourdough-assistant\" target=\"_blank\">GitHub</a></p>";
    html += "</div>";
    html += "</body></html>";
    return html;
}

String WifiManager::generateSavedHTML(const String& ssid) {
    String html = "<!DOCTYPE html><html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">";
    html += "<title>Credentials Saved</title>";
    html += "<style>";
    html += "body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; box-sizing: border-box; }";
    html += ".card { background: #181825; border-radius: 12px; padding: 30px; width: 100%; max-width: 400px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; text-align: center; }";
    html += "h2 { color: #a6e3a1; margin-top: 0; margin-bottom: 20px; }";
    html += "p { color: #cdd6f4; margin-bottom: 20px; line-height: 1.5; }";
    html += "</style></head><body>";
    html += "<div class='card'>";
    html += "<h2>Configuration Saved</h2>";
    html += "<p>Connecting to <strong>" + ssid + "</strong>...</p>";
    html += "<p>The device will now reboot to apply the new settings. You can close this page.</p>";
    html += "</div>";
    html += "</body></html>";
    return html;
}

String WifiManager::generateScanningHTML() {
    String html = "<!DOCTYPE html><html><head>";
    html += "<meta http-equiv='refresh' content='3;url=/'>";
    html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
    html += "<title>Scanning...</title>";
    html += "<style>";
    html += "body { font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; box-sizing: border-box; }";
    html += ".card { background: #181825; border-radius: 12px; padding: 30px; width: 100%; max-width: 400px; box-shadow: 0 8px 30px rgba(0,0,0,0.3); border: 1px solid #313244; text-align: center; }";
    html += "h2 { color: #f5c2e7; margin-top: 0; }";
    html += "p { color: #a6adc8; }";
    html += "</style></head><body>";
    html += "<div class='card'><h2>Scanning for Wi-Fi...</h2><p>Please wait while we refresh the network list.</p></div>";
    html += "</body></html>";
    return html;
}
