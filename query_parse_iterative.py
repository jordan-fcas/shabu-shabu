import re
import sys
from collections import deque
from pyparsing import (
    CaselessKeyword,
    Forward,
    infixNotation,
    opAssoc,
    ParseException,
    ParserElement,
    QuotedString,
    Regex,
    Suppress,
    Word,
)

###############################################################################
# AST Node
###############################################################################
class ASTNode:
    """
    ntype: 'AND', 'OR', 'NOT', 'TERM'
    children: list[ASTNode]
    value: string if ntype == 'TERM'
    """
    def __init__(self, ntype, children=None, value=None):
        self.ntype = ntype
        self.children = children or []
        self.value = value

    def __repr__(self):
        if self.ntype == 'TERM':
            return f"TERM({self.value})"
        elif self.ntype in ('AND', 'OR'):
            return f"{self.ntype}({', '.join(repr(c) for c in self.children)})"
        elif self.ntype == 'NOT':
            return f"NOT({', '.join(repr(c) for c in self.children)})"
        return f"{self.ntype}? {self.value}"

###############################################################################
# 1) Remove <<< ... >>> blocks (comments)
###############################################################################
def remove_comments(query_text: str) -> str:
    return re.sub(r'<<<.*?>>>', '', query_text, flags=re.DOTALL)

###############################################################################
# 2) Build Grammar (NEAR as AND) with curly, quoted, normal words
###############################################################################
def build_grammar():
    ParserElement.setDefaultWhitespaceChars(" \t\r\n")

    NOT_  = CaselessKeyword("NOT")
    AND_  = CaselessKeyword("AND")
    OR_   = CaselessKeyword("OR")
    NEAR_ = Regex(r'(?i)NEAR/\d+f?')  # treat as AND

    # We define separate tokens for:
    #   - curly braces, e.g. {ABC}
    #   - quoted strings, e.g. "some text"
    #   - single words (which we'll .lower())
    curly = Regex(r'\{[^}]*\}')
    quoted = QuotedString('"', escChar='\\', unquoteResults=True)
    word   = Regex(r'[^\s()"]+')  # raw "word" token

    def term_action(toks):
        raw = toks[0]
        # If it's curly-braced, keep it as-is (case sensitive).
        # Otherwise, .lower() it.
        if raw.startswith('{') and raw.endswith('}'):
            # Keep entire {abc} exactly
            return ASTNode('TERM', value=raw)
        else:
            # If it's a quoted phrase or normal word, unify to .lower()
            return ASTNode('TERM', value=raw.lower())

    # We'll combine them as an OR in "base_term"
    base_term = (curly | quoted | word).setParseAction(term_action)

    expr = Forward()
    group = Suppress("(") + expr + Suppress(")")
    atom = (base_term | group)

    # parse actions
    def not_action(toks):
        # [NOT, <child>]
        return ASTNode('NOT', children=[toks[0][1]])

    def and_action(toks):
        items = toks[0]
        res = items[0]
        i = 1
        while i < len(items):
            rhs = items[i+1]
            res = ASTNode('AND', children=[res, rhs])
            i += 2
        return res

    def or_action(toks):
        items = toks[0]
        res = items[0]
        i = 1
        while i < len(items):
            rhs = items[i+1]
            res = ASTNode('OR', children=[res, rhs])
            i += 2
        return res

    def near_action(toks):
        # treat NEAR as AND
        items = toks[0]
        res = items[0]
        i = 1
        while i < len(items):
            rhs = items[i+1]
            res = ASTNode('AND', children=[res, rhs])
            i += 2
        return res

    expr <<= infixNotation(
        atom,
        [
            (NOT_,  1, opAssoc.RIGHT, not_action),
            (NEAR_, 2, opAssoc.LEFT, near_action),
            (AND_,  2, opAssoc.LEFT, and_action),
            (OR_,   2, opAssoc.LEFT, or_action),
        ]
    )
    return expr

def parse_query(query_text: str):
    cleaned = remove_comments(query_text)
    grammar = build_grammar()
    try:
        result = grammar.parseString(cleaned, parseAll=True)
        if len(result) == 1:
            return result[0]
        else:
            return result.asList()
    except ParseException as pe:
        print("Parse Error:", pe)
        return None

###############################################################################
# 3) Iterative BFS rewrite to flatten AND and expand AND+OR
###############################################################################
class Rewriter:
    def __init__(self, root):
        self.root = root

    def rewrite_ast_iterative(self, pass_limit=1000):
        if not self.root:
            return self.root

        changed = True
        passes = 0
        while changed and passes < pass_limit:
            changed = False
            passes += 1

            queue = deque([self.root])
            parent_map = {id(self.root): (None, -1)}

            # BFS gather
            bfs_list = []
            while queue:
                node = queue.popleft()
                bfs_list.append(node)
                for i, c in enumerate(node.children):
                    parent_map[id(c)] = (node, i)
                    queue.append(c)

            # process BFS
            for node in bfs_list:
                if node.ntype == 'AND':
                    # flatten
                    did_flatten = self.flatten_and(node)
                    if did_flatten:
                        changed = True

                    # expand if OR child
                    or_index = None
                    for i, c in enumerate(node.children):
                        if c.ntype == 'OR':
                            or_index = i
                            break
                    if or_index is not None:
                        new_node = self.expand_and_with_or(node, or_index)
                        # reassign in parent's child list
                        pinfo = parent_map[id(node)]
                        parent, idx = pinfo
                        if parent is None:
                            # node was root
                            self.root = new_node
                        else:
                            parent.children[idx] = new_node
                        changed = True
            # repeat if changed
        return self.root

    def flatten_and(self, node):
        """If node is AND, flatten sub-AND children into one level."""
        if node.ntype != 'AND':
            return False
        new_children = []
        changed = False
        for ch in node.children:
            if ch.ntype == 'AND':
                new_children.extend(ch.children)
                changed = True
            else:
                new_children.append(ch)
        if changed:
            node.children = new_children
        return changed

    def expand_and_with_or(self, node, or_index):
        """
        AND(..., OR(...), ...) => OR( AND(..., eachChildOfOR, ...), ...)
        """
        or_node = node.children[or_index]
        before = node.children[:or_index]
        after  = node.children[or_index+1:]
        new_or_children = []
        for or_child in or_node.children:
            combined = before + [or_child] + after
            new_and = ASTNode('AND', children=combined)
            new_or_children.append(new_and)
        return ASTNode('OR', children=new_or_children)


