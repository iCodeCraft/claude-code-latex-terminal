# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-02

### Added

- Preserve Markdown-sensitive backslash escapes in dollar-delimited inline
  math and in display blocks that share a replacement batch.
- Track math, code-fence, and inline-code state across `MessageDisplay` batches.
- Keep ordinary Markdown, code, currency, transcripts, and model context
  unchanged.
- Support Python discovery on macOS, Linux, and Git Bash on Windows.
- Add unit and hook integration tests.

[Unreleased]: https://github.com/iCodeCraft/claude-code-latex-terminal/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/iCodeCraft/claude-code-latex-terminal/releases/tag/v0.1.0
