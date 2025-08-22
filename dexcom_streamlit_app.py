import streamlit as st
import requests
import urllib.parse
import os
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
import hashlib
import secrets

# Load environment variables
load_dotenv()

# Configuration - Securely loaded from .env file
CLIENT_ID = os.getenv('DEXCOM_CLIENT_ID')
CLIENT_SECRET = os.getenv('DEXCOM_CLIENT_SECRET')
REDIRECT_URI = os.getenv('DEXCOM_REDIRECT_URI', 'http://localhost:8501')

# API Configuration
BASE_URL = "https://sandbox-api.dexcom.com"  # For testing
# BASE_URL = "https://api.dexcom.com"  # For production - uncomment when ready
AUTH_URL = f"{BASE_URL}/v2/oauth2/login"
TOKEN_URL = f"{BASE_URL}/v2/oauth2/token"
API_URL = f"{BASE_URL}/v2/users/self"

st.set_page_config(
    page_title="Dexcom Data Viewer", 
    page_icon="📊", 
    layout="wide",
    initial_sidebar_state="expanded"
)

def validate_credentials():
    """Validate that required credentials are present"""
    if not CLIENT_ID or not CLIENT_SECRET:
        return False
    return True

def get_auth_url():
    """Generate the authorization URL with state parameter for security"""
    # Generate a random state parameter for CSRF protection
    if 'oauth_state' not in st.session_state:
        st.session_state.oauth_state = secrets.token_urlsafe(32)
    
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'offline_access',
        'state': st.session_state.oauth_state  # CSRF protection
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

def exchange_code_for_token(auth_code, state):
    """Exchange authorization code for access token with state verification"""
    # Verify state parameter to prevent CSRF attacks
    if 'oauth_state' not in st.session_state or state != st.session_state.oauth_state:
        st.error("⚠️ Security error: Invalid state parameter")
        return None
    
    payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        with st.spinner("🔐 Exchanging authorization code for access token..."):
            response = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
    except requests.exceptions.Timeout:
        st.error("⏰ Request timed out. Please try again.")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 400:
            st.error("❌ Invalid authorization code. Please try connecting again.")
        elif response.status_code == 401:
            st.error("🔒 Authentication failed. Please check your app credentials.")
        else:
            st.error(f"🚫 HTTP Error {response.status_code}: {e}")
    except requests.exceptions.RequestException as e:
        st.error(f"🌐 Connection error: {e}")
    return None

def refresh_access_token(refresh_token):
    """Refresh the access token using refresh token"""
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"🔄 Error refreshing token: {e}")
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
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            st.error("🔒 Access token expired. Please refresh your token or reconnect.")
        elif response.status_code == 403:
            st.error("🚫 Access forbidden. Please check your app permissions.")
        else:
            st.error(f"📡 API Error {response.status_code}: {e}")
    except requests.exceptions.RequestException as e:
        st.error(f"🌐 Error fetching glucose data: {e}")
    return None

def plot_glucose_data(data):
    """Create a glucose level chart with enhanced visualization"""
    if not data or 'egvs' not in data:
        st.warning("📊 No glucose data available")
        return
    
    df = pd.DataFrame(data['egvs'])
    if df.empty:
        st.warning("📈 No glucose readings found for the selected period")
        return
    
    # Convert timestamp to datetime
    df['displayTime'] = pd.to_datetime(df['displayTime'])
    df = df.sort_values('displayTime')  # Sort by time
    
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
    
    # Display comprehensive statistics
    col1, col2, col3, col4, col5 = st.columns(5)
    
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
    with col5:
        st.metric("📋 Total Readings", len(df))

