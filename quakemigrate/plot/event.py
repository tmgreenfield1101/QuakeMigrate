# -*- coding: utf-8 -*-
"""
Module containing methods to generate event summaries and videos.

:copyright:
    2020, QuakeMigrate developers.
:license:
    GNU General Public License, Version 3
    (https://www.gnu.org/licenses/gpl-3.0.html)

"""

import logging

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd

import quakemigrate.util as util


@util.timeit("info")
def event_summary(run, event, marginal_coalescence, lut, xy_files=None):
    """
    Plots an event summary illustrating the locate results: slices through the
    marginalised coalescence with the location estimates (best-fitting spline
    to interpolated coalescence; Gaussian fit; covariance fit) and associated
    uncertainties; a gather of the filtered station data, sorted by distance
    from the event; and the maximum coalescence through time.

    Parameters
    ----------
    run : :class:`~quakemigrate.io.Run` object
        Light class encapsulating i/o path information for a given run.
    event : :class:`~quakemigrate.io.Event` object
        Light class encapsulating signal, onset, and location information
        for a given event.
    marginal_coalescence : `~numpy.ndarray` of `~numpy.double`
        Marginalised 3-D coalescence map, shape(nx, ny, nz).
    lut : :class:`~quakemigrate.lut.LUT` object
        Contains the traveltime lookup tables for seismic phases, computed for
        some pre-defined velocity model.
    xy_files : str, optional
        Path to comma-separated value file (.csv) containing a series of
        coordinate files to plot. Columns: ["File", "Color", "Linewidth",
        "Linestyle"], where "File" is the absolute path to the file containing
        the coordinates to be plotted. E.g:
        "/home/user/volcano_outlines.csv,black,0.5,-". Each .csv coordinate
        file should contain coordinates only, with columns: ["Longitude",
        "Latitude"]. E.g.: "-17.5,64.8".
        .. note:: Do not include a header line in either file.

    """

    logging.info("\tPlotting event summary figure...")

    # Extract indices and grid coordinates of maximum coalescence
    coa_map = np.ma.masked_invalid(marginal_coalescence)
    idx_max = np.column_stack(np.where(coa_map == np.nanmax(coa_map)))[0]
    slices = [coa_map[:, :, idx_max[2]],
              coa_map[:, idx_max[1], :],
              coa_map[idx_max[0], :, :].T]
    otime = event.otime

    fig = plt.figure(figsize=(25, 15))

    # Create plot axes, ordering: [SIGNAL, COA, XY, XZ, YZ]
    sig_spec = GridSpec(9, 15).new_subplotspec((0, 8), colspan=7, rowspan=7)
    fig.add_subplot(sig_spec)
    fig.canvas.draw()
    coa_spec = GridSpec(9, 15).new_subplotspec((7, 8), colspan=7, rowspan=2)
    fig.add_subplot(coa_spec)

    # --- Plot LUT, waveform gather, and max coalescence trace ---
    lut.plot(fig, (9, 15), slices, event.hypocentre, "white")
    _plot_waveform_gather(fig.axes[0], lut, event, idx_max)
    _plot_coalescence_trace(fig.axes[1], event)

    # --- Plot xy files on map ---
    _plot_xy_files(xy_files, fig.axes[2])

    # --- Add event origin time to signal and coalescence plots ---
    for ax in fig.axes[:2]:
        ax.axvline(otime.datetime, label="Origin time", ls="--", lw=2,
                   c="#F03B20")

    # --- Create and plot covariance and Gaussian uncertainty ellipses ---
    gues = _make_ellipses(lut, event, "gaussian", "k")
    for ax, gue in zip(fig.axes[2:], gues):
        ax.add_patch(gue)

    # --- Write summary information ---
    text = plt.subplot2grid((9, 15), (0, 0), colspan=8, rowspan=2, fig=fig)
    _plot_text_summary(text, lut, event)

    fig.axes[0].legend(fontsize=14, loc=1, framealpha=1, markerscale=0.5)
    fig.axes[1].legend(fontsize=14, loc=1, framealpha=1)
    fig.axes[2].legend(fontsize=14)
    fig.tight_layout(pad=1, h_pad=0)
    plt.subplots_adjust(wspace=0.3, hspace=0.3)

    # --- Adjust cross sections to match map aspect ratio ---
    # Get left, bottom, width, height of each subplot bounding box
    xy_left, xy_bottom, xy_width, xy_height = fig.axes[2].get_position().bounds
    xz_l, xz_b, xz_w, xz_h = fig.axes[3].get_position().bounds
    yz_l, yz_b, _, _ = fig.axes[4].get_position().bounds
    # Find height and width spacing of subplots in figure coordinates
    hdiff = yz_b - (xz_b + xz_h)
    wdiff = yz_l - (xz_l + xz_w)
    # Adjust bottom of xz cross section (if bottom of map has moved up)
    new_xz_bottom = xy_bottom - hdiff - xz_h
    fig.axes[3].set_position([xy_left, new_xz_bottom, xy_width, xz_h])
    # Adjust left of yz cross section (if right side of map has moved left)
    new_yz_left = xy_left + xy_width + wdiff
    # Take this opportunity to ensure the height of both cross sections is
    # equal by adjusting yz width (almost there from gridspec maths already)
    new_yz_width = xz_h * (fig.get_size_inches()[1]
                           / fig.get_size_inches()[0])
    fig.axes[4].set_position([new_yz_left, xy_bottom, new_yz_width, xy_height])

    fpath = run.path / "locate" / run.subname / "summaries"
    fpath.mkdir(exist_ok=True, parents=True)
    fstem = f"{run.name}_{event.uid}_EventSummary"
    file = (fpath / fstem).with_suffix(".pdf")
    plt.savefig(file, dpi=400)
    plt.close("all")


