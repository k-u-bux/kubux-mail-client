import sys
import email
from email import policy

def get_message_id_from_file(file_path):
    """
    Parses an email file and returns the Message-ID header value
    without the surrounding angle brackets.

    Args:
        file_path (str): The path to the email file.

    Returns:
        str: The Message-ID value, or None if the header is not found.
    """
    try:
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
            message_id = msg.get('Message-ID')
            if message_id:
                return message_id.strip('<>')
            else:
                return None
                
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An error occurred while parsing the file: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_message_id.py <path_to_email_file>", file=sys.stderr)
        sys.exit(1)
    
    file_path = sys.argv[1]
    message_id = get_message_id_from_file(file_path)
    
    if message_id:
        print(f"{message_id}")
