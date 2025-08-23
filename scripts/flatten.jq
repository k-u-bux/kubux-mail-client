# Define a recursive filter for walking the forest.
def flatten_forest:
  .[] | # Iterate over the trees in the forest.
  (
    .[0], # The first element is the mail object; output it.
    (.[1] | # The second element is the sub-forest; recursively process it.
      if length > 0 then
        flatten_forest # If the forest is not empty, recurse.
      else
        empty # If it's an empty forest, do nothing.
      end
    )
  );

# Apply the filter to the top-level forest output by notmuch.
.[] | flatten_forest