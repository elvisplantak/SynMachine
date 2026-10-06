# UI verification

`npm test` runs the API contract tests and connected-execution browser regressions.
Browser cases require Chrome/Chromium. The default executable is
`/usr/bin/google-chrome`; set `LABFORGE_TEST_BROWSER` to another installed browser
path if needed. If no executable is present, browser cases are explicitly skipped;
passing API tests alone does not claim browser coverage.

The browser runner starts an isolated localhost Vite test server and headless
browser profiles with temporary caches. The fixture intercepts every application
fetch with an in-memory fake API. A server middleware also blocks API fallthrough,
so the tests cannot contact a running backend or device. Profiles/caches and the
test server are closed after the tests; no dependencies are downloaded.

Cases exercise actual React/DOM navigation, scrolling, page reload/fresh mounts,
retained recovery/flush states, failed/timed-out reads, connected percentage labels,
SF duration input, and the explicit execution-control request sequence. They do
not establish backend policy, physical readiness or device behavior.


Fresh operator cases additionally cover blank RUN/recovery forms, credential
clearing on success/error, explicit per-request consent, unknown recovery
references, cancellation/expiration and read-only restoration. A RUN retry keeps
the existing CREATED run ID and sends exactly one explicit Start and one
declaration, with no new run or automatic command replay. Backend tests remain
the authority for actual eligibility, ownership and durable command behavior.
