#!/usr/bin/env python3

import argparse
import joblib
import sys
from pathlib import Path
import email
from email import policy
from typing import List

def extract_email_body(file_path: Path) -> str:
    """Extracts the plain text body from an email file."""
    try:
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/plain':
                    body = part.get_content()
                    break
        else:
            body = msg.get_content()
        return body
    except Exception as e:
        sys.stderr.write(f"Error processing {file_path}: {e}\n")
        return ""

def main():
    parser = argparse.ArgumentParser(description="Predict tags for email files using a trained model.")
    parser.add_argument("--model", required=True, help="Path to the trained model file.")
    parser.add_argument("mail_files", nargs='+', type=Path, help="Paths to the email files to classify.")
    args = parser.parse_args()

    try:
        model_data = joblib.load(args.model)
        vectorizer = model_data['vectorizer']
        classifier = model_data['classifier']
        tag_list = model_data['tags']
    except FileNotFoundError:
        sys.stderr.write(f"Error: Model file not found at {args.model}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error loading model: {e}\n")
        sys.exit(1)

    for mail_file in args.mail_files:
        if not mail_file.exists():
            sys.stderr.write(f"Warning: Mail file not found at {mail_file}. Skipping.\n")
            continue
            
        body = extract_email_body(mail_file)
        if not body:
            continue

        X_test = [body]
        X_test_vectorized = vectorizer.transform(X_test)
        
        predictions = classifier.predict(X_test_vectorized)
        predicted_tags = [tag_list[i] for i, pred in enumerate(predictions[0]) if pred == 1]
        
        print(f"{mail_file.name} {' '.join(predicted_tags)}")

if __name__ == "__main__":
    main()
