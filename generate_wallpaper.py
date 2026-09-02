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
Z500_COLOR = "#ff9e64"    # Tokyo Night vibrant orange
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
    """Loads map center coordinates, extent, and show_z500 toggle from dotfile ~/.weatherwallpaper.conf."""
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
        'show_z500': True
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
            'show_z500': 'True'
        }
        try:
            with open(default_path, 'w') as f:
                f.write("# Fitxer de configuració de Weather Wallpaper\n")
                config.write(f)
            print(f"Fitxer de configuració creat amb valors per defecte a: {default_path}")
            found_file = default_path
        except Exception as e:
            print(f"Avís: no s'ha pogut crear el fitxer de configuració: {e}")

    try:
        section = config['MAP'] if 'MAP' in config else (config[config.sections()[0]] if config.sections() else {})
        cfg = {
            'central_longitude': float(section.get('central_longitude', defaults['central_longitude'])),
            'central_latitude': float(section.get('central_latitude', defaults['central_latitude'])),
            'min_longitude': float(section.get('min_longitude', defaults['min_longitude'])),
            'max_longitude': float(section.get('max_longitude', defaults['max_longitude'])),
            'min_latitude': float(section.get('min_latitude', defaults['min_latitude'])),
            'max_latitude': float(section.get('max_latitude', defaults['max_latitude'])),
            'show_z500': section.getboolean('show_z500', fallback=defaults['show_z500'])
        }
        print(f"Configuració carregada des de '{found_file}': Centre=({cfg['central_longitude']}, {cfg['central_latitude']}), Z500={cfg['show_z500']}")
    except Exception as e:
        print(f"Avís: Error llegint configuració ({e}). Utilitzant valors per defecte.")
        cfg = defaults

    return cfg

def create_tokyo_night_cmap():
    """Creates a custom vibrant Tokyo Night temperature colormap."""
    tokyo_colors = [
        "#0f172a", # -24°C Deep dark navy
        "#1e3a8a", # -18°C Deep blue
        "#2563eb", # -12°C Bright blue
        "#38bdf8", # -6°C Electric cyan
        "#2dd4bf", # 0°C Mint green (Freezing point)
        "#34d399", # 4°C Soft emerald
        "#a3e635", # 8°C Lime green
        "#facc15", # 12°C Warm yellow
        "#fb923c", # 16°C Sunset orange
        "#f87171", # 20°C Coral red
        "#e11d48", # 24°C Crimson
        "#9333ea", # 28°C Neon purple
        "#4c1d95"  # 32°C Deep violet
    ]
    return LinearSegmentedColormap.from_list("tokyo_night_t850", tokyo_colors, N=256)

