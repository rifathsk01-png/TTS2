import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")

if FIREBASE_CREDENTIALS:
    cred_dict = json.loads(FIREBASE_CREDENTIALS)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
else:
    db = None

def save_user(user_id, data):
    if db:
        db.collection("users").document(user_id).set(data)
