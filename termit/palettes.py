"""Terminal colour palettes."""

PALETTES = {
    "gnome": {
        "name": "GNOME",
        "dark": {"fg": "#ffffff", "bg": "#1e1e1e"},
        "light": {"fg": "#171421", "bg": "#ffffff"},
        "colors": [
            "#171421", "#c01c28", "#26a269", "#a2734c", "#12488b", "#a347ba", "#2aa1b3", "#d0cfcc",
            "#5e5c64", "#f66151", "#33d17a", "#e9ad0c", "#2a7bde", "#c061cb", "#33c7de", "#ffffff",
        ],
    },
    "tango": {
        "name": "Tango",
        "dark": {"fg": "#d3d7cf", "bg": "#2e3436"},
        "light": {"fg": "#2e3436", "bg": "#eeeeec"},
        "colors": [
            "#2e3436", "#cc0000", "#4e9a06", "#c4a000", "#3465a4", "#75507b", "#06989a", "#d3d7cf",
            "#555753", "#ef2929", "#8ae234", "#fce94f", "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
        ],
    },
    "dracula": {
        "name": "Dracula",
        "dark": {"fg": "#f8f8f2", "bg": "#282a36"},
        "colors": [
            "#21222c", "#ff5555", "#50fa7b", "#f1fa8c", "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
            "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5", "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
        ],
    },
    "nord": {
        "name": "Nord",
        "dark": {"fg": "#d8dee9", "bg": "#2e3440"},
        "colors": [
            "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
            "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
        ],
    },
    "gruvbox": {
        "name": "Gruvbox Dark",
        "dark": {"fg": "#ebdbb2", "bg": "#282828"},
        "colors": [
            "#282828", "#cc241d", "#98971a", "#d79921", "#458588", "#b16286", "#689d6a", "#a89984",
            "#928374", "#fb4934", "#b8bb26", "#fabd2f", "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
        ],
    },
    "catppuccin": {
        "name": "Catppuccin Mocha",
        "dark": {"fg": "#cdd6f4", "bg": "#1e1e2e"},
        "colors": [
            "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
            "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8",
        ],
    },
    "solarized": {
        "name": "Solarized",
        "dark": {"fg": "#839496", "bg": "#002b36"},
        "light": {"fg": "#657b83", "bg": "#fdf6e3"},
        "colors": [
            "#073642", "#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83", "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
    },
}

PALETTE_ORDER = ["gnome", "tango", "dracula", "nord", "gruvbox", "catppuccin", "solarized"]


def resolve(palette_id, dark):
    """Return (fg, bg, colors) hex strings for a palette and theme variant."""
    pal = PALETTES.get(palette_id, PALETTES["gnome"])
    variant = pal.get("light" if not dark and "light" in pal else "dark")
    return variant["fg"], variant["bg"], pal["colors"]
