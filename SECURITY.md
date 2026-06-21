# Security policy

## Supported version

The latest minor release is supported while the project remains pre-1.0.

## Reporting

Report vulnerabilities privately to the repository owner rather than opening a
public issue when disclosure could expose credentials, local files, command
execution, or data integrity.

## Threat model

The optional agent command is an explicitly configured local executable. The
project invokes it without a shell, but the executable itself has the user's
permissions. Review any command before running it. Agent outputs are marked
untrusted and must not be treated as verified evidence.

Never commit SEC contact details that should remain private, API keys, broker
credentials, proprietary research, or licensed datasets.
