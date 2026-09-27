import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

# Load Firebase credentials from Streamlit secrets
firebase_credentials = {
    "type": os.environ["FIREBASE_TYPE"],
    "project_id": os.environ["FIREBASE_PROJECT_ID"],
    "private_key_id": os.environ["FIREBASE_PRIVATE_KEY_ID"],
    "private_key": os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": os.environ["FIREBASE_CLIENT_EMAIL"],
    "client_id": os.environ["FIREBASE_CLIENT_ID"],
    "auth_uri": os.environ["FIREBASE_AUTH_URI"],
    "token_uri": os.environ["FIREBASE_TOKEN_URI"],
    "auth_provider_x509_cert_url": os.environ["FIREBASE_AUTH_PROVIDER_CERT_URL"],
    "client_x509_cert_url": os.environ["FIREBASE_CLIENT_CERT_URL"],
    "universe_domain": os.environ["FIREBASE_UNIVERSE_DOMAIN"],
}


# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_credentials)  # Use dictionary directly
    firebase_admin.initialize_app(cred)

# Connect to Firestore
db = firestore.client()

# Example: Add a new order
def add_order(order_id, sku, quantity,status,picked_by,validated_by,platform,created_at,updated_at,dispatch_date):

    doc_ref = db.collection("orders").document(order_id)
    doc_ref.set({
        "sku": sku,
        "quantity": quantity,
        "status": status,
        "picked_by": picked_by,
        "validated_by": validated_by,
        "platform": platform,
        "created_at": created_at,
        "updated_at": updated_at,
        "dispatch_date": dispatch_date
    })
    return True

# Example: Fetch all orders
def get_orders():
    orders = db.collection("orders").stream()
    return [{order.id: order.to_dict()} for order in orders]

def get_sku_from_order(order_id):
    doc_ref = db.collection("orders").document(order_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("sku")
    else:
        return None
