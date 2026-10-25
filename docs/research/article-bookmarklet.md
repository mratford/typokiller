# Can a bookmarklet send article text from FT, NYT and O'Reilly to typokiller?

Resolves issue #4 (part of #1). Researched 2026-10-25. Vocabulary follows `CONTEXT.md`: the thing being sent is the text of an article, which becomes a **Source**.

## Short answer

Yes, but not with a plain `fetch()` to an HTTP server. The three viable routes, least fiddly first:

1. **Bookmarklet that opens a typokiller tab with the text in the URL fragment** (`window.open` or `location.href` to `http(s)://typokiller/send#...`). It works with an HTTP server, needs no CORS, is not mixed content, and is not covered by any CSP directive the sites send. The typokiller page reads `location.hash` and POSTs to its own origin.
2. **Bookmarklet that `fetch()`es the text to typokiller.** This only works if typokiller is served over **HTTPS** (NYT's CSP forces it, and mixed-content rules require it on all three), the server sends CORS headers, and, in Chrome 142+, the user accepts a Local Network Access prompt for each of the three sites.
3. **Browser extension** with `host_permissions` for the typokiller origin. It bypasses page CSP and CORS but needs installation on every browser, so it is only worth it if the bookmarklet's text extraction proves too poor.

Copy-paste into a typokiller textarea is the always-works fallback.

## What I could and could not observe

I fetched headers with `curl` using a desktop Chrome user agent, with no login. The sites are behind bot walls, so some responses are challenge pages, not articles. The headers below are therefore **what the edge sends to an anonymous client**, not necessarily what a logged-in article page carries. A logged-in check in the user's own browser (DevTools, Network, Response headers) should confirm before relying on any row.

| Site | URL fetched | Result | CSP / other headers observed |
|---|---|---|---|
| NYT | `https://www.nytimes.com/` (403, DataDome challenge), `/robots.txt` (200), a section page, an article URL | The same CSP on the challenge and on the 200 `robots.txt`, so it is probably edge-wide | `content-security-policy: upgrade-insecure-requests; default-src data: 'unsafe-inline' 'unsafe-eval' https: nytresource:; script-src data: 'unsafe-inline' 'unsafe-eval' https: blob: nytresource:; ... connect-src data: https: wss: blob: nytresource:; ... form-action https: nytimes: nytcooking: nytxwd:; report-uri https://csp.nytimes.com/report;` and `x-frame-options: DENY` |
| FT | `https://www.ft.com/` and an article-shaped URL (403, Cloudflare `cf-mitigated: challenge`) | No CSP header on the challenge, `robots.txt` or home page | `cross-origin-opener-policy: same-origin`, `cross-origin-embedder-policy: require-corp`, `cross-origin-resource-policy: same-origin`, `x-frame-options: SAMEORIGIN`, a restrictive `permissions-policy` (no clipboard-read/write) |
| O'Reilly (`learning.oreilly.com`) | Home, library and login URLs | 302 to login, no CSP on those responses | Only `x-frame-options: DENY`, HSTS, `referrer-policy`. The marketing site `https://www.oreilly.com/` sends a very permissive CSP: `default-src ... * 'unsafe-inline' 'unsafe-eval' data: blob: ...` |

I could not see the headers on authenticated `learning.oreilly.com` or FT article pages. I also did not run a bookmarklet in a real browser, so everything about runtime behaviour is derived from specs, docs and Chromium source, and is marked where it is an inference.

## Bookmarklets and CSP

- A bookmarklet is a `javascript:` URL. The CSP3 spec applies the `'unsafe-inline'` check to navigations to `javascript:` URLs ([CSP3 section 4.2.4](https://www.w3.org/TR/CSP3/)).
- In Chromium, the check that enforces this, `FrameLoader::AllowRequestForThisFrame`, starts with "If no origin Document* was specified, skip remaining security checks" and returns true. The `AllowInlineJavascriptUrl` CSP check is only run when there is an origin window ([`frame_loader.cc`](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/third_party/blink/renderer/core/loader/frame_loader.cc)). My inference: a `javascript:` URL activated from the bookmarks UI is browser-initiated and has no origin window, so Chrome does not apply the page's `script-src` to it. I did not verify this by running one.
- Firefox historically blocked bookmarklets under CSP ([bug 866522](https://bugzilla.mozilla.org/show_bug.cgi?id=866522), still open). Firefox 69 fixed the main case ([bug 1478037](https://bugzilla.mozilla.org/show_bug.cgi?id=1478037)): bookmarklets now run, but "will not allow bookmarklets to access subresources that CSP blocks".
- Either way, the CSP still governs what the bookmarklet's code does afterwards. In Chromium the script runs in the page's world, so `connect-src` and similar apply to its `fetch()` calls (inference from the Firefox bug's description above; not tested in Chrome).
- NYT's CSP has `'unsafe-inline'` anyway, and none of the three sites' observed headers use `navigate-to`.

What each CSP means for the routes:

| Route | NYT (observed CSP) | FT (observed: no CSP) | O'Reilly (observed: no CSP on login/redirect responses) |
|---|---|---|---|
| `fetch()` to `https://typokiller...` | allowed by `connect-src https:` | no CSP seen | no CSP seen |
| `fetch()` to `http://...` | `upgrade-insecure-requests` rewrites it to `https://` (see below), so an HTTP-only server fails | blocked as mixed content | blocked as mixed content |
| Top-level navigation or `window.open` to the server | not restricted by `connect-src`; `form-action` covers forms only | not restricted | not restricted |
| `<form method=POST target=_blank>` to the server | `form-action https: ...` allows `https:` targets and rejects `http:` | no CSP seen | no CSP seen |

Sources for the table's mechanics:

- `upgrade-insecure-requests`: "non-navigational insecure resource requests are automatically upgraded" and navigations to third-party resources are not ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/upgrade-insecure-requests)).
- `form-action`: restricts "the URLs which can be used as the target of form submissions" and is a navigation directive for forms only. MDN does not say it covers `window.open` or links ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/form-action)).

## Mixed content (HTTPS page to HTTP server)

From [MDN: Mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content):

- `fetch()`, `XMLHttpRequest` and `Navigator.sendBeacon` from an HTTPS page to an `http:` URL are **blocked**, not upgraded. Only images, audio and video are auto-upgraded, and not when the host is an IP address.
- "Navigation requests from a secure context that target insecure target top-level browsing contexts are not considered mixed content". That covers `window.open()` and link navigation to an `http://` page.
- Loopback addresses count as secure, but a LAN name or IP or a tailnet name does not.
- Chrome's [Local Network Access](https://developer.chrome.com/blog/local-network-access) work adds one exception: permission-gated requests are exempt from mixed content checks if Chrome knows in advance that the destination is local, meaning a private IP literal or a `.local` hostname (a public name that resolves to a private address is not exempt). That exemption does not help on NYT, where `upgrade-insecure-requests` rewrites the URL to `https://` before the request is made (my inference from the two sources).
- A `<form>` on an HTTPS page whose action is `http:` is a "mixed form". Chrome began warning on these in version 86/87 and shows a full-page block the user can override on submit ([Chromium blog, 2020-08](https://blog.chromium.org/2020/08/protecting-google-chrome-users-from.html), via search result; I did not open the page itself). Avoid that route against an HTTP server.

## CORS

From [MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS):

- A cross-origin `POST` with `Content-Type` of `text/plain`, `application/x-www-form-urlencoded` or `multipart/form-data` is a "simple request": no preflight, and it is still sent to the server. Script can only read the response if the server sends `Access-Control-Allow-Origin`.
- `Content-Type: application/json` triggers a preflight, so the server would need to answer `OPTIONS` with the CORS headers.
- FT sends `Cross-Origin-Embedder-Policy: require-corp`. With that, "a cross-origin subresource requested in `no-cors` mode is blocked unless the response explicitly allows embedding through CORP", while requests in `cors` mode are not blocked by COEP ([MDN: COEP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy)). So on FT a fire-and-forget `no-cors` POST would need `Cross-Origin-Resource-Policy: cross-origin` on typokiller's response; a proper `cors` fetch needs the CORS headers. Either is easy to add, but both are server work that the navigation route avoids.
- A cross-site form or fetch POST can reach typokiller from any page the user visits, not only the three sites. If typokiller accepts article writes from other origins, add a shared token or check `Origin`. The fragment route avoids this: the cross-origin step only carries data into a page that then submits it same-origin.

## Chrome Private Network Access and Local Network Access

- The older **Private Network Access** design was a CORS preflight for requests from public sites to private addresses; Chrome put it on hold and replaced it with **Local Network Access (LNA)**, a permission prompt ([Chrome blog](https://developer.chrome.com/blog/local-network-access), posted 2025-06-09, updated 2025-09-29).
- The post says the prompt launches in **Chrome 142** and applies to `fetch()`, subresource loading and subframe navigation from a public site to a local-network or loopback destination. It can only be requested from a secure context. It does not address top-level navigations, form posts or `window.open`.
- The [LNA spec](https://wicg.github.io/local-network-access/) lists `10/8`, `172.16/12`, `192.168/16`, `169.254/16` **and `100.64.0.0/10`** as "local". `100.64.0.0/10` is the Tailscale address range (my knowledge, not a cited source), so a tailnet address is covered. The spec says navigations are included, but "Chromium only applies LNA restrictions to iframe navigations currently", so a top-level `window.open`/`location` navigation to the server is not prompted today.
- Consequence: a `fetch()` bookmarklet will trigger a permission prompt on each of ft.com, nytimes.com and learning.oreilly.com in Chrome 142+ (once per site, if the user grants it), whatever the server's TLS setup. The navigation route avoids it. Safari and Firefox behaviour was not researched.
- The older WICG [Private Network Access spec](https://wicg.github.io/private-network-access/) also lists `100.64.0.0/10` as private and says "This includes navigations", but Chrome's shipped behaviour is the LNA one above.

## Giving the server HTTPS

Needed only for the `fetch()` route (and for NYT form-POST).

- **`tailscale serve`**: `tailscale serve localhost:3000` shares a local service over HTTPS inside the tailnet, with an automatically provisioned certificate, at a name like `https://my-node.example.ts.net/` ([Tailscale docs](https://tailscale.com/kb/1242/tailscale-serve)). It needs MagicDNS and "Enable HTTPS" in the admin console, and the machine name is published to public Certificate Transparency logs ([Tailscale HTTPS docs](https://tailscale.com/kb/1153/enabling-https)). Only devices on the tailnet can reach it. Certificates are publicly trusted, so no per-device setup. `tailscale` was not installed on this machine, so I did not try it.
- **mkcert**: creates a local CA and certificates that chain to it; other devices need `rootCA.pem` installed and trusted (iOS needs the profile installed and then enabled under certificate trust settings), and `rootCA-key.pem` must never leave the Mac ([mkcert README](https://github.com/FiloSottile/mkcert)). More per-device fiddliness than Tailscale, but works on a plain LAN with no account. `mkcert` was not installed here either.
- The server must also add the CORS headers above; HTTPS alone does not make cross-origin `fetch()` readable.

## Alternatives

### Navigate to typokiller carrying the text in the URL fragment

The bookmarklet gathers the text and does `window.open(base + '/send#' + encodeURIComponent(text))` (or `location.href = ...` to avoid popup blockers; popup-blocker behaviour for bookmarklets was not researched).

- Not mixed content, per the MDN navigation rule above, so `http://mac.local:8000` is fine.
- Not subject to CORS, `connect-src`, or `form-action`.
- Not subject to LNA in Chrome today (iframe navigations only).
- The fragment "is not sent to the server when the URI is requested" ([MDN: Fragment](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment)), so server logs never hold the article, and the typokiller page's own JS reads `location.hash` and POSTs to its own origin.
- Size: Chromium passes URLs up to `kMaxURLChars = 2 * 1024 * 1024` between processes ([`url_constants.h`](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/url/url_constants.h)). A long article is tens of kilobytes, well within that. Limits in Safari and Firefox were not checked, and iOS Safari is the one to test.
- Do not rely on `postMessage` to the opened window: FT sends COOP `same-origin`, and per [MDN: COOP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy) a cross-origin page opened from a `same-origin` document goes into a new browsing context group, where it "can't access it using `window.opener`". The opener's handle is also likely to be unusable (not confirmed on that page). The fragment carries the data in the URL itself, so COOP does not matter.

### Auto-submitting form POST to a new tab

A bookmarklet that builds a `<form method=POST target=_blank action=...>` with a hidden `<textarea>` removes the size limit and needs no CORS. Downsides: NYT's `form-action` rejects `http:` targets, Chrome shows the mixed-form warning for `http:` actions, and typokiller would accept cross-site writes. It needs an HTTPS server, so it is no easier than fetch.

### Browser extension

- A content script's cross-origin requests "are always treated as such ... even if the extension has host permissions", but the extension service worker can reach remote servers outside its origin when `host_permissions` allows it, which bypasses CORS ([Chrome extensions: network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)). The documented pattern is for the content script to message the service worker, which does the `fetch`.
- That avoids page CSP and CORS and, as far as I can tell, the page's mixed-content rules. It also means no per-site prompts, but I did not verify mixed-content or LNA behaviour for extension contexts.
- Cost: installing on each browser (unpacked in developer mode on Chrome; Firefox and Safari have heavier signing/packaging, not researched here). Worth it only if typokiller needs Readability-quality extraction on pages where a bookmarklet is awkward.

### Copy-paste fallback

Select text on the page and paste it into a typokiller textarea. Needs nothing from the three sites' headers. The bookmarklet can also fall back to `getSelection()` when the page has no recognisable article element. Note FT's `permissions-policy` disables `clipboard-read`/`clipboard-write` on its own pages, so the bookmarklet should not write to the clipboard from FT.

## Text extraction

- [Mozilla Readability.js](https://github.com/mozilla/readability) is the library behind Firefox Reader View (Apache-2.0). `new Readability(document.cloneNode(true)).parse()` returns `title`, `byline`, `textContent` and `content`. It mutates the DOM, so pass a clone. `isProbablyReaderable()` is a fast pre-check.
- Readability is large to inline in a bookmarklet and, if loaded as a script from typokiller, is subject to each site's `script-src` (NYT allows `https:` scripts; the others are unobserved). Cheaper options for a bookmarklet: use `getSelection()` if non-empty, else `document.querySelector('article')?.innerText`, else `document.body.innerText`. Have typokiller do the clean-up on the server or in its own page, where there is no CSP to fight. Readability can also run in Node with jsdom on the server if the bookmarklet sends `document.documentElement.outerHTML` (hence larger fragments or a POST), but I did not test how much of FT and O'Reilly's article markup it handles.
- Only the page the user is already logged into is read; nothing here fetches article URLs from the server side, and nothing tries to get around paywalls.

## Implications for typokiller

- **Pick the fragment-handoff bookmarklet as the first implementation.** It works with a plain HTTP server on the LAN, avoids CORS, mixed content, NYT's CSP and Chrome's Local Network Access prompt, and survives FT's COOP/COEP headers. The typokiller side is one small page (`/send`) that reads `location.hash`, shows a preview and POSTs it as a Source.
- **Do not build the server around a cross-origin `fetch()` from the bookmarklet.** It would need HTTPS (mkcert or `tailscale serve`), CORS and CORP headers, and a permission prompt per site in Chrome 142+. If HTTPS is wanted anyway for other reasons, `tailscale serve` is the lower-effort option because the certificate is publicly trusted and needs no device setup.
- **Keep the server free of cross-site writes.** If any endpoint must accept a cross-origin POST, require a token.
- **Keep text extraction simple in the bookmarklet** (selection, then `article`, then `body`) and do clean-up inside typokiller. Add a paste-into-textarea page as the fallback.
- **Open things to check in the user's logged-in browsers** before finalising: (1) the real response headers (especially CSP) on a logged-in FT article, NYT article and `learning.oreilly.com` book page; (2) that the bookmarklet runs and the new tab opens without a popup block in the browsers actually used; (3) fragment size handling on iOS Safari if phones are in the plan; (4) whether Chrome shows any prompt for a navigation to a LAN/tailnet address.
- If the bookmarklet turns out to be flaky on one of the sites, the fallback order is: extension with `host_permissions` for the typokiller origin, then copy-paste.
