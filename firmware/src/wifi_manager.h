#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Arduino.h>

#ifndef NATIVE_TEST
#include <WiFi.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <Preferences.h>
#endif

enum WifiState {
    WIFI_STATE_DISCONNECTED,
    WIFI_STATE_CONNECTING,
    WIFI_STATE_CONNECTED,
    WIFI_STATE_AP_MODE
};

class WifiManager {
public:
    WifiManager(const char* defaultSSID = "", const char* defaultPassword = "");
    void begin();
    void update();
    WifiState getState() const;
    String getIPAddress() const;
    int8_t getRSSI() const;
    String getSSID() const;
    void setCredentials(const String& ssid, const String& password);
    String getAPSSID();
    void resetSettings();
    void startAPMode();

    // HTML generation helpers
    static String generatePortalHTML(int16_t scanStatus, const String& networksHTML, const String& currentSSID = "");
    static String generateSavedHTML(const String& ssid);
    static String generateScanningHTML();

private:
    void stopAPMode();
    void handleRoot();
    void handleSave();
    void handleScan();
    void handleNotFound();
    void loadCredentials();
    void saveCredentials(const String& ssid, const String& password);

    String _defaultSSID;
    String _defaultPassword;
    String _ssid;
    String _password;

    WifiState _state;
    unsigned long _lastReconnectAttempt;
    unsigned long _connectionStartTime;
    const unsigned long _reconnectInterval = 10000; // 10 seconds
    const unsigned long _connectionTimeout = 20000; // 20 seconds
    String _cachedNetworksHTML;

#ifndef NATIVE_TEST
    DNSServer* _dnsServer = nullptr;
    WebServer* _webServer = nullptr;
#endif
};

#endif // WIFI_MANAGER_H
