from pygments.lexer import RegexLexer, bygroups, include
from pygments.token import (Comment, Keyword, Name, Operator, Whitespace, Text)

__all__ = ['SCYLexer']

class SCYLexer(RegexLexer):
    name = 'Sequence of Covers'
    aliases = ['scy']
    filenames = ['*.scy']

    keyword_re = r'(cover|append|trace|add|disable|enable)'

    tokens = {
        'common': [
            (r'\s+', Whitespace),
            (r'#.*', Comment.Single),
            (r':', Operator),
            (r'(\S+)', Text),
        ],
        'root': [
            (keyword_re, Keyword, 'stmt'),
            include('common'),
        ],
        'stmt': [
            (r'(\S+)( )(.*)(:)?',
                bygroups(Name.Function, Whitespace, Text, Operator)),
            (r'(\S+)(:?)',
                bygroups(Text, Operator)),
            (r'(\n)', Whitespace, '#pop'),
            include('common'),
        ],
    }