WAVEFORM_COLOURS1 = ["#FB9A99", "#7570b3", "#1b9e77"]
WAVEFORM_COLOURS2 = ["#33a02c", "#b2df8a", "#1f78b4"]
PICK_COLOURS = ["#F03B20", "#3182BD"]


def _plot_waveform_gather(ax, lut, event, idx):
    """
    Utility function to bring all aspects of plotting the waveform gather into
    one place.

    Parameters
    ----------
    ax : `~matplotlib.Axes` object
        Axes on which to plot the waveform gather.
    lut : :class:`~quakemigrate.lut.LUT` object
        Contains the traveltime lookup tables for seismic phases, computed for
        some pre-defined velocity model.
    event : :class:`~quakemigrate.io.Event` object
        Light class encapsulating signal, onset, and location information
        for a given event.
    idx : `~numpy.ndarray` of `numpy.double`
        Marginalised 3-D coalescence map, shape(nx, ny, nz).

    """

    # --- Predicted traveltimes ---
    ttpf, ttsf = [lut.traveltime_to(phase, idx) for phase in ["P", "S"]]
    ttp = [(event.otime + tt).datetime for tt in ttpf]
    tts = [(event.otime + tt).datetime for tt in ttsf]
    range_order = abs(np.argsort(np.argsort(ttp)) - len(ttp)) * 2
    s = (ax.get_window_extent().height / (max(range_order)+1) * 1.2) ** 2
    max_tts = max(ttsf)
    for tt, c, phase in zip([ttp, tts], PICK_COLOURS, "PS"):
        ax.scatter(tt, range_order, s=s, c=c, marker="|", zorder=5, lw=1.5,
                   label=f"Modelled {phase}")

    # --- Waveforms ---
    times_utc = event.data.times(type="UTCDateTime")
    mint, maxt = event.otime - 0.1, event.otime + max_tts*1.5
    mint_i, maxt_i = [np.argmin(abs(times_utc - t)) for t in (mint, maxt)]
    times_plot = event.data.times(type="matplotlib")[mint_i:maxt_i]
    for i, signal in enumerate(np.rollaxis(event.data.filtered_signal, 1)):
        for data, c, comp in zip(signal[::-1], WAVEFORM_COLOURS1,
                                 "ZNE"):
            if not data.any():
                continue
            data[mint_i:]

            # Get station specific range for norm factor
            stat_maxt = event.otime + ttsf[i]*1.5
            norm = max(abs(data[mint_i:np.argmin(abs(times_utc - stat_maxt))]))

            y = data[mint_i:maxt_i] / norm + range_order[i]
            label = f"{comp} component" if i == 0 else None
            ax.plot(times_plot, y, c=c, lw=0.3, label=label, alpha=0.85)

    # --- Limits, annotations, and axis formatting ---
    ax.set_xlim([mint.datetime, maxt.datetime])
    ax.set_ylim([0, max(range_order)+2])
    ax.xaxis.set_major_formatter(util.DateFormatter("%H:%M:%S.{ms}", 2))
    ax.yaxis.set_ticks(range_order)
    ax.yaxis.set_ticklabels(event.data.stations, fontsize=14)


def _plot_coalescence_trace(ax, event):
    """
    Utility function to plot the maximum coalescence trace around the event
    origin time.

    Parameters
    ----------
    ax : `~matplotlib.Axes` object
        Axes on which to plot the coalescence trace.
    event : :class:`~quakemigrate.io.Event` object
        Light class encapsulating signal, onset, and location information
        for a given event.

    """

    times = [x.datetime for x in event.coa_data["DT"]]
    ax.plot(times, event.coa_data["COA"], c="k", lw=0.5, zorder=10,
            label="Maximum coalescence")
    ax.set_ylabel("Maximum coalescence", fontsize=14)
    ax.set_xlabel("DateTime", fontsize=14)
    ax.set_xlim([times[0], times[-1]])
    ax.xaxis.set_major_formatter(util.DateFormatter("%H:%M:%S.{ms}", 2))


