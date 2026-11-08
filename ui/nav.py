"""Registry of st.Page objects so pages can link to each other with st.page_link
(client-side navigation keeps session state, unlike plain href links)."""
PAGES = {}
