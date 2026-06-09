def render_asset_finder(con):


    sim_date = st.session_state.get("current_sim_date")

    # ======================================================
    # DATA CHECK (SAFE)
    # ======================================================
    df = st.session_state.get("closest_assets")


    # ======================================================
    # CONTROLS
    # ======================================================
    


    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    


    # ---- Strategy selector (SAFE ISOLATION) ----
    with col1:
        strategy_id = render_strategy_selector(con)

        if strategy_id is None:
            st.warning("Please select a strategy")
            return

        # חשוב: שמירה כדי לא לאבד state ברי־ראן
        st.session_state["strategy_id"] = strategy_id

    # ---- K ----
    with col2:
        k_option = st.selectbox(
            "Show top assets",
            options=[20, 5, 10],
            index=1,
            key="k_option"
        )

    # ---- Sector filter ----
    with col3:

        df_sectors = pd.read_sql_query("SELECT DISTINCT sector FROM assets", con)

        # Now you can proceed with your logic
        all_sectors = sorted(df_sectors["sector"].dropna().tolist())

        if "selected_sectors" not in st.session_state:
            st.session_state.selected_sectors = all_sectors

        st.markdown(
            """
            <div style="font-size:12px; line-height:1.1; margin-bottom: 2px;">
                Select sectors to include in your investment universe
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.popover("🎯 Filter sectors"):

            cols = st.columns(3)
            new_selected = []

            for i, sector in enumerate(all_sectors):
                with cols[i % 3]:
                    if st.checkbox(
                        sector,
                        value=(sector in st.session_state.selected_sectors),
                        key=f"sector_{sector}"
                    ):
                        new_selected.append(sector)

            st.session_state.selected_sectors = new_selected

    # ---- RUN BUTTON ----
    with col4:

        if st.button("🔍 Find closest assets", type="primary"):

            if strategy_id and sim_date:

                results = get_closest_assets(con, strategy_id, sim_date)

                st.session_state["closest_assets"] = results

                st.rerun()  

            else:
                st.error("Missing strategy or simulation date.")

    st.divider()

    # ======================================================
    # FILTERING
    # ======================================================

    filtered_df = df.copy()

    selected_sectors = st.session_state.get("selected_sectors", [])

    if selected_sectors:
        filtered_df = filtered_df[filtered_df["sector"].isin(selected_sectors)]

    filtered_df = filtered_df.head(int(k_option))

    # ======================================================
    # CARD RENDER
    # ======================================================

    def render_asset_card(row, rank):

        st.html(f"""
        <div style="line-height:1.2;">
            <div style="font-size:18px; font-weight:600;">
                #{rank} {row['name']}
            </div>

            <div style="
                display:inline-block;
                padding:2px 8px;
                border-radius:12px;
                background:rgba(76,175,80,0.15);
                color:#4CAF50;
                font-size:12px;
                font-weight:600;
                margin-top:4px;
            ">
                {row['sector']}
            </div>

            <div style="
                font-size:12px;
                opacity:0.65;
                margin-top:4px;
            ">
                {row['ticker']} • distance {row['distance']:.2f}
            </div>
        </div>
        """)

        c1, c2 = st.columns([1, 1], gap="small")

        with c1:
            if st.button(
                "🔍 Analyze",
                key=f"analyze_{row['ticker']}"
            ):
                show_asset_analysis_dialog(row["ticker"])

        with c2:
            with st.popover("💼 Trade"):
                st.radio(
                    "Direction",
                    ["Buy", "Sell"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"side_{row['ticker']}"
                )

    # ======================================================
    # DISPLAY
    # ======================================================

    items = list(filtered_df.iterrows())

    for i in range(0, len(items), 2):

        col1, col2 = st.columns(2, gap="small")

        with col1:
            if i < len(items):
                _, row = items[i]
                render_asset_card(row, i + 1)

        with col2:
            if i + 1 < len(items):
                _, row = items[i + 1]
                render_asset_card(row, i + 2) 

