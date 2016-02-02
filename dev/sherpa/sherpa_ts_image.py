# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
"""Compute TS image with Sherpa.

TODO: describe what is done.
"""

# TODO: clean up or remove!

# Parse command line arguments

from gammapy.utils.scripts import argparse, GammapyFormatter
parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=GammapyFormatter)
parser.add_argument('--counts', type=str, default='counts.fits',
                    help='Counts FITS file name')
parser.add_argument('--exposure', type=str, default='exposure.fits',
                    help='Exposure FITS file name')
parser.add_argument('--background', type=str, default='background.fits',
                    help='Background FITS file name')
parser.add_argument('--psf', type=str, default='psf.json',
                    help='PSF JSON file name')
parser.add_argument('--sources', type=str, default=None,
                    help='Background sources JSON file name')
parser.add_argument('--significance_image', type=str, default='significance.fits',
                    help='Output significance image FITS file name')
parser.add_argument('--filter', type=str, default=None,
                    help='Select region where you want to compute significance'
                    ' (ds9 reg format)')
parser.add_argument('--sigma', type=float, default=0.1,
                    help='Width of the Gaussian test source (pix). '
                    'Values much smaller than 0.1 cause numerical trouble. '
                    'This parameter corresponds in spirit to the theta parameter '
                    'for Li & Ma significance maps, i.e. the tophat correlation radius.')
parser.add_argument('--roi_containment', type=float, default=95,
                    help='Fraction of PSF-convolved test source that should be contained '
                    'in the ROI in %%. Making this fraction small will make the '
                    'ROI small and the significance computation fast, but also inaccurate.')
parser.add_argument('--stepsize', type=int, default=1,
                    help='E.g. stepsize = 3 computes significance only for every third pixel. '
                    'This can be useful to get a quick look at a significance map without '
                    'bothering fimgbin on the input images. By default significance is '
                    'computed for all pixels')
parser.add_argument('--overwrite', action='store_true',
                    help='Overwrite existing output file?')
args = parser.parse_args()

import logging
from gammapy.extern.pathlib import Path
from time import time
import numpy as np
from sherpa.astro.ui import *
from sherpa.utils.err import FitErr
from astropy.stats import gaussian_sigma_to_fwhm
import morphology.utils
import morphology.psf


logger = logging.getLogger('sherpa')
logger.setLevel(logging.WARN)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------
# Check if output significance file exists to make sure we don't waste
# time computing the significance image but not being able to save it
# ---------------------------------------------------------

if (args.overwrite == False and Path(args.significance_image).is_file()):
    logging.error('Output file exists: {0}'.format(args.significance_image))
    from sys import exit
    exit(-1)

# ---------------------------------------------------------
# Load images, PSF and sources
# ---------------------------------------------------------
logging.info('Reading counts: {0}'.format(args.counts))
load_data(args.counts)

logging.info('Reading exposure: {0}'.format(args.exposure))
load_table_model('exposure', args.exposure)

logging.info('Reading background: {0}'.format(args.background))
load_table_model('background', args.background)

logging.info('Reading PSF: {0}'.format(args.psf))
morphology.psf.Sherpa(args.psf).set()

# ---------------------------------------------------------
# Set up the full model and freeze everything but the
# norm of the test_source
# ---------------------------------------------------------

if args.sources:
    logging.info('Reading sources: {0}'.format(args.sources))
    morphology.utils.read_json(args.sources, set_source)
    # Add a Gaussian test_source to the other background sources
    set_source('gauss2d.test_source + ' + get_source().name)
else:
    logging.info('No sources in the background model')
    set_source('gauss2d.test_source')

set_full_model('background + exposure * psf(' + get_source().name + ')')
[par.freeze() for par in get_model().pars]
test_source.fwhm = gaussian_signma_to_fwhm * args.sigma
#test_source.ampl.min = 0
thaw(test_source.ampl)

# ---------------------------------------------------------
# Set up the fit
# ---------------------------------------------------------
set_coord('physical') # @todo Check is positions are correct
set_stat('cash') # Do a likelihood fit
set_method('levmar') # Use the fastest optimizer
set_method_opt('maxfev', int(1e2)) # Limit should never be reached
set_method_opt('verbose', 0) # Don't babble

# ---------------------------------------------------------
# Compute ROI such that a certain fraction of the PSF-
# convolved test_source is inside
# ---------------------------------------------------------
# @todo Implement a more precise formula as promised,
# i.e. using the convolved model image
psf_width = max(psf1.fwhm.val, psf2.fwhm.val, psf3.fwhm.val)
roi_sigma = np.sqrt(psf_width ** 2 + test_source.fwhm.val ** 2)
roi_psf = morphology.psf.GaussianPSF(roi_sigma)
roi_size = roi_psf.containment_angle(args.roi_containment / 100.)
logging.info('psf_width = {0}, roi_sigma = {1}, roi_size = {2}'
             ''.format(psf_width, roi_sigma, roi_size))

# ---------------------------------------------------------
# Make an empty significance image and a mask
# of pixels for which it should be computed
# ---------------------------------------------------------

copy_data(1, 'significance')
get_data('significance').y = np.zeros_like(get_data('significance').y)

if args.filter:
    logging.info('Reading filter: {0}'.format(args.filter))
    notice2d_id('significance', args.filter)
    mask = get_data('significance').mask
else:
    logging.info('No filter. Computing significance for whole image.')
    mask = np.ones_like(get_data('significance').y)

# ---------------------------------------------------------
# Compute the significance for each position
# ---------------------------------------------------------

ny, nx = get_data().shape
counter = 0
npix = mask.sum() / args.stepsize ** 2
last_ampl = 1
start = time()
for x in range(0, nx, args.stepsize):
    for y in range(0, ny, args.stepsize):
        bin = x + y * nx
        #bin = y + x * ny    
        if mask[bin] == True:
            # Set up the test_source and ROI
            notice2d_id(1) # This clears previous selections
            notice2d_id(1, 'circle(%s, %s, %s)' % (x, y, roi_size))
            test_source.xpos= x
            test_source.ypos= y
            freeze(test_source.xpos, test_source.ypos)
            
            try:
                # Compute L0
                #test_source.ampl = test_source.ampl.min
                test_source.ampl = 0
                L0 = get_stat_info()[0].statval
                
                # Compute L1
                # @todo When taking the last amplitude as fit start value I observed
                # zero significance in the whole first row and column.
                # This occurs irrespective of using last_ampl or 1 here as a starting
                # value!???
                #test_source.ampl = last_ampl
                test_source.ampl = 1
                fit(1)
                last_ampl = test_source.ampl.val
                r1 = get_fit_results()
                L1 = r1.statval
                
                # Compute significance
                significance = np.sign(test_source.ampl.val) * np.sqrt(np.abs(L0 - L1))
                
            except FitErr as e:
                print(e)
                significance = np.nan
            
            # Print and remember values
            counter += 1
            r = get_fit_results()
            current = (time() - start) / 60.
            remaining = current * (npix / counter - 1)
            print('%4d min running, %4d min remain, '
                  'pix %5d of %5d, (x, y) = (%5d, %5d), '
                  'sig = %10.5f, ampl = %10.5f '
                  'nfev = %3d, bins = %5d' % 
                  (current, remaining, counter, npix, x, y, 
                   significance, test_source.ampl.val, 
                   r.nfev, r.numpoints))
            get_data('significance').y[bin] = significance

# ---------------------------------------------------------
# Save the TS map to file
# ---------------------------------------------------------
logging.info('Writing significance_image: {0}'.format(args.significance_image))
save_data('significance', args.significance_image, clobber=args.overwrite)

