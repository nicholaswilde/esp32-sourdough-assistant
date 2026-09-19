---
name: create-sandbox
description: Creates a new ESP32 sandbox project complete with platformio.ini, README.md, and updates the root Taskfile.yml.
---

# Create Sandbox

When the user asks you to create a new sandbox project, use this skill to quickly bootstrap it.

## Instructions

1. Use `run_command` to execute the bundled Python script from the repository root:
   ```bash
   python3 .agents/skills/create-sandbox/scripts/create_sandbox.py <project-name> "<optional description>"
   ```
2. Verify that the script successfully ran, created the folder, and updated `Taskfile.yml`.
3. Inform the user that the project was created and is ready for use.
4. DO NOT manually edit `Taskfile.yml` or create the boilerplate files yourself; the script handles the entire workflow automatically and safely.

## Features
- Generates `src/main.cpp`, `platformio.ini`, and `README.md`.
- Automatically injects `build:<project-name>` and `test:<project-name>` into `Taskfile.yml` and adds them to the `build:all` and `test:all` dependencies.