def get_ecmwf_client_and_latest():
    """Tries cloud mirrors (azure, aws, ecmwf) to get client and latest available run time quickly."""
    for src in ["azure", "aws", "ecmwf"]:
        try:
            client = Client(source=src)
            latest_run = client.latest()
            print(f"Font ECMWF trobada '{src}' (Última passada disponible: {latest_run})")
            return client, latest_run, src
        except Exception as e:
            print(f"Avís: no s'ha pogut consultar la font {src}: {e}")
    
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

    # 2. Detect dynamic screen resolution of current machine
    screen_w, screen_h = get_screen_resolution()
    print(f"Resolució detectada de la pantalla: {screen_w}x{screen_h}")

    # 3. Get latest available run and determine dynamic future step
    client, latest_run, active_src = get_ecmwf_client_and_latest()
    target_step, now_utc = calculate_target_future_step(latest_run)
    
    valid_dt = latest_run + datetime.timedelta(hours=target_step)
    print(f"Pas de temps objectiu (futur): +{target_step}h -> Vàlid a les {valid_dt} UTC")

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
        print(f"Fitxers GRIB (+{target_step}h) trobats a la memòria cau local (~/.cache/weatherwallpaper/). Ometent descàrrega.")
    else:
        print(f"Descarregant noves dades de l'ECMWF IFS (pas +{target_step}h)...")
        success = False
        for src in [active_src, "azure", "aws", "ecmwf"]:
            try:
                c = Client(source=src)
                print(f"Descarregant via font '{src}'...")
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
                print("Descàrrega completada amb èxit!")
                success = True
                break
            except Exception as e:
                print(f"Avís: fallada des de la font {src}: {e}")

        if not success:
            existing_sfc = glob.glob(os.path.join(cache_dir, "ecmwf_ifs_sfc*.grib2"))
            existing_pl = glob.glob(os.path.join(cache_dir, "ecmwf_ifs_pl*.grib2"))
            if existing_sfc and existing_pl:
                sfc_cache = sorted(existing_sfc)[-1]
                pl_cache = sorted(existing_pl)[-1]
                print(f"Utilitzant fitxer de reserva disponible: {sfc_cache}")

    print("Processant conjunts de dades GRIB...")
    ds_msl = xr.open_dataset(sfc_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'meanSea'}})
    ds_wind = xr.open_dataset(sfc_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'heightAboveGround', 'level': 10}})
    ds_tp = xr.open_dataset(sfc_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'surface'}})
    ds_t850 = xr.open_dataset(pl_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'isobaricInhPa', 'level': 850}})
    
    ds_z500 = None
    if map_cfg['show_z500']:
        try:
            ds_z500 = xr.open_dataset(pl_cache, engine='cfgrib', backend_kwargs={'filter_by_keys': {'typeOfLevel': 'isobaricInhPa', 'level': 500}})
        except Exception as e:
            print(f"Avís: no s'ha pogut carregar el nivell de 500 hPa: {e}")

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

    # 5. Figure Setup for Tokyo Night Theme with Configurable Map Center & Extent
    dpi = 100
    fig_w = screen_w / dpi
    fig_h = screen_h / dpi

    print(f"Renderitzant fons de pantalla Tokyo Night ({screen_w}x{screen_h} px)...")
    proj = ccrs.LambertConformal(
        central_longitude=map_cfg['central_longitude'],
        central_latitude=map_cfg['central_latitude']
    )
    data_crs = ccrs.PlateCarree()

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor('#1a1b26')

    # Main map axis filling screen completely (0, 0, 1, 1)
    ax = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax.set_facecolor('#16161e')
    ax.set_extent([
        map_cfg['min_longitude'],
        map_cfg['max_longitude'],
        map_cfg['min_latitude'],
        map_cfg['max_latitude']
    ], crs=data_crs)
    ax.set_aspect('auto') # Adjust aspect ratio dynamically to fill exact screen bounds!

    # Tokyo Night Map Base Features
    ax.add_feature(cfeature.LAND, facecolor='#1f2335', edgecolor='none')
    ax.add_feature(cfeature.OCEAN, facecolor='#13141f', edgecolor='none')

    # Base layer: Temperature at 850 hPa (°C) with Tokyo Night palette
    cmap_t850 = create_tokyo_night_cmap()
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
    if not np.all(np.isnan(tp_vals)):
        ax.contourf(
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
            colors=Z500_COLOR,
            linewidths=1.2,
            linestyles=Z500_LINESTYLE,
            alpha=0.85,
            transform=data_crs,
            zorder=35
        )
        clabels_z = ax.clabel(cs_z, fmt='%d', inline=True, fontsize=8.5, colors=Z500_COLOR)
        for txt in clabels_z:
            txt.set_path_effects([path_effects.withStroke(linewidth=2.0, foreground='#16161e')])

    # Layer: MSLP isobars (thin light gray/white lines every 4 hPa)
    msl_min = int(np.floor(msl.values.min() / 4.0) * 4)
    msl_max = int(np.ceil(msl.values.max() / 4.0) * 4)
    msl_levels = np.arange(msl_min, msl_max + 4, 4)

    cs = ax.contour(
        lons, lats, msl.values,
        levels=msl_levels,
        colors='#c0caf5',
        linewidths=1.0,
        alpha=0.85,
        transform=data_crs,
        zorder=40
    )
    clabels = ax.clabel(cs, fmt='%d', inline=True, fontsize=9, colors='#ffffff')
    for txt in clabels:
        txt.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground='#16161e')])

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

    # Prominent Black Coastlines & Country Borders
    ax.add_feature(cfeature.COASTLINE, edgecolor='#000000', linewidth=1.4, zorder=50)
    ax.add_feature(cfeature.BORDERS, linestyle=':', edgecolor='#565f89', linewidth=0.8, alpha=0.8, zorder=51)

    # Draw High ('H') and Low ('L') Pressure Centers
    stroke_effect = [path_effects.withStroke(linewidth=3.0, foreground='#101216')]
    
    # High Pressure Centers ('H' cyan)
    for hlon, hlat, hval in highs:
        lbl_text = f"H\n{int(round(hval))}"
        txt = ax.text(
            hlon, hlat, lbl_text,
            transform=data_crs,
            color="#7dcfff",
            fontsize=13,
            fontweight="bold",
            horizontalalignment="center",
            verticalalignment="center",
            zorder=80
        )
        txt.set_path_effects(stroke_effect)

    # Low Pressure Centers ('L' pink/red)
    for llon, llat, lval in lows:
        lbl_text = f"L\n{int(round(lval))}"
        txt = ax.text(
            llon, llat, lbl_text,
            transform=data_crs,
            color="#f7768e",
            fontsize=13,
            fontweight="bold",
            horizontalalignment="center",
            verticalalignment="center",
            zorder=80
        )
        txt.set_path_effects(stroke_effect)

    # 6. HUD Info Text (Bottom Right corner, transparent without box, local & UTC time, active layers)
    valid_utc = pd.to_datetime(valid_time).tz_localize('UTC')
    valid_local = valid_utc.tz_convert('Europe/Madrid')

    run_utc = pd.to_datetime(run_time).tz_localize('UTC')

    step_hours = int((pd.to_datetime(valid_time) - pd.to_datetime(run_time)).total_seconds() / 3600)

    z500_badge = " + Z500" if (z500 is not None and map_cfg['show_z500']) else ""

    badge_text = (
        f"ECMWF IFS (0.25°){z500_badge}\n"
        f"Previsió: {valid_utc.strftime('%d/%m/%Y %H:%M UTC')} / {valid_local.strftime('%H:%M %Z')} (+{step_hours}h)\n"
        f"Inici: {run_utc.strftime('%d/%m/%Y %H:%M UTC')}"
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
        fontweight='medium',
        zorder=1000
    )
    t_hud.set_path_effects([path_effects.withStroke(linewidth=2.5, foreground='#101216')])

    # 7. Bottom Colorbar Legend for T850 (°C)
    cbar_ax = fig.add_axes([0.22, 0.035, 0.45, 0.022])
    cbar_ax.set_facecolor('#16161e')

    cbar = plt.colorbar(
        cf_t850,
        cax=cbar_ax,
        orientation='horizontal',
        ticks=np.arange(-24, 36, 4)
    )

    cbar.set_label('Temperatura a 850 hPa (°C)', color='#c0caf5', fontsize=10.5, fontweight='bold', labelpad=5)
    cbar.ax.tick_params(labelsize=9, colors='#a9b1d6', length=3)
    cbar.outline.set_edgecolor('#7dcfff')
    cbar.outline.set_linewidth=1.0

    # Save exact screen resolution wallpaper
    plt.savefig(
        output_path,
        dpi=dpi,
        facecolor='#1a1b26',
        edgecolor='none'
    )
    plt.close(fig)

    print(f"Fons de pantalla desat correctament ({screen_w}x{screen_h}) a {output_path}")

    # GNOME integration via gsettings
    print("Actualitzant fons d'escriptori de GNOME...")
    wallpaper_uri = f"file://{output_path}"
    try:
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", wallpaper_uri], check=False)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", wallpaper_uri], check=False)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-options", "zoom"], check=False)
        print("Paràmetres de GNOME actualitzats amb èxit.")
    except Exception as e:
        print(f"Avís: No s'ha pogut actualitzar gsettings: {e}")

    # Clean temporary cfgrib indices and obsolete GRIB2 datasets
    current_files = {os.path.basename(sfc_cache), os.path.basename(pl_cache)}
    for grib_file in glob.glob(os.path.join(cache_dir, "*.grib2")):
        if os.path.basename(grib_file) not in current_files:
            try:
                os.remove(grib_file)
                print(f"Esborrat fitxer de dades obsolet: {os.path.basename(grib_file)}")
            except OSError as e:
                print(f"Avís: no s'ha pogut esborrar {grib_file}: {e}")

    for idx in glob.glob(os.path.join(cache_dir, "*.idx")) + glob.glob("/tmp/*.idx"):
        try:
            os.remove(idx)
        except OSError:
            pass

if __name__ == "__main__":
    generate_wallpaper()
