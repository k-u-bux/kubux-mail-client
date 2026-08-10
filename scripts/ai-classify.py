#!/usr/bin/env python3

import sys
from pathlib import Path
import argparse

import joblib

from config import config
from common import extract_email_text

def main():
    parser = argparse.ArgumentParser(description="Predict tags for email files using a trained model.")
    parser.add_argument("--model", default=config.get_model(), help="Path to the trained model file.")
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

        text = extract_email_text(mail_file)
        if not text:
            continue

        test_vectorized = vectorizer.transform( [text] )

        predictions = classifier.predict( test_vectorized )
        predicted_tags = [tag_list[i] for i, pred in enumerate(predictions[0]) if pred == 1]

        classified_mail = f"{mail_file.name} {' '.join(predicted_tags)}"
        print( classified_mail )
        # print( classified_mail, file=sys.stderr )

if __name__ == "__main__":
    main()

# end of file
