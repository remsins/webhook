# ui/app.py

import streamlit as st
import requests
import pandas as pd
import uuid
from datetime import datetime
import os

# --- Configuration ---
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
st.set_page_config(page_title="Webhook Service UI", layout="wide")
st.title("Webhook Delivery Service - Minimal UI")

# --- Helper Functions to Interact with API ---

def handle_response(response, success_status=200):
    """Checks response status and returns JSON or None."""
    if response.status_code == success_status:
        try:
            # Handle 204 No Content specifically
            if success_status == 204:
                return True
            return response.json()
        except requests.exceptions.JSONDecodeError:
            st.error("Failed to decode JSON response from API.")
            return None
    else:
        try:
            detail = response.json().get("detail", "Unknown error")
        except requests.exceptions.JSONDecodeError:
            detail = f"Unknown error (Status code: {response.status_code})"
        st.error(f"API Error ({response.status_code}): {detail}")
        return None

def get_subscriptions():
    """Fetches all subscriptions from the API."""
    try:
        response = requests.get(f"{API_BASE_URL}/subscriptions/")
        return handle_response(response)
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error fetching subscriptions: {e}")
        return None

def create_subscription(target_url, secret=None, events=None):
    """Creates a new subscription."""
    payload = {"target_url": target_url}
    if secret:
        payload["secret"] = secret
    if events:
        # Assuming events are comma-separated string, convert to list
        payload["events"] = [e.strip() for e in events.split(",") if e.strip()]

    try:
        response = requests.post(f"{API_BASE_URL}/subscriptions/", json=payload)
        return handle_response(response, success_status=201)
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error creating subscription: {e}")
        return None

def delete_subscription(sub_id):
    """Deletes a subscription by ID."""
    try:
        # Validate UUID format before sending
        uuid.UUID(sub_id)
        response = requests.delete(f"{API_BASE_URL}/subscriptions/{sub_id}")
        return handle_response(response, success_status=204)
    except ValueError:
        st.error("Invalid Subscription ID format. Please enter a valid UUID.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error deleting subscription: {e}")
        return None

def get_subscription_attempts(sub_id, limit=20):
    """Fetches recent delivery attempts for a subscription."""
    try:
        uuid.UUID(sub_id) # Validate UUID
        response = requests.get(f"{API_BASE_URL}/subscriptions/{sub_id}/attempts?limit={limit}")
        return handle_response(response)
    except ValueError:
        st.error("Invalid Subscription ID format. Please enter a valid UUID.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error fetching attempts: {e}")
        return None

def get_webhook_status(webhook_id):
    """Fetches status and attempts for a specific webhook ID."""
    try:
        uuid.UUID(webhook_id) # Validate UUID
        response = requests.get(f"{API_BASE_URL}/status/{webhook_id}")
        return handle_response(response)
    except ValueError:
        st.error("Invalid Webhook ID format. Please enter a valid UUID.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error fetching webhook status: {e}")
        return None

# --- Streamlit UI Layout ---

tab1, tab2 = st.tabs(["Manage Subscriptions", "View Delivery Status"])

with tab1:
    st.header("Manage Subscriptions")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Existing Subscriptions")
        if st.button("Refresh List"):
            st.experimental_rerun() # Simple way to refresh

        subs_data = get_subscriptions()
        if subs_data:
            if subs_data: # Check if list is not empty
                 # Convert list of dicts to DataFrame for better display
                df_subs = pd.DataFrame(subs_data)
                # Optionally hide or reorder columns
                st.dataframe(df_subs[['id', 'target_url', 'secret', 'events']], use_container_width=True)
            else:
                st.info("No subscriptions found.")
        else:
            st.warning("Could not fetch subscriptions.")

    with col2:
        st.subheader("Create New Subscription")
        with st.form("create_sub_form"):
            new_target_url = st.text_input("Target URL*", help="The URL to send webhooks to.")
            new_secret = st.text_input("Secret (Optional)", type="password", help="Secret key for signature verification.")
            new_events = st.text_input("Events (Optional, comma-separated)", help="e.g., order.created, user.updated")
            submitted_create = st.form_submit_button("Create Subscription")

            if submitted_create:
                if not new_target_url:
                    st.warning("Target URL is required.")
                else:
                    result = create_subscription(new_target_url, new_secret or None, new_events or None)
                    if result:
                        st.success(f"Subscription created successfully! ID: {result.get('id')}")
                        # No automatic rerun here, user can press Refresh List

        st.subheader("Delete Subscription")
        sub_id_to_delete = st.text_input("Subscription ID to Delete", key="delete_sub_id", help="Enter the full UUID.")
        if st.button("Delete Subscription", type="primary"):
            if not sub_id_to_delete:
                st.warning("Please enter a Subscription ID to delete.")
            else:
                 delete_success = delete_subscription(sub_id_to_delete)
                 if delete_success:
                     st.success(f"Subscription {sub_id_to_delete} deleted successfully.")
                     # No automatic rerun here, user can press Refresh List


with tab2:
    st.header("View Delivery Status")

    st.subheader("View by Subscription ID")
    sub_id_for_logs = st.text_input("Subscription ID", key="log_sub_id", help="Enter the UUID of the subscription.")
    log_limit = st.number_input("Limit", min_value=1, max_value=100, value=20, key="log_limit")

    if st.button("Fetch Subscription Attempts", key="fetch_sub_logs"):
        if sub_id_for_logs:
            attempts_data = get_subscription_attempts(sub_id_for_logs, log_limit)
            if attempts_data is not None: # API call might return empty list successfully
                if attempts_data:
                    df_attempts = pd.DataFrame(attempts_data)
                    # Format timestamp for readability
                    df_attempts['timestamp'] = pd.to_datetime(df_attempts['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                    st.dataframe(df_attempts[['timestamp', 'attempt_number', 'outcome', 'status_code', 'error', 'webhook_id']], use_container_width=True)
                else:
                    st.info("No delivery attempts found for this subscription.")
            # Error messages handled within the helper function
        else:
            st.warning("Please enter a Subscription ID.")

    st.divider()

    st.subheader("View by Webhook ID")
    webhook_id_for_status = st.text_input("Webhook ID", key="status_wh_id", help="Enter the UUID returned during ingestion.")

    if st.button("Fetch Webhook Status", key="fetch_wh_status"):
        if webhook_id_for_status:
            status_data = get_webhook_status(webhook_id_for_status)
            if status_data:
                st.metric("Final Outcome", status_data.get('final_outcome', 'N/A'))
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Attempts", status_data.get('total_attempts', 'N/A'))
                col2.metric("Last Status Code", status_data.get('last_status_code', 'N/A'))
                col3.metric("Last Attempt At", pd.to_datetime(status_data.get('last_attempt_at')).strftime('%H:%M:%S UTC') if status_data.get('last_attempt_at') else 'N/A')
                if status_data.get('error'):
                    st.error(f"Last Error: {status_data.get('error')}")

                st.subheader("Recent Attempts for this Webhook")
                if status_data.get('recent_attempts'):
                    df_wh_attempts = pd.DataFrame(status_data['recent_attempts'])
                    df_wh_attempts['timestamp'] = pd.to_datetime(df_wh_attempts['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                    st.dataframe(df_wh_attempts[['timestamp', 'attempt_number', 'outcome', 'status_code', 'error']], use_container_width=True)
                else:
                    st.info("No attempt details found.")
            # Error messages handled within the helper function
        else:
            st.warning("Please enter a Webhook ID.")

