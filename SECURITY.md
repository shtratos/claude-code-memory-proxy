# Security Policy

## Scope

Claude Code Memory Proxy is a local, file-backed prototype intended for development and experimentation. It does **not** provide authentication, encryption, quota management, or multi-tenant isolation. Treat the memory directory as sensitive data and secure the host accordingly.

## Reporting a Vulnerability

- Please open a GitHub issue in the repository with a concise description of the problem. Do **not** include secrets, API keys, or personal information in the report.
- If you prefer private disclosure, open a private discussion request via GitHub and we will coordinate a secure channel.

## Responsible Usage Guidelines

- Do not store production PII or secrets in the memory directory.
- Rotate any Anthropic API keys used for testing and avoid committing them to the repository.
- Review and configure proxy environment variables before routing production traffic through the proxy.

Thank you for helping keep the project safe and transparent for the community.
