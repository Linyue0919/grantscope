"""Visual style for the Funding Brief (spec section 12). Call inject_css() once per run."""
import streamlit as st

NC_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 38" width="{w}" height="{h}" aria-hidden="true">'
    '<path fill="#1F4E9C" d="M29.8 0 L95.4 0.6 L99.2 11 L100 18.9 L93.9 21.1 L87.9 27.3 L78.1 29 L71.9 38 L65.2 37.9 L52.5 24.8 L39.7 24.5 L38.3 20.7 L21.7 19.3 L13.7 22 L0 22 L3.3 18 L9.3 14.3 L15.8 9.3 L23.9 6.1 Z"/></svg>'
)

LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 44" width="520" height="44">'
    '<path fill="#1F4E9C" transform="translate(2,4) scale(0.95)" d="M29.8 0 L95.4 0.6 L99.2 11 L100 18.9 L93.9 21.1 L87.9 27.3 L78.1 29 L71.9 38 L65.2 37.9 L52.5 24.8 L39.7 24.5 L38.3 20.7 L21.7 19.3 L13.7 22 L0 22 L3.3 18 L9.3 14.3 L15.8 9.3 L23.9 6.1 Z"/>'
    '<rect x="112" y="8" width="1.5" height="28" fill="#B8C0CC"/>'
    '<text x="126" y="29" font-family="Public Sans, system-ui, sans-serif" font-size="21" font-weight="700" '
    'fill="#1B2230">GrantScope</text>'
    '<text x="262" y="28" font-family="Public Sans, system-ui, sans-serif" font-size="13" fill="#4B5565">'
    'Federal Grants Matcher for NC Agencies</text></svg>'
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap');
:root{
  --gs-text:#1B2230; --gs-secondary:#3A4352; --gs-muted:#4B5565; --gs-border:#D9DEE5; --gs-bg:#F5F6F8;
  --gs-card:#FFFFFF; --gs-navy:#1F4E9C; --gs-navy-hover:#163A75; --gs-tint:#EAF0FA; --gs-amber-text:#7A4300;
  --gs-amber-bg:#FDF1DC; --gs-neutral:#EEF1F5; --gs-focus:#E59A00;
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp a,
.stApp h1, .stApp h2, .stApp h3, .stApp summary {
  font-family: 'Public Sans', system-ui, sans-serif;
}
.stApp { background: var(--gs-bg); color: var(--gs-text); }
.block-container { max-width: 1440px; padding-top: 4.2rem; }
.stApp [data-testid="stMarkdownContainer"] p:not([class]), .stApp [data-testid="stMarkdownContainer"] li { font-size: 15px; color: var(--gs-text); }
img[data-testid="stHeaderLogo"] { width: 360px !important; max-width: none !important; height: 32px !important; object-fit: contain; object-position: left; }
a { color: var(--gs-navy); }
*:focus-visible { outline: 3px solid var(--gs-focus) !important; outline-offset: 2px; }

/* Buttons */
.stButton button, .stLinkButton a, .stDownloadButton button, [data-testid="stPopover"] button {
  min-height: 40px; border-radius: 8px; font-weight: 600;
}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
  background: var(--gs-navy); border-color: var(--gs-navy); color: #fff;
}
.stButton button[kind="primary"]:hover { background: var(--gs-navy-hover); border-color: var(--gs-navy-hover); }
.stApp button[kind="primary"] p, .stApp button[kind="primary"] [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stPopover"] button[kind="primary"] p { color: #fff !important; }
.stButton button[kind="secondary"], .stLinkButton a { background: #fff; border: 1px solid #B8C0CC; color: var(--gs-text); }
.stButton button[kind="tertiary"] { text-decoration: underline; color: var(--gs-muted); font-weight: 500; min-height: 32px; }

/* Cards: bordered containers keyed card_* / selcard_* */
[class*="st-key-card_"], [class*="st-key-selcard_"], [class*="st-key-panel"], [class*="st-key-section_"] {
  background: var(--gs-card); border-radius: 12px;
}
[class*="st-key-selcard_"] { border: 2px solid var(--gs-navy) !important; }

/* Brief header */
.stApp .gs-eyebrow { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--gs-muted); font-weight: 600; margin: 0 0 2px; }
.stApp .gs-h1 { font-size: 30px; font-weight: 700; color: var(--gs-text); margin: 0; line-height: 1.2; }
.stApp .gs-scope { font-size: 15px; color: var(--gs-secondary); margin: 0; }
.stApp .gs-muted { color: var(--gs-muted); font-size: 13px; }
.stApp .gs-small { font-size: 13px; color: var(--gs-muted); }
.stApp .gs-right { text-align: right; }

/* Section headings */
.stApp .gs-section-title { font-size: 20px; font-weight: 700; margin: 18px 0 2px; color: var(--gs-text); }
.stApp .gs-section-desc { font-size: 14px; color: var(--gs-muted); margin: 0 0 8px; }

/* Card internals */
.stApp .gs-card-row { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.stApp .gs-title { font-size: 18px; font-weight: 700; color: var(--gs-text); line-height: 1.3; margin: 0; }
.stApp .gs-agency { font-size: 14px; color: var(--gs-muted); margin: 2px 0 0; }
.stApp .gs-due { text-align: right; white-space: nowrap; }
.stApp .gs-due b { font-size: 15px; color: var(--gs-text); }
.stApp .gs-due span { display: block; font-size: 13px; color: var(--gs-muted); }
.stApp .gs-right-col { display: flex; gap: 12px; align-items: flex-start; }
.stApp .gs-score { border-radius: 10px; padding: 6px 10px; min-width: 84px; white-space: nowrap; text-align: center; line-height: 1.05; }
.stApp .gs-score .n { font-size: 26px; font-weight: 700; }
.stApp .gs-score .d { font-size: 12px; }
.stApp .gs-score .t { display: block; font-size: 12px; font-weight: 600; margin-top: 2px; }
.stApp .gs-tier-Strong { background: var(--gs-tint); color: var(--gs-navy); }
.stApp .gs-tier-Moderate { background: var(--gs-neutral); color: var(--gs-text); }
.stApp .gs-tier-Low { background: #F1F2F4; color: var(--gs-muted); }
.stApp .gs-reason { font-size: 16px; color: var(--gs-text); margin: 10px 0 8px; line-height: 1.45; }
.stApp .gs-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 4px; }
.stApp .gs-chip { background: var(--gs-bg); border: 1px solid #E3E7EC; border-radius: 999px; padding: 3px 12px; font-size: 14px; color: var(--gs-secondary); }
.stApp .gs-chip b { color: var(--gs-text); }
.stApp .gs-unclear { background: var(--gs-amber-bg); color: var(--gs-amber-text); border-radius: 8px; padding: 8px 12px; font-size: 14px; margin: 8px 0 2px; }
.stApp .gs-positive { color: #1F5E3A; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); border:0; }

/* Hidden placeholder, lower rows, soon items */
.stApp .gs-hidden { border: 1px dashed #B8C0CC; border-radius: 10px; padding: 8px 12px; color: var(--gs-muted); font-size: 14px; background: #fff; }
.stApp .gs-row { padding: 10px 0; border-bottom: 1px solid #E3E7EC; }
.stApp .gs-row:last-child { border-bottom: none; }
.stApp .gs-row-title { font-weight: 600; color: var(--gs-text); }
.stApp .gs-row-sub { font-size: 14px; color: var(--gs-secondary); margin-top: 2px; }

/* Detail panel */
.stApp .gs-panel-title { font-size: 18px; font-weight: 700; line-height: 1.3; margin: 0; }
.stApp .gs-reco { border-radius: 10px; padding: 14px 16px; display: flex; gap: 14px; justify-content: space-between; }
.stApp .gs-reco-top { background: var(--gs-tint); }
.stApp .gs-reco-check { background: var(--gs-amber-bg); }
.stApp .gs-reco-soon, .stApp .gs-reco-lower { background: var(--gs-neutral); }
.stApp .gs-reco-label { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; color: var(--gs-secondary); }
.stApp .gs-reco-label a.gs-ai-tag { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--gs-muted); margin-left: 6px; font-size: 12px; }
.stApp .gs-reco-text { font-size: 15px; color: var(--gs-text); margin-top: 6px; line-height: 1.45; }
.stApp .gs-reco-score { white-space: nowrap; background: #fff; border-radius: 8px; padding: 8px 12px; text-align: center; min-width: 78px; align-self: flex-start; }
.stApp .gs-reco-score .n { font-size: 24px; font-weight: 700; color: var(--gs-navy); }
.stApp .gs-h3 { font-size: 16px; font-weight: 700; margin: 16px 0 6px; color: var(--gs-text); }
.stApp .gs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.stApp .gs-tile { background: var(--gs-bg); border-radius: 8px; padding: 10px 12px; }
.stApp .gs-tile .l { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--gs-muted); font-weight: 600; }
.stApp .gs-tile .v { font-size: 15px; font-weight: 700; color: var(--gs-text); margin-top: 2px; }
.stApp .gs-tile .s { font-size: 13px; color: var(--gs-muted); margin-top: 2px; }
.stApp .gs-quote { border-left: 3px solid var(--gs-border); padding: 4px 12px; color: var(--gs-secondary); font-size: 14px; margin: 6px 0; }
.stApp .gs-evidence { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.stApp .gs-evbox { border: 1px solid var(--gs-border); border-radius: 8px; padding: 10px 12px; font-size: 14px; background: #fff; }
.stApp .gs-evbox .l { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--gs-muted); font-weight: 700; }
.stApp .gs-drivers { width: 100%; border-collapse: collapse; font-size: 14px; }
.stApp .gs-drivers td { padding: 6px 4px; border-bottom: 1px solid #E3E7EC; vertical-align: top; }
.stApp .gs-drivers td.v { text-align: right; font-weight: 600; }
.stApp .gs-pursue { background: var(--gs-bg); border-radius: 10px; padding: 12px 14px; }
.stApp .gs-footer { font-size: 13px; color: var(--gs-muted); margin-top: 24px; border-top: 1px solid var(--gs-border); padding-top: 10px; }
.stApp .gs-savedbar { background: #1B2230; color: #fff; border-radius: 10px; padding: 12px 16px; font-size: 14px; margin-top: 18px; }
.stApp .gs-savedbar b { color: #fff; }
.stApp .gs-savedbar-note { color: #C9D1DC; }
.st-key-inlinelink_mygrants_bar { background: var(--gs-tint); border-radius: 10px; padding: 10px 16px; margin-top: 18px; }
.st-key-inlinelink_mygrants_bar p { margin: 0 !important; }
/* Alerts page */
.stApp .gs-h3-first { margin-top: 0; }
.stApp .gs-count { background: var(--gs-tint); color: var(--gs-text); border-radius: 8px; padding: 10px 12px; font-size: 14px; line-height: 1.4; }
.stApp .gs-count b { color: var(--gs-navy); }
.stApp .gs-count-zero { background: var(--gs-bg); }
.stApp .gs-count-zero b { color: var(--gs-text); }
.stApp .gs-warn { color: var(--gs-amber-text); }
.stApp .gs-remind { margin: 6px 0 4px 18px; padding: 0; }
.stApp .gs-remind li { margin: 2px 0; color: var(--gs-text); font-size: 14px; }
.st-key-inlinelink_alerts_brief p { margin: 0 !important; }
.stApp table.gs-mail-facts { width: 100%; border-collapse: collapse; border: none; font-size: 14px; margin: 6px 0; }
.stApp table.gs-mail-facts td { border: none; border-bottom: 1px solid #EEF0F3; padding: 6px 0; vertical-align: top; }
.stApp table.gs-mail-facts td.l { color: var(--gs-muted); width: 92px; }
.stApp table.gs-mail-facts td.v { font-weight: 600; color: var(--gs-text); }
.stApp .gs-preview-label { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--gs-muted); font-weight: 600; margin: 14px 0 6px; }
.stApp .gs-mail { background: var(--gs-card); border: 1px solid var(--gs-border); border-radius: 12px; overflow: hidden; font-size: 14px; }
.stApp .gs-mail-none { padding: 14px 16px; color: var(--gs-secondary); background: var(--gs-bg); }
.stApp .gs-mail-off { background: var(--gs-neutral); color: var(--gs-secondary); padding: 6px 16px; font-size: 13px; }
.stApp .gs-mail-head { border-top: 4px solid var(--gs-navy); padding: 12px 16px 10px; border-bottom: 1px solid var(--gs-border); background: #FBFCFD; }
.stApp .gs-mail-meta { font-size: 13px; color: var(--gs-secondary); line-height: 1.6; }
.stApp .gs-mail-meta span { display: inline-block; width: 48px; color: var(--gs-muted); }
.stApp .gs-mail-subject { font-size: 16px; font-weight: 700; color: var(--gs-text); margin-top: 6px; line-height: 1.35; }
.stApp .gs-mail-body { padding: 4px 16px 14px; }
.stApp .gs-mail-group { font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--gs-navy); font-weight: 700; margin: 14px 0 4px; }
.stApp .gs-mail-item { display: flex; gap: 10px; align-items: flex-start; padding: 7px 0; border-bottom: 1px solid #EEF0F3; }
.stApp .gs-mail-item .t { font-weight: 600; color: var(--gs-text); line-height: 1.3; }
.stApp .gs-mail-item .t a { color: var(--gs-navy); text-decoration: none; }
.stApp .gs-mail-item .t a:hover { text-decoration: underline; }
.stApp .gs-mail-item .d { font-size: 13px; color: var(--gs-muted); margin-top: 1px; }
.stApp .gs-mini-score { flex: none; min-width: 38px; text-align: center; border-radius: 6px; padding: 3px 6px; font-weight: 700; font-size: 14px; }
.stApp .gs-mail-empty { color: var(--gs-muted); font-size: 13px; margin: 4px 0; }
.stApp .gs-mail-text { color: var(--gs-text); margin: 10px 0 6px; line-height: 1.45; }
.stApp .gs-mail-foot { color: var(--gs-muted); font-size: 12px; margin: 12px 0 0; }
/* Stacked header */
.st-key-brief_header { margin-bottom: 12px; }
.st-key-brief_header p { margin: 0 !important; }
.stApp .gs-h1-compact { font-size: 26px; }
.st-key-brief_filter_row [data-testid="stNumberInputStepDown"],
.st-key-brief_filter_row [data-testid="stNumberInputStepUp"] { display: none !important; }
.st-key-brief_filter_row input { text-align: center; }
/* st.page_link styled as an ordinary inline link (keeps session state on navigation) */
[class*="st-key-inlinelink"] [data-testid="stPageLink"] { margin: 0; }
.st-key-inlinelink_browse [data-testid="stPageLink"], .st-key-brief_meta_row .stButton { transform: translateY(4px); }
[class*="st-key-inlinelink"] [data-testid="stPageLink-NavLink"],
[class*="st-key-inlinelink"] a[data-testid="stPageLink-NavLink"] {
  padding: 0 !important; margin: 0 !important; background: none !important; border: none !important;
  min-height: 0 !important; line-height: inherit;
}
[class*="st-key-inlinelink"] [data-testid="stPageLink-NavLink"] p,
[class*="st-key-inlinelink"] [data-testid="stPageLink-NavLink"] span {
  color: #1F4E9C !important; text-decoration: underline; font-size: 15px; font-weight: 400;
}
.st-key-inlinelink_footer_how [data-testid="stPageLink-NavLink"] p,
.st-key-inlinelink_panel_how [data-testid="stPageLink-NavLink"] p,
.st-key-inlinelink_lower_browse [data-testid="stPageLink-NavLink"] p { font-size: 13px; }
.st-key-brief_meta_row button[kind="tertiary"] { min-height: 28px; font-size: 13px; padding: 0 4px; }
.st-key-brief_meta_row button[kind="tertiary"] p { font-size: 13px; }
/* Agency menu: compact left-aligned list */
.st-key-agencymenu button { justify-content: flex-start !important; text-align: left; min-height: 34px;
  text-decoration: none !important; padding: 4px 8px !important; border-radius: 6px; }
.st-key-agencymenu button p { color: var(--gs-text) !important; font-size: 14px; font-weight: 500; text-align: left; }
.st-key-agencymenu button:hover { background: var(--gs-tint) !important; }
.st-key-agencymenu button > div, .st-key-agencymenu button [data-testid="stMarkdownContainer"] { justify-content: flex-start !important; text-align: left !important; width: 100%; }
.st-key-agencymenu button:disabled { background: var(--gs-tint) !important; opacity: 1; }
.st-key-agencymenu button:disabled p { color: var(--gs-navy) !important; font-weight: 700; }
/* Detail panel stays in view while the brief scrolls */
[data-testid="stColumn"]:has(.st-key-panel) { position: sticky; top: 4.2rem; align-self: flex-start;
  max-height: calc(100vh - 5rem); overflow-y: auto; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)