###############################################################################
# 4) Categorization
###############################################################################
def get_all_terms(ast_node):
    """Return a list of all TERM(...) values in the subtree."""
    results = []
    if not ast_node or not hasattr(ast_node, 'ntype'):
        return results
    if ast_node.ntype == 'TERM':
        results.append(ast_node.value)
    else:
        for c in ast_node.children:
            results.extend(get_all_terms(c))
    return results

def categorize_terms(node, context=None, output=None):
    """
    We'll store:
      {
        "standalone": set(),
        "excluded": set(),
        "requires_pairs": set()  # set of (a,b) with a<b
      }
    """
    if context is None:
        context = []
    if output is None:
        output = {
            "standalone": set(),
            "excluded": set(),
            "requires_pairs": set(),
        }

    if not node:
        return output

    ntype = node.ntype

    if ntype == 'TERM':
        if 'NOT' in context:
            output["excluded"].add(node.value)
        elif 'AND' in context:
            # We'll collect pairs in the parent AND node, see below
            pass
        else:
            # top-level or in OR context => "standalone"
            output["standalone"].add(node.value)

    elif ntype == 'NOT':
        new_context = context + ['NOT']
        for child in node.children:
            categorize_terms(child, new_context, output)

    elif ntype == 'AND':
        # gather all terms in this AND node => produce pairwise
        all_terms = list(set(get_all_terms(node)))
        for i in range(len(all_terms)):
            for j in range(i+1, len(all_terms)):
                a, b = sorted([all_terms[i], all_terms[j]])
                output["requires_pairs"].add((a,b))

        new_context = context + ['AND']
        for child in node.children:
            categorize_terms(child, new_context, output)

    elif ntype == 'OR':
        new_context = context
        for child in node.children:
            categorize_terms(child, new_context, output)

    return output

###############################################################################
# 5) Summarize
###############################################################################
def print_summary(summary_dict):
    """
    Summarize:
      - standalone (alphabetical)
      - excluded (alphabetical)
      - requires pairs, grouped by the first term (alphabetical)
    Then remove from requires any term that is in 'standalone'
    """
    standalone_terms = summary_dict["standalone"]
    excluded_terms   = summary_dict["excluded"]
    requires_pairs   = summary_dict["requires_pairs"]

    # 1) Print standalone (alphabetical)
    st_sorted = sorted(standalone_terms, key=str.lower)
    print("Standalone Terms:")
    if st_sorted:
        for t in st_sorted:
            print(f" - {t}")
    else:
        print(" (none)")
    print()

    # 2) Print excluded (alphabetical)
    ex_sorted = sorted(excluded_terms, key=str.lower)
    print("Excluded Terms:")
    if ex_sorted:
        for t in ex_sorted:
            print(f" - {t}")
    else:
        print(" (none)")
    print()

    # 3) Build dictionary for requires
    pairs_by_a = {}
    for (a, b) in requires_pairs:
        # skip if a or b is in standalone
        if a in standalone_terms or b in standalone_terms:
            continue
        if a not in pairs_by_a:
            pairs_by_a[a] = set()
        pairs_by_a[a].add(b)

    print("Requires Another:")
    if not pairs_by_a:
        print(" (none)\n")
        return

    # sort the 'a' terms
    for a in sorted(pairs_by_a, key=str.lower):
        bs = sorted(pairs_by_a[a], key=str.lower)
        if len(bs) == 1:
            print(f" - {a} must appear with {bs[0]}")
        else:
            print(f" - {a} must appear with ({', '.join(bs)})")
    print()

###############################################################################
# 6) Example usage
###############################################################################
if __name__ == "__main__":
    # Simple example that triggers expansion
    # (A NEAR/0 B) => AND(A,B)
    # (X AND Y) => AND(X,Y)
    # (A AND B) AND (C OR D) => expand to OR(AND(A,B,C), AND(A,B,D))
    sample_query = r'''
'''

    sys.setrecursionlimit(10**7)
    ast = parse_query(sample_query)
    # print("=== RAW AST ===")
    # print(ast)

    if ast:
        rewriter = Rewriter(ast)
        new_root = rewriter.rewrite_ast_iterative(pass_limit=1000)
        # print("\n=== REWRITTEN AST ===")
        # print(new_root)

        summary = categorize_terms(new_root)
        print("\n=== SUMMARY ===")
        print_summary(summary)
