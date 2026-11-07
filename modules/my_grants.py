"""Persistent My Grants workspace shared with Search."""
import streamlit as st

from services.calendar_export import grants_to_ics
from services.grant_store import LocalGrantStore


def show_my_grants(store=None):
    store = store or LocalGrantStore()
    st.header("My Grants")
    st.caption("Saved grants and coordinator workflow state persist in the local development store.")
    records = store.list_records()
    if not records:
        st.info("No saved grants yet. Bookmark opportunities from Search.")
        return
    selected = []
    for record in records:
        key = f"{record['agency']}::{record['opportunity_id']}"
        with st.container(border=True):
            if st.checkbox("Include in calendar export", key=f"calendar_{key}"):
                selected.append(record)
            st.subheader(record.get("title") or "Untitled grant")
            st.caption(f"{record['agency']} · Opportunity {record['opportunity_id']}")
            st.write(f"**Official deadline:** {record.get('close_date') or 'Missing'}")
            decision = st.selectbox(
                "Decision",
                ["", "Pursue", "Maybe", "Pass"],
                index=["", "Pursue", "Maybe", "Pass"].index(record.get("decision", "")),
                key=f"my_decision_{key}",
            )
            notes = st.text_input("Notes", value=record.get("notes", ""), key=f"my_notes_{key}")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save decision and notes", key=f"save_notes_{key}"):
                    store.save(
                        record["agency"], record["opportunity_id"],
                        {"decision": decision, "notes": notes},
                    )
                    st.success("Decision and notes saved.")
            with col2:
                if st.button("Remove bookmark", key=f"remove_{key}"):
                    store.remove(record["agency"], record["opportunity_id"])
                    st.rerun()
            if record.get("official_url"):
                st.link_button("View official opportunity", record["official_url"])
    st.download_button(
        "Download selected deadlines (.ics)",
        grants_to_ics(selected),
        file_name="grantscope-deadlines.ics",
        mime="text/calendar",
        disabled=not selected,
    )
