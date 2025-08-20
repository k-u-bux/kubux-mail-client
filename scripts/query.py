#!/usr/bin/env python3

import toml
from pathlib import Path
import logging
import re

from config import config

class QueryParser:
    """
    Parses and expands user-defined named queries.
    """
    def __init__(self, config_dir: config.config_dir):
        """
        Initializes the parser and loads named queries from a file.
        """
        self.queries_path = config_dir / "queries.toml"
        self.named_queries = self._load_queries()
        
    def _load_queries(self):
        """
        Loads named queries from the TOML configuration file.
        """
        if not self.queries_path.exists():
            logging.warning(f"Queries file not found at {self.queries_path}. Using empty named queries.")
            # Create a default file
            default_queries = {"queries": []}
            try:
                with open(self.queries_path, "w") as f:
                    toml.dump(default_queries, f)
            except Exception as e:
                logging.error(f"Failed to create default queries.toml file: {e}")
            return {}

        try:
            with open(self.queries_path, "r") as f:
                data = toml.load(f)
                return {q["name"]: q["query"] for q in data.get("queries", [])}
        except Exception as e:
            logging.error(f"Failed to load queries from {self.queries_path}: {e}")
            return {}

    def parse(self, query_expression: str) -> str:
        """
        Expands named queries in the given expression.
        Handles nested queries and checks for circular dependencies.
        """
        return self._expand_queries(query_expression, [], [])

    def _expand_queries(self, expression: str, visited: list, trace: list) -> str:
        """Recursive helper function to expand queries."""
        # Find all named query references
        references = re.findall(r'$(\w+)', expression)
        
        if not references:
            return expression
        
        expanded_expression = expression
        for ref in references:
            # Check for circular dependency
            if ref in trace:
                raise ValueError(f"Circular query reference detected: {' -> '.join(trace + [ref])}")
            
            if ref not in self.named_queries:
                raise ValueError(f"Undefined query name: '${ref}'")
            
            referenced_query = self.named_queries[ref]
            
            # Recursively expand the referenced query
            expanded_sub_query = self._expand_queries(referenced_query, visited + [expression], trace + [ref])
            
            # Substitute the reference with the expanded query, wrapped in parentheses
            # to preserve notmuch's operator precedence
            expanded_expression = expanded_expression.replace(f"${ref}", f"({expanded_sub_query})")
            
        return expanded_expression

if __name__ == '__main__':
    # This is a simple example to test the parser
    # You would use this in a GUI application to tie it to the config
    
    # Mock a configuration directory
    from pathlib import Path
    mock_config_dir = Path("./mock_config")
    mock_config_dir.mkdir(exist_ok=True)
    
    # Create a mock queries.toml file
    mock_queries_content = """
    [[queries]]
    name = "unread"
    query = "tag:inbox and tag:unread"

    [[queries]]
    name = "from_me"
    query = "from:me@kubux.net"
    
    [[queries]]
    name = "urgent_inbox"
    query = "tag:urgent and $unread"
    
    [[queries]]
    name = "recursive_example"
    query = "$recursive_example"
    """
    
    with open(mock_config_dir / "queries.toml", "w") as f:
        f.write(mock_queries_content)

    parser = QueryParser(mock_config_dir)

    print("Named queries loaded:")
    print(parser.named_queries)

    test_queries = [
        "subject:project and $urgent_inbox",
        "$unread and not $from_me",
        "tag:archive",
        "tag:unread and $unknown_query",
        "tag:unread or $recursive_example"
    ]

    for q in test_queries:
        try:
            expanded = parser.parse(q)
            print(f"'{q}' -> '{expanded}'")
        except Exception as e:
            print(f"ERROR: {e}")
