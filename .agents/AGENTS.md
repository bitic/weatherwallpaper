# Project Guidelines & Rules for WeatherWallpaper

This document defines architectural constraints, design standards, and coding conventions for AI agents working in this repository.

---

## 1. Environment & Dependency Management
- **Python Environment**: Always use `uv` for virtual environment management (`.venv`).
- **Core Dependencies**: `ecmwf-opendata`, `xarray`, `cfgrib`, `eccodes`, `matplotlib`, `cartopy`, `scipy`, `pandas`.
- **Cache Management**: Store raw GRIB2 datasets strictly in `~/.cache/weatherwallpaper/`.

---

## 2. Design System & Aesthetics (Tokyo Night Theme)
- **Primary Aesthetic**: Modern dark mode with high contrast inspired by *Tokyo Night*.
- **Color Palette**:
  - Figure background: `#1a1b26`
  - Map background: `#16161e`
  - Land background: `#1f2335`
  - Ocean background: `#13141f`
  - Coastlines: `#000000` (linewidth: 1.4)
  - Borders: `#565f89` (linestyle: dotted)
  - MSLP Isobars: `#c0caf5` (linewidth: 1.0)
  - High Pressure Centers ('H'): `#7dcfff` (bold, stroke: `#101216`)
  - Low Pressure Centers ('L'): `#f7768e` (bold, stroke: `#101216`)
  - Z500 Isohypses: `#ff9e64` (dashed, linewidth: 1.2, step: 8 gpdm)
  - Precipitation Layer: `PuBu_r` colormap (> 1 mm, alpha: 0.6)

---

## 3. Configuration Philosophy (Keep it Simple)
- **Minimal Dotfile**: Keep `~/.weatherwallpaper.conf` focused strictly on spatial extent and primary feature toggles:
  - `central_longitude`, `central_latitude`
  - `min_longitude`, `max_longitude`, `min_latitude`, `max_latitude`
  - `show_z500` (boolean)
- **Hardcoded Styling**: Do NOT bloat the configuration file with visual style knobs (colors, line weights, font sizes). Keep design constants fixed inside `generate_wallpaper.py`.

---

## 4. Execution & Integration
- **Dynamic Resolution**: Always detect display resolution dynamically across X11, Wayland, GNOME, or DRM sysfs before rendering.
- **Dynamic Forecast Step**: Calculate `target_step` (+6h, +12h, etc.) dynamically so that `valid_time > current_utc_time`.
- **GNOME Integration**: Apply generated wallpaper using `gsettings set org.gnome.desktop.background picture-uri`.
- **Systemd Automation**: User units located in `systemd/` (`synoptic-bg.service` and `synoptic-bg.timer`).

---

## 5. Version Control & Git Conventions
- **Commit Messages**: Always write Git commit messages strictly in English (e.g., using Conventional Commits such as `feat: ...`, `fix: ...`).