def main():
    st.title("🩺 Dexcom Data Viewer")
    st.markdown("### Connect to your Dexcom account to view glucose data")
    
    # Validate credentials
    if not validate_credentials():
        st.error("🔐 **Configuration Error**: Missing Dexcom app credentials")
        st.info("""
        **Setup Instructions:**
        1. Create a `.env` file in your project folder
        2. Add your Dexcom credentials:
        ```
        DEXCOM_CLIENT_ID=your_client_id
        DEXCOM_CLIENT_SECRET=your_client_secret
        DEXCOM_REDIRECT_URI=http://localhost:8501
        ```
        3. Restart the application
        """)
        return
    
    # Initialize session state
    if 'access_token' not in st.session_state:
        st.session_state.access_token = None
    if 'refresh_token' not in st.session_state:
        st.session_state.refresh_token = None
    if 'token_expires_at' not in st.session_state:
        st.session_state.token_expires_at = None
    
    # Check for authorization code in URL
    query_params = st.query_params
    if 'code' in query_params and 'state' in query_params and st.session_state.access_token is None:
        auth_code = query_params['code']
        state = query_params['state']
        
        token_data = exchange_code_for_token(auth_code, state)
        if token_data:
            st.session_state.access_token = token_data.get('access_token')
            st.session_state.refresh_token = token_data.get('refresh_token')
            # Calculate token expiration time
            expires_in = token_data.get('expires_in', 7200)  # Default 2 hours
            st.session_state.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            st.success("✅ Successfully connected to Dexcom!")
            st.balloons()
            # Clear query parameters
            st.query_params.clear()
            st.rerun()
    
    # Main app logic
    if st.session_state.access_token:
        # Check if token is close to expiring
        if st.session_state.token_expires_at:
            time_until_expire = st.session_state.token_expires_at - datetime.now()
            if time_until_expire.total_seconds() < 300:  # Less than 5 minutes
                st.warning("🕐 Your access token will expire soon. Consider refreshing it.")
        
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
        st.sidebar.subheader("🚀 Quick Ranges")
        col1, col2 = st.sidebar.columns(2)
        
        if col1.button("📅 Today"):
            start_date = end_date = datetime.now().date()
            st.rerun()
            
        if col2.button("📅 Last 3 Days"):
            start_date = datetime.now().date() - timedelta(days=3)
            end_date = datetime.now().date()
            st.rerun()
        
        # Token management
        st.sidebar.subheader("🔐 Authentication")
        
        if st.sidebar.button("🔄 Refresh Token"):
            if st.session_state.refresh_token:
                token_data = refresh_access_token(st.session_state.refresh_token)
                if token_data:
                    st.session_state.access_token = token_data.get('access_token')
                    st.session_state.refresh_token = token_data.get('refresh_token')
                    expires_in = token_data.get('expires_in', 7200)
                    st.session_state.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    st.success("✅ Token refreshed successfully!")
                    st.rerun()
        
        if st.sidebar.button("🚪 Disconnect"):
            # Clear all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.info("👋 Disconnected from Dexcom")
            st.rerun()
        
        # Show token expiration info
        if st.session_state.token_expires_at:
            time_left = st.session_state.token_expires_at - datetime.now()
            if time_left.total_seconds() > 0:
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                st.sidebar.info(f"⏰ Token expires in: {hours}h {minutes}m")
        
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
                    st.success(f"✅ Successfully loaded glucose data!")
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
        with st.expander("ℹ️ Setup Information", expanded=True):
            st.markdown("""
            ### 📋 Before you start:
            
            1. **Dexcom Developer Account**: Make sure you have a Dexcom Developer account
            2. **App Configuration**: Your app should be configured with:
               - **Redirect URI**: `http://localhost:8501`
               - **Scopes**: `offline_access`
            3. **Environment**: Currently using **sandbox** environment for testing
            
            ### 🔄 For Production:
            - Change `BASE_URL` to `https://api.dexcom.com` in the code
            - Update your redirect URI for your production domain
            - Ensure your app is approved for production access
            """)

if __name__ == "__main__":
    main()

