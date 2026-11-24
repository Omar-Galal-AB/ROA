# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in ROA, please report it privately:

1. **Do NOT open a public issue**
2. **Email:** omer.galal33@gmail.com (or use GitHub's private vulnerability reporting)
3. **Include:**
   - Component affected (roa-linux, ue5-plugin, etc.)
   - Detailed description
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix timeline:** Depends on severity
  - Critical: Within 7 days
  - High: Within 30 days
  - Medium/Low: Next release

## Security Considerations

### UE5 Plugin
- Network communication on port 9876 (local only by default)
- Python script execution (sandboxed to plugin context)
- USD file parsing (validate external files)

### roa-linux
- IPC communication via ZMQ (port 5555)
- File system access (URDF/USD conversion)
- No authentication by default (assumes trusted network)

### Deployment Recommendations
1. Run on trusted networks only
2. Use firewall rules to restrict port access
3. Validate all imported robot models
4. Keep dependencies updated

## Known Limitations

- No built-in authentication/authorization
- Network communication is unencrypted (local network assumed)
- File permissions follow OS defaults

## Updates

Security updates will be released as patch versions (e.g., v0.2.1) and announced via:
- GitHub Security Advisories
- CHANGELOG.md
- Release notes
