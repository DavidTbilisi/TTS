"""Filters for non-readable substrings.

Replaces fenced and inline code, URLs, shebang lines, HTML-like markup,
file extensions, common tech abbreviations, math symbols, and huge digit
runs with short spoken-friendly phrases so TTS does not read raw syntax.

Design
------
Each filter is a plain ``TextFilter`` callable (``str -> str``).
``TextProcessingPipeline`` composes them in order. The module-level
``replace_not_readable`` runs the default pipeline.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

__all__ = [
    "TextFilter",
    "TextProcessingPipeline",
    "replace_not_readable",
    "CODE_BLOCK_PLACEHOLDER",
    "INLINE_CODE_PLACEHOLDER",
    "LINK_PLACEHOLDER",
    "filter_code_blocks",
    "filter_inline_code",
    "filter_urls",
    "filter_shebang_lines",
    "filter_html_like_tags",
    "filter_file_extensions",
    "filter_tech_abbreviations",
    "filter_symbols_to_words",
    "filter_big_numbers",
]

# Spoken placeholders (spaces help TTS word boundaries).
CODE_BLOCK_PLACEHOLDER = " omitted fenced code block "
INLINE_CODE_PLACEHOLDER = " omitted inline code snippet "
LINK_PLACEHOLDER = " omitted hyperlink "

TextFilter = Callable[[str], str]

# ── Compiled regexes ─────────────────────────────────────────────────────────

CODE_BLOCK_RE: Pattern = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE: Pattern = re.compile(r"`([^`]+)`")
URL_RE: Pattern = re.compile(r"\b(?:https?://|http://|www\.)\S+\b", re.IGNORECASE)
SHEBANG_LINE_RE: Pattern = re.compile(r"^#!.+$", re.MULTILINE)
HTML_LIKE_TAG_RE: Pattern = re.compile(r"<[!/?]?[a-zA-Z][^>\s=]*(?:\s[^>]*)?>")
BIG_NUMBER_RE: Pattern = re.compile(r"\b\d{7,}\b")
_WHITESPACE_RE: Pattern = re.compile(r"\s{2,}")

# Extension (without dot) → spoken name. Longer keys must win in alternation.
_FILE_EXT_SPEAK: Tuple[Tuple[str, str], ...] = (
    ("ipynb", "Jupyter notebook"),
    ("pyc", "Python bytecode"),
    ("pyw", "Python script"),
    ("pyi", "Python type stubs"),
    ("py", "Python"),
    ("tsx", "TypeScript React"),
    ("jsx", "JavaScript React"),
    ("ts", "TypeScript"),
    ("mjs", "JavaScript module"),
    ("cjs", "JavaScript"),
    ("js", "JavaScript"),
    ("vue", "Vue"),
    ("svelte", "Svelte"),
    ("rs", "Rust"),
    ("go", "Go"),
    ("rb", "Ruby"),
    ("php", "P H P"),
    ("java", "Java"),
    ("kts", "Kotlin script"),
    ("kt", "Kotlin"),
    ("swift", "Swift"),
    ("scala", "Scala"),
    ("clj", "Clojure"),
    ("exs", "Elixir script"),
    ("ex", "Elixir"),
    ("erl", "Erlang"),
    ("lua", "Lua"),
    ("pm", "Perl module"),
    ("pl", "Perl"),
    ("r", "R"),
    ("jl", "Julia"),
    ("dart", "Dart"),
    ("fsx", "F sharp script"),
    ("fs", "F sharp"),
    ("cs", "C sharp"),
    ("vb", "Visual Basic"),
    ("sqlite", "SQLite"),
    ("sql", "S Q L"),
    ("ps1", "PowerShell script"),
    ("zsh", "Z shell script"),
    ("bash", "bash script"),
    ("sh", "shell script"),
    ("cmd", "Windows command script"),
    ("bat", "batch script"),
    ("cmake", "CMake"),
    ("dockerfile", "Dockerfile"),
    ("hcl", "HashiCorp config"),
    ("yaml", "Y A M L"),
    ("yml", "Y A M L"),
    ("toml", "Toml"),
    ("json", "J S O N"),
    ("xml", "X M L"),
    ("html", "H T M L"),
    ("htm", "H T M L"),
    ("scss", "Sass C S S"),
    ("sass", "Sass"),
    ("less", "Less C S S"),
    ("css", "C S S"),
    ("rst", "reStructuredText"),
    ("md", "Markdown"),
    ("tex", "LaTeX"),
    ("bib", "BibTeX"),
    ("hpp", "C plus plus header"),
    ("hxx", "C plus plus header"),
    ("cpp", "C plus plus"),
    ("cxx", "C plus plus"),
    ("cc", "C plus plus"),
    ("wasm", "WebAssembly"),
    ("wat", "WebAssembly text"),
    ("h", "C header"),
    ("c", "C source"),
    ("tf", "Terraform"),
)

_EXT_KEYS = "|".join(re.escape(k) for k, _ in _FILE_EXT_SPEAK)
FILE_EXT_RE: Pattern = re.compile(rf"\.({_EXT_KEYS})\b", re.IGNORECASE)
_FILE_EXT_MAP: Dict[str, str] = {k.lower(): v for k, v in _FILE_EXT_SPEAK}

# Longer / more specific acronyms first. Patterns use word boundaries where sensible.
_TECH_ABBREV_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\bCI/CD\b", " continuous integration and delivery "),
    (r"\bUTF-8\b", " U T F eight "),
    (r"\bUTF8\b", " U T F eight "),
    (r"\bIPv6\b", " I P v 6 "),
    (r"\bIPv4\b", " I P v 4 "),
    (r"\bJSONL\b", " J S O N lines "),
    (r"\bNode\.js\b", " Node jay ess "),
    (r"\bnode\.js\b", " Node jay ess "),
    (r"\bThree\.js\b", " Three jay ess "),
    (r"\bD3\.js\b", " D three jay ess "),
    (r"\bVue\.js\b", " Vue jay ess "),
    (r"\bNext\.js\b", " Next jay ess "),
    (r"\bNuxt\.js\b", " Nuxt jay ess "),
    (r"\bExpress\.js\b", " Express jay ess "),
    (r"\bReact\.js\b", " React jay ess "),
    (r"\bNestJS\b", " Nest jay ess "),
    (r"\bSpringBoot\b", " Spring Boot "),
    (r"\bFastAPI\b", " Fast A P I "),
    (r"\bSQLAlchemy\b", " S Q L Alchemy "),
    (r"\bOpenID\b", " Open I D "),
    (r"\bOpenGL\b", " Open G L "),
    (r"\bOpenCL\b", " Open C L "),
    (r"\bWebGL\b", " Web G L "),
    (r"\bWebRTC\b", " Web R T C "),
    (r"\bWebSocket\b", " Web socket "),
    (r"\bGraphQL\b", " Graph Q L "),
    (r"\bActive Directory\b", " Active Directory "),
    (r"\bDNSSEC\b", " D N S sec "),
    (r"\bSpring Boot\b", " Spring Boot "),
    (r"\bC\+\+\b", " C plus plus "),
    (r"\bC#\b", " C sharp "),
    (r"\bF#\b", " F sharp "),
    (r"\b\.NET\b", " dot net "),
    (r"\bASP\.NET\b", " A S P dot net "),
    (r"\bHTTPS\b", " H T T P S "),
    (r"\bHTTP\b", " H T T P "),
    (r"\bREST\b", " R E S T "),
    (r"\bSOAP\b", " S O A P "),
    (r"\bSQL\b", " S Q L "),
    (r"\bNoSQL\b", " No S Q L "),
    (r"\bJSON\b", " J S O N "),
    (r"\bXML\b", " X M L "),
    (r"\bYAML\b", " Y A M L "),
    (r"\bHTML\b", " H T M L "),
    (r"\bXHTML\b", " X H T M L "),
    (r"\bCSS\b", " C S S "),
    (r"\bSCSS\b", " S C S S "),
    (r"\bSVG\b", " S V G "),
    (r"\bDOM\b", " D O M "),
    (r"\bBOM\b", " B O M "),
    (r"\bJWT\b", " J W T "),
    (r"\bOAuth\b", " Oh auth "),
    (r"\bSAML\b", " S A M L "),
    (r"\bTLS\b", " T L S "),
    (r"\bSSL\b", " S S L "),
    (r"\bSSH\b", " S S H "),
    (r"\bSFTP\b", " S F T P "),
    (r"\bFTP\b", " F T P "),
    (r"\bTCP\b", " T C P "),
    (r"\bUDP\b", " U D P "),
    (r"\bIP\b", " I P "),
    (r"\bDNS\b", " D N S "),
    (r"\bCDN\b", " C D N "),
    (r"\bVPC\b", " V P C "),
    (r"\bIAM\b", " I A M "),
    (r"\bAWS\b", " A W S "),
    (r"\bGCP\b", " G C P "),
    (r"\bGKE\b", " G K E "),
    (r"\bEKS\b", " E K S "),
    (r"\bAKS\b", " A K S "),
    (r"\bORM\b", " O R M "),
    (r"\bCRUD\b", " crud "),
    (r"\bSDK\b", " S D K "),
    (r"\bAPI\b", " A P I "),
    (r"\bGUI\b", " G U I "),
    (r"\bCLI\b", " C L I "),
    (r"\bTUI\b", " T U I "),
    (r"\bIDE\b", " I D E "),
    (r"\bLSP\b", " L S P "),
    (r"\bCPU\b", " C P U "),
    (r"\bGPU\b", " G P U "),
    (r"\bRAM\b", " R A M "),
    (r"\bROM\b", " R O M "),
    (r"\bSSD\b", " S S D "),
    (r"\bHDD\b", " H D D "),
    (r"\bUSB\b", " U S B "),
    (r"\bHDMI\b", " H D M I "),
    (r"\bOLED\b", " O L E D "),
    (r"\bLCD\b", " L C D "),
    (r"\bPDF\b", " P D F "),
    (r"\bPNG\b", " P N G "),
    (r"\bJPEG\b", " J P E G "),
    (r"\bJPG\b", " J P G "),
    (r"\bGIF\b", " G I F "),
    (r"\bASCII\b", " A S C I I "),
    (r"\bURL\b", " U R L "),
    (r"\bURI\b", " U R I "),
    (r"\bURN\b", " U R N "),
    (r"\bMIME\b", " M I M E "),
    (r"\bLAN\b", " L A N "),
    (r"\bWAN\b", " W A N "),
    (r"\bVPN\b", " V P N "),
    (r"\bVLAN\b", " V LAN "),
    (r"\bDHCP\b", " D H C P "),
    (r"\bNAT\b", " N A T "),
    (r"\bBGP\b", " B G P "),
    (r"\bOSPF\b", " O S P F "),
    (r"\bIoT\b", " internet of things "),
    (r"\bAI\b", " A I "),
    (r"\bML\b", " machine learning "),
    (r"\bNLP\b", " natural language processing "),
    (r"\bOCR\b", " O C R "),
    (r"\bCUDA\b", " C U D A "),
    (r"\bVulkan\b", " Vulkan "),
    (r"\bDirectX\b", " Direct X "),
    (r"\bSSR\b", " S S R "),
    (r"\bSSG\b", " S S G "),
    (r"\bCSR\b", " C S R "),
    (r"\bSPA\b", " S P A "),
    (r"\bPWA\b", " P W A "),
    (r"\bSEO\b", " S E O "),
    (r"\bCMS\b", " C M S "),
    (r"\bWYSIWYG\b", " wizzy wig "),
    (r"\bACID\b", " A C I D "),
    (r"\bBASE\b", " B A S E "),
    (r"\bCAP\b", " C A P "),
    (r"\bRPC\b", " R P C "),
    (r"\bgRPC\b", " g R P C "),
    (r"\bE2E\b", " end to end "),
    (r"\bUAT\b", " U A T "),
    (r"\bQA\b", " Q A "),
    (r"\bSRE\b", " S R E "),
    (r"\bDevOps\b", " Dev Ops "),
    (r"\bGitOps\b", " Git Ops "),
    (r"\bIaC\b", " infrastructure as code "),
    (r"\bKPI\b", " K P I "),
    (r"\bSLA\b", " S L A "),
    (r"\bSLO\b", " S L O "),
    (r"\bSLI\b", " S L I "),
    (r"\bRFC\b", " R F C "),
    (r"\bISO\b", " I S O "),
    (r"\bGDPR\b", " G D P R "),
    (r"\bHIPAA\b", " hipaa "),
    (r"\bPCI\b", " P C I "),
    (r"\bSOC\b", " S O C "),
    (r"\bSSO\b", " S S O "),
    (r"\bMFA\b", " multi factor authentication "),
    (r"\b2FA\b", " two factor authentication "),
    (r"\bRBAC\b", " R B A C "),
    (r"\bABAC\b", " A B A C "),
    (r"\bLDAP\b", " L D A P "),
    (r"\bMITM\b", " man in the middle "),
    (r"\bXSS\b", " cross site scripting "),
    (r"\bCSRF\b", " C S R F "),
    (r"\bCORS\b", " C O R S "),
    (r"\bSSRF\b", " S S R F "),
    (r"\bXXE\b", " X X E "),
    (r"\bRCE\b", " remote code execution "),
    (r"\bLFI\b", " local file inclusion "),
    (r"\bRFI\b", " remote file inclusion "),
    (r"\bIDOR\b", " I D O R "),
    (r"\bCVE\b", " C V E "),
    (r"\bCVSS\b", " C V S S "),
    (r"\bOWASP\b", " O W A S P "),
    (r"\bSAST\b", " S A S T "),
    (r"\bDAST\b", " D A S T "),
    (r"\bIAST\b", " I A S T "),
    (r"\bSBOM\b", " S B O M "),
    (r"\bRSA\b", " R S A "),
    (r"\bECC\b", " E C C "),
    (r"\bAES\b", " A E S "),
    (r"\bSHA\b", " S H A "),
    (r"\bMD5\b", " M D five "),
    (r"\bHMAC\b", " H mac "),
    (r"\bPKI\b", " P K I "),
    (r"\bPEM\b", " P E M "),
    (r"\bDER\b", " D E R "),
    (r"\bOIDC\b", " Open I D Connect "),
    (r"\bk8s\b", " Kubernetes "),
    (r"\bK8s\b", " Kubernetes "),
    (r"\bGoLang\b", " Go "),
    (r"\bGolang\b", " Go "),
    (r"\bGNU\b", " G N U "),
    (r"\bGCC\b", " G C C "),
    (r"\bLLVM\b", " L L V M "),
    (r"\bMSVC\b", " M S V C "),
    (r"\bGitLab\b", " Git Lab "),
    (r"\bGitHub\b", " Git Hub "),
    (r"\bBitbucket\b", " Bit bucket "),
    (r"\bSVN\b", " S V N "),
    (r"\bnpm\b", " N P M "),
    (r"\bpnpm\b", " P N P M "),
    (r"\bWebpack\b", " Web pack "),
    (r"\bVite\b", " Veet "),
    (r"\bRollup\b", " Roll up "),
    (r"\besbuild\b", " es build "),
    (r"\bESLint\b", " E S lint "),
    (r"\bPyTest\b", " Py test "),
    (r"\bpytest\b", " py test "),
    (r"\bJUnit\b", " J unit "),
    (r"\bNUnit\b", " N unit "),
    (r"\bxUnit\b", " x unit "),
    (r"\bPlaywright\b", " Play wright "),
    (r"\bPostgreSQL\b", " Postgres S Q L "),
    (r"\bPostgres\b", " Postgres "),
    (r"\bMySQL\b", " My S Q L "),
    (r"\bMongoDB\b", " Mongo D B "),
    (r"\bRedis\b", " Redis "),
    (r"\bKafka\b", " Kafka "),
    (r"\bRabbitMQ\b", " Rabbit M Q "),
    (r"\bElasticsearch\b", " Elastic search "),
    (r"\bnginx\b", " engine x "),
    (r"\bNginx\b", " engine x "),
    (r"\bmacOS\b", " Mac O S "),
    (r"\biOS\b", " i O S "),
    (r"\bWSL2\b", " W S L two "),
    (r"\bWSL\b", " W S L "),
    (r"\bPowerShell\b", " Power Shell "),
    (r"\bZsh\b", " Z shell "),
)

_TECH_ABBREV_COMPILED: Tuple[Tuple[Pattern[str], str], ...] = tuple(
    (re.compile(p, re.IGNORECASE), r) for p, r in _TECH_ABBREV_PATTERNS
)

_SYMBOL_PHRASES: Tuple[Tuple[str, str], ...] = (
    ("<=>", " if and only if "),
    ("<->", " if and only if "),
    ("==>", " implies "),
    ("=>", " implies "),
    ("->", " maps to "),
    ("<-", " gets value from "),
    ("<=", " less than or equal to "),
    (">=", " greater than or equal to "),
    ("!=", " not equal to "),
    ("==", " equals "),
    ("...", " dot dot dot "),
    ("\u2026", " dot dot dot "),
    ("||", " or "),
    ("&&", " and "),
    ("**", " to the power "),
    ("+=", " plus equals "),
    ("-=", " minus equals "),
    ("*=", " times equals "),
    ("/=", " divided by equals "),
    ("±", " plus or minus "),
    ("×", " times "),
    ("÷", " divided by "),
    ("·", " dot "),
    ("⋅", " dot "),
    ("→", " right arrow "),
    ("←", " left arrow "),
    ("↔", " bidirectional arrow "),
    ("↦", " maps to "),
    ("⇒", " implies "),
    ("⟹", " implies "),
    ("⇐", " implied by "),
    ("⇔", " if and only if "),
    ("⟺", " if and only if "),
    ("∀", " for all "),
    ("∃", " there exists "),
    ("∄", " there does not exist "),
    ("∧", " and "),
    ("∨", " or "),
    ("¬", " not "),
    ("⊢", " proves "),
    ("⊤", " top "),
    ("⊥", " bottom "),
    ("∈", " in "),
    ("∉", " not in "),
    ("⊂", " subset of "),
    ("⊆", " subset of or equal to "),
    ("∪", " union "),
    ("∩", " intersection "),
    ("∅", " empty set "),
    ("∞", " infinity "),
    ("∑", " sum "),
    ("∏", " product "),
    ("∫", " integral "),
    ("∮", " contour integral "),
    ("∂", " partial "),
    ("∇", " gradient "),
    ("√", " square root "),
    ("∝", " proportional to "),
    ("≈", " approximately "),
    ("≃", " asymptotically equal to "),
    ("≡", " equivalent to "),
    ("≠", " not equal to "),
    ("≤", " less than or equal to "),
    ("≥", " greater than or equal to "),
    ("≪", " much less than "),
    ("≫", " much greater than "),
    ("∼", " tilde operator "),
    ("≅", " approximately equal to "),
    ("°", " degrees "),
    ("′", " prime "),
    ("″", " double prime "),
    ("…", " dot dot dot "),
    ("–", " dash "),
    ("—", " em dash "),
    ("−", " minus "),
    ("⁄", " divided by "),
    ("½", " one half "),
    ("¼", " one quarter "),
    ("¾", " three quarters "),
    ("¹", " to the first "),
    ("²", " squared "),
    ("³", " cubed "),
    ("⁰", " to the zero "),
    ("⁻", " superscript minus "),
    ("€", " euros "),
    ("£", " pounds "),
    ("¥", " yen "),
    ("¢", " cents "),
    ("™", " trademark "),
    ("®", " registered trademark "),
    ("©", " copyright "),
    ("¶", " paragraph "),
    ("§", " section sign "),
    ("•", " bullet "),
    ("◦", " hollow bullet "),
    ("|", " vertical bar "),
    ("\\", " backslash "),
    ("#", " hash "),
    ("@", " at "),
    ("%", " percent "),
    ("&", " ampersand "),
    ("*", " star "),
    ("`", " backtick "),
    ("~", " tilde "),
    ("^", " caret "),
)


# ── Individual filters ────────────────────────────────────────────────────────


def filter_code_blocks(text: str) -> str:
    """Replace fenced Markdown code blocks with a clear spoken placeholder."""
    return CODE_BLOCK_RE.sub(CODE_BLOCK_PLACEHOLDER, text)


def filter_inline_code(text: str) -> str:
    """Replace inline backtick spans with a clear spoken placeholder."""
    return INLINE_CODE_RE.sub(INLINE_CODE_PLACEHOLDER, text)


def filter_urls(text: str) -> str:
    """Replace URLs and bare www links."""
    return URL_RE.sub(LINK_PLACEHOLDER, text)


def filter_shebang_lines(text: str) -> str:
    """Replace Unix script shebang lines (``#!/...``) so TTS does not read paths."""
    return SHEBANG_LINE_RE.sub(" omitted script shebang line ", text)


def filter_html_like_tags(text: str) -> str:
    """Replace angle-bracket markup (HTML / XML / JSX-looking) with a placeholder."""
    return HTML_LIKE_TAG_RE.sub(" omitted markup tag ", text)


def filter_file_extensions(text: str) -> str:
    """Replace ``.ext`` file suffixes with spoken language or format names."""
    if not text:
        return text

    def _repl(m: Any) -> str:
        key = m.group(1).lower()
        name = _FILE_EXT_MAP.get(key)
        if name:
            return f" {name} "
        return m.group(0)

    return FILE_EXT_RE.sub(_repl, text)


def filter_tech_abbreviations(text: str) -> str:
    """Expand common technical acronyms and product names for speech."""
    if not text:
        return text
    out = text
    for cre, repl in _TECH_ABBREV_COMPILED:
        out = cre.sub(repl, out)
    return out


def filter_symbols_to_words(text: str) -> str:
    """Replace common math / logic / punctuation symbols with spoken phrases."""
    if not text:
        return text
    try:
        normalized = unicodedata.normalize("NFKC", text)
    except (TypeError, ValueError):
        normalized = text
    out = normalized
    for old, new in _SYMBOL_PHRASES:
        out = out.replace(old, new)
    return out


def filter_big_numbers(text: str) -> str:
    """Replace long digit sequences (7+ digits) with a placeholder."""
    return BIG_NUMBER_RE.sub(" a large number ", text)


# ── Pipeline ─────────────────────────────────────────────────────────────────-


class TextProcessingPipeline:
    """Composes a sequence of :data:`TextFilter` callables and applies them in order."""

    _DEFAULT_FILTERS: List[TextFilter] = [
        filter_code_blocks,
        filter_inline_code,
        filter_urls,
        filter_shebang_lines,
        filter_html_like_tags,
        filter_file_extensions,
        filter_tech_abbreviations,
        filter_symbols_to_words,
        filter_big_numbers,
    ]

    def __init__(self, filters: Optional[List[TextFilter]] = None) -> None:
        self._filters: List[TextFilter] = (
            filters if filters is not None else list(self._DEFAULT_FILTERS)
        )

    def process(self, text: str) -> str:
        """Apply all filters in order and return a whitespace-normalised result."""
        if not text:
            return text
        result = text
        for f in self._filters:
            result = f(result)
        return _WHITESPACE_RE.sub(" ", result).strip()


_default_pipeline = TextProcessingPipeline()


def replace_not_readable(text: str) -> str:
    """Apply all default filters and return a cleaned string suitable for TTS.

    Order: fenced code, inline code, URLs, shebang lines, HTML-like tags,
    file extensions, tech abbreviations, math symbols, big numbers.
    """
    return _default_pipeline.process(text)


if __name__ == "__main__":
    sample = (
        "Use `npm i` in ```js\nconsole.log(1)\n``` see https://ex.com/a.ts "
        "and API + JSON for app.py CVE-2024-1."
    )
    print(replace_not_readable(sample))
