# Security policy

Never post credentials or personal/client data in public issues. Report a suspected
vulnerability using the repository Security tab → Report a vulnerability. Include
reproduction steps with synthetic data and the affected release/commit.

The maintained branch is `main`; released tags are historical snapshots. Local hooks
are not a sandbox, cannot prevent bypass, and do not grant permission for publication,
production changes or spending. Gitleaks does not detect every secret or private fact.

If a real credential was exposed, revoke/rotate it first. Deleting the file or rewriting
history does not make a leaked credential safe again. Do not send credentials to maintainers.
