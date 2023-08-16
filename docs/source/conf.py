#!/usr/bin/env python3
import sys
import os

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'SCY'
copyright = '2023, YosysHQ GmbH'
author = 'YosysHQ GmbH'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.autosectionlabel']
extensions += ['sphinxarg.ext']

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ['_static']

html_logo = '_static/logo.png'
html_favicon = '_static/favico.png'
html_css_files = ['custom.css']

# code blocks style
pygments_style = 'colorful'

html_theme_options = {
    "sidebar_hide_name": True,

    "light_css_variables": {
        "color-brand-primary": "#d6368f",
        "color-brand-content": "#4b72b8",
        "color-api-name": "#8857a3",
        "color-api-pre-name": "#4b72b8",
        "color-link": "#8857a3",
    },

    "dark_css_variables": {
        "color-brand-primary": "#e488bb",
        "color-brand-content": "#98bdff",
        "color-api-name": "#8857a3",
        "color-api-pre-name": "#4b72b8",
        "color-link": "#be95d5",
    },
}

def setup(sphinx):
    sys.path += [os.path.dirname(__file__) + "/../util"]
    from YoscryptLexer import YoscryptLexer
    sphinx.add_lexer("yoscrypt", YoscryptLexer)
    
    from SCYLexer import SCYLexer
    sphinx.add_lexer("scy", SCYLexer)
