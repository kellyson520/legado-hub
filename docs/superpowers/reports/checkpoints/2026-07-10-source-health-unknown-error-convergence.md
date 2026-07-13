# 2026-07-10 source health unknown-error convergence

## Infrastructure fixes

- `LegadoHttpClient` no longer advertises Brotli (`br`) without a decoder.
  - This removed false transport failures for sites returning Brotli content.
- `SourceProbeService` now issues a single transport diagnostic request when an `@js:` search produces no books.
  - Captures `http_status`, `http_error`, `response_kind`, `response_preview`, and elapsed time.
- Health probe fetchers now use `timeout=10` and `max_retries=0` to prevent batch probing from spending 90+ seconds on unreachable sources.

## JS compatibility fixes

- Prefix-sensitive `@js:` sources using `key.charAt()/slice()/startsWith()/substring()` now receive raw `key` input instead of percent-encoded input.
- This restores Lofter (`source_id=108`) ordinary keyword search: encoded Chinese no longer incorrectly enters the `%` grain-search branch.

## Classifier additions

- `network_unreachable`
- `tls_or_handshake_error`
- `http_error`
- `waf_blocked` from 403/429, Cloudflare / Just a moment / captcha signals
- `parse_empty` for search-ok + toc-failed chains

## Test result

```powershell
.\.venv\Scripts\python.exe -m pytest <source-health + legado regression selection> -q
```

- `68 passed`

## Real-source JS smoke result

| source_id | Source | Classification | Search result |
|---:|---|---|---|
| 4 | 起点读书限免+本章说 | `blocked / token_missing` | 0 |
| 8 | 群U聚合 | `blocked / network_unreachable` | 0 |
| 23 | 冰清阁小说 | `blocked / token_missing` | 0 |
| 30 | 八叉书库 | `blocked / network_unreachable` | 0 |
| 50 | Pixiv 小说 | `dead / helper_missing` | 0 |
| 59 | 禁漫天堂 | `blocked / network_unreachable` | 0 |
| 67 | 和圖書 | `blocked / waf_blocked` | 0 |
| 91 | 禁漫天堂 | `blocked / network_unreachable` | 0 |
| 108 | Lofter | `healthy` in search-only probe | 捞尸人=1, 斗罗大陆=1 |
| 109 | 读书阁③ | `dead / upstream_changed` | 0 |

## Remaining observed issue

- Lofter full-chain probe is `degraded / parse_empty`: search now works, but its compound `bookUrl` JavaScript rule still yields an unusable downstream TOC URL. This is a rule-execution compatibility issue, not a transport failure.
