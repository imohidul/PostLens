# Changelog

All notable changes to PostLens are documented here. This project uses [semantic versioning](https://semver.org/).

## [1.0.4] - 2026-10-02

### Changed
- The interface now runs on React 19 (`react`, `react-dom` and their type definitions upgraded together).

## [1.0.3] - 2026-10-02

### Changed
- UI build tools updated to Vite 8 (with the matching React and Tailwind plugins), and React Router to 7.18, which fixes two security advisories (open redirect, constructor injection) reported against older versions.

### Fixed
- Card titles such as "Recurring words" were cut off when the card was narrow; the buttons now move below the title instead.

## [1.0.2] - 2026-10-02

### Added
- **Automatic updates.** PostLens checks GitHub for new versions in the background (at startup and every few hours), downloads the update, verifies it against the checksum GitHub publishes, and installs it when you close the app. A sidebar notice offers **Restart to update** if you want it right away. Turn this off or check manually in **Settings → Updates**.

## [1.0.1] - 2026-10-02

### Fixed
- **"Couldn't download the browser engine" on Windows** even with a working internet connection. The check for an installed browser engine failed when it ran inside an open browser session (connecting Facebook, checking login), so PostLens wrongly thought the engine was missing. The error message now shows the real reason, and the details go to `~/.postlens/logs/browser-install.log`.
- The app now shows the correct version number.
- The Mac disk image is built and attached to the release again.

### Changed
- Download files are now simply named `postlens.exe` (Windows) and `postlens.dmg` (Mac).

## [1.0.0] - 2026-10-01

### Added
- **Website analysis.** Analyze any website (one page or up to 200 pages): sitemap discovery, `robots.txt` compliance, JavaScript rendering when needed, and main-content extraction with Trafilatura.
- Site overview with content & SEO checks (broken pages, titles, meta descriptions, H1s, thin content, image alt text, JavaScript-only pages), plus a page reader.
- **Desktop app.** A Windows installer and a Mac (Apple Silicon) app with its own window, built automatically for every release.
- **More AI providers.** ChatGPT (OpenAI), Claude (Anthropic) and Gemini (Google), alongside Groq and Local AI.
- **Fast answers.** Pre-built hybrid search index (BM25 + multilingual embeddings), cache-friendly prompts with provider prompt caching, Local AI warm-up, instant repeat answers, and time-to-first-word shown on each reply.
- **Local AI manager.** Hardware check with minimum requirements, a recommended model per hardware tier, one-click download, and model recommendations that update from this repository.
- Appearance settings: system/light/dark theme and six accent colors.
- API keys stored in the operating system's credential vault. A test fails the build if a key is ever committed.

### Changed
- Local AI only offers catalog models suited to the computer's tier, and is hidden on computers below the minimum.

## [0.1.0] - 2026-09-30

### Added
- First version: Facebook page and post collection (anonymized), overview dashboard, and AI Q&A with Ollama or Groq.
