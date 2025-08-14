#!/usr/bin/env python3

import argparse
import joblib
from pathlib import Path
import email
from email import policy
from typing import List, Dict

def extract_email_text(file_path: Path) -> str:
    """
    Extracts the subject, from, to, and plain text body from an email file
    to use for classification.
    """
    try:
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        subject = msg.get("Subject", "")
        from_field = msg.get("From", "")
        to_field = msg.get("To", "")
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/plain':
                    body = part.get_content()
                    break
        else:
            body = msg.get_content()
            
        return f"Subject: {subject}\nFrom: {from_field}\nTo: {to_field}\n\n{body}"
    except Exception as e:
        return ""

def load_tagged_mails(maildir: Path, tags_file: Path) -> Dict[str, List[str]]:
    """Loads tagged mail data from the maildir and a tag file."""
    tagged_data = {}
    with open(tags_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            mail_file = parts[0]
            tags = parts[1:]
            if tags:
                tagged_data[mail_file] = tags
    return tagged_data

def main():
    parser = argparse.ArgumentParser(description="Retrain an existing AI classifier with new data.")
    parser.add_argument("--model", required=True, help="Path to the model file to update.")
    parser.add_argument("--maildir", required=True, type=Path, help="Path to the directory containing email files.")
    parser.add_argument("--tags", required=True, type=Path, help="Path to the file with new tag data.")
    args = parser.parse_args()

    try:
        existing_model_data = joblib.load(args.model)
        existing_vectorizer = existing_model_data['vectorizer']
        existing_classifier = existing_model_data['classifier']
        existing_tags = set(existing_model_data['tags'])
    except FileNotFoundError:
        print(f"Model file not found at {args.model}. Starting a full training run instead.")
        # Fallback to training from scratch if no model exists
        return

    print("Loading existing and new data...")
    new_tagged_data = load_tagged_mails(args.maildir, args.tags)
    
    X_data = []
    y_data_map = {}
    
    combined_data = {**new_tagged_data}
    all_tags = set(existing_tags)
    for filename, tags in combined_data.items():
        all_tags.update(tags)
        mail_path = args.maildir / filename
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
