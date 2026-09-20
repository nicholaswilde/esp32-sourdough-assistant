#ifndef ARDUINO_MOCK_H
#define ARDUINO_MOCK_H

#include <stdint.h>
#include <string>
#include <iostream>
#include <stdarg.h>

class String : public std::string {
public:
    String(const char* s) : std::string(s ? s : "") {}
    String(const std::string& s) : std::string(s) {}
    String() : std::string() {}
    String(int val) : std::string(std::to_string(val)) {}

    const char* c_str() const { return std::string::c_str(); }

    bool startsWith(const char* prefix) const {
        std::string p(prefix);
        return this->rfind(p, 0) == 0;
    }

    int indexOf(const char* val) const {
        size_t pos = this->find(val);
        return (pos == std::string::npos) ? -1 : (int)pos;
    }

    String substring(size_t from, size_t to = std::string::npos) const {
        if (from >= this->length()) return String("");
        if (to == std::string::npos || to > this->length()) {
            return String(this->substr(from));
        }
        return String(this->substr(from, to - from));
    }

    String& operator+=(const String& other) {
        this->append(other);
        return *this;
    }
    String& operator+=(const char* other) {
        if (other) this->append(other);
        return *this;
    }
};

inline String operator+(const String& lhs, const String& rhs) {
    String res = lhs;
    res.append(rhs);
    return res;
}

inline String operator+(const String& lhs, const char* rhs) {
    String res = lhs;
    if (rhs) res.append(rhs);
    return res;
}

inline String operator+(const char* lhs, const String& rhs) {
    String res(lhs ? lhs : "");
    res.append(rhs);
    return res;
}

class IPAddress {
public:
    String toString() const { return "192.168.4.1"; }
};

class SerialMock {
public:
    void println(const char* s) {}
    void println(const String& s) {}
    void print(const char* s) {}
    void print(char c) {}
    void printf(const char* format, ...) {}
};

static SerialMock Serial;

inline unsigned long millis() {
    return 0;
}

inline void delay(unsigned long ms) {}

#ifndef PROGMEM
#define PROGMEM
#endif

#endif // ARDUINO_MOCK_H

