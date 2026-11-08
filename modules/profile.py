"""Alerts page (nav label "Alerts"; file name kept so imports don't break).

Proactive notifications for the agency selected on the Brief: weekly digest, instant
alerts for high-fit grants, and deadline reminders for grants in My Grants. The preview is
built from the Brief's cached backend result through ui/view_model.py; no new backend
or LLM calls. Delivery isn't switched on yet and settings last for this session.
"""
from html import escape

import streamlit as st

from ui import alerts_data as ad
from ui.nav import PAGES
from ui.view_model import agency_display_name, fmt_date, mark

# --------------------------------------------------------------------------- legacy defaults
# modules/search.py (partner-owned) and the Brief still read these old Profile defaults.
# They are no longer editable in the UI; get_preferences() keeps the same values and keys.
LEGACY_DEFAULTS = {
    "agency": "NC Department of Environmental Quality",
    "priorities": ["Clean Water", "Climate Resilience"],
    "deadline_days": 15,
    "minimum_award": 100000,
    "minimum_match_score": 75,
    "notification": "Weekly digest",
}


def get_preferences():
    if "agency_preferences" not in st.session_state:
        st.session_state.agency_preferences = {**LEGACY_DEFAULTS, "priorities": list(LEGACY_DEFAULTS["priorities"])}
    return st.session_state.agency_preferences


# --------------------------------------------------------------------------- settings state

def alert_settings():
    """Session-only alert settings (survive page switches, unlike widget-keyed state)."""
    settings = st.session_state.setdefault("alert_settings", dict(ad.DEFAULT_SETTINGS))
    for key, value in ad.DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)
    return settings


def _key(name):
    key = f"alerts_{name}"
    if key not in st.session_state:
        st.session_state[key] = alert_settings()[name]
    return key


def _sync():
    settings = alert_settings()
    for name in ad.DEFAULT_SETTINGS:
        if f"alerts_{name}" in st.session_state:
            settings[name] = st.session_state[f"alerts_{name}"]


# --------------------------------------------------------------------------- data

def _load(agency):
    """(views, closing_soon, saved_views) from the Brief's cached pipeline; None on failure."""
    from modules.dashboard import _shared_details_cache, load_brief
    from services.application_effort import find_announcement
    from ui import my_grants_store

    min_days = int(st.session_state.get("brief_days", 30))
    result, profile, views = load_brief(agency, min_days)
    closing = ad.closing_soon_views(result, profile, _shared_details_cache(), find_announcement, views)
    saved = my_grants_store.reminder_views(agency, views)
    return views, closing, saved, profile


# --------------------------------------------------------------------------- small HTML helpers

def _deadline(view):
    if view.deadline_date is None:
        return "Deadline not stated"
    if view.days_left is None:
        return f"Due {fmt_date(view.deadline_date)}"
    return f"Due {fmt_date(view.deadline_date)} · {view.days_left} day{'s' if view.days_left != 1 else ''} left"


def _badge(view):
    if view.fit_score is None:
        return '<span class="gs-mini-score gs-tier-Low">–</span>'
    return (f'<span class="gs-mini-score gs-tier-{view.fit_tier}" title="Fit score {view.fit_score}/100, '
            f'{view.fit_tier} fit">{view.fit_score}</span>')


def _title_link(view):
    if view.grants_gov_url:
        return f'<a href="{escape(view.grants_gov_url)}" target="_blank" rel="noopener">{escape(view.short_name)}</a>'
    return escape(view.short_name)


def _mail_item(view):
    return (f'<div class="gs-mail-item">{_badge(view)}<div><div class="t">{_title_link(view)}</div>'
            f'<div class="d">{escape(_deadline(view))} · {escape(view.agency_full_name)}</div></div></div>')


def _mail_group(title, views, empty, cap=5):
    html = f'<div class="gs-mail-group">{escape(title)} ({len(views)})</div>'
    if not views:
        return html + f'<p class="gs-mail-empty">{escape(empty)}</p>'
    html += "".join(_mail_item(v) for v in views[:cap])
    if len(views) > cap:
        html += f'<p class="gs-mail-empty">and {len(views) - cap} more in your brief</p>'
    return html


def _mail_head(subject, to, when, off_note):
    off = f'<div class="gs-mail-off">{escape(off_note)}</div>' if off_note else ""
    return (f'{off}<div class="gs-mail-head">'
            f'<div class="gs-mail-meta"><span>From</span>GrantScope alerts</div>'
            f'<div class="gs-mail-meta"><span>To</span>{escape(to)}</div>'
            f'<div class="gs-mail-meta"><span>When</span>{escape(when)}</div>'
            f'<div class="gs-mail-subject">{escape(subject)}</div></div>')


# --------------------------------------------------------------------------- page sections

def _digest_settings():
    with st.container(border=True, key="section_alerts_digest"):
        st.markdown('<div class="gs-h3 gs-h3-first">Weekly digest</div>', unsafe_allow_html=True)
        st.toggle("Send me a weekly digest", key=_key("digest_on"))
        st.selectbox("Day of the week", ad.DAYS, key=_key("digest_day"),
                     disabled=not st.session_state["alerts_digest_on"], width=220)
        st.markdown(f'<p class="gs-small">Covers this week\'s Top candidates, newly added grants that need a quick '
                    f'check, and relevant grants closing within {ad.CLOSING_WITHIN} days.</p>', unsafe_allow_html=True)


