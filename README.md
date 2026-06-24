# Soundmaster

GTK3 audio controller for XFCE/Linux with PulseAudio/PipeWire.

- Volume control for audio devices and application streams
- Star/favorite system for devices
- Health check indicator (green/red)
- Test sound playback via selected output
- Debounced sliders, popup behavior (closes on focus loss)

## Install

```bash
cp soundmaster.py ~/.local/bin/
cp testa-ljudet.desktop ~/.local/share/applications/
mkdir -p ~/.local/share/icons/hicolor/48x48/apps
cp icon.png ~/.local/share/icons/hicolor/48x48/apps/
gtk-update-icon-cache ~/.local/share/icons/hicolor/
```

Add to XFCE panel: `xfce4-panel --add=launcher`

## Requirements

- Python 3 + PyGObject (GTK3)
- PulseAudio/PipeWire utilities (pactl, paplay)
- Pillow (for icon generation)
