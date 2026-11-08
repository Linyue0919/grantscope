# Public WebSocket mitigation — November 8, 2026

The public Streamlit browser reported `Cached ForwardMsg MISS` and disabled inputs. This is the framework's browser-message reference cache, not the application's persistent research cache. It occurred while navigating between Search and My Grants.

The pinned Streamlit 1.51.0 source (`runtime/forward_msg_cache.py`, `populate_hash_if_needed`) marks large `new_element` messages cacheable when their serialized size exceeds `global.minCachedMessageSize`. The default is 10 KB. A server reference to a message missing from the browser cache causes the observed error. The exact underlying framework timing defect is not claimed to be independently fixed.

The one-line startup mitigation sets `--global.minCachedMessageSize 2147483647`, above the 200 MB maximum allowed message size. Permitted application messages are sent in full instead of hash-only references. There is no dependency upgrade, protocol monkey patch, Search edit, CORS/XSRF change, data deletion or change to AI citations. More WebSocket bandwidth is the tradeoff. The flag is an internal option verified against pinned 1.51.0 and must be rechecked before upgrading Streamlit.

Regression tests exercise Streamlit's actual protobuf message/cacheability path with repeated >10 KB evidence. The default caches it; the configured threshold retains the full message and does not mark it cacheable. Persistence startup paths remain intact. Public browser navigation, Sol, research reuse and bookmark persistence still require live acceptance on the deployed commit.

Primary reference: [Streamlit 1.51.0 forward-message implementation](https://github.com/streamlit/streamlit/blob/1.51.0/lib/streamlit/runtime/forward_msg_cache.py). [Upstream reports](https://github.com/streamlit/streamlit/issues/17265) also describe this error; their differing versions do not prove the exact trigger in this app.

Copilot's Search work and the original checkout are not modified. Only startup, this note and transport regression tests are included in this fix.
