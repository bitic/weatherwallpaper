import os
import glob
import time
import datetime
import subprocess
import configparser
import numpy as np
import pandas as pd
import xarray as xr
import cfgrib
import scipy.ndimage as ndimage
from ecmwf.opendata import Client
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.colors import LinearSegmentedColormap
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# Constant visual design parameters for Z500 layer
Z500_STEP = 8            # 8 gpdm = 80 gpm step between isohypses
Z500_LINESTYLE = "dashed" # Dashed isohypse lines

def get_screen_resolution():
    """Detects active display resolution dynamically across X11, Wayland, GNOME, KDE, or DRM sysfs."""
    # 1. Try xrandr (X11)
    try:
        out = subprocess.check_output("xrandr 2>/dev/null | grep '*'", shell=True, text=True)
        for line in out.strip().splitlines():
            res = line.strip().split()[0]
            if 'x' in res:
                w, h = map(int, res.split('x'))
                if w > 0 and h > 0:
                    return w, h
    except Exception:
        pass

    # 2. Try gnome-randr (Wayland)
    try:
        out = subprocess.check_output("gnome-randr 2>/dev/null | grep '*'", shell=True, text=True)
        for line in out.strip().splitlines():
            res = line.strip().split()[0]
            if 'x' in res:
                w, h = map(int, res.split('x'))
                if w > 0 and h > 0:
                    return w, h
    except Exception:
        pass

    # 3. Try sysfs DRM modes
    try:
        for path in glob.glob("/sys/class/drm/card*-*/modes"):
            with open(path) as f:
                line = f.readline().strip()
                if line and 'x' in line:
                    w, h = map(int, line.split('x'))
                    if w > 0 and h > 0:
                        return w, h
    except Exception:
        pass

    # Default fallback
    return 1920, 1080

def load_config():
    """Loads map center coordinates, extent, show_z500 toggle, and active theme from dotfile ~/.weatherwallpaper.conf."""
    config_paths = [
        os.path.expanduser("~/.weatherwallpaper.conf"),
        os.path.expanduser("~/.config/weatherwallpaper/config.conf"),
        os.path.abspath(".weatherwallpaper.conf")
    ]
    
    defaults = {
        'central_longitude': 5.0,
        'central_latitude': 42.0,
        'min_longitude': -25.0,
        'max_longitude': 20.0,
        'min_latitude': 28.0,
        'max_latitude': 58.0,
        'show_z500': True,
        'theme': 'dracula'
    }
    
    config = configparser.ConfigParser()
    found_file = None
    for p in config_paths:
        if os.path.exists(p):
            config.read(p)
            found_file = p
            break
            
    if not found_file:
        default_path = config_paths[0]
        config['MAP'] = {
            'central_longitude': '5.0',
            'central_latitude': '42.0',
            'min_longitude': '-25.0',
            'max_longitude': '20.0',
            'min_latitude': '28.0',
            'max_latitude': '58.0',
            'show_z500': 'True',
            'theme': 'dracula'
        }
        try:
            with open(default_path, 'w') as f:
                f.write("# Weather Wallpaper Configuration File\n")
                config.write(f)
            print(f"Configuration file created with default values at: {default_path}")
            found_file = default_path
        except Exception as e:
            print(f"Warning: Could not create configuration file: {e}")

    try:
        section = config['MAP'] if 'MAP' in config else (config[config.sections()[0]] if config.sections() else {})
        cfg = {
            'central_longitude': float(section.get('central_longitude', defaults['central_longitude'])),
            'central_latitude': float(section.get('central_latitude', defaults['central_latitude'])),
            'min_longitude': float(section.get('min_longitude', defaults['min_longitude'])),
            'max_longitude': float(section.get('max_longitude', defaults['max_longitude'])),
            'min_latitude': float(section.get('min_latitude', defaults['min_latitude'])),
            'max_latitude': float(section.get('max_latitude', defaults['max_latitude'])),
            'show_z500': section.getboolean('show_z500', fallback=defaults['show_z500']),
            'theme': str(section.get('theme', defaults['theme'])).strip()
        }
        print(f"Configuration loaded from '{found_file}': Center=({cfg['central_longitude']}, {cfg['central_latitude']}), Z500={cfg['show_z500']}, Theme='{cfg['theme']}'")
    except Exception as e:
        print(f"Warning: Error reading configuration ({e}). Using default values.")
        cfg = defaults

    return cfg

def load_theme(theme_name="dracula"):
    """Loads a theme configuration file from the themes/ directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(script_dir, "themes", f"{theme_name}.conf"),
        os.path.expanduser(f"~/.config/weatherwallpaper/themes/{theme_name}.conf"),
        os.path.expanduser(f"~/.weatherwallpaper/themes/{theme_name}.conf"),
        os.path.join(script_dir, "themes", "dracula.conf")
    ]

    # Default fallback (Dracula Neon)
    theme = {
        'name': 'dracula',
        'fig_bg': '#282a36',
        'map_bg': '#282a36',
        'land': '#44475a',
        'ocean': '#1d1e26',
        'coastline': '#f8f8f2',
        'borders': '#6272a4',
        'mslp_line': '#f8f8f2',
        'mslp_text': '#ffffff',
        'high_h': '#8be9fd',
        'low_l': '#ff79c6',
        'z500_color': '#ffb86c',
        't850_colors': [
            '#191a21', '#21222c', '#6272a4', '#8be9fd', '#50fa7b',
            '#f1fa8c', '#ffb86c', '#ff5555', '#ff79c6', '#bd93f9'
        ]
    }

    found_file = None
    for p in possible_paths:
        if os.path.exists(p):
            found_file = p
            break

    if found_file:
        try:
            config = configparser.ConfigParser()
            config.read(found_file)
            sec = config['THEME'] if 'THEME' in config else (config[config.sections()[0]] if config.sections() else {})
            theme['name'] = sec.get('name', theme_name)
            theme['fig_bg'] = sec.get('fig_bg', theme['fig_bg'])
            theme['map_bg'] = sec.get('map_bg', theme['map_bg'])
            theme['land'] = sec.get('land', theme['land'])
            theme['ocean'] = sec.get('ocean', theme['ocean'])
            theme['coastline'] = sec.get('coastline', theme['coastline'])
            theme['borders'] = sec.get('borders', theme['borders'])
            theme['mslp_line'] = sec.get('mslp_line', theme['mslp_line'])
            theme['mslp_text'] = sec.get('mslp_text', theme['mslp_text'])
            theme['high_h'] = sec.get('high_h', theme['high_h'])
            theme['low_l'] = sec.get('low_l', theme['low_l'])
            theme['z500_color'] = sec.get('z500_color', theme['z500_color'])

            t850_raw = sec.get('t850_colors', '')
            if t850_raw:
                colors_list = [c.strip() for c in t850_raw.split(',') if c.strip()]
                if colors_list:
                    theme['t850_colors'] = colors_list
            print(f"Theme '{theme_name}' loaded from '{found_file}'")
        except Exception as e:
            print(f"Warning: Could not load theme file '{found_file}' ({e}). Falling back to default Dracula theme.")
    else:
        print(f"Warning: Theme '{theme_name}' not found. Falling back to default Dracula theme.")

    return theme

def create_theme_cmap(theme):
    """Creates a custom 850 hPa temperature colormap from theme colors."""
    return LinearSegmentedColormap.from_list(f"t850_{theme['name']}", theme['t850_colors'], N=256)


def get_ecmwf_client_and_latest():
    """Tries cloud mirrors (azure, aws, ecmwf) to get client and latest available run time quickly."""
    for src in ["azure", "aws", "ecmwf"]:
        try:
            client = Client(source=src)
            latest_run = client.latest()
            print(f"ECMWF source found '{src}' (Latest available run: {latest_run})")
            return client, latest_run, src
        except Exception as e:
            print(f"Warning: Could not query source {src}: {e}")
    
    fallback_client = Client(source="azure")
    return fallback_client, datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), "azure"

def calculate_target_future_step(latest_run):
    """Determines the nearest future forecast step (multiples of 6h) relative to current UTC time."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    
    possible_steps = [6, 12, 18, 24, 30, 36, 42, 48]
    target_step = 6
    for s in possible_steps:
        valid_dt = latest_run + datetime.timedelta(hours=s)
        if valid_dt > now_utc:
            target_step = s
            break
            
    return target_step, now_utc

def find_pressure_centers(msl_da, map_cfg, min_dist_deg=8.0):
    """Locates prominent High ('H') and Low ('L') pressure centers within visible map bounds."""
    # Slice to active map view extent with margin
    margin = 3.0
    msl_crop = msl_da.sel(
        latitude=slice(map_cfg['min_latitude'] - margin, map_cfg['max_latitude'] + margin),
        longitude=slice(map_cfg['min_longitude'] - margin, map_cfg['max_longitude'] + margin)
    )
    
    vals = msl_crop.values
    lats = msl_crop.latitude.values
    lons = msl_crop.longitude.values

    # Gaussian smoothing to remove small grid noise
    smooth = ndimage.gaussian_filter(vals, sigma=2.5)
    max_f = ndimage.maximum_filter(smooth, size=15)
    min_f = ndimage.minimum_filter(smooth, size=15)

    high_mask = (smooth == max_f) & (smooth >= 1018.0)
    low_mask = (smooth == min_f) & (smooth <= 1012.0)

    # High pressure candidates
    margin = 1.0
    high_candidates = []
    for j, i in zip(*np.where(high_mask)):
        lon, lat, val = lons[i], lats[j], smooth[j, i]
        if (map_cfg['min_longitude'] - margin) <= lon <= (map_cfg['max_longitude'] + margin) and (map_cfg['min_latitude'] - margin) <= lat <= (map_cfg['max_latitude'] + margin):
            high_candidates.append((lon, lat, val))

    # Low pressure candidates
    low_candidates = []
    for j, i in zip(*np.where(low_mask)):
        lon, lat, val = lons[i], lats[j], smooth[j, i]
        if (map_cfg['min_longitude'] - margin) <= lon <= (map_cfg['max_longitude'] + margin) and (map_cfg['min_latitude'] - margin) <= lat <= (map_cfg['max_latitude'] + margin):
            low_candidates.append((lon, lat, val))

    # Deduplicate candidates using distance thresholding
    def filter_prominent(candidates, reverse_sort=True):
        candidates.sort(key=lambda item: item[2], reverse=reverse_sort)
        selected = []
        for lon, lat, val in candidates:
            too_close = False
            for slon, slat, sval in selected:
                dist = np.hypot(lon - slon, lat - slat)
                if dist < min_dist_deg:
                    too_close = True
                    break
            if not too_close:
                selected.append((lon, lat, val))
        return selected[:6]

    selected_highs = filter_prominent(high_candidates, reverse_sort=True)  # Highest pressure first
    selected_lows = filter_prominent(low_candidates, reverse_sort=False)   # Lowest pressure first

    return selected_highs, selected_lows

def generate_wallpaper():
    output_dir = os.path.expanduser("~/.local/share/backgrounds")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "synoptic_wallpaper.png")

    cache_dir = os.path.expanduser("~/.cache/weatherwallpaper")
    os.makedirs(cache_dir, exist_ok=True)

    # 1. Load map configuration from dotfile ~/.weatherwallpaper.conf
    map_cfg = load_config()

    # Load visual theme configuration
    theme = load_theme(map_cfg.get('theme', 'dracula'))

    # 2. Detect dynamic screen resolution of current machine
    screen_w, screen_h = get_screen_resolution()
    print(f"Detected screen resolution: {screen_w}x{screen_h}")

    # 3. Get latest available run and determine dynamic future step
    client, latest_run, active_src = get_ecmwf_client_and_latest()
    target_step, now_utc = calculate_target_future_step(latest_run)
    
    valid_dt = latest_run + datetime.timedelta(hours=target_step)
    print(f"Target forecast step: +{target_step}h -> Valid at {valid_dt} UTC")

    sfc_cache = os.path.join(cache_dir, f"ecmwf_ifs_sfc_step{target_step}.grib2")
    pl_cache = os.path.join(cache_dir, f"ecmwf_ifs_pl_v2_step{target_step}.grib2")

    # 4. Check local cache validity (max age: 3 hours)
    max_age_seconds = 3 * 3600
    now_stamp = time.time()
    
    cache_valid = False
    if os.path.exists(sfc_cache) and os.path.exists(pl_cache):
        sfc_age = now_stamp - os.path.getmtime(sfc_cache)
        pl_age = now_stamp - os.path.getmtime(pl_cache)
        if sfc_age < max_age_seconds and pl_age < max_age_seconds:
            try:
                test_ds = xr.open_dataset(pl_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'isobaricInhPa', 'level': 500}})
                test_ds.close()
                cache_valid = True
            except Exception:
                cache_valid = False

    if cache_valid:
        print(f"GRIB files (+{target_step}h) found in local cache (~/.cache/weatherwallpaper/). Skipping download.")
    else:
        print(f"Downloading new data from ECMWF IFS (+{target_step}h step)...")
        success = False
        for src in [active_src, "azure", "aws", "ecmwf"]:
            try:
                c = Client(source=src)
                print(f"Downloading via source '{src}'...")
                c.download(
                    type="fc",
                    step=target_step,
                    levtype="sfc",
                    param=["msl", "tp", "10u", "10v"],
                    target=sfc_cache
                )
                c.download(
                    type="fc",
                    step=target_step,
                    levtype="pl",
                    levelist=[850, 500],
                    param=["t", "gh"],
                    target=pl_cache
                )
                print("Download completed successfully!")
                success = True
                break
            except Exception as e:
                print(f"Warning: Failure from source {src}: {e}")

        if not success:
            existing_sfc = glob.glob(os.path.join(cache_dir, "ecmwf_ifs_sfc*.grib2"))
            existing_pl = glob.glob(os.path.join(cache_dir, "ecmwf_ifs_pl*.grib2"))
            if existing_sfc and existing_pl:
                sfc_cache = sorted(existing_sfc)[-1]
                pl_cache = sorted(existing_pl)[-1]
                print(f"Using available fallback file: {sfc_cache}")

    print("Processing GRIB datasets...")
    ds_msl = xr.open_dataset(sfc_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'meanSea'}})
    ds_wind = xr.open_dataset(sfc_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'heightAboveGround', 'level': 10}})
    ds_tp = xr.open_dataset(sfc_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'surface'}})
    ds_t850 = xr.open_dataset(pl_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'isobaricInhPa', 'level': 850}})
    
    ds_z500 = None
    if map_cfg['show_z500']:
        try:
            ds_z500 = xr.open_dataset(pl_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'isobaricInhPa', 'level': 500}})
        except Exception as e:
            print(f"Warning: Could not load 500 hPa level: {e}")

    msl = ds_msl['msl'] / 100.0  # Pa a hPa
    u10 = ds_wind['u10']
    v10 = ds_wind['v10']
    tp = ds_tp['tp'] * 1000.0    # m a mm
    t850 = ds_t850['t'] - 273.15 # K a °C

    z500 = None
    if ds_z500 is not None:
        if 'gh' in ds_z500:
            z500 = ds_z500['gh'] / 10.0  # m a gpdm
        elif 'z' in ds_z500:
            z500 = ds_z500['z'] / 98.0665 # m2/s2 a gpdm

    valid_time = ds_msl['valid_time'].values
    run_time = ds_msl['time'].values

    def prepare_da(da):
        if da is not None and da.latitude[0] > da.latitude[-1]:
            da = da.reindex(latitude=da.latitude[::-1])
        return da

    msl = prepare_da(msl)
    t850 = prepare_da(t850)
    tp = prepare_da(tp)
    u10 = prepare_da(u10)
    v10 = prepare_da(v10)
    if z500 is not None:
        z500 = prepare_da(z500)

    # Detect H and L pressure centers
    highs, lows = find_pressure_centers(msl, map_cfg)

    # Wide spatial crop to fill projection viewport smoothly
    msl = msl.sel(latitude=slice(10, 75), longitude=slice(-50, 45))
    t850 = t850.sel(latitude=slice(10, 75), longitude=slice(-50, 45))
    tp = tp.sel(latitude=slice(10, 75), longitude=slice(-50, 45))
    u10 = u10.sel(latitude=slice(10, 75), longitude=slice(-50, 45))
    v10 = v10.sel(latitude=slice(10, 75), longitude=slice(-50, 45))
    if z500 is not None:
        z500 = z500.sel(latitude=slice(10, 75), longitude=slice(-50, 45))

    lons = msl.longitude.values
    lats = msl.latitude.values

    # 5. Figure Setup with Configurable Theme & Map Bounds
    dpi = 100
    fig_w = screen_w / dpi
    fig_h = screen_h / dpi

    print(f"Rendering wallpaper with theme '{theme['name']}' ({screen_w}x{screen_h} px)...")
    proj = ccrs.LambertConformal(
        central_longitude=map_cfg['central_longitude'],
        central_latitude=map_cfg['central_latitude']
    )
    data_crs = ccrs.PlateCarree()

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor(theme['fig_bg'])

    # Main map axis filling screen completely (0, 0, 1, 1)
    ax = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax.set_facecolor(theme['map_bg'])
    ax.set_extent([
        map_cfg['min_longitude'],
        map_cfg['max_longitude'],
        map_cfg['min_latitude'],
        map_cfg['max_latitude']
    ], crs=data_crs)
    ax.set_aspect('auto') # Adjust aspect ratio dynamically to fill exact screen bounds!

    # Map Base Features
    ax.add_feature(cfeature.LAND, facecolor=theme['land'], edgecolor='none')
    ax.add_feature(cfeature.OCEAN, facecolor=theme['ocean'], edgecolor='none')

    # Base layer: Temperature at 850 hPa (°C) with active theme palette
    cmap_t850 = create_theme_cmap(theme)
    t_levels = np.arange(-24, 34, 1.5)
    cf_t850 = ax.contourf(
        lons, lats, t850.values,
        levels=t_levels,
        cmap=cmap_t850,
        alpha=0.55,
        extend='both',
        transform=data_crs,
        zorder=10
    )

    # Precipitation layer (> 1mm) - Translucent cyan/electric blue
    tp_vals = np.where(tp.values >= 1.0, tp.values, np.nan)
    tp_levels = [1, 2, 5, 10, 20, 40, 70, 100]
    cf_tp = None
    if not np.all(np.isnan(tp_vals)):
        cf_tp = ax.contourf(
            lons, lats, tp_vals,
            levels=tp_levels,
            cmap='PuBu_r',
            alpha=0.6,
            extend='max',
            transform=data_crs,
            zorder=15
        )

    # Layer: Z500 Isohypses (Decameters geopotential)
    if z500 is not None and map_cfg['show_z500']:
        z_min = int(np.floor(z500.values.min() / float(Z500_STEP)) * Z500_STEP)
        z_max = int(np.ceil(z500.values.max() / float(Z500_STEP)) * Z500_STEP)
        z_levels = np.arange(z_min, z_max + Z500_STEP, Z500_STEP)

        cs_z = ax.contour(
            lons, lats, z500.values,
            levels=z_levels,
            colors=theme['z500_color'],
            linewidths=1.2,
            linestyles=Z500_LINESTYLE,
            alpha=0.85,
            transform=data_crs,
            zorder=35
        )
        clabels_z = ax.clabel(cs_z, fmt='%d', inline=True, fontsize=8.5, colors=theme['z500_color'])
        for txt in clabels_z:
            txt.set_path_effects([path_effects.withStroke(linewidth=2.0, foreground=theme['map_bg'])])

    # Layer: MSLP isobars
    msl_min = int(np.floor(msl.values.min() / 4.0) * 4)
    msl_max = int(np.ceil(msl.values.max() / 4.0) * 4)
    msl_levels = np.arange(msl_min, msl_max + 4, 4)

    cs = ax.contour(
        lons, lats, msl.values,
        levels=msl_levels,
        colors=theme['mslp_line'],
        linewidths=1.0,
        alpha=0.85,
        transform=data_crs,
        zorder=40
    )
    clabels = ax.clabel(cs, fmt='%d', inline=True, fontsize=9, colors=theme['mslp_text'])
    for txt in clabels:
        txt.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground=theme['map_bg'])])

    # Wind 10m streamplot
    ax.streamplot(
        lons, lats, u10.values, v10.values,
        color=(0.7, 0.75, 0.9, 0.4),
        linewidth=0.75,
        density=1.3,
        arrowsize=0.7,
        transform=data_crs,
        zorder=45
    )

    # Coastlines & Country Borders
    ax.add_feature(cfeature.COASTLINE, edgecolor=theme['coastline'], linewidth=1.4, zorder=50)
    ax.add_feature(cfeature.BORDERS, linestyle=':', edgecolor=theme['borders'], linewidth=0.8, alpha=0.8, zorder=51)

    # Draw High ('H') and Low ('L') Pressure Centers
    stroke_effect = [path_effects.withStroke(linewidth=3.0, foreground=theme['fig_bg'])]
    
    # High Pressure Centers
    for hlon, hlat, hval in highs:
        lbl_text = f"H\n{int(round(hval))}"
        txt = ax.text(
            hlon, hlat, lbl_text,
            transform=data_crs,
            color=theme['high_h'],
            fontsize=13,
            fontweight="bold",
            horizontalalignment="center",
            verticalalignment="center",
            zorder=80
        )
        txt.set_path_effects(stroke_effect)

    # Low Pressure Centers
    for llon, llat, lval in lows:
        lbl_text = f"L\n{int(round(lval))}"
        txt = ax.text(
            llon, llat, lbl_text,
            transform=data_crs,
            color=theme['low_l'],
            fontsize=13,
            fontweight="bold",
            horizontalalignment="center",
            verticalalignment="center",
            zorder=80
        )
        txt.set_path_effects(stroke_effect)

    # 6. HUD Info Text
    valid_utc = pd.to_datetime(valid_time).tz_localize('UTC')
    valid_local = valid_utc.tz_convert('Europe/Madrid')

    run_utc = pd.to_datetime(run_time).tz_localize('UTC')

    step_hours = int((pd.to_datetime(valid_time) - pd.to_datetime(run_time)).total_seconds() / 3600)

    z500_badge = " + Z500" if (z500 is not None and map_cfg['show_z500']) else ""

    badge_text = (
        f"ECMWF IFS (0.25°){z500_badge}\n"
        f"Forecast: {valid_utc.strftime('%Y-%m-%d %H:%M UTC')} / {valid_local.strftime('%H:%M %Z')} (+{step_hours}h)\n"
        f"Run: {run_utc.strftime('%Y-%m-%d %H:%M UTC')}"
    )

    t_hud = ax.text(
        0.985, 0.025, badge_text,
        transform=ax.transAxes,
        fontsize=11.5,
        color="#ffffff",
        alpha=0.95,
        verticalalignment='bottom',
        horizontalalignment='right',
        fontfamily='DejaVu Sans',
        fontweight='bold',
        zorder=1000
    )
    t_hud.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground=theme['fig_bg'])])

    # 7. Bottom Colorbar Legends for T850 (°C) and Precipitation (mm)
    if cf_tp is not None:
        # Dual Colorbars (Side-by-Side: T850 on left, Precipitation in center)
        cbar_t_ax = fig.add_axes([0.04, 0.035, 0.28, 0.020])
        cbar_t_ax.set_facecolor(theme['map_bg'])
        cbar_t = plt.colorbar(
            cf_t850,
            cax=cbar_t_ax,
            orientation='horizontal',
            ticks=np.arange(-24, 36, 8)
        )
        cbar_t.set_label('850 hPa Temperature (°C)', color='#c0caf5', fontsize=9.5, fontweight='bold', labelpad=4)
        cbar_t.ax.tick_params(labelsize=8.5, colors='#a9b1d6', length=3)
        cbar_t.outline.set_edgecolor(theme['high_h'])
        cbar_t.outline.set_linewidth(1.0)

        cbar_tp_ax = fig.add_axes([0.36, 0.035, 0.26, 0.020])
        cbar_tp_ax.set_facecolor(theme['map_bg'])
        cbar_tp = plt.colorbar(
            cf_tp,
            cax=cbar_tp_ax,
            orientation='horizontal',
            ticks=tp_levels,
            format='%g'
        )
        cbar_tp.set_label('Accumulated Precipitation (mm)', color='#c0caf5', fontsize=9.5, fontweight='bold', labelpad=4)
        cbar_tp.ax.tick_params(labelsize=8.5, colors='#a9b1d6', length=3)
        cbar_tp.outline.set_edgecolor(theme['z500_color'])
        cbar_tp.outline.set_linewidth(1.0)
    else:
        cbar_t_ax = fig.add_axes([0.04, 0.035, 0.45, 0.020])
        cbar_t_ax.set_facecolor(theme['map_bg'])
        cbar_t = plt.colorbar(
            cf_t850,
            cax=cbar_t_ax,
            orientation='horizontal',
            ticks=np.arange(-24, 36, 4)
        )
        cbar_t.set_label('850 hPa Temperature (°C)', color='#c0caf5', fontsize=9.5, fontweight='bold', labelpad=4)
        cbar_t.ax.tick_params(labelsize=8.5, colors='#a9b1d6', length=3)
        cbar_t.outline.set_edgecolor(theme['high_h'])
        cbar_t.outline.set_linewidth(1.0)


    # Save exact screen resolution wallpaper
    plt.savefig(
        output_path,
        dpi=dpi,
        facecolor='#1a1b26',
        edgecolor='none'
    )
    plt.close(fig)

    print(f"Wallpaper successfully saved ({screen_w}x{screen_h}) to {output_path}")

    # GNOME integration via gsettings
    print("Updating GNOME desktop background...")
    wallpaper_uri = f"file://{output_path}"
    try:
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", wallpaper_uri], check=False)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", wallpaper_uri], check=False)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-options", "zoom"], check=False)
        print("GNOME settings successfully updated.")
    except Exception as e:
        print(f"Warning: Could not update gsettings: {e}")

    # Clean temporary cfgrib indices and obsolete GRIB2 datasets
    current_files = {os.path.basename(sfc_cache), os.path.basename(pl_cache)}
    for grib_file in glob.glob(os.path.join(cache_dir, "*.grib2")):
        if os.path.basename(grib_file) not in current_files:
            try:
                os.remove(grib_file)
                print(f"Deleted obsolete data file: {os.path.basename(grib_file)}")
            except OSError as e:
                print(f"Warning: Could not delete {grib_file}: {e}")

    for idx in glob.glob(os.path.join(cache_dir, "*.idx")) + glob.glob("/tmp/*.idx"):
        try:
            os.remove(idx)
        except OSError:
            pass

if __name__ == "__main__":
    generate_wallpaper()
