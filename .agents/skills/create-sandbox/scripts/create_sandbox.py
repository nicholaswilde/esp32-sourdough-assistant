import sys
import os
import re

if len(sys.argv) < 2:
    print("Usage: python3 create_sandbox.py <project_name> [description]")
    sys.exit(1)

project_name = sys.argv[1]
desc = sys.argv[2] if len(sys.argv) > 2 else f"Sandbox project: {project_name}"

if os.path.exists(f"projects/{project_name}"):
    print(f"Error: Directory {project_name} already exists.")
    sys.exit(1)

print(f"Creating project {project_name}...")
os.makedirs(f"projects/{project_name}/src", exist_ok=True)

with open(f"projects/{project_name}/platformio.ini", "w") as f:
    f.write(f"""[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200

[env:native]
platform = native
""")

with open(f"projects/{project_name}/README.md", "w") as f:
    f.write(f"# {project_name}\n\n{desc}\n")

with open(f"projects/{project_name}/src/main.cpp", "w") as f:
    f.write("""#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  Serial.println("Hello from sandbox!");
}

void loop() {
  delay(1000);
}
""")

os.makedirs(f"projects/{project_name}/test", exist_ok=True)
with open(f"projects/{project_name}/test/test_main.cpp", "w") as f:
    f.write("""#include <unity.h>

void test_dummy() { TEST_ASSERT_EQUAL(1, 1); }

int main(int argc, char **argv) {
    UNITY_BEGIN();
    RUN_TEST(test_dummy);
    UNITY_END();
    return 0;
}
""")

print("Updating Taskfile.yml...")
try:
    with open("Taskfile.yml", "r") as f:
        content = f.read()

    build_dep = f"      - build:{project_name}\n"
    test_dep = f"      - test:{project_name}\n"

    # Safely insert the dependency into the list
    content = re.sub(r"(build:all:[\s\S]*?deps:\n)", r"\1" + build_dep, content, 1)
    content = re.sub(r"(test:all:[\s\S]*?deps:\n)", r"\1" + test_dep, content, 1)

    new_tasks = f"""
  build:{project_name}:
    desc: Build the {project_name} sandbox project
    dir: projects/{project_name}
    cmds:
      - pio run

  test:{project_name}:
    desc: Run host-native tests for the {project_name} sandbox project
    dir: projects/{project_name}
    cmds:
      - pio test -e native
"""
    content += new_tasks

    with open("Taskfile.yml", "w") as f:
        f.write(content)
except Exception as e:
    print(f"Warning: Failed to update Taskfile.yml: {e}")

print("Done!")