def _plot_text_summary(ax, lut, event):
    """
    Utility function to plot the event summary information.

    Parameters
    ----------
    ax : `~matplotlib.Axes` object
        Axes on which to plot the text summary.
    lut : :class:`~quakemigrate.lut.LUT` object
        Contains the traveltime lookup tables for seismic phases, computed for
        some pre-defined velocity model.
    event : :class:`~quakemigrate.io.Event` object
        Light class encapsulating signal, onset, and location information
        for a given event.

    """

    # Grab a conversion factor based on the grid projection to convert the
    # hypocentre depth + uncertainties to the correct units and evaluate the
    # suitable precision to which to report results from the LUT.
    km_cf = 1000 / lut.unit_conversion_factor
    precision = [max((prec + 2), 6) for prec in lut.precision[:2]]
    unit_correction = 3 if lut.unit_name == "km" else 0
    precision.append(max((lut.precision[2] + 2), 0 + unit_correction))

    hypocentre = [round(dimh, dimp) for dimh, dimp
                  in zip(event.hypocentre, precision)]
    gau_unc = [round(dim, precision[2]) for dim in event.loc_uncertainty/km_cf]
    hypo = (f"{hypocentre[1]}\u00b0N \u00B1 {gau_unc[1]} km\n"
            f"{hypocentre[0]}\u00b0E \u00B1 {gau_unc[0]} km\n"
            f"{hypocentre[2]/km_cf} \u00B1 {gau_unc[2]} km")

    # Grab the magnitude information
    mag_info = event.local_magnitude

    ax.text(0.25, 0.8, f"Event: {event.uid}", fontsize=20, fontweight="bold")
    ot_text = event.otime.strftime("%Y-%m-%d %H:%M:%S.")
    ot_text += event.otime.strftime("%f")[:3]
    with plt.rc_context({"font.size": 16}):
        ax.text(0.35, 0.65, "Origin time:", ha="right", va="center")
        ax.text(0.37, 0.65, f"{ot_text}", ha="left", va="center")
        ax.text(0.35, 0.55, "Hypocentre:", ha="right", va="top")
        ax.text(0.37, 0.55, hypo, ha="left", va="top")
        if mag_info is not None:
            mag, mag_err, mag_r2 = mag_info
            ax.text(0.35, 0.19, "Local magnitude:", ha="right")
            ax.text(0.37, 0.19, f"{mag:.3g} \u00B1 {mag_err:.3g}", ha="left")
            ax.text(0.35, 0.09, "Local magnitude r\u00B2:", ha="right")
            ax.text(0.37, 0.09, f"{mag_r2:.3g}", ha="left")
    ax.set_axis_off()


def _make_ellipses(lut, event, uncertainty, clr):
    """
    Utility function to create uncertainty ellipses for plotting.

    Parameters
    ----------
    lut : :class:`~quakemigrate.lut.LUT` object
        Contains the traveltime lookup tables for seismic phases, computed for
        some pre-defined velocity model.
    event : :class:`~quakemigrate.io.Event` object
        Light class encapsulating signal, onset, and location information
        for a given event.
    uncertainty : {"covariance", "gaussian"}
        Choice of uncertainty for which to generate ellipses.
    clr : str
        Colour for the ellipses - see matplotlib documentation for more
        details.

    Returns
    -------
    xy, yz, xz : `~matplotlib.Ellipse` (Patch) objects
        Ellipses for the requested uncertainty measure.

    """

    coord = event.get_hypocentre(method=uncertainty)
    error = event.get_loc_uncertainty(method=uncertainty)
    xyz = lut.coord2grid(coord)[0]
    d = abs(coord - lut.coord2grid(xyz + error, inverse=True))[0]

    xy = Ellipse((coord[0], coord[1]), 2*d[0], 2*d[1], lw=2, edgecolor=clr,
                 fill=False, label=f"{uncertainty.capitalize()} uncertainty")
    yz = Ellipse((coord[2], coord[1]), 2*d[2], 2*d[1], lw=2, edgecolor=clr,
                 fill=False)
    xz = Ellipse((coord[0], coord[2]), 2*d[0], 2*d[2], lw=2, edgecolor=clr,
                 fill=False)

    return xy, xz, yz


def _plot_xy_files(xy_files, ax):
    """
    Plot xy files supplied by user.

    The user can specify a list of xy files to plot by supplying a csv file
    with columns: ["File", "Color", "Linewidth", "Linestyle"], where "File" is
    the absolute path to the file containing the coordinates to be plotted.
    E.g: "/home/user/volcano_outlines.csv,black,0.5,-"

    Each specified xy file should contain coordinates only, with columns:
    ["Longitude", "Latitude"]. E.g.: "-17.5,64.8".

    .. note:: Do not include a header line in either file.

    Parameters
    ----------
    xy_files : str
        Path to .csv file containing a list of coordinates files to plot, and
        the linecolor and style to plot them with.
    ax : `~matplotlib.Axes` object
        Axes on which to plot the xy files.

    """

    if xy_files is not None:
        xy_files = pd.read_csv(xy_files,
                               names=["File", "Color",
                                      "Linewidth", "Linestyle"],
                               header=None)
        for _, f in xy_files.iterrows():
            xy_file = pd.read_csv(f["File"], names=["Longitude",
                                                    "Latitude"],
                                  header=None)
            ax.plot(xy_file["Longitude"], xy_file["Latitude"],
                    ls=f["Linestyle"], lw=f["Linewidth"],
                    c=f["Color"])