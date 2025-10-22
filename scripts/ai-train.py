#!/usr/bin/env python3

import argparse
import joblib
import subprocess
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.multiclass import OneVsRestClassifier
import email
from email import policy
from typing import List, Dict
from notmuch import notmuch_show, flatten_message_tree, find_matching_messages
from config import config 


def ignore(title, message):
    pass

def filter(tag):
    if tag.startswith("$"):
        return False
    if tag == "inbox":
        return False
    if tag == "attachment":
        return False
    if tag == "unread":
        return False
    if tag == "todo":
        return False
    if tag == "open":
        return False
    if tag == "done":
        return False
    if tag == "read":
        return False
    if tag == "mark_for_training":
        return False
    return True

def extract_email_text(file_path: Path) -> str:
    """
    Extracts the subject, from, to, cc, and plain text body from an email file
    to use for classification.
    """
    try:
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        subject = msg.get("Subject", "")
        from_field = msg.get("From", "")
        to_field = msg.get("To", "")
        cc_field = msg.get("Cc", "")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/plain':
                    body = part.get_content()
                    break
        else:
            body = msg.get_content()

        return f"Subject: {subject}\nFrom: {from_field}\nTo: {to_field}\nCc: {cc_field}\n\n{body}"
    except Exception as e:
        return ""

def main():
    parser = argparse.ArgumentParser(description="Retrain an existing AI classifier with new data.")
    parser.add_argument("--query", default='tag:$unused and not tag:unread and (tag:spam or not tag:spam)', help="Notmuch query for new training mails.")
    parser.add_argument("--model", default=config.get_model(), help="Path to the model file to update.")
    args = parser.parse_args()

    # for the time being, always start over:
    Path( args.model ).unlink( missing_ok = True )


    # Define model components outside the try block
    vectorizer = None
    classifier = None
    all_tags = set()
    full_training_mode = False

    try:
        # --- Retraining Logic (existing model found) ---
        existing_model_data = joblib.load(args.model)
        vectorizer = existing_model_data['vectorizer']
        classifier = existing_model_data['classifier']
        all_tags = set(existing_model_data['tags'])
        print("Model file found. Entering retraining mode.")
        
        # Load new data based on the query
        new_tagged_data = {}
        messages = find_matching_messages(args.query, ignore)
        for msg in messages:
             tags = [f"{tag}" for tag in msg["tags"] if filter(tag)]
             file = f"{msg["filename"][0]}"
             new_tagged_data[file] = tags
        
    except FileNotFoundError:
        # --- Full Training Logic (no model found) ---
        print(f"Model file not found at {args.model}. Starting a full training run.")
        full_training_mode = True
        
        new_tagged_data = {}
        messages = find_matching_messages(args.query, ignore)
        for msg in messages:
            tags = [f"{tag}" for tag in msg["tags"] if filter(tag)]
            file = f"{msg["filename"][0]}"
            new_tagged_data[file] = tags
        
        vectorizer = TfidfVectorizer(ngram_range=(1, 4), stop_words='english', min_df=5, max_df=0.9)
        classifier = OneVsRestClassifier(LinearSVC(C=1.0, dual=True, max_iter=1000))

    # --- Data Preparation and Training (common to both modes) ---
    X_data = []
    y_data_map = {}
    
    # Bug fix: use the maildir argument for the Path object
    for filename, tags in new_tagged_data.items():
        all_tags.update(tags)
        mail_path = Path( filename )
        if mail_path.exists():
            text = extract_email_text(mail_path)
            if text:
                X_data.append(text)
                y_data_map[filename] = tags

    tag_list = sorted(list(all_tags))

    print(f"Found {len(X_data)} emails and {len(tag_list)} unique tags for training.")

    if full_training_mode:
        X_vectorized = vectorizer.fit_transform(X_data)
    else:
        X_vectorized = vectorizer.transform(X_data)

    y_data = []
    for filename in new_tagged_data.keys():
        row = [1 if tag in y_data_map.get(filename, []) else 0 for tag in tag_list]
        y_data.append(row)

    print("Training model...")
    classifier.fit(X_vectorized, y_data)

    print(f"Saving updated model to {args.model}...")
    model_data = {
        'vectorizer': vectorizer,
        'classifier': classifier,
        'tags': tag_list
    }
    joblib.dump(model_data, args.model)
    print("Training complete.")

    print( f"tags = {tag_list}" )

def old_main():
    parser = argparse.ArgumentParser(description="Retrain an existing AI classifier with new data.")
    parser.add_argument("--query", default='tag:$unused and not tag:unread and (tag:spam or not tag:spam)', help="Path to the output model file.")
    parser.add_argument("--model", default=config.get_model(), help="Path to the model file to update.")
    args = parser.parse_args()

    try:
        existing_model_data = joblib.load(args.model)
        existing_vectorizer = existing_model_data['vectorizer']
        existing_classifier = existing_model_data['classifier']
        existing_tags = set(existing_model_data['tags'])
    except FileNotFoundError:
        print(f"Model file not found at {args.model}. Starting a full training run instead.")
        return

    new_tagged_data = {}
    try:
        messages = find_matching_messages(args.query, ignore)
        for msg in messages:
            tags = [f"{tag}" for tag in msg["tags"] if filter(tag)]
            file = f"{msg["filename"][0]}"
            print( f"{file} --> {tags}" )
            new_tagged_data[ file ] = tags
    except Exception as e:
        print(f"{e}")
        pass

    # print( f"pre-existing tags = {existing_tags}" )
    # print( f"{ " or ".join( [ f"tag:{tag}" for tag in existing_tags] ) }" )

    # return

    X_data = []
    y_data_map = {}

    combined_data = {**new_tagged_data}
    all_tags = set(existing_tags)
    for filename, tags in combined_data.items():
        all_tags.update(tags)
        mail_path = Path( filename )
        if mail_path.exists():
            text = extract_email_text(mail_path)
            if text:
                X_data.append(text)
                y_data_map[filename] = tags

    tag_list = sorted(list(all_tags))

    print(f"Found {len(X_data)} emails and {len(tag_list)} unique tags for retraining.")

    X_vectorized = existing_vectorizer.transform(X_data)

    y_data = []
    for filename in combined_data.keys():
        row = [1 if tag in y_data_map.get(filename, []) else 0 for tag in tag_list]
        y_data.append(row)

    print("Re-training model...")
    existing_classifier.fit(X_vectorized, y_data)

    print(f"Saving updated model to {args.model}...")
    model_data = {
        'vectorizer': existing_vectorizer,
        'classifier': existing_classifier,
        'tags': tag_list
    }
    joblib.dump(model_data, args.model)
    print("Retraining complete.")

if __name__ == "__main__":
    main()
