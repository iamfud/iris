"""Custom vector icons for flight simulation and specialized cockpit controls."""

CUSTOM_SVG_ICONS = {
    "landing-gear-down": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2v10M8 12h8M6 18a2 2 0 1 0 4 0a2 2 0 1 0 -4 0M14 18a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/>'
        '<path d="M8 12l-1 4M16 12l1 4M12 12v6"/>'
        '</svg>'
    ),
    "landing-gear-up": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 6h16M7 6l5 6l5-6M10 16a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/>'
        '<path d="M12 12v2"/>'
        '</svg>'
    ),
    "flight-stick": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 20v-8M9 20h6M10 12l1-7a1.5 1.5 0 0 1 3 0l1 7H10z"/>'
        '<circle cx="12" cy="7" r="1" fill="currentColor"/>'
        '</svg>'
    ),
    "afterburner": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M6 3v6M18 3v6M4 9h16l-3 12H7L4 9zM9 13l3 5l3-5"/>'
        '</svg>'
    )
}

def get_custom_svg(name: str) -> str | None:
    return CUSTOM_SVG_ICONS.get(name.lower().strip())
