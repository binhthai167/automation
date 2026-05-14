import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import datetime as dt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Page configuration
st.set_page_config(
    page_title="EDMS Workflow Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main {
        padding-top: 2rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        margin: 0;
    }
    
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
        margin: 0;
    }
    
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .stSelectbox > div > div {
        background-color: #f8f9fa;
        color: #333333 !important;
    }
    
    .stSelectbox > div > div > div {
        color: #333333 !important;
    }
    
    .stSelectbox label {
        color: white !important;
        font-weight: 600;
    }
    
    .stDateInput > div > div {
        background-color: #f8f9fa;
        color: #333333 !important;
    }

    .stDateInput input {
        color: #333333 !important;
    }

    .stDateInput label {
        color: white !important;
        font-weight: 600;
    }
    
    /* Fix selectbox dropdown text color */
    .stSelectbox > div > div > div > div {
        color: #333333 !important;
    }
    
    /* Fix selectbox selected value text color */
    .stSelectbox > div > div > div[data-baseweb="select"] > div {
        color: #333333 !important;
    }
    
    .chart-container {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Database connection and data loading
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data():
    """Load data from MySQL database"""
    try:
        engine = create_engine(
            'mysql+pymysql://admin:Nidec%40123456@192.168.150.210:3306/edms'
        )
        
        # Read data using SQLAlchemy connection
        folder_dept = pd.read_sql("SELECT * FROM edms.folder_of_dept", engine)
        dept = pd.read_sql("SELECT id, name FROM edms.org_department", engine)
        form_folder = pd.read_sql("SELECT * FROM edms.form_of_folder", engine)
        form_data = pd.read_sql("""
            SELECT id, form_id, wf_done, wf_date_done, wf_dead_line, 
                   wf_status, date_create, date_update, update_count 
            FROM edms.wf_form_data
        """, engine)
        form_name = pd.read_sql(
            "SELECT id, name FROM edms.wf_form WHERE parent_id is NULL",
            engine
        )
        
        engine.dispose()
        
        # Data processing
        folder_dept = folder_dept.merge(dept, left_on="dept_id", right_on="id", suffixes=("", "_dept"))
        form_folder = form_folder.merge(folder_dept, left_on="folder_id", right_on="id", suffixes=("", "_folder"))
        form_name = form_name.merge(form_folder, left_on="id", right_on="form_id", suffixes=("", "_form_type"))
        report = form_data.merge(form_name, left_on="form_id", right_on="form_id")
        
        # Convert date columns
        report["date_create"] = pd.to_datetime(report["date_create"], errors="coerce")
        report["wf_date_done"] = pd.to_datetime(report["wf_date_done"], errors="coerce")
        report["wf_dead_line"] = pd.to_datetime(report["wf_dead_line"], errors="coerce")
        report["create_date"] = report["date_create"].dt.date
        report["done_date"] = report["wf_date_done"].dt.date
        
        # Remove Draft departments
        report = report[report["name_dept"] != "Draft"]
        return report,form_name
        
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

def create_kpi_metrics(data):
    """Create KPI metrics"""
    if data.empty:
        return {
            "total_forms": 0, "completed_forms": 0, "pending_forms": 0,
            "completion_rate": 0, "avg_processing_time": 0, "overdue_forms": 0
        }
    
    total_forms = len(data)
    completed_forms = len(data[data["wf_done"] == 1])
    pending_forms = total_forms - completed_forms
    completion_rate = (completed_forms / total_forms * 100) if total_forms > 0 else 0
    
    # Calculate average processing time for completed forms
    completed_data = data[data["wf_done"] == 1].copy()
    if not completed_data.empty:
        completed_data["processing_time"] = (completed_data["wf_date_done"] - completed_data["date_create"]).dt.days
        avg_processing_time = completed_data["processing_time"].mean()
    else:
        avg_processing_time = 0
    
    # Calculate overdue forms
    today = pd.Timestamp.now()
    overdue_forms = len(data[(data["wf_done"] == 0) & (data["wf_dead_line"] < today)])
    
    return {
        "total_forms": total_forms,
        "completed_forms": completed_forms,
        "pending_forms": pending_forms,
        "completion_rate": round(completion_rate, 1),
        "avg_processing_time": round(avg_processing_time, 1),
        "overdue_forms": overdue_forms
    }

def create_performance_data(data):
    """Create performance data for charts"""
    if data.empty:
        return pd.DataFrame()
    
    dept_stats = data.groupby("name_dept").agg({
        "id_x": "count",
        "wf_done": "sum"
    }).reset_index()
    
    dept_stats.columns = ["Department", "Total", "Completed"]
    dept_stats["Pending"] = dept_stats["Total"] - dept_stats["Completed"]
    dept_stats["Completion_Rate"] = (dept_stats["Completed"] / dept_stats["Total"] * 100).round(1)
    
    return dept_stats.sort_values("Total", ascending=False)

def create_timeline_data(data):
    """Create timeline data for charts"""
    if data.empty:
        return pd.DataFrame()
    
    # Daily form creation
    daily_created = data.groupby("create_date").size().reset_index(name="Created")
    daily_created.rename(columns={"create_date": "Date"}, inplace=True)
    
    # Daily form completion
    completed_data = data[data["wf_done"] == 1]
    if not completed_data.empty:
        daily_completed = completed_data.groupby("done_date").size().reset_index(name="Completed")
        daily_completed.rename(columns={"done_date": "Date"}, inplace=True)
        timeline_data = pd.merge(daily_created, daily_completed, on="Date", how="outer").fillna(0)
    else:
        timeline_data = daily_created.copy()
        timeline_data["Completed"] = 0
    
    return timeline_data.sort_values("Date")

def create_form_distribution_data(data):
    """Create form distribution data for charts"""
    if data.empty:
        return pd.DataFrame()
    
    form_stats = data.groupby("name_form_type").agg({
        "id_x": "count",
        "wf_done": "sum"
    }).reset_index()
    
    form_stats.columns = ["Form_Type", "Total", "Completed"]
    form_stats["Pending"] = form_stats["Total"] - form_stats["Completed"]
    
    return form_stats.sort_values("Total", ascending=False).head(10)

def filter_data(data, selected_department, selected_form_type, selected_date_range):
    """Filter data based on selections"""
    filtered_data = data.copy()

    if selected_department != "All":
        filtered_data = filtered_data[filtered_data["name_dept"] == selected_department]

    if selected_form_type != "All":
        filtered_data = filtered_data[filtered_data["name_form_type"] == selected_form_type]

    if selected_date_range and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        filtered_data = filtered_data[
            (filtered_data["create_date"] >= start_date) &
            (filtered_data["create_date"] <= end_date)
        ]

    return filtered_data

def main():
    # Header
    st.markdown("""
    <div class="header-container">
        <h1>📊 EDMS Workflow Dashboard</h1>
        <h3>Real-time Workflow Analytics & Performance Monitoring</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Load data
    with st.spinner("Loading data from database..."):
        report_data,form_name = load_data()
    
    if report_data.empty:
        st.error("No data available. Please check your database connection.")
        return
    
    # Sidebar controls
    with st.sidebar:
        st.markdown("## 🔧 Dashboard Controls")
        
        # Add some styling for sidebar
        st.markdown("""
        <style>
        .sidebar .sidebar-content {
            background-color: #f8f9fa;
        }
        
        /* Ensure sidebar text is visible */
        .sidebar .element-container {
            color: white;
        }
        
        /* Sidebar labels should be white */
        .sidebar .stSelectbox label,
        .sidebar .stDateInput label {
            color: white !important;
            font-weight: 600;
        }
        
        /* Style sidebar selectbox specifically */
        .sidebar .stSelectbox > div > div {
            background-color: white !important;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        
        .sidebar .stSelectbox > div > div > div {
            color: #333333 !important;
        }
        
        .sidebar .stDateInput > div > div {
            background-color: white !important;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Initialize session state for filters
        if 'dept_index' not in st.session_state:
            st.session_state.dept_index = 0
        if 'form_type_index' not in st.session_state:
            st.session_state.form_type_index = 0
        if 'clear_counter' not in st.session_state:
            st.session_state.clear_counter = 0
        if 'selected_date_range' not in st.session_state:
            # Calculate default date range
            min_date = report_data["create_date"].min()
            max_date = report_data["create_date"].max()
            today = dt.date.today()
            start_of_week = today - dt.timedelta(days=today.weekday())
            default_start = max(start_of_week, min_date)
            default_end = min(today, max_date)
            st.session_state.selected_date_range = (default_start, default_end)

        # Clear all filters button
        if st.button("🧹 Clear All Filters", key="clear_filters_btn"):
            st.session_state.dept_index = 0
            st.session_state.form_type_index = 0
            st.session_state.clear_counter += 1
            # Reset date range to full data range
            min_date = report_data["create_date"].min()
            max_date = report_data["create_date"].max()
            st.session_state.selected_date_range = (min_date, max_date)
            st.rerun()

        # Department filter
        departments = ["All"] + sorted(report_data["name_dept"].unique())
        selected_department = st.selectbox(
            "📍 Select Department",
            departments,
            index=st.session_state.dept_index
        )
        st.session_state.dept_index = departments.index(selected_department)

        # Form type filter - filtered by selected department
        if selected_department == "All":
            available_form_types = report_data["name_form_type"].unique()
        else:
            dept_data = report_data[report_data["name_dept"] == selected_department]
            available_form_types = dept_data["name_form_type"].unique()

        form_types = ["All"] + sorted(available_form_types)

        # Reset form type index if department changed
        if 'previous_department' not in st.session_state:
            st.session_state.previous_department = selected_department
        if st.session_state.previous_department != selected_department:
            st.session_state.form_type_index = 0
            st.session_state.previous_department = selected_department
            st.rerun()

        # Ensure form_type_index is valid for current form_types
        if st.session_state.form_type_index >= len(form_types):
            st.session_state.form_type_index = 0
        selected_form_type = st.selectbox(
            "📄 Select Form Type",
            form_types,
            index=st.session_state.form_type_index
        )
        st.session_state.form_type_index = form_types.index(selected_form_type)

        # Date range filter
        min_date = report_data["create_date"].min()
        max_date = report_data["create_date"].max()

        selected_date_range = st.date_input(
            "📅 Select Date Range",
            value=st.session_state.selected_date_range,
            # min_value=min_date,
            max_value=max_date,
            key="date_selector"
        )
        st.session_state.selected_date_range = selected_date_range

        if st.button("🔄 Refresh Data", key="refresh_btn"):
            st.cache_data.clear()
            st.rerun()
        
        # Data info
        st.markdown("---")
        st.markdown("**📊 Data Overview**")
        st.info(f"Total records: {len(report_data):,}")
        st.info(f"Date range: {min_date} to {max_date}")
        st.info(f"Departments: {len(departments)-1}")
        st.info(f"Form types: {len(form_types)-1}")
    
    # Filter data
    filtered_data = filter_data(report_data, selected_department, selected_form_type, selected_date_range)

    # Filter data for unique forms count (excluding date filter)
    def filter_data_no_date(data, selected_department, selected_form_type):
        """Filter data based on department and form type only (no date filter)"""
        filtered_data = data.copy()

        if selected_department != "All":
            filtered_data = filtered_data[filtered_data["name_dept"] == selected_department]

        if selected_form_type != "All":
            filtered_data = filtered_data[filtered_data["name_form_type"] == selected_form_type]

        return filtered_data

    filtered_data_no_date = filter_data_no_date(form_name, selected_department, selected_form_type)

    # KPI Metrics
    kpis = create_kpi_metrics(filtered_data)

    # Calculate total unique forms from filtered data (excluding date filter)
    total_unique_forms = len(filtered_data_no_date['name'].unique()) if not filtered_data_no_date.empty else 0

    # Display KPIs
    col_header1, col_header2 = st.columns([6, 1])
    with col_header1:
        st.markdown("### 📈 Key Performance Indicators")
    with col_header2:
        # Help button for metrics explanation
        if 'show_help' not in st.session_state:
            st.session_state.show_help = False
        
        if st.button("❓ Help", key="metrics_help"):
            st.session_state.show_help = True
    
    # Modal container for help
    if st.session_state.show_help:
        # Create a modal container using Streamlit's layout
        # Overlay
        st.markdown("""
        <div style="
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
        ">
        </div>
        """, unsafe_allow_html=True)
        
        # Modal content
        st.markdown("""
        <div style="
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background-color: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            z-index: 10000;
            max-width: 600px;
            width: 80%;
            max-height: 80vh;
            overflow-y: auto;
        ">
        """, unsafe_allow_html=True)
        
        # Modal header
        st.markdown("<h3 style='margin-top: 0;'>💡 Metrics Explanation</h3>", unsafe_allow_html=True)
        
        # Metrics explanations
            # Metrics explanations
        st.markdown("""
            **📋 Total Forms:** Total number of forms in the system
            
            **✅ Completed:** Number of forms that have been completed successfully
            
            **⏳ Pending:** Number of forms that are still in progress/waiting to be completed
            
            **📊 Completion Rate:** Percentage of forms completed out of total forms
            
            **⏱️ Avg Process Time:** Average time taken to complete a form (in days)
            
            **🚨 Overdue:** Number of forms that are past their deadline and not yet completed
            
            **📝 Based Forms Created:** Number of unique form templates that have been created
            """)
            
            # Close button
        st.markdown("<hr style='margin-top: 1rem; margin-bottom: 1rem;'>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center; margin-top: 1rem;'><button style='padding: 8px 16px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer;' onclick='window.parent.document.querySelector(\"button[data-testid='stMarkdownContainer'] > div > button[key='close_modal_help']\").click();'>Close</button></div>", unsafe_allow_html=True)
            
        st.markdown("</div>", unsafe_allow_html=True)
            
            # Actual close button (hidden but functional)
        if st.button("Close", key="close_modal_help", type="secondary"):
                st.session_state.show_help = False
                st.rerun()
    
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    
    with col1:
        st.metric(
            label="📋 Total Forms",
            value=f"{kpis['total_forms']:,}",
            delta=None
        )
    
    with col2:
        st.metric(
            label="✅ Completed",
            value=f"{kpis['completed_forms']:,}",
            delta=f"{kpis['completion_rate']}%"
        )
    
    with col3:
        st.metric(
            label="⏳ Pending",
            value=f"{kpis['pending_forms']:,}",
            delta=None
        )
    
    with col4:
        st.metric(
            label="📊 Completion Rate",
            value=f"{kpis['completion_rate']}%",
            delta=None
        )
    
    with col5:
        st.metric(
            label="⏱️ Avg Process Time",
            value=f"{kpis['avg_processing_time']:.1f} days",
            delta=None
        )
    
    with col6:
        st.metric(
            label="🚨 Overdue",
            value=f"{kpis['overdue_forms']:,}",
            delta=None,
            delta_color="inverse"
        )

    with col7:
        st.metric(
            label="📝 Based Forms Created",
            value=f"{total_unique_forms:,}",
            delta=None
        )
    
    # Charts Section
    st.markdown("---")
    st.markdown("### 📊 Performance Analytics")
    
    # Department Performance Chart
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🏢 Department Performance Overview")
        performance_data = create_performance_data(filtered_data)
        
        if not performance_data.empty:
            fig = px.bar(
                performance_data,
                x="Department",
                y=["Completed", "Pending"],
                title="Forms by Department Status",
                color_discrete_map={
                    "Completed": "#28a745",
                    "Pending": "#dc3545"
                },
                height=400
            )
            fig.update_layout(
                xaxis_tickangle=-45,
                showlegend=True,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, width=True)
        else:
            st.info("No data available for the selected filters.")
    
    with col2:
        st.markdown("#### 📅 Daily Activity Timeline")
        timeline_data = create_timeline_data(filtered_data)
        
        if not timeline_data.empty:
            fig = px.line(
                timeline_data,
                x="Date",
                y=["Created", "Completed"],
                title="Daily Form Creation vs Completion",
                color_discrete_map={
                    "Created": "#007bff",
                    "Completed": "#28a745"
                },
                height=400
            )
            fig.update_layout(
                showlegend=True,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, width=True)
        else:
            st.info("No timeline data available for the selected filters.")
    
    # Form Distribution Chart
    st.markdown("#### 📋 Top 10 Form Types by Volume")
    form_distribution_data = create_form_distribution_data(filtered_data)
    
    if not form_distribution_data.empty:
        fig = px.bar(
            form_distribution_data,
            x="Form_Type",
            y=["Completed", "Pending"],
            title="Form Types Distribution",
            color_discrete_map={
                "Completed": "#28a745",
                "Pending": "#ffc107"
            },
            height=400
        )
        fig.update_layout(
            xaxis_tickangle=-45,
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig, width=True)
    else:
        st.info("No form distribution data available for the selected filters.")
    
    # Additional Analytics
    if not filtered_data.empty:
        st.markdown("---")
        st.markdown("### 📋 Detailed Data Table")
        
        # Data table with key columns
        display_columns = ["name",
            "name_form_type", "name_dept", "wf_status", "date_create", 
            "wf_date_done", "wf_dead_line", "wf_done"
        ]
        
        display_data = filtered_data[display_columns].copy()
        display_data.columns = ["Form Name",
            "Form Type", "Department", "Status", "Created", 
            "Completed", "Deadline", "Done"
        ]
        
        st.dataframe(
            display_data,
            width=True,
            height=400
        )
        
        # Download button
        csv = filtered_data.to_csv(index=False)
        st.download_button(
            label="📥 Download Data as CSV",
            data=csv,
            file_name=f"edms_data_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
