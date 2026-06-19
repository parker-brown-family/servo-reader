"""servo-reader — ultra-lightweight terminal web reader over the Servo engine.

Fetch a page with a *real* browser engine (post-JS DOM), distill it to clean
markdown, and render that markdown to the terminal. Lynx-grade weight, modern
engine fidelity.
"""

__version__ = "0.4.0"

from .fetch import fetch_markdown
from .render import render

__all__ = ["fetch_markdown", "render", "__version__"]
