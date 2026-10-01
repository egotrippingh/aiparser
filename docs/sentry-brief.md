# Sentry brief

Optional, sanitized error telemetry for server, agent and five React roots. Captcha/auth/cancellation and confirmed client status errors are excluded; unexpected scanner, control-sync, API and server-AI failures are captured without changing workflow or billing behavior.

Acceptance: absent/malformed configuration and unavailable collectors cannot block normal use. Actual SDK serialized envelopes contain only approved error fields; sessions, attachments, logs, traces, content and credentials are excluded. Scoped internal identities cannot leak between captures. Both global hooks and handled failures are covered; unexpected missing-provider-UI errors remain visible.

Delivery is a reviewed feature PR from production plus setup instructions. Account/DSNs, live ingestion, source-map upload, production deployment and publishing a newly versioned Windows release are pending operator steps. Redis, dashboards, distributed tracing and session replay are outside this task.
