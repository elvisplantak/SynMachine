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

UVP regression cases cover recipe edits/version saves/reload without execution,
review invalidation, stale-save failure, explicit fresh-preparation Start, run
progress and owned controls across navigation, and cancellation before commands.
`uvp.fixture.html` intercepts every API request; no real backend or device is used.

Recipe layout cases check all four preparation and five maintenance confirmation
rows at 2560x1440 and 480x900 requested browser window sizes. They measure that
checkboxes stay at the left beside the first text line, with no stretched control,
large text gap or row overflow, and verify that clicking the label text toggles
the correct checkbox. These cases also check the English recipe page headings.

Command-flow browser cases use `execution-flow.fixture.html` with every fetch
intercepted. Guided Demo and Recipes each exercise all nine supported routes,
actual SVG dash CSS direction, aspiration/dispense separation, inactive/unknown
valve symbols and navigation without POSTs. Failure cases cover stalled/late
responses, loss of connectivity, foreign run identity, malformed/unsupported
activity, idle/error status and older backends lacking the activity field. Unit
contracts separately check strict activity parsing and P1/P2 direction mapping.
