# Project Guidelines & Rules for WeatherWallpaper

This document defines architectural constraints, design standards, and coding conventions for AI agents working in this repository.

---

## 1. Environment & Dependency Management
- **Python Environment**: Always use `uv` for virtual environment management (`.venv`).
- **Core Dependencies**: `ecmwf-opendata`, `xarray`, `cfgrib`, `eccodes`, `matplotlib`, `cartopy`, `scipy`, `pandas`.
- **Cache Management**: Store raw GRIB2 datasets strictly in `~/.cache/weatherwallpaper/`.

---

## 2. Design System & Modular Themes
- **Primary Aesthetic**: Modern high-contrast dark themes defined in `themes/`.
- **Default Theme**: `dracula` (`themes/dracula.conf`).
- **Theme Files**: Each theme in `themes/*.conf` defines `fig_bg`, `map_bg`, `land`, `ocean`, `coastline`, `borders`, `mslp_line`, `mslp_text`, `high_h`, `low_l`, `z500_color`, and `t850_colors`.

---

## 3. Configuration Philosophy (Keep it Simple)
- **Minimal Dotfile**: Keep `~/.weatherwallpaper.conf` focused strictly on spatial extent, primary feature toggles, and active theme:
  - `central_longitude`, `central_latitude`
  - `min_longitude`, `max_longitude`, `min_latitude`, `max_latitude`
  - `show_z500` (boolean)
  - `theme` (string, defaults to `dracula`)
- **Theme Architecture**: Individual color themes are kept inside `themes/*.conf` files.


---

## 4. Execution & Integration
- **Dynamic Resolution**: Always detect display resolution dynamically across X11, Wayland, GNOME, or DRM sysfs before rendering.
- **Dynamic Forecast Step**: Calculate `target_step` (+6h, +12h, etc.) dynamically so that `valid_time > current_utc_time`.
- **GNOME Integration**: Apply generated wallpaper using `gsettings set org.gnome.desktop.background picture-uri`.
- **Systemd Automation**: User units located in `systemd/` (`synoptic-bg.service` and `synoptic-bg.timer`).

---

## 5. Version Control & Git Conventions
- **Commit Messages**: Always write Git commit messages strictly in English (e.g., using Conventional Commits such as `feat: ...`, `fix: ...`).
