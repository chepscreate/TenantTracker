import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import io
import re
import altair as alt

# Connect to database
conn = sqlite3.connect('tenants.db')
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    total_units INTEGER NOT NULL DEFAULT 1,
    location TEXT,
    address TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER,
    name TEXT NOT NULL,
    unit TEXT,
    rent REAL NOT NULL,
    email TEXT,
    phone TEXT,
    FOREIGN KEY (property_id) REFERENCES properties(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    property_id INTEGER,
    payment_date TEXT,
    month_year TEXT,
    amount REAL,
    method TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    property_id INTEGER,
    note_date TEXT,
    note_type TEXT,
    note_text TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS maintenance_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER,
    property_id INTEGER,
    photo_data BLOB NOT NULL,
    filename TEXT,
    upload_date TEXT,
    FOREIGN KEY (note_id) REFERENCES notes(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER,
    month_year TEXT,
    garden REAL DEFAULT 0,
    electrical REAL DEFAULT 0,
    other_maintenance REAL DEFAULT 0,
    FOREIGN KEY (property_id) REFERENCES properties(id)
)
''')
conn.commit()

# One-time migration: add property_id columns if missing
cursor.execute("PRAGMA table_info(tenants)")
columns = [col[1] for col in cursor.fetchall()]
if 'property_id' not in columns:
    cursor.execute("ALTER TABLE tenants ADD COLUMN property_id INTEGER REFERENCES properties(id)")
    conn.commit()

cursor.execute("PRAGMA table_info(payments)")
columns = [col[1] for col in cursor.fetchall()]
if 'property_id' not in columns:
    cursor.execute("ALTER TABLE payments ADD COLUMN property_id INTEGER REFERENCES properties(id)")
    conn.commit()

cursor.execute("PRAGMA table_info(notes)")
columns = [col[1] for col in cursor.fetchall()]
if 'property_id' not in columns:
    cursor.execute("ALTER TABLE notes ADD COLUMN property_id INTEGER REFERENCES properties(id)")
    conn.commit()

cursor.execute("PRAGMA table_info(maintenance_photos)")
columns = [col[1] for col in cursor.fetchall()]
if 'property_id' not in columns:
    cursor.execute("ALTER TABLE maintenance_photos ADD COLUMN property_id INTEGER REFERENCES properties(id)")
    conn.commit()

conn.commit()

# Pre-load your 7 properties if none exist
cursor.execute("SELECT COUNT(*) FROM properties")
if cursor.fetchone()[0] == 0:
    properties_data = [
        ("LE SOUVENIR (1168)", 10, "Bloemfontein Area", "Farm 1168"),
        ("Farm 222", 8, "Bloemfontein Area", "Farm 222"),
        ("15 Buitekant Straat 874", 4, "Brandfort", "15 Buitekant Straat 874, Brandfort"),
        ("3638 Mothibi 874", 1, "Bloemfontein", "4 Room House, Mothibi 874, Bloemfontein"),
        ("Little Blackwood", 5, "Zimbabwe", "Plot Little Blackwood, Zimbabwe"),
        ("43 Golfcourse Road", 6, "Walkerville", "43 Golfcourse Road, Walkerville"),
        ("Midrand Apartment", 2, "Midrand", "Apartment in Midrand")
    ]
    cursor.executemany("INSERT INTO properties (name, total_units, location, address) VALUES (?, ?, ?, ?)", properties_data)
    conn.commit()

# Streamlit configuration
st.set_page_config(page_title="ALOTA PROPERTIES", layout="wide", initial_sidebar_state="expanded")
st.title("ALOTA PROPERTIES")

# Sidebar navigation
page = st.sidebar.selectbox(
    "Menu",
    ["Dashboard", "Properties", "Add/Edit Tenants", "Record Payment", "Manage Expenses", "Expense Trend Dashboard", "Monthly Report", "Payment History", "Notes Overview", "Search"]
)

# Sidebar property selector
props_df = pd.read_sql_query("SELECT id, name FROM properties ORDER BY name", conn)
property_options = ["All Properties"] + props_df['name'].tolist()
selected_property_name = st.sidebar.selectbox("Select Property", property_options)

if selected_property_name == "All Properties":
    selected_property_id = None
else:
    selected_property_id = props_df[props_df['name'] == selected_property_name]['id'].iloc[0]

# Helper functions
def get_tenants(property_id=None):
    if property_id:
        return pd.read_sql_query("SELECT * FROM tenants WHERE property_id = ? ORDER BY name", conn, params=(property_id,))
    return pd.read_sql_query("SELECT * FROM tenants ORDER BY name", conn)

def get_payments(property_id=None):
    if property_id:
        return pd.read_sql_query('''
            SELECT p.*, t.name, t.unit 
            FROM payments p 
            JOIN tenants t ON p.tenant_id = t.id 
            WHERE p.property_id = ?
            ORDER BY p.payment_date DESC
        ''', conn, params=(property_id,))
    return pd.read_sql_query('''
        SELECT p.*, t.name, t.unit 
        FROM payments p 
        JOIN tenants t ON p.tenant_id = t.id 
        ORDER BY p.payment_date DESC
    ''', conn)

def get_notes(property_id=None):
    if property_id:
        return pd.read_sql_query('''
            SELECT n.*, t.name, t.unit 
            FROM notes n 
            JOIN tenants t ON n.tenant_id = t.id 
            WHERE n.property_id = ?
            ORDER BY n.note_date DESC
        ''', conn, params=(property_id,))
    return pd.read_sql_query('''
        SELECT n.*, t.name, t.unit 
        FROM notes n 
        JOIN tenants t ON n.tenant_id = t.id 
        ORDER BY n.note_date DESC
    ''', conn)

def get_photos_for_note(note_id):
    return pd.read_sql_query('''
        SELECT id, filename, upload_date 
        FROM maintenance_photos 
        WHERE note_id = ?
        ORDER BY upload_date
    ''', conn, params=(note_id,))

def get_expenses(property_id=None, month_year=None):
    if property_id and month_year:
        return pd.read_sql_query('''
            SELECT * FROM expenses 
            WHERE property_id = ? AND month_year = ?
        ''', conn, params=(property_id, month_year))
    elif property_id:
        return pd.read_sql_query('''
            SELECT * FROM expenses 
            WHERE property_id = ?
            ORDER BY month_year DESC
        ''', conn, params=(property_id,))
    return pd.read_sql_query("SELECT * FROM expenses ORDER BY month_year DESC", conn)

# ────────────────────────────────────────────────
# DASHBOARD
# ────────────────────────────────────────────────
if page == "Dashboard":
    st.header("ALOTA PROPERTIES - Dashboard")
    
    properties = pd.read_sql_query("SELECT * FROM properties", conn)
    
    total_potential = 0
    total_actual = 0
    total_expenses = 0
    
    for _, prop in properties.iterrows():
        tenants_in_prop = get_tenants(prop['id'])
        occupied = len(tenants_in_prop)
        occupancy = (occupied / prop['total_units'] * 100) if prop['total_units'] > 0 else 0
        
        potential = tenants_in_prop['rent'].sum() if not tenants_in_prop.empty else 0
        total_potential += potential
        
        current_month = datetime.now().strftime("%b %Y")
        payments_this_month = get_payments(prop['id'])
        payments_this_month = payments_this_month[payments_this_month['month_year'] == current_month]
        actual = payments_this_month['amount'].sum()
        total_actual += actual
        
        expenses = get_expenses(prop['id'], current_month)
        exp_total = expenses[['garden', 'electrical', 'other_maintenance']].sum().sum() if not expenses.empty else 0
        total_expenses += exp_total
        
        net = actual - exp_total
        
        st.subheader(f"{prop['name']}")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Units", prop['total_units'])
        col2.metric("Occupied", f"{occupied}/{prop['total_units']}", f"{occupancy:.1f}%")
        col3.metric("Potential Revenue", f"R{potential:,.0f}")
        col4.metric("Actual Revenue", f"R{actual:,.0f}")
        col5.metric("Net This Month", f"R{net:,.0f}", delta_color="inverse" if net < 0 else "normal")
        
        st.divider()
    
    st.subheader("ALOTA PROPERTIES - Grand Total")
    grand_net = total_actual - total_expenses
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Potential", f"R{total_potential:,.0f}")
    col2.metric("Total Actual Revenue", f"R{total_actual:,.0f}")
    col3.metric("Total Expenses", f"R{total_expenses:,.0f}")
    col4.metric("Overall Net", f"R{grand_net:,.0f}", delta_color="inverse" if grand_net < 0 else "normal")

# ────────────────────────────────────────────────
# MANAGE EXPENSES
# ────────────────────────────────────────────────
elif page == "Manage Expenses":
    st.header("Manage Monthly Expenses")
    
    prop_list = pd.read_sql_query("SELECT id, name FROM properties ORDER BY name", conn)
    selected_prop = st.selectbox(
        "Property",
        options=prop_list['id'].tolist(),
        format_func=lambda x: prop_list[prop_list['id']==x]['name'].iloc[0]
    )
    
    current_month = datetime.now().strftime("%b %Y")
    month_input = st.text_input("Month/Year (e.g. Feb 2026)", value=current_month)
    
    with st.form("Add/Update Expenses"):
        garden = st.number_input("Garden Service (R)", min_value=0.0, step=50.0, value=0.0)
        electrical = st.number_input("Electrical (R)", min_value=0.0, step=50.0, value=0.0)
        other = st.number_input("Other Maintenance (R)", min_value=0.0, step=50.0, value=0.0)
        
        submitted = st.form_submit_button("Save Expenses")
        if submitted:
            # Check if entry exists
            existing = get_expenses(selected_prop, month_input)
            if not existing.empty:
                cursor.execute("""
                    UPDATE expenses SET garden=?, electrical=?, other_maintenance=?
                    WHERE property_id=? AND month_year=?
                """, (garden, electrical, other, selected_prop, month_input))
            else:
                cursor.execute("""
                    INSERT INTO expenses (property_id, month_year, garden, electrical, other_maintenance)
                    VALUES (?, ?, ?, ?, ?)
                """, (selected_prop, month_input, garden, electrical, other))
            conn.commit()
            st.success(f"Expenses saved for {month_input}")
            st.rerun()

    # Show existing expenses
    expenses = get_expenses(selected_prop)
    if not expenses.empty:
        st.subheader("Recorded Expenses")
        st.dataframe(expenses[['month_year', 'garden', 'electrical', 'other_maintenance']], use_container_width=True)
    else:
        st.info("No expenses recorded yet for this property.")

# ────────────────────────────────────────────────
# EXPENSE TREND DASHBOARD – NEW PAGE
# ────────────────────────────────────────────────
elif page == "Expense Trend Dashboard":
    st.header("Expense Trend Dashboard")
    
    prop_list = pd.read_sql_query("SELECT id, name FROM properties ORDER BY name", conn)
    selected_prop = st.selectbox(
        "Select Property",
        options=prop_list['id'].tolist(),
        format_func=lambda x: prop_list[prop_list['id']==x]['name'].iloc[0]
    )
    
    expenses = get_expenses(selected_prop)
    if expenses.empty:
        st.info("No expenses recorded for this property yet.")
    else:
        # Prepare data for chart (long format)
        chart_data = expenses[['month_year', 'garden', 'electrical', 'other_maintenance']].copy()
        chart_data = chart_data.melt(id_vars=['month_year'], 
                                     value_vars=['garden', 'electrical', 'other_maintenance'],
                                     var_name='Category',
                                     value_name='Amount (R)')
        chart_data['Category'] = chart_data['Category'].map({
            'garden': 'Garden Service',
            'electrical': 'Electrical',
            'other_maintenance': 'Other Maintenance'
        })
        
        # Interactive trend chart
        trend_chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(filled=True, size=80)).encode(
            x=alt.X('month_year:N', title='Month/Year', axis=alt.Axis(labelAngle=-45, labelFontSize=11)),
            y=alt.Y('Amount (R):Q', title='Expense Amount (R)', axis=alt.Axis(labelFontSize=11)),
            color=alt.Color('Category:N', legend=alt.Legend(title="Expense Type", labelFontSize=11, symbolSize=150)),
            tooltip=[
                alt.Tooltip('month_year:N', title='Month'),
                alt.Tooltip('Category:N', title='Type'),
                alt.Tooltip('Amount (R):Q', title='Amount (R)', format='.2f')
            ]
        ).properties(
            width='container',
            height=450,
            title=alt.TitleParams(f"Monthly Expense Trends - {prop_list[prop_list['id']==selected_prop]['name'].iloc[0]}", fontSize=16)
        ).configure_view(strokeWidth=0).configure_axis(labelFontSize=11, titleFontSize=13).configure_legend(labelFontSize=11, titleFontSize=13).interactive()

        st.altair_chart(trend_chart, use_container_width=True)
        
        # Summary table
        st.subheader("Expense Summary Table")
        st.dataframe(
            expenses[['month_year', 'garden', 'electrical', 'other_maintenance']],
            use_container_width=True,
            column_config={
                "month_year": st.column_config.TextColumn("Month/Year"),
                "garden": st.column_config.NumberColumn("Garden Service (R)", format="R%.2f"),
                "electrical": st.column_config.NumberColumn("Electrical (R)", format="R%.2f"),
                "other_maintenance": st.column_config.NumberColumn("Other Maintenance (R)", format="R%.2f")
            }
        )
        
        # Total expenses
        total_garden = expenses['garden'].sum()
        total_electrical = expenses['electrical'].sum()
        total_other = expenses['other_maintenance'].sum()
        grand_total = total_garden + total_electrical + total_other
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Garden Service", f"R{total_garden:,.2f}")
        col2.metric("Total Electrical", f"R{total_electrical:,.2f}")
        col3.metric("Total Other Maintenance", f"R{total_other:,.2f}")
        col4.metric("Grand Total Expenses", f"R{grand_total:,.2f}")

# ────────────────────────────────────────────────
# ADD/EDIT TENANTS
# ────────────────────────────────────────────────
elif page == "Add/Edit Tenants":
    st.header("Manage Tenants")
    
    prop_list = pd.read_sql_query("SELECT id, name FROM properties ORDER BY name", conn)
    selected_prop = st.selectbox(
        "Property",
        options=prop_list['id'].tolist(),
        format_func=lambda x: prop_list[prop_list['id']==x]['name'].iloc[0]
    )
    
    with st.form("Add Tenant", clear_on_submit=True):
        name = st.text_input("Tenant Name *")
        unit = st.text_input("Unit / Apartment")
        rent = st.number_input("Monthly Rent (R) *", min_value=0.0, step=100.0)
        email = st.text_input("Email (optional)")
        phone = st.text_input("Phone (international format, e.g. +27831234567)")
        
        submitted = st.form_submit_button("Add New Tenant")
        if submitted and name and rent > 0:
            cursor.execute("""
                INSERT INTO tenants (property_id, name, unit, rent, email, phone)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (selected_prop, name, unit, rent, email, phone))
            conn.commit()
            st.success("Tenant added successfully")
            st.rerun()

    tenants = get_tenants(selected_prop)
    if not tenants.empty:
        st.subheader("Current Tenants")
        for _, row in tenants.iterrows():
            with st.expander(f"{row['name']} – Unit {row['unit']} – R{row['rent']:,.0f}"):
                col1, col2, col3 = st.columns([3,2,1])
                new_name = col1.text_input("Name", value=row['name'], key=f"name_{row['id']}")
                new_unit = col2.text_input("Unit", value=row['unit'] or "", key=f"unit_{row['id']}")
                new_rent = col3.number_input("Rent", value=row['rent'], step=100.0, key=f"rent_{row['id']}")
                
                col_email, col_phone, col_btn = st.columns([2,2,1])
                new_email = col_email.text_input("Email", value=row['email'] or "", key=f"email_{row['id']}")
                new_phone = col_phone.text_input("Phone (+27...)", value=row['phone'] or "", key=f"phone_{row['id']}")
                
                if col_btn.button("Save Changes", key=f"save_{row['id']}"):
                    cursor.execute("""
                        UPDATE tenants SET name=?, unit=?, rent=?, email=?, phone=?
                        WHERE id=?
                    """, (new_name, new_unit, new_rent, new_email, new_phone, row['id']))
                    conn.commit()
                    st.success("Tenant updated")
                    st.rerun()
                
                if st.button("Delete Tenant", key=f"del_{row['id']}"):
                    cursor.execute("DELETE FROM tenants WHERE id=?", (row['id'],))
                    cursor.execute("DELETE FROM payments WHERE tenant_id=?", (row['id'],))
                    cursor.execute("DELETE FROM notes WHERE tenant_id=?", (row['id'],))
                    cursor.execute("DELETE FROM maintenance_photos WHERE note_id IN (SELECT id FROM notes WHERE tenant_id=?)", (row['id'],))
                    conn.commit()
                    st.error("Tenant deleted")
                    st.rerun()
                
                st.subheader("Notes")
                note_type_filter = st.selectbox("Filter by type", ["All", "Payment Excuse", "Maintenance Needed", "Late Payment Notice"], key=f"filter_tenant_{row['id']}")
                notes = get_notes(row['id'], note_type_filter)

                if not notes.empty:
                    for _, note in notes.iterrows():
                        cols = st.columns([1, 4, 1, 1])
                        cols[0].write(note['note_date'])
                        cols[1].markdown(f"**{note['note_type']}**: {note['note_text']}")
                        
                        edit_key = f"edit_note_{note['id']}"
                        if cols[2].button("Edit", key=f"btn_edit_{note['id']}"):
                            st.session_state[edit_key] = True

                        if cols[3].button("Delete", key=f"btn_del_{note['id']}"):
                            cursor.execute("DELETE FROM notes WHERE id = ?", (note['id'],))
                            conn.commit()
                            st.success("Note deleted")
                            st.rerun()

                        if st.session_state.get(edit_key, False):
                            new_text = st.text_area("Edit note text", value=note['note_text'], key=f"edit_text_{note['id']}")
                            col_save, col_cancel = st.columns(2)
                            if col_save.button("Save Edit", key=f"save_edit_{note['id']}"):
                                cursor.execute("UPDATE notes SET note_text = ? WHERE id = ?", (new_text, note['id']))
                                conn.commit()
                                st.session_state[edit_key] = False
                                st.success("Note updated")
                                st.rerun()
                            if col_cancel.button("Cancel", key=f"cancel_edit_{note['id']}"):
                                st.session_state[edit_key] = False
                                st.rerun()
                        
                        if note['note_type'] == "Maintenance Needed":
                            photos = get_photos_for_note(note['id'])
                            if not photos.empty:
                                st.caption(f"Attached photos ({len(photos)})")
                                photo_cols = st.columns(min(3, len(photos)))
                                for i, photo in enumerate(photos.itertuples()):
                                    with photo_cols[i % 3]:
                                        cursor.execute("SELECT photo_data FROM maintenance_photos WHERE id = ?", (photo.id,))
                                        img_data = cursor.fetchone()[0]
                                        st.image(img_data, caption=photo.filename, use_container_width=True)
                            else:
                                st.caption("No photos attached.")

                st.subheader("Add New Note")

                type_key = f"note_type_{row['id']}"
                text_key = f"note_text_{row['id']}"
                date_key = f"promised_date_{row['id']}"
                photos_key = f"photos_uploader_{row['id']}"
                reset_key = f"reset_form_{row['id']}"

                if type_key not in st.session_state:
                    st.session_state[type_key] = "Payment Excuse"
                if reset_key not in st.session_state:
                    st.session_state[reset_key] = False

                note_type = st.selectbox(
                    "Note Type",
                    ["Payment Excuse", "Maintenance Needed", "Late Payment Notice"],
                    index=0 if st.session_state[type_key] == "Payment Excuse" else 
                          1 if st.session_state[type_key] == "Maintenance Needed" else 2,
                    key=type_key
                )

                note_text_value = "" if st.session_state.get(reset_key, False) else st.session_state.get(text_key, "")
                note_text = st.text_area("Note Details", value=note_text_value, key=text_key)

                promised_date = None
                if note_type == "Payment Excuse":
                    st.markdown("**For Payment Excuse only:** Select when the tenant promised to pay")
                    default_date = datetime.now().date() + timedelta(days=7)
                    promised_date = st.date_input(
                        "Promised payment date",
                        value=default_date,
                        min_value=datetime.now().date(),
                        max_value=datetime.now().date() + timedelta(days=365),
                        format="YYYY-MM-DD",
                        key=date_key
                    )

                uploaded_photos = None
                if note_type == "Maintenance Needed":
                    st.markdown("**Upload photos** (e.g. leak, damage, broken item)")
                    uploaded_photos = st.file_uploader(
                        "Choose image files",
                        type=["jpg", "jpeg", "png"],
                        accept_multiple_files=True,
                        key=photos_key
                    )

                col_submit, col_reset = st.columns(2)
                if col_submit.button("Add Note", key=f"add_note_btn_{row['id']}"):
                    if not note_text:
                        st.warning("Please enter note details.")
                    else:
                        final_text = note_text
                        if note_type == "Payment Excuse" and promised_date:
                            final_text += f" → Promised payment date: {promised_date.strftime('%Y-%m-%d')}"

                        note_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("""
                            INSERT INTO notes (tenant_id, property_id, note_date, note_type, note_text)
                            VALUES (?, ?, ?, ?, ?)
                        """, (row['id'], selected_prop, note_date_str, note_type, final_text))
                        conn.commit()
                        
                        note_id = cursor.lastrowid
                        
                        if uploaded_photos and note_type == "Maintenance Needed":
                            for photo_file in uploaded_photos:
                                photo_bytes = photo_file.getvalue()
                                upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                cursor.execute("""
                                    INSERT INTO maintenance_photos (note_id, property_id, photo_data, filename, upload_date)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (note_id, selected_prop, photo_bytes, photo_file.name, upload_date))
                            conn.commit()

                        st.success("Note added successfully" + (f" ({len(uploaded_photos)} photos)" if uploaded_photos else ""))
                        
                        st.session_state[reset_key] = True
                        st.rerun()

                if col_reset.button("Clear Form", key=f"clear_btn_{row['id']}"):
                    st.session_state[reset_key] = True
                    st.rerun()

                if st.session_state.get(reset_key, False):
                    st.session_state[reset_key] = False
                    st.rerun()

# ────────────────────────────────────────────────
# NOTES OVERVIEW
# ────────────────────────────────────────────────
elif page == "Notes Overview":
    st.header("Notes & Payment Promise Overview")

    note_type_filter = st.selectbox("Filter by note type", ["All", "Payment Excuse", "Maintenance Needed", "Late Payment Notice"])

    notes = get_notes(selected_property_id)

    if notes.empty:
        st.info("No notes found matching the filter.")
    else:
        st.subheader(f"Found {len(notes)} notes")

        st.subheader("Payment Promise Alerts")
        promises = []
        for _, note in notes.iterrows():
            promise_date_str = extract_promise_date(note['note_text'], note['note_date'])
            if promise_date_str:
                promise_date = datetime.strptime(promise_date_str, "%Y-%m-%d").date()
                days_diff = (promise_date - datetime.now().date()).days
                
                if days_diff < 0:
                    status = "Overdue"
                    color = "red"
                elif days_diff == 0:
                    status = "Due Today"
                    color = "green"
                elif days_diff <= 7:
                    status = f"In {days_diff} days"
                    color = "orange"
                else:
                    status = f"In {days_diff} days"
                    color = "green"

                promises.append({
                    "Tenant": note['name'],
                    "Unit": note['unit'],
                    "Promised Date": promise_date_str,
                    "Status": status,
                    "Note Excerpt": note['note_text'][:100] + ("..." if len(note['note_text']) > 100 else ""),
                    "Note Type": note['note_type'],
                    "_color": color
                })

        if promises:
            df_promises = pd.DataFrame(promises)

            def style_promise_row(row):
                color = row['_color']
                styles = ['' for _ in row]
                try:
                    status_idx = list(row.index).index('Status')
                    styles[status_idx] = f'color: {color}; font-weight: bold;'
                except ValueError:
                    pass
                return styles

            styled = df_promises.style.apply(style_promise_row, axis=1)

            display_df = df_promises.drop(columns=['_color'])

            st.dataframe(
                styled,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No payment promises detected in the notes.")

        st.subheader("All Notes")
        enhanced_notes = notes.copy()
        enhanced_notes['Photos'] = enhanced_notes['id'].apply(
            lambda nid: len(get_photos_for_note(nid)) if get_photos_for_note(nid).shape[0] > 0 else 0
        )
        st.dataframe(
            enhanced_notes[['name', 'unit', 'note_date', 'note_type', 'note_text', 'Photos']],
            use_container_width=True,
            column_config={
                "note_text": st.column_config.TextColumn("Note Text", width="large"),
                "Photos": st.column_config.NumberColumn("Photos")
            }
        )

# ────────────────────────────────────────────────
# RECORD PAYMENT
# ────────────────────────────────────────────────
elif page == "Record Payment":
    st.header("Record a Payment")
    
    tenants = get_tenants(selected_property_id)
    if tenants.empty:
        st.warning("No tenants yet. Add some first!")
    else:
        tenant_dict = {f"{r['name']} ({r['unit'] or 'No unit'})": r['id'] for _, r in tenants.iterrows()}
        selected = st.selectbox("Tenant", list(tenant_dict.keys()))
        tenant_id = tenant_dict.get(selected)
        
        with st.form("Payment"):
            col1, col2 = st.columns(2)
            month = col1.selectbox("Month", ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])
            year = col2.number_input("Year", min_value=2000, max_value=2035, value=datetime.now().year)
            month_year = f"{month} {year}"
            
            amount = st.number_input("Amount Paid (R)", min_value=0.0, step=50.0)
            method = st.selectbox("Method", ["EFT", "Cash", "SnapScan", "Other"])
            
            if st.form_submit_button("Record"):
                if amount > 0:
                    payment_date = datetime.now().strftime("%Y-%m-%d")
                    cursor.execute("""
                        INSERT INTO payments (tenant_id, property_id, payment_date, month_year, amount, method)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (tenant_id, selected_property_id, payment_date, month_year, amount, method))
                    conn.commit()
                    st.success("Payment recorded successfully")
                    st.rerun()
                else:
                    st.warning("Amount must be greater than 0")

# ────────────────────────────────────────────────
# MONTHLY REPORT
# ────────────────────────────────────────────────
elif page == "Monthly Report":
    st.header("Monthly Rent Report")
    
    current_month = datetime.now().strftime("%b %Y")
    month_input = st.text_input("Month/Year (e.g. Feb 2026)", value=current_month)
    
    if st.button("Generate Report"):
        query = '''
        SELECT t.id, t.name, t.unit, t.rent, t.phone, t.email,
               COALESCE(SUM(p.amount), 0) as total_paid,
               (t.rent - COALESCE(SUM(p.amount), 0)) as balance,
               CASE WHEN (t.rent - COALESCE(SUM(p.amount), 0)) > 0 THEN 'Overdue' 
                    WHEN (t.rent - COALESCE(SUM(p.amount), 0)) = 0 THEN 'Paid' 
                    ELSE 'Overpaid' END as status,
               ? as month_year
        FROM tenants t
        LEFT JOIN payments p ON t.id = p.tenant_id AND p.month_year = ?
        WHERE t.property_id = COALESCE(?, t.property_id)
        GROUP BY t.id
        ORDER BY t.name
        '''
        df = pd.read_sql_query(query, conn, params=(month_input, month_input, selected_property_id))
        
        def highlight_overdue(row):
            return ['background-color: #ffcccc' if row['balance'] > 0 else '' for _ in row]
        
        styled_df = df.style.format({
            'rent': 'R{:,.0f}',
            'total_paid': 'R{:,.0f}',
            'balance': 'R{:,.0f}'
        }).apply(highlight_overdue, axis=1)
        
        st.dataframe(styled_df, use_container_width=True)
        
        total_due = df['rent'].sum()
        total_collected = df['total_paid'].sum()
        arrears = total_due - total_collected
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Due", f"R{total_due:,.0f}")
        col2.metric("Collected", f"R{total_collected:,.0f}")
        col3.metric("Arrears", f"R{arrears:,.0f}", delta_color="inverse")
        
        if not df.empty:
            st.subheader("Rent Collection Breakdown")
            chart_data = df[['name', 'rent', 'total_paid', 'balance']].copy()
            chart_data = chart_data.melt(id_vars=['name'], 
                                         value_vars=['rent', 'total_paid', 'balance'],
                                         var_name='Category',
                                         value_name='Amount (R)')
            chart_data['Category'] = chart_data['Category'].map({
                'rent': 'Due',
                'total_paid': 'Paid',
                'balance': 'Arrears'
            })
            
            line_chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(filled=True, size=80)).encode(
                x=alt.X('name:N', title='Tenant', axis=alt.Axis(labelAngle=-45)),
                y=alt.Y('Amount (R):Q', title='Amount (R)'),
                color=alt.Color('Category:N', legend=alt.Legend(title="Category")),
                tooltip=['name', 'Category', 'Amount (R)']
            ).properties(
                width='container',
                height=450
            ).interactive()

            st.altair_chart(line_chart, use_container_width=True)

        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="Download Report as CSV",
            data=csv_buffer.getvalue(),
            file_name=f"rent_report_{month_input.replace(' ', '_')}.csv",
            mime="text/csv"
        )

        st.subheader("Overdue Tenants – Manual Reminder List")
        overdue = df[df['balance'] > 0]
        if overdue.empty:
            st.info("No overdue tenants this month")
        else:
            reminder_df = overdue[['name', 'unit', 'phone', 'email', 'balance', 'month_year']].copy()
            reminder_df = reminder_df.rename(columns={
                'name': 'Tenant Name',
                'unit': 'Unit',
                'phone': 'Phone (+27...)',
                'email': 'Email',
                'balance': 'Amount Overdue (R)',
                'month_year': 'Month'
            })
            reminder_df['Amount Overdue (R)'] = reminder_df['Amount Overdue (R)'].apply(lambda x: f"R{x:,.2f}")
            
            st.dataframe(
                reminder_df,
                use_container_width=True
            )
            
            st.markdown("""
            **How to use this list:**
            - Copy phone numbers to send WhatsApp/SMS manually from your phone
            - Copy emails to send reminders via email
            - Use the amount and month to personalize your message
            - Sort/filter the table by clicking column headers
            """)

# ────────────────────────────────────────────────
# PAYMENT HISTORY
# ────────────────────────────────────────────────
elif page == "Payment History":
    st.header("All Payments")
    payments = get_payments(selected_property_id)
    
    if not payments.empty:
        search_term = st.text_input("Search tenant name or unit", "")
        if search_term:
            payments = payments[
                payments['name'].str.contains(search_term, case=False) |
                payments['unit'].str.contains(search_term, case=False, na=False)
            ]
        st.dataframe(payments[['name', 'unit', 'month_year', 'amount', 'method', 'payment_date']],
                     use_container_width=True)
    else:
        st.info("No payments recorded yet.")

# ────────────────────────────────────────────────
# SEARCH
# ────────────────────────────────────────────────
elif page == "Search":
    st.header("Search Tenants & Payments")
    
    tab1, tab2 = st.tabs(["Tenants", "Payments"])
    
    with tab1:
        search_t = st.text_input("Search tenants by name or unit")
        if search_t:
            q = f"%{search_t}%"
            df = pd.read_sql_query("SELECT * FROM tenants WHERE name LIKE ? OR unit LIKE ?", conn, params=(q, q))
            st.dataframe(df)
    
    with tab2:
        search_p = st.text_input("Search payments by tenant name or month/year")
        if search_p:
            q = f"%{search_p}%"
            df = pd.read_sql_query('''
                SELECT p.*, t.name, t.unit 
                FROM payments p JOIN tenants t ON p.tenant_id = t.id
                WHERE t.name LIKE ? OR p.month_year LIKE ?
                ORDER BY p.payment_date DESC
            ''', conn, params=(q, q))
            st.dataframe(df)

# End of file