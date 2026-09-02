# 📋 TODO & Roadmap

## 💡 Maybe / Future Ideas

- [ ] **GNOME Shell Extension (Hybrid GJS + Python Backend)**:
  - Create a native GNOME Shell extension with a top bar status indicator menu.
  - Quick action buttons to trigger instant wallpaper regeneration.
  - Graphical toggle switches for active layers (Z500 isohypses, wind streamlines, MSLP isobars).
  - Libadwaita / GTK4 preferences window to visually edit geographic bounds without manually modifying `~/.weatherwallpaper.conf`.
  - Publish on [extensions.gnome.org](https://extensions.gnome.org).

- [ ] **Additional Weather Parameter Presets**:
  - Add optional 500 hPa Absolute Vorticity / Geopotential combo preset.
  - Add 2m Temperature anomaly / 850 hPa temperature anomaly preset.

## 🛠️ Planned Improvements

- [ ] Add explicit network retry handlers for transient cloud mirror 503/429 HTTP codes.
- [ ] Add automated GitHub Actions workflow to check for Python dependency updates.
