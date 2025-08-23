import streamlit as st
import requests
import urllib.parse
import os
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go

# Configuration - With your credentials hardcoded
CLIENT_ID = 'GGcQog7pK7JJE7IdAQneV9KJ3sL9StNl'
CLIENT_SECRET = 'ptYnq85tqEc5BJm7'
REDIRECT_URI = 'https://dexcom-2zqv2mhmkwgqqedzkjvfeq.streamlit.app'

# API Configuration
BASE_URL = "https://sandbox-api.dexcom.com"  # For testing
AUTH_URL = f"{BASE_URL}/v2/oauth2/login"
TOKEN_URL = f"{BASE_URL}/v2/oauth2/token"
API_URL = f"{BASE_URL}/v2/users/self"

st.set_page_config(
    page_title="Dexcom Data Viewer", 
    page_icon="📊", 
    layout="wide"
)

def get_auth_url():
    """Generate the authorization URL"""
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'offline_access'
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

def exchange_code_for_token(auth_code):
    """Exchange authorization code for access token"""
    payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error exchanging code for token: {e}")
        return None

def get_glucose_data(access_token, start_date, end_date):
    """Fetch glucose data from Dexcom API"""
    headers = {'Authorization': f'Bearer {access_token}'}
    
    params = {
        'startDate': start_date.isoformat(),
        'endDate': end_date.isoformat()
    }
    
    try:
        response = requests.get(f"{API_URL}/egvs", headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching glucose data: {e}")
        return None

def plot_glucose_data(data):
    """Create a glucose level chart"""
    if not data or 'egvs' not in data:
        st.warning("📊 No glucose data available")
        return
    
    df = pd.DataFrame(data['egvs'])
    if df.empty:
        st.warning("📈 No glucose readings found for the selected period")
        return
    
    # Convert timestamp to datetime
    df['displayTime'] = pd.to_datetime(df['displayTime'])
    df = df.sort_values('displayTime')
    
    # Create the plot
    fig = go.Figure()
    
    # Color code points based on glucose ranges
    colors = []
    for value in df['value']:
        if value < 70:
            colors.append('red')      # Low
        elif value > 180:
            colors.append('orange')   # High
        else:
            colors.append('green')    # In range
    
    # Add glucose line
    fig.add_trace(go.Scatter(
        x=df['displayTime'],
        y=df['value'],
        mode='lines+markers',
        name='Glucose Level',
        line=dict(color='blue', width=2),
        marker=dict(size=6, color=colors, line=dict(width=1, color='white'))
    ))
    
    # Add target range bands
    fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Low (70 mg/dL)")
    fig.add_hline(y=180, line_dash="dash", line_color="orange", annotation_text="High (180 mg/dL)")
    fig.add_hrect(y0=70, y1=180, fillcolor="lightgreen", opacity=0.2, annotation_text="Target Range")
    
    fig.update_layout(
        title="📊 Glucose Levels Over Time",
        xaxis_title="Time",
        yaxis_title="Glucose (mg/dL)",
        height=500,
        showlegend=True,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Display statistics
    col1, col2, col3, col4 = st.columns(4)
    
    avg_glucose = df['value'].mean()
    min_glucose = df['value'].min()
    max_glucose = df['value'].max()
    in_range_count = ((df['value'] >= 70) & (df['value'] <= 180)).sum()
    time_in_range = (in_range_count / len(df) * 100) if len(df) > 0 else 0
    
    with col1:
        st.metric("📊 Average", f"{avg_glucose:.1f} mg/dL")
    with col2:
        st.metric("📉 Minimum", f"{min_glucose} mg/dL")
    with col3:
        st.metric("📈 Maximum", f"{max_glucose} mg/dL")
    with col4:
        st.metric("🎯 Time in Range", f"{time_in_range:.1f}%")

def main():
    st.title("🩺 Dexcom Data Viewer")
    st.markdown("### Connect to your Dexcom account to view glucose data")
    
    # Initialize session state
    if 'access_token' not in st.session_state:
        st.session_state.access_token = None
    if 'refresh_token' not in st.session_state:
        st.session_state.refresh_token = None
    if 'processing_callback' not in st.session_state:
        st.session_state.processing_callback = False
    
    # 🔧 FIXED: Handle OAuth callback without redirect loop
    query_params = st.query_params
    
    # Check if we're processing a callback and have a code
    if 'code' in query_params and not st.session_state.processing_callback and st.session_state.access_token is None:
        st.session_state.processing_callback = True
        
        # Clear query params immediately
        auth_code = query_params['code']
        st.query_params.clear()
        
        # Show processing message
        st.info("🔄 Processing your Dexcom authentication...")
        
        # Exchange code for token
        token_data = exchange_code_for_token(auth_code)
        
        if token_data:
            st.session_state.access_token = token_data.get('access_token')
            st.session_state.refresh_token = token_data.get('refresh_token')
            st.success("✅ Successfully connected to Dexcom!")
            st.balloons()
        else:
            st.error("❌ Failed to connect to Dexcom. Please try again.")
        
        st.session_state.processing_callback = False
        st.rerun()
    
    # Main app logic
    if st.session_state.access_token:
        st.success("✅ Connected to Dexcom")
        
        # Sidebar controls
        st.sidebar.header("🎛️ Data Controls")
        
        # Date range selection
        end_date = st.sidebar.date_input("📅 End Date", datetime.now().date())
        start_date = st.sidebar.date_input("📅 Start Date", end_date - timedelta(days=1))
        
        # Validate date range
        if start_date > end_date:
            st.sidebar.error("❌ Start date must be before end date")
            return
        
        # Quick date range buttons
        col1, col2 = st.sidebar.columns(2)
        
        if col1.button("📅 Today"):
            st.query_params.clear()
            st.rerun()
            
        if col2.button("📅 Last 3 Days"):
            st.query_params.clear()
            st.rerun()
        
        # Disconnect button
        if st.sidebar.button("🚪 Disconnect"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
        
        # Main content area
        st.header("📊 Glucose Data Dashboard")
        
        # Fetch and display data
        if st.button("📡 Load Glucose Data", type="primary"):
            with st.spinner("🔄 Fetching glucose data from Dexcom..."):
                glucose_data = get_glucose_data(
                    st.session_state.access_token,
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time())
                )
                
                if glucose_data:
                    st.success("✅ Successfully loaded glucose data!")
                    plot_glucose_data(glucose_data)
                    
                    # Additional data insights
                    if 'egvs' in glucose_data and glucose_data['egvs']:
                        with st.expander("📋 Raw Data", expanded=False):
                            df = pd.DataFrame(glucose_data['egvs'])
                            df['displayTime'] = pd.to_datetime(df['displayTime'])
                            st.dataframe(df, use_container_width=True)
                        
                        # Download option
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="💾 Download Data as CSV",
                            data=csv,
                            file_name=f"glucose_data_{start_date}_to_{end_date}.csv",
                            mime="text/csv"
                        )
    
    else:
        # Authentication flow
        st.info("🔗 Click the button below to connect to your Dexcom account")
        
        auth_url = get_auth_url()
        
        # Create a nice-looking button
        st.markdown(f"""
        <div style="text-align: center; margin: 2rem 0;">
            <a href="{auth_url}" target="_self" style="text-decoration: none;">
                <button style="
                    background: linear-gradient(45deg, #4CAF50, #45a049);
                    border: none;
                    color: white;
                    padding: 15px 40px;
                    text-align: center;
                    text-decoration: none;
                    display: inline-block;
                    font-size: 18px;
                    margin: 4px 2px;
                    cursor: pointer;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                    transition: all 0.3s;
                " onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
                    🔗 Connect to Dexcom
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)
        
        # Setup information
        with st.expander("ℹ️ App Information", expanded=False):
            st.markdown("""
            ### 📋 About this app:
            
            - **Secure OAuth**: Uses Dexcom's official authentication
            - **Your data**: Only you can access your glucose readings
            - **Sandbox mode**: Currently using test environment
            - **Privacy**: No data is stored permanently
            
            ### 🔒 Security:
            - All communication is encrypted
            - Credentials are handled securely
            - You can disconnect anytime
            """)

if __name__ == "__main__":
    main()