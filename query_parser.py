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
<<<General terms>>>
(anti NEAR/0f (semitism OR semitic OR semetism OR semetic OR semtism OR jew OR jews OR Jewish)) OR antisem?tism OR antisemtism OR antijew OR antijewish OR "anti-semitism" OR "anti-semetism" OR antisem?tic OR antisemite OR "anti-semite" OR "Jewish hate" OR Jewishhate OR Judeophobia OR #StandUpToJewishHate OR #EndJewHatred 

OR Jew OR J3W OR Jewish OR Jews OR J3ws OR Judaism

OR Chabad* OR synagogue* OR Yeshiva* OR Shul OR Mikveh* OR "star of david" OR starofdavid OR "Magen david" OR Magendavid OR Mezuzah OR Mezuzot OR tallis OR Tallit OR tefillin OR torah OR tehilim OR talmud OR yiddish OR Rabbi OR Rabbis OR Rabbinic* OR menorah OR Kipah OR Kippa OR Kipa OR Kippah OR yarmulke* OR shtreimel OR Mezuzah OR Mezuza OR kosher OR Shalom OR Emunah

OR ✡️ OR 🕎 OR 🕍

OR

<<<derogatory terms>>>
"bagel bender" OR "christ killer" OR "christ-killer" OR hebe OR heeb OR hymie OR kike OR turbokik OR Cryptokik OR turbokike OR Cryptokike OR amerikike OR amerigoi OR "crypto kike" OR "crypto-kike" OR cryptoJew OR "crypto jew" OR yid OR yahudi OR yahoodi OR Yahud OR yahood OR (zio NEAR/0f (pig OR pigs OR nazi OR nazis)) OR Zionazi* OR "anudda Shoah" OR annudashoah OR anuddahshoah OR "anuddah shoah" OR "oven dodger" OR "jewish features" OR "synagogue of satan" OR "oy vey" OR "satanic talmud" OR cohencidence OR "imposter Jews" OR "fake jew" OR "fake Jews" OR "Jew York" OR ((belong OR Kill OR killed) NEAR/50 ("Gas Chamber" OR "gas chambers")) OR "Jew down" OR Kvetching OR "oy gevalt"

OR "totally joyful day" OR "totally nice day" OR "total Jew death" OR "total Jewish death" OR "total kike death" OR "talmud and endorse TKD" OR "Total kikes death" OR "total jews death" OR (TKD NEAR/10 TND) OR (TKD NEAR/10 TJD) OR (TJD NEAR/10 TND) OR (TKD NEAR/10 TND) OR (TKD NEAR/10 TJD) OR (TJD NEAR/10 TND) OR TJD.TKD

OR

<<<Conspiracy Theories>>>

"Jewish privilege" OR "Jewish supremacy" OR "jew privilege" OR "jew supremacy" OR ((Jews OR jews OR jewish OR hebrew OR hebrews OR Zionist OR Zionists) NEAR/100 (traitor OR traitors OR greed OR power OR control OR evil OR sneky OR puppet OR warmong* OR bankster OR globalist OR cosmopolitan OR marxist* OR Capitalis* OR communis* OR lobby)) OR "Jew-down" OR
 
"blood libel" OR "great replacement" OR "new world order" OR "rothschild" OR "rothschilds" OR "jewish agenda" OR goy OR goyim OR "the goyim know" OR "the nose knows" OR "the noticing" OR "the deepstate" OR "Jewish mafia" OR "jewish cabal" OR "khazarian mafia" OR Khazars OR "khazaria" OR ("federal reserve" AND (Jew* OR control OR conspiracy OR Banksters OR Rothschild* OR CIA OR "New World Order")) OR "cosmopolitan elite" OR cosmopolitanelite* OR "elders of Zion" OR "kosher tax" OR Koshertax* OR (kosher NEAR/0f tax*) OR (("not" NEAR/1f "real") NEAR/1f (Jew OR Jews OR jewish)) OR (protocol* NEAR/3f (elder* OR Zion)) OR (Jews NEAR/3f 9/11) OR 1488 OR QAnon OR 14/88 OR "Jews will not replace us" OR {14-88} OR 8814 OR "14 words" OR 14words OR RaHoWa OR "Jews control" OR "Jews secretly" OR groyper OR groypers OR "deadly exchange" OR ("killed Jesus" AND (Jews OR they)) OR "30 pieces of silver"

