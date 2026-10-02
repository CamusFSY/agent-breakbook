# Security

Breakbook runs synthetic tools locally. It is a testing fixture, not a security sandbox for untrusted agents or repositories. Run only trusted callbacks. The optional live adapter sends model requests to the configured provider.

Do not commit API keys or real production data. Local reports may contain data from adapters you add, so inspect them before sharing. Built-in reports store exception types rather than provider exception messages and escape dynamic HTML content.

For a vulnerability, use the repository's private vulnerability reporting feature when available. Otherwise open an issue requesting a private contact channel without publishing exploit details or secrets. Ordinary fixture bugs can be reported as public issues.

The maintained line is currently 0.1.x. Dependency pins record the integration tested by this release; they are not a claim that upstream packages are free from vulnerabilities.
