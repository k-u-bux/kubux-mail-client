#!/usr/bin/env python3

import argparse
import joblib
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
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
        
        # Extract headers, handling potential missing values
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
        
        # Combine headers and body into a single string for classification
        return f"Subject: {subject}\nFrom: {from_field}\nTo: {to_field}\n\n{body}"
    except Exception as e:
        # In case of any parsing error, return an empty string
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
    parser = argparse.ArgumentParser(description="Train a multi-label AI classifier for email tagging.")
    parser.add_argument("--model", required=True, help="Path to the output model file.")
    parser.add_argument("--maildir", required=True, type=Path, help="Path to the directory containing email files.")
    parser.add_argument("--tags", required=True, type=Path, help="Path to the file with mail filenames and their tags.")
    args = parser.parse_args()

    print("Loading data...")
    tagged_data = load_tagged_mails(args.maildir, args.tags)
    
    X_train = []
    y_train_map = {}
    all_tags = set()
    
    for filename, tags in tagged_data.items():
        mail_path = args.maildir / filename
        if mail_path.exists():
            text = extract_email_text(mail_path)
            if text:
                X_train.append(text)
                y_train_map[filename] = tags
                all_tags.update(tags)
    
    tag_list = sorted(list(all_tags))
    
    print(f"Found {len(X_train)} emails and {len(tag_list)} unique tags.")
    
    # Create multi-label targets
    y_train = []
    for filename in tagged_data.keys():
        row = [1 if tag in y_train_map.get(filename, []) else 0 for tag in tag_list]
        y_train.append(row)
    
    print("Vectorizing email content...")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words='english', min_df=5, max_df=0.9)
    X_train_vectorized = vectorizer.fit_transform(X_train)

    print("Training model...")
    classifier = OneVsRestClassifier(LinearSVC(C=1.0, dual=True, max_iter=1000))
    classifier.fit(X_train_vectorized, y_train)

    print(f"Saving model to {args.model}...")
    model_data = {
        'vectorizer': vectorizer,
        'classifier': classifier,
        'tags': tag_list
    }
    joblib.dump(model_data, args.model)
    print("Training complete.")

if __name__ == "__main__":
    main()
