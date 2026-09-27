from google.cloud import firestore
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import os


def get_db_connection():
    print("Connecting to Firestore database...")
    
    try:
        # Check if secrets exist
        if "firebase" not in os.environ:
            error_msg = "❌ Firebase secrets not found in os.environ"
            print(error_msg)
            # st.error(error_msg)
            return None
            
        print("Firebase secrets found")
        
        firebase_credentials = {
            "type": os.environ["type"],
            "project_id": os.environ["project_id"],
            "private_key_id": os.environ["private_key_id"],
            "private_key": os.environ["private_key"].replace("\\n", "\n"),
            "client_email": os.environ["client_email"],
            "client_id": os.environ["client_id"],
            "auth_uri": os.environ["auth_uri"],
            "token_uri": os.environ["token_uri"],
            "auth_provider_x509_cert_url": os.environ["auth_provider_x509_cert_url"],
            "client_x509_cert_url": os.environ["client_x509_cert_url"],
            "universe_domain": os.environ["universe_domain"],
        }
  # Convert secrets to dict

        # Initialize Firebase if not already initialized
        if not firebase_admin._apps:
            print("Initializing Firebase app...")
            cred = credentials.Certificate(firebase_credentials)  # Use dictionary directly
            firebase_admin.initialize_app(cred)
            print("Firebase app initialized successfully")
        else:
            print("Firebase app already initialized")

        # Connect to Firestore
        print("Creating Firestore client...")
        db = firestore.client()
        print("Firestore client created successfully")
        return db

    except Exception as e:
        error_msg = f"❌ Error connecting to Firestore: {e}"
        print(error_msg)
        # st.error(error_msg)
        return None


def init_database():
    """
    Initialize the database with the required tables
    """
    try:
        # Connect to Firestore
        print("Creating Firestore client...")
        db = firestore.client()
        print("Firestore client created successfully")
        return db

    except Exception as e:
        error_msg = f"❌ Error connecting to Firestore: {e}"
        print(error_msg)
        # st.error(error_msg)
        return None