def _instant_settings(views):
    with st.container(border=True, key="section_alerts_instant"):
        st.markdown('<div class="gs-h3 gs-h3-first">Instant alerts for highly relevant grants</div>',
                    unsafe_allow_html=True)
        st.toggle("Alert me when a high-fit grant appears", key=_key("instant_on"))
        off = not st.session_state["alerts_instant_on"]
        left, right = st.columns([3, 2], gap="medium", vertical_alignment="center")
        with left:
            low, high = ad.THRESHOLD_RANGE
            st.slider("Fit score threshold", low, high, step=1, key=_key("threshold"), disabled=off)
        with right:
            if views is None:
                count_html = '<p class="gs-small">Live count unavailable: brief data didn\'t load.</p>'
            else:
                n = len(ad.instant_matches(views, st.session_state["alerts_threshold"],
                                           st.session_state.get("alerts_positive_only", True)))
                if n == 0:
                    count_html = ('<div class="gs-count gs-count-zero">At this threshold, <b>no open opportunities</b> '
                                  'would trigger an alert right now.</div>')
                else:
                    count_html = (f'<div class="gs-count">At this threshold, <b>{n} open opportunit'
                                  f'{"ies" if n != 1 else "y"}</b> would trigger an alert right now.</div>')
            st.markdown(count_html, unsafe_allow_html=True)
        st.checkbox("Only grants with positive eligibility evidence", key=_key("positive_only"), disabled=off,
                    help="State governments are listed as eligible applicants (or the notes name state agencies), "
                         "with no conflicting restriction.")
        days = int(st.session_state.get("brief_days", 30))
        st.markdown(f'<p class="gs-small">Counted from your current brief (open opportunities with at least {days} '
                    'days left).</p>', unsafe_allow_html=True)


def _reminder_settings(saved):
    with st.container(border=True, key="section_alerts_reminders"):
        st.markdown('<div class="gs-h3 gs-h3-first">Deadline reminders for My Grants</div>', unsafe_allow_html=True)
        with st.container(horizontal=True, gap="medium"):
            st.checkbox("14 days before", key=_key("remind_14"))
            st.checkbox("3 days before", key=_key("remind_3"))
        chosen = tuple(n for n, k in ((14, "alerts_remind_14"), (3, "alerts_remind_3")) if st.session_state[k])
        if saved is None:
            st.markdown('<p class="gs-small">My Grants couldn\'t be loaded right now.</p>', unsafe_allow_html=True)
            return
        if not saved:
            st.markdown('<p class="gs-small">Nothing in My Grants for this agency yet. Use ☆ Save to My Grants on '
                        'the Brief and reminders will follow their deadlines.</p>', unsafe_allow_html=True)
            return
        rows, skipped = ad.reminder_schedule(saved, chosen)
        lines = []
        if not chosen:
            lines.append("Reminders are off.")
        elif rows:
            items = "".join(f'<li><b>{fmt_date(when)}</b>: {escape(v.short_name)} '
                            f'<span class="gs-muted">({n} days before the deadline)</span></li>'
                            for when, n, v in rows[:5])
            more = f'<li class="gs-muted">and {len(rows) - 5} more</li>' if len(rows) > 5 else ""
            lines.append(f'Upcoming reminders for the {len(saved)} grant{"s" if len(saved) != 1 else ""} in My Grants:'
                         f'<ul class="gs-remind">{items}{more}</ul>')
        else:
            lines.append("No upcoming reminder dates: the chosen reminder days have already passed.")
        if skipped:
            lines.append(f'{skipped} grant{"s" if skipped != 1 else ""} in My Grants {"have" if skipped != 1 else "has"} no fixed deadline, so '
                         f'{"they get" if skipped != 1 else "it gets"} no reminders.')
        st.markdown('<div class="gs-small">' + " ".join(lines) + "</div>", unsafe_allow_html=True)


def _delivery_settings():
    with st.container(border=True, key="section_alerts_delivery"):
        st.markdown('<div class="gs-h3 gs-h3-first">Delivery</div>', unsafe_allow_html=True)
        email = st.text_input("Email address", key=_key("email"), placeholder="name@agency.nc.gov")
        if email.strip() and not ad.valid_email(email):
            st.markdown('<p class="gs-small gs-warn">That doesn\'t look like an email address.</p>',
                        unsafe_allow_html=True)
        st.checkbox("Microsoft Teams (planned)", value=False, disabled=True, key="alerts_teams_planned")


