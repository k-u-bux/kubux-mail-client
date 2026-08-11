import json
import sys

def format_email_address(name, email):
    """
    Formats an email address string in the style of email.message.get("From").
    """
    if name:
        # If a name is provided, format it as "Name" <email>
        return f'{name} <{email}>'
    else:
        # If no name, just return the email
        return f"<{email}>"

def process_json_stream():
    email_addresses = []
    
    # Read the input line by line
    for line in sys.stdin:
        # Check if the line starts with '{' to identify a new JSON object
        if line.strip().startswith('{'):
            json_obj_str = line.strip()
            # Read the rest of the object until '}' is found
            for next_line in sys.stdin:
                json_obj_str += next_line.strip()
                if next_line.strip() == '}':
                    break
            
            try:
                # Parse the complete JSON object
                data = json.loads(json_obj_str)
                name = data.get("name")
                email = data.get("email")

                if email:
                    # Format and append the email address
                    formatted_address = format_email_address(name, email)
                    email_addresses.append(formatted_address)

            except json.JSONDecodeError as e:
                # Fail hard if an error occurs while decoding
                raise ValueError(f"Failed to decode JSON object: {e}") from e

    uniq_addresses = sorted( list( set( email_addresses ) ) )
    
    

    print(json.dumps(uniq_addresses, indent=2))

if __name__ == "__main__":
    process_json_stream()
