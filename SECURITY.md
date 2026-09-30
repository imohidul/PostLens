# Security policy

## Reporting a vulnerability
Please **don't open a public issue** for security problems. Use GitHub's private reporting instead:
[Report a vulnerability](https://github.com/imohidul/PostLens/security/advisories/new).
You'll get a reply as soon as possible.

## How PostLens protects your data
- The app only listens on `127.0.0.1`, so other computers can't reach it.
- API keys are stored in the operating system's credential vault (Windows Credential Manager, macOS Keychain). They are never written to settings files, logs, exports or the project folder, and are never sent back to the web page.
- Collected data stays in `.postlens` in your user folder.
- `tests/test_security.py` fails the build if something that looks like an API key is committed.