def _digest_preview(agency_short, views, closing, settings):
    groups = ad.digest_groups(views, closing)
    to = settings["email"].strip() if ad.valid_email(settings["email"]) else "Your email (add one under Delivery)"
    when = f"{settings['digest_day']}s · next on {ad.next_weekday(settings['digest_day']):%A, %b %-d}"
    off = None if settings["digest_on"] else "Weekly digest is off. This is what it would look like."
    html = _mail_head(ad.digest_subject(agency_short, groups), to, when, off)
    html += '<div class="gs-mail-body">'
    html += _mail_group("Top candidates", groups["top"], "No top candidates this week.")
    html += _mail_group("Needs a quick check", groups["check"], "Nothing to check this week.")
    html += _mail_group(f"Closing within {ad.CLOSING_WITHIN} days", groups["closing"],
                        f"No relevant grants close within {ad.CLOSING_WITHIN} days.")
    html += ('<p class="gs-mail-foot">Scores are fit with your strategic plan (0–100). Open GrantScope for '
             'details and next steps.</p></div>')
    st.markdown(f'<div class="gs-mail">{html}</div>', unsafe_allow_html=True)
    st.markdown('<p class="gs-small">This preview lists every current “needs a quick check” grant. Once delivery '
                'is on, the digest includes only those added since the last one.</p>', unsafe_allow_html=True)


def _instant_preview(views, settings):
    matches = ad.instant_matches(views, settings["threshold"], settings["positive_only"])
    off = None if settings["instant_on"] else "Instant alerts are off. This is what one would look like."
    if not matches:
        st.markdown(f'<div class="gs-mail gs-mail-none">No open opportunity scores {settings["threshold"]} or '
                    'higher right now, so no instant alert would be sent. Lower the threshold to see an example.'
                    '</div>', unsafe_allow_html=True)
        return
    v = matches[0]
    to = settings["email"].strip() if ad.valid_email(settings["email"]) else "Your email (add one under Delivery)"
    why = f"fit score {v.fit_score} is at or above your threshold of {settings['threshold']}"
    if settings["positive_only"]:
        why += " and the listing names state governments as eligible applicants"
    award = v.award_chip if v.award_status != "Not stated" else "Not stated"
    links = " &nbsp; ".join(x for x in (
        f'<a href="{escape(v.grants_gov_url)}" target="_blank" rel="noopener">Grants.gov listing ↗</a>'
        if v.grants_gov_url else "",
        f'<a href="{escape(v.nofo_url)}" target="_blank" rel="noopener">Funding notice (NOFO) ↗</a>'
        if v.nofo_url else "") if x)
    html = _mail_head(ad.instant_subject(v), to, "As soon as it's found", off)
    html += (f'<div class="gs-mail-body"><div class="gs-mail-item">{_badge(v)}<div>'
             f'<div class="t">{_title_link(v)}</div><div class="d">{escape(v.agency_full_name)}</div></div></div>'
             f'<p class="gs-mail-text">{escape(v.reason_sentence)}</p>'
             f'<table class="gs-mail-facts">'
             f'<tr><td class="l">Deadline</td><td class="v">{escape(_deadline(v))}</td></tr>'
             f'<tr><td class="l">Eligibility</td><td class="v">{mark(v.eligibility_status)} {escape(v.eligibility_short)}</td></tr>'
             f'<tr><td class="l">Award</td><td class="v">{escape(award)} {mark(v.award_status)}</td></tr></table>'
             f'<p class="gs-mail-text">{links}</p>'
             f'<p class="gs-mail-foot">You got this because the {escape(why)}.</p></div>')
    st.markdown(f'<div class="gs-mail">{html}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- page

def show_profile():
    from modules.dashboard import _agency

    agency = _agency()
    settings = alert_settings()
    st.markdown('<p class="gs-eyebrow">Alerts</p>'
                f'<p class="gs-h1">Alerts for {escape(agency_display_name(agency))}</p>', unsafe_allow_html=True)
    st.markdown('<p class="gs-scope">Get told about new matches and deadlines without opening GrantScope.</p>',
                unsafe_allow_html=True)
    if "brief" in PAGES:
        with st.container(key="inlinelink_alerts_brief"):
            st.page_link(PAGES["brief"], label="To switch agency, use Change agency on the Brief", width="content")

    views = closing = saved = profile = None
    with st.spinner("Loading your brief data…"):
        try:
            views, closing, saved, profile = _load(agency)
        except Exception:  # noqa: BLE001 - settings still work without the preview
            st.error("Couldn't load opportunities from Grants.gov right now, so the preview is unavailable.")

    left, right = st.columns([5, 4], gap="large")
    with left:
        _digest_settings()
        _instant_settings(views)
        _reminder_settings(saved)
        _delivery_settings()
        _sync()
    with right:
        st.markdown('<div class="gs-h3 gs-h3-first">Preview</div>'
                    '<p class="gs-small">Built from your current brief data.</p>', unsafe_allow_html=True)
        if views is not None:
            agency_short = (profile or {}).get("short_name") or agency_display_name(agency)
            st.markdown('<p class="gs-preview-label">This week\'s digest</p>', unsafe_allow_html=True)
            _digest_preview(agency_short, views, closing, settings)
            st.markdown('<p class="gs-preview-label">Example instant alert</p>', unsafe_allow_html=True)
            _instant_preview(views, settings)

    st.markdown('<div class="gs-footer"><p class="gs-small">Prototype preview: email delivery isn\'t switched on '
                'yet. Settings last for this session.</p></div>', unsafe_allow_html=True)
