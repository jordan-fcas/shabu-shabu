import re
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
    value: optional str (for TERM)
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
# 1) Remove <<< ... >>> blocks
###############################################################################
def remove_comments(query_text: str) -> str:
    return re.sub(r'<<<.*?>>>', '', query_text, flags=re.DOTALL)

###############################################################################
# 2) Build Grammar, treat NEAR as AND
###############################################################################
def build_grammar():
    ParserElement.setDefaultWhitespaceChars(" \t\r\n")

    NOT_  = CaselessKeyword("NOT")
    AND_  = CaselessKeyword("AND")
    OR_   = CaselessKeyword("OR")
    # e.g. NEAR/10f => treat as AND
    NEAR_ = Regex(r'(?i)NEAR/\d+f?')

    quoted = QuotedString('"', escChar='\\', unquoteResults=True)
    word   = Regex(r'[^\s()"]+')

    def term_action(toks):
        return ASTNode('TERM', value=toks[0])

    base_term = (quoted | word).setParseAction(term_action)

    expr = Forward()
    group = Suppress("(") + expr + Suppress(")")
    atom = (base_term | group)

    # parse actions
    def not_action(toks):
        op, operand = toks[0]  # [NOT, <child>]
        return ASTNode('NOT', children=[operand])

    def and_action(toks):
        tokens = toks[0]
        res = tokens[0]
        i = 1
        while i < len(tokens):
            rhs = tokens[i+1]
            res = ASTNode('AND', children=[res, rhs])
            i += 2
        return res

    def or_action(toks):
        tokens = toks[0]
        res = tokens[0]
        i = 1
        while i < len(tokens):
            rhs = tokens[i+1]
            res = ASTNode('OR', children=[res, rhs])
            i += 2
        return res

    def near_action(toks):
        # interpret NEAR as AND
        tokens = toks[0]
        res = tokens[0]
        i = 1
        while i < len(tokens):
            rhs = tokens[i+1]
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
# 3) Rewrite AST for deeply nested expansions
###############################################################################
def rewrite_ast(node):
    """
    Recursively:
      - flatten AND children (so AND(AND(A,B),C) => AND(A,B,C))
      - if we find an OR among AND's children, expand:
        AND(..., OR(a,b), ...) => OR( AND(..., a, ...), AND(..., b, ...) )
      do it repeatedly until no more expansions are possible
    """
    if not node:
        return node

    # rewrite children first
    for i, ch in enumerate(node.children):
        node.children[i] = rewrite_ast(ch)

    ntype = node.ntype
    if ntype == 'AND':
        # 1) Flatten any sub-AND
        flattened = []
        for child in node.children:
            if child.ntype == 'AND':
                flattened.extend(child.children)
            else:
                flattened.append(child)
        node.children = flattened

        # 2) If any child is OR, expand
        # We'll repeatedly expand the *first* OR child we see, then rewrite again
        or_index = None
        for i, c in enumerate(node.children):
            if c.ntype == 'OR':
                or_index = i
                break

        if or_index is not None:
            # E.g. AND(x,y, OR(a,b), z) => OR( AND(x,y,a,z), AND(x,y,b,z) )
            or_node = node.children[or_index]
            before = node.children[:or_index]
            after  = node.children[or_index+1:]

            new_or_children = []
            for or_child in or_node.children:
                # build new AND containing before + [or_child] + after
                new_and_children = before + [or_child] + after
                # build an AND node
                new_and = ASTNode('AND', children=new_and_children)
                new_and = rewrite_ast(new_and)  # recursively rewrite deeper
                new_or_children.append(new_and)

            new_node = ASTNode('OR', children=new_or_children)
            return rewrite_ast(new_node)  # rewrite again, in case more expansions needed

    elif ntype == 'OR':
        # rewrite children if needed
        # no flatten for OR in this example
        pass
    elif ntype == 'NOT':
        # rewrite child
        pass
    elif ntype == 'TERM':
        # nothing to do
        pass

    return node

###############################################################################
# 4) Summaries
###############################################################################
def get_all_terms(ast_node):
    """Return a list of all TERM(...) values in the subtree."""
    results = []
    if ast_node.ntype == 'TERM':
        results.append(ast_node.value)
    else:
        for c in ast_node.children:
            results.extend(get_all_terms(c))
    return results

def categorize_terms(node, context=None, output=None):
    """
    We'll store in output:
      {
        "standalone": set(),
        "excluded": set(),
        "requires_pairs": set()  # set of (a,b) with a<b to avoid duplicates
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
            # We'll add pairs in the parent AND node
            pass
        else:
            # presumably top-level or under OR
            output["standalone"].add(node.value)

    elif ntype == 'NOT':
        new_context = context + ['NOT']
        for child in node.children:
            categorize_terms(child, new_context, output)

    elif ntype == 'AND':
        # gather all terms in this AND node
        all_terms = list(set(get_all_terms(node)))  # unique
        # produce pairwise combos
        for i in range(len(all_terms)):
            for j in range(i+1, len(all_terms)):
                t1, t2 = all_terms[i], all_terms[j]
                a, b = sorted([t1, t2])
                output["requires_pairs"].add((a, b))

        new_context = context + ['AND']
        for child in node.children:
            categorize_terms(child, new_context, output)

    elif ntype == 'OR':
        new_context = context
        for child in node.children:
            categorize_terms(child, new_context, output)

    return output

def print_summary(summary_dict):
    """
    Summarize:
      - standalone
      - excluded
      - requires (pairwise)
    Then remove from requires any term in 'standalone'.
    """
    standalone_terms = summary_dict["standalone"]
    excluded_terms   = summary_dict["excluded"]
    requires_pairs   = summary_dict["requires_pairs"]

    # 1) Print standalone
    st_sorted = sorted(standalone_terms)
    print("Standalone Terms:")
    if st_sorted:
        for t in st_sorted:
            print(f" - {t}")
    else:
        print(" (none)")
    print()

    # 2) Print excluded
    ex_sorted = sorted(excluded_terms)
    print("Excluded Terms:")
    if ex_sorted:
        for t in ex_sorted:
            print(f" - {t}")
    else:
        print(" (none)")
    print()

    # 3) Build pairs_by_a
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

    for a in sorted(pairs_by_a):
        bs = sorted(pairs_by_a[a])
        if len(bs) == 1:
            print(f" - {a} must appear with {bs[0]}")
        else:
            b_str = ", ".join(bs)
            print(f" - {a} must appear with ({b_str})")
    print()


###############################################################################
# Example usage
###############################################################################
if __name__ == "__main__":
    sample_query = r'''
'''

    # 1) Parse
    ast = parse_query(sample_query)
    # print("=== RAW AST ===")
    # print(ast)

    # 2) Rewrite expansions
    new_ast = rewrite_ast(ast)
    print("\n=== REWRITTEN AST ===")
    print(new_ast)

    # 3) Categorize
    summary = categorize_terms(new_ast)
    print("\n=== SUMMARY ===")
    print_summary(summary)