OR 
<<<Holocaust Terms>>> 
Holocaust OR shoah OR hitler OR "Adolf Eichmann" OR adolfEichmann OR "Joseph Mengele" OR JosephMengele OR "Dr Mengele" OR DRmengele OR "Henrich Himmler" OR Henrichhimmler OR "Reinhard Heydrich" OR ReinhardHeydrich OR nazi OR nazis OR Nazism OR "Third Reich" OR "3 reich" OR "3rd reich" OR SSHitler OR gestapo OR Heilhitler OR "heil hitler" OR "hail hitler" OR "seig hail" OR "seig heil" OR Seigheil OR swastika OR swastikas OR Fuhrer OR "aryan race" OR aryanrace OR Auschwitz OR Birkenau OR {auschwitz-Birkenau} OR "arbeit mecht frei" OR "work makes you free" OR "bergen belsen" OR {bergen-belsen} OR belzec OR Buchenwald OR Chelmno OR Dachau OR majdanek OR mauthausen OR sobibor OR Terezin OR teresienstadt OR Treblinka OR "dora Mittelbau" OR {dora-mittelbau} OR Flossenburg OR "gross rosen" OR {gross-rosen} OR Janowska OR Kaiserwald OR "Natzweiler Struthof" OR {Natzweiler-Struthof} OR Neuengamme OR Oranienburg OR Plaszow OR Ravensburck OR Sachsenhausen OR Stutthof OR Westerbork OR Ghetto OR "Anne Frank" OR annefrank OR Kristallnacht OR "night of the broken glass" OR "nuremberg code" OR "nuremberg trials" OR "wannsee conference" OR wannseeconference OR ashkenazi OR "gas chambers" OR gaschambers OR juden OR mischlinge OR "waffen-SS" OR "babi yar" OR "Evian conference" OR Kindertransport OR "Mein Kampf" OR (Germany NEAR/50 (1930 OR 1930s))

OR (("6 million" OR 6mil* OR "six million" OR sixmil*) NEAR/1f ((wasnt OR {wasn't} OR "wasn t" OR "was not") NEAR/0f enough)) OR 6MWE OR "fourth Reich" OR h0l0c4ust OR h0l0caust OR h0l0hoax* OR holohoax* OR holocaugh OR holocough OR hol0hoax* OR "holo_hoax" OR "hitler was right" OR hitlerwasright OR "hitler is right" OR hitlerisright OR "holocaust_lies" OR holocaustisalie OR holocaustneverhappened OR "Jewish question" OR "Jewish problem" OR ("final solution" NEAR/1f "jewish") OR fakeholocaust OR "gas the kikes" OR {GTK} OR {GTKRWN} OR "6 gorillion" OR "six gorrilion" OR Judenrat OR "muh Holocause" OR holocaustneverhappened OR H1tler

<<<hate groups>>>
OR "the turner diaries" OR "white power world wide" OR #WPWW OR "white power" OR #whitepower OR Whitepower OR "goyim defense legaue" OR GDL OR "White Lives Matter" OR "blood tribe" OR "neo nazis" OR "neo-nazis" OR "White supremacists" OR "White supremacist" OR "white supremacy" OR "black supremacist" OR "Black Hebrew Israelites" OR "Nation of Islam"

<<<College Campuses>>>

OR "students for Justice in Palestine" OR SJP OR "Jewish Voices for peace" OR JVP OR "Columbia University Apartheid Divest" OR "Students for a democratic society" OR {SDS} OR "Young Democratic Socialists of America" OR {YDSA}

<<<Jewish holidays>>>
OR "rosh hashana" OR "Rosh hashanah" OR roshhashana OR Roshhashanah OR "shana tovah" OR "L'shana tova" OR "Yom kippur" OR YomKippur OR Sukkot OR "tu beshevat" OR "tu Bshevat" OR "tu B shevat" OR Purim OR Pesach OR Passover OR "Yom Hashoah" OR YomHashoah OR "Yom Hazikaron" OR YomHazikaron OR "Yom Ha'atzmaut" OR "Yom Haatzmaut" OR YomHaatzmaut OR (Israel* NEAR/0f "Independence day") OR "yom yerushalayim" OR YomYerushalayim OR "Shavuot" OR "Tisha B'av" OR "Tisha Bav" OR TishaBav OR "Shemini Atzeret" OR SheminiAtzeret OR "Simchat Torah" OR SimchatTorah OR Chanukah OR Hanukkah OR Hannukah OR "lag B'omer" OR "Lag B omer" 

<<<Jewish organizations>>>

OR "Anti-Defamation League" OR "anti defamation league" OR {ADL} OR "American Jewish Committee" OR {AJC} OR "foundation to combat antisemitism" OR {FCAS} OR "Stand up to Jewish hate" OR #StandUpTpJewishHate OR "whats up with hate" OR "hillel" OR "Jewish federation" OR "Jewish federations" OR {JFNA} OR {UJA} OR {CJP} OR {JCRC} OR #BanTheADL OR IHRA OR "International Holocaust Rememberance Alliance" OR AIPAC OR "American Israel Public Affairs Committee" OR "Secure community network" OR "JewBelong" OR "Simon Wiesenthal Center" OR "Zeta Beta Tau" OR {ZBT} OR "conference of presidents" OR "Stand with us" OR "Alpha Epsilon Phi" OR {AEPhi} OR "Hadassah" OR "creative community for peace" OR "Fuente Latina" OR "amcha Initiative"

OR "Deborah Lipstadt" OR "jonathan Greenblatt" OR "Ted Deutch"
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
