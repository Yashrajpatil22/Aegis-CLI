import tree_sitter_python as tspython
from tree_sitter import Language, Parser

# Initialize the Python Tree-sitter language grammar
PY_LANGUAGE = Language(tspython.language())

class ASTPruner:
    def __init__(self):
        self.parser = Parser(PY_LANGUAGE)

    def extract_skeleton(self, code: str) -> str:
        """
        Parses Python code and extracts imports, class definitions, 
        and function/method signatures, omitting implementation bodies.
        """
        code_bytes = bytes(code, "utf-8")
        tree = self.parser.parse(code_bytes)
        
        extracted_lines = []
        lines = code.split("\n")

        def visit_node(node):
            # Capture imports
            if node.type in ["import_statement", "import_from_statement"]:
                start_row = node.start_point.row
                end_row = node.end_point.row
                for r in range(start_row, end_row + 1):
                    extracted_lines.append((r, lines[r]))

            # Capture class definitions (header line)
            elif node.type == "class_definition":
                start_row = node.start_point.row
                extracted_lines.append((start_row, lines[start_row]))

            # Capture function/method definitions (header line)
            elif node.type == "function_definition":
                start_row = node.start_point.row
                # Handles multi-line function defs until the colon
                end_row = node.start_point.row
                for child in node.children:
                    if child.type == "parameters":
                        end_row = child.end_point.row
                        break
                for r in range(start_row, end_row + 1):
                    extracted_lines.append((r, lines[r]))

            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)

        # Sort lines by original line numbers and deduplicate
        extracted_lines.sort(key=lambda x: x[0])
        unique_lines = []
        seen_rows = set()

        for r, line in extracted_lines:
            if r not in seen_rows:
                seen_rows.add(r)
                unique_lines.append(line)

        return "\n".join(unique_lines)

    def prune_file(self, file_path: str) -> str:
        """Reads a target file and returns its pruned structural skeleton."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.extract_skeleton(content)