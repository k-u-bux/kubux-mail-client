# This script processes a stream of JSON objects, one per line.
# It handles both names and emails.

# This function emulates 'trim' for older jq versions.
def my_trim:
  sub("^ +"; "") | sub(" +$"; "");

# A filter to extract and validate an email address and name using a more robust method.
def extract_name_and_email:
  # Check for the format "Name" <email> or Name <email>.
  if test("<.*>") then
    # Split the string on '<' to get the name and email parts.
    (split("<") | .[0] | my_trim) as $name |
    (split("<") | .[1] | sub(">;.*$"; "") | sub(">$"; "") | my_trim) as $email |
    # Test if the extracted email part contains an '@'.
    if $email | test("@") then
      {"name": $name, "email": $email}
    else
      empty
    end
  # If there are no angle brackets, assume it's just an email and check for '@'.
  elif test("@") then
    {"email": . | my_trim}
  # If neither, it's just a name, so discard it.
  else
    empty
  end;

# The main filter that processes a stream of individual mail objects.
. as $mail |
  # Create a stream of header strings from the current mail object.
  (
    $mail.headers.From // empty,
    $mail.headers.To // empty,
    $mail.headers.Cc // empty
  ) |
  
  # For each header string in the stream...
  . |
    split(",") |
    .[] |
    # Clean and extract the address information.
    my_trim |
    extract_name_and_email |
    # Add the timestamp to the resulting object.
    . + {"timestamp": $mail.timestamp}