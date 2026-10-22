# AnySearch as a second search provider

## Decision

Add AnySearch alongside Web IQ, not underneath it. Expose native
`POST /v1/search` and provide `anysearch_search` as a client-executed function
tool in the built-in Chat page. Existing Web IQ routes and tool names remain
unchanged. The LLM proxy does not secretly execute searches or inject results
into prompts. `ghc_api/web_search.py` (the older Anthropic rejection fallback)
is unrelated and is not changed by this integration.

References:

- https://www.anysearch.com/docs/api-endpoints/v1-search
- https://www.anysearch.com/docs/api-endpoints
- https://www.anysearch.com/docs/auth

## Native contract and transport

- Forward request bytes, including unknown/additive parameters. Do not validate
  search fields, clamp counts, insert defaults, or rewrite `tag`, `zone`,
  `language`, `params`, or `format` at the proxy layer.
- Preserve a missing/wrong Content-Type so upstream owns the 415 decision.
- Preserve ordinary upstream status, body, and end-to-end headers, including
  Retry-After and X-Request-ID. Reuse the existing Web IQ HTTP header filter.
- `format: markdown` changes result content, not the outer JSON envelope.
- Require the server-held key; no anonymous mode, auto-registration, retries,
  provider fallback, fusion, or upstream redirect following.
- Server config alone selects the base URL. Clients cannot route credentials
  to arbitrary paths/hosts. Support a base path for private reverse proxies.
- Disabled/unconfigured is 503; timeout is 504; other transport failure is 502.
  Network exception strings are not returned or logged.

## Authentication and configuration

`POST /v1/search` is in `PROTECTED_PATHS` and uses ghc-api's existing optional
user-token gate. Its Authorization header is never forwarded. AnySearch sees
only `Authorization: Bearer <server key>`.

Settings: `enable_anysearch`, `anysearch_api_key`, `anysearch_api_key_file`,
`anysearch_base_url`, `anysearch_timeout`, `log_anysearch_requests`.
An inline key and a key file are mutually exclusive. Key files are read at
startup (use an absolute path or `~`), not automatically discovered or created.
The key must be one nonempty ASCII token to enable requests. Missing keys do
not cause anonymous traffic. Invalid configuration aborts startup with messages
that never interpolate keys or key-file contents. No key is exposed through
Chat template data or the runtime config API.

As with the other quota-spending endpoints, disable user auth only behind an
appropriate access boundary. Dashboard/admin endpoints still require external
protection; this change does not alter the application's auth architecture.

## Sensitive-response boundary

AnySearch documents that anonymous HTTP 402 may contain a generated username,
password, and API key. We never use anonymous access, but still treat **every
402** as sensitive, independent of its body or Content-Type.

`ghc_api/anysearch.py` consumes and closes the upstream response. Before any
response leaves that module:

- 402 becomes a fixed quota error with status 402.
- 401/403 become a fixed server-credential/access error with status 503.
- Redirects become a fixed 502 without forwarding Location.
- These responses contain only a safe error envelope and fixed response
  headers. Only a validated UUID v4 upstream request ID may be preserved;
  otherwise use the locally generated ID. They include Cache-Control: no-store.

The route receives only a `SearchResponse`, never the original response or
its history. No raw sensitive body/headers go to Flask, stdout, audit files,
request cache, exports, browser history, or later model requests. This holds
for malformed and non-JSON 402 responses too; it is not regex-based redaction.
The upstream HTTP status remains available as safe audit metadata.

## Chat tool layer

One selector: Off / Native / Web IQ / AnySearch. Preserve the old Native
preference/default and Web IQ precedence when migrating localStorage. A
provider becoming unavailable never selects another provider automatically.
Native retains its existing Copilot GPT Responses restrictions; function tools
work with the existing Chat Completions, Responses, and Messages loops.

A small client-side registry supplies schemas and executors. Only a tool
actually declared for that turn can execute, even if another provider is
configured or the selector changes during the turn. Keep round limits,
cancellation, call-ID correlation, result history, and source deduplication.
A tool call in the forced-answer round is an error, not another search.

The AnySearch schema deliberately exposes only `query` and `max_results`.
The UI asks for five results by default and Markdown content; it does not
invent capability tags. Advanced fields remain fully available on the HTTP API.

Tool success requires HTTP success, `code == 0`, and a well-formed results list.
Empty results are valid; bad JSON/business errors are not empty successes.
The UI uses content or snippet, clips content to 3000 characters and snippets
to 1000, and marks truncation. This is a model-context policy, not a native API
transformation. Results are labeled untrusted and include citation URLs.
Failures return safe tool outputs, not failed chat turns. Cancellation propagates.

## Observability

Daily safe audit: `<config_dir>/anysearch/YYYY-MM-DD.jl`, controlled independently
by `log_anysearch_requests`. Like Web IQ, the shared request cache remains active
when the dedicated file log is disabled and obeys its existing body-size limits.
The dedicated audit is untruncated for normal responses, never for sensitive ones.

Model label: `anysearch_search`; LLM token counts remain zero. Record local and
upstream IDs, user, HTTP and business status, duration, and result count. A
malformed or business-failed HTTP 200 keeps the native HTTP status but is marked
as an error in the audit/cache and increments `anysearch.search_error`, not
`anysearch.search`.

## Validation and exclusions

Mock tests cover passthrough, key-only behavior, auth separation, 402 bodies
across all sinks, header/ID handling, error classification, config loading,
and business failures. Node-based tests execute real Chat code with fake HTTP
and SSE for all three protocols, including history, rejection of undeclared
tools, round limits, cancellation, and old setting migration. Existing Web IQ
regression tests remain in place.

Real integration was checked with three authenticated requests: ordinary JSON,
Chinese language/region, and `code.doc` with params/Markdown. All returned HTTP
200 and valid results. These are explicit smoke checks, never part of CI.
Live model reasoning/tool choice is not tested by these HTTP smoke checks.

Extract, MCP, automatic retries/fallback, result fusion, and anonymous credential
management are out of scope.
