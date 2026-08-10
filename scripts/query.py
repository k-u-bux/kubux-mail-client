import json
import os
from pathlib import Path
import logging
import re

from config import config

class QueryParser:
    """
    Parses and expands user-defined named queries.
    """
    def __init__(self, config_dir = config.config_dir):
        """
        Initializes the parser and loads named queries from a file.
        """
        self.queries_path = config_dir / "queries.json"
        self.queries = self._load_queries().get("queries",[])
        self.named_queries = {name:query for name, query in self.queries if name != ""}
        self.names  = [name for name, query in self.queries if name != ""]

    def _load_queries(self):
        """
        Loads named queries from the TOML configuration file.
        """
        if not self.queries_path.exists():
            logging.warning(f"Queries file not found at {self.queries_path}. Using empty named queries.")
            # Create a default file
            default_queries = []
            try:
                with open(self.queries_path, "w") as f:
                    json.dump(default_queries, f)
            except Exception as e:
                logging.error(f"Failed to create default queries.toml file: {e}")
            return {}

        try:
            with open(self.queries_path, "r") as f:
                data = json.load(f)
                return data
        except Exception as e:
            logging.error(f"Failed to load queries from {self.queries_path}: {e}")
            return {}

    def parse(self, query_expression: str) -> str:
        """
        Expands named queries in the given expression.
        Handles nested queries and checks for circular dependencies.
        """
        return self._expand_queries(query_expression, [])

    def _expand_queries(self, expression: str, trace: list) -> str:
        """Recursive helper function to expand queries."""
        # Find all named query references
        references = re.findall(r'\$(\w+)', expression)

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
            expanded_sub_query = self._expand_queries(referenced_query, trace + [ref])
            
            # Substitute the reference with the expanded query, wrapped in parentheses
            # to preserve notmuch's operator precedence
            expanded_expression = expanded_expression.replace(f"${ref}", f"({expanded_sub_query})")
            
        return expanded_expression
