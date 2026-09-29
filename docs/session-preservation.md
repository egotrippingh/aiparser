# Saved agent sessions

The installer marker previously changed the data directory from the portable app's `data` to `%LOCALAPPDATA%/AIParser`. On this machine the old profiles retained valid cookies; installed profiles were new. Local profiles were restored from the known old source after closing browsers, with a complete destination backup. All five saved sessions are now visible through the installed agent API.

Version 2026.9.29.3 checks local saved cookies at startup, before agent work. Existing installed data remains authoritative. A same-folder portable-to-installer upgrade reuses actual legacy data when installed storage has no state. Empty folders do not count; unreadable state aborts selection rather than switching accounts. Cookie read failures appear as unknown, and stale scan success cannot override missing cookies.

This preserves paths without copying or replacing profiles. The tradeoff is that an unrelated previous portable location cannot be discovered automatically. Preserve its `data`, or transfer the complete `profiles` directory explicitly while the agent and its browsers are closed. Installer users can unpack a profiles archive into `%LOCALAPPDATA%/AIParser`; rename an existing profiles folder to retain a backup. Account/device credentials are not part of a profiles export.

Checks: `pytest tests/test_data_paths.py tests/test_main_session_check.py tests/test_profiles.py tests/test_login_feedback.py tests/test_updates.py tests/test_agent_publication.py tests/test_desktop_login.py -q`, frontend tests/lint/build, EXE self-test. The installer lifecycle script checks untracked legacy data survives updates/uninstall, but needs an isolated Windows installation and refuses to overwrite an existing install.

Local cookie presence does not prove a provider still accepts the session; that is checked during the normal scan/login flow. Unknown roots are never searched recursively across the computer.