st.set_page_config(page_title="Dexcom Data Viewer", page_icon="📊", layout="wide")

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
        response = requests.post(TOKEN_URL, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting token: {e}")
        return None

def refresh_access_token(refresh_token):
    """Refresh the access token using refresh token"""
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(TOKEN_URL, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error refreshing token: {e}")
        return None

def get_glucose_data(access_token, start_date, end_date):
    """Fetch glucose data from Dexcom API"""
    headers = {'Authorization': f'Bearer {access_token}'}
    
    params = {
        'startDate': start_date.isoformat(),
        'endDate': end_date.isoformat()
    }
    
    try:
        response = requests.get(f"{API_URL}/egvs", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching glucose data: {e}")
        return None

def plot_glucose_data(data):
    """Create a glucose level chart"""
    if not data or 'egvs' not in data:
        st.warning("No glucose data available")
        return
    
    df = pd.DataFrame(data['egvs'])
    if df.empty:
        st.warning("No glucose readings found for the selected period")
        return
    
    # Convert timestamp to datetime
    df['displayTime'] = pd.to_datetime(df['displayTime'])
    
    # Create the plot
    fig = go.Figure()
    
    # Add glucose line
    fig.add_trace(go.Scatter(
        x=df['displayTime'],
        y=df['value'],
        mode='lines+markers',
        name='Glucose Level',
        line=dict(color='blue', width=2),
        marker=dict(size=4)
    ))
    
    # Add target range
    fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Low (70)")
    fig.add_hline(y=180, line_dash="dash", line_color="red", annotation_text="High (180)")
    fig.add_hrect(y0=70, y1=180, fillcolor="lightgreen", opacity=0.2, annotation_text="Target Range")
    
    fig.update_layout(
        title="Glucose Levels Over Time",
        xaxis_title="Time",
        yaxis_title="Glucose (mg/dL)",
        height=500,
        showlegend=True
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Display statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Average", f"{df['value'].mean():.1f} mg/dL")
    with col2:
        st.metric("Min", f"{df['value'].min()} mg/dL")
    with col3:
        st.metric("Max", f"{df['value'].max()} mg/dL")
    with col4:
        in_range = ((df['value'] >= 70) & (df['value'] <= 180)).sum()
        st.metric("In Range", f"{(in_range/len(df)*100):.1f}%")

def main():
    st.title("🩺 Dexcom Data Viewer")
    st.markdown("Connect to your Dexcom account to view glucose data")
    
    # Check if credentials are configured
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error("Please configure your Dexcom app credentials in the .env file")
        st.info("""
        Create a .env file with:
        ```
        DEXCOM_CLIENT_ID=your_client_id_here
        DEXCOM_CLIENT_SECRET=your_client_secret_here
        DEXCOM_REDIRECT_URI=http://localhost:8501
        ```
        """)
        return
    
    # Initialize session state
    if 'access_token' not in st.session_state:
        st.session_state.access_token = None
    if 'refresh_token' not in st.session_state:
        st.session_state.refresh_token = None
    
    # Check for authorization code in URL
    query_params = st.query_params
    if 'code' in query_params and st.session_state.access_token is None:
        auth_code = query_params['code']
        st.info("Exchanging authorization code for access token...")
        
        token_data = exchange_code_for_token(auth_code)
        if token_data:
            st.session_state.access_token = token_data.get('access_token')
            st.session_state.refresh_token = token_data.get('refresh_token')
            st.success("Successfully connected to Dexcom!")
            st.rerun()
    
    # Main app logic
    if st.session_state.access_token:
        st.success("✅ Connected to Dexcom")
        
        # Date range selection
        st.sidebar.header("Data Selection")
        end_date = st.sidebar.date_input("End Date", datetime.now().date())
        start_date = st.sidebar.date_input("Start Date", end_date - timedelta(days=1))
        
        if st.sidebar.button("Refresh Token"):
            if st.session_state.refresh_token:
                token_data = refresh_access_token(st.session_state.refresh_token)
                if token_data:
                    st.session_state.access_token = token_data.get('access_token')
                    st.session_state.refresh_token = token_data.get('refresh_token')
                    st.success("Token refreshed successfully!")
        
        if st.sidebar.button("Disconnect"):
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.rerun()
        
        # Fetch and display data
        if st.button("Load Glucose Data"):
            with st.spinner("Fetching glucose data..."):
                glucose_data = get_glucose_data(
                    st.session_state.access_token,
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time())
                )
                
                if glucose_data:
                    plot_glucose_data(glucose_data)
                    
                    # Show raw data option
                    if st.checkbox("Show Raw Data"):
                        st.json(glucose_data)
    
    else:
        st.info("Click the button below to connect to your Dexcom account")
        auth_url = get_auth_url()
        st.markdown(f"""
        <a href="{auth_url}" target="_self">
            <button style="background-color:#4CAF50;border:none;color:white;padding:15px 32px;text-align:center;text-decoration:none;display:inline-block;font-size:16px;margin:4px 2px;cursor:pointer;border-radius:4px;">
                Connect to Dexcom
            </button>
        </a>
        """, unsafe_allow_html=True)
        
        st.markdown("### Setup Instructions:")
        st.markdown("""
        1. Go to [Dexcom Developer Portal](https://developer.dexcom.com/)
        2. Create an app and get your Client ID and Secret
        3. Set your redirect URI to: `http://localhost:8501`
        4. Add credentials to your .env file
        """)

if __name__ == "__main__":
    main()