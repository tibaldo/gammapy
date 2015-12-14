# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, print_function, unicode_literals
from numpy.testing import assert_allclose
from astropy.coordinates import SkyCoord, Angle
from ...utils.testing import requires_dependency, requires_data
from ...region import SkyCircleRegion
from ...datasets import gammapy_extra
from ...utils.scripts import read_yaml
from ...utils.energy import EnergyBounds
from ...image import ExclusionMask
from ...data import DataStore
from ...spectrum import (
    SpectrumAnalysis,
    run_spectral_fit_using_config,
    SpectralFit,
)


@requires_dependency('scipy')
@requires_data('gammapy-extra')
def test_spectrum_analysis(tmpdir):
    # Construct w/o config file
    center = SkyCoord(83.63, 22.01, unit='deg', frame='icrs')
    radius = Angle('0.3 deg')
    on_region = SkyCircleRegion(pos=center, radius=radius)

    bkg_method = dict(type='reflected')

    exclusion_file = gammapy_extra.filename("test_datasets/spectrum/dummy_exclusion.fits")
    excl = ExclusionMask.from_fits(exclusion_file)

    bounds = EnergyBounds.equal_log_spacing(1, 10, 40, unit='TeV')

    obs = [23523, 23559]
    store = gammapy_extra.filename("datasets/hess-crab4")
    ds = DataStore.from_dir(store)

    ana = SpectrumAnalysis(datastore=ds, obs=obs, on_region=on_region,
                           bkg_method=bkg_method, exclusion=excl, ebounds=bounds)

    ana.write_ogip_data(outdir=str(tmpdir))


@requires_dependency('sherpa')
@requires_data('gammapy-extra')
def test_spectral_fit(tmpdir):
    pha1 = gammapy_extra.filename("datasets/hess-crab4_pha/pha_run23592.pha")
    pha2 = gammapy_extra.filename("datasets/hess-crab4_pha/pha_run23526.pha")
    pha_list = [pha1, pha2]
    fit = SpectralFit(pha_list)
    fit.model = 'PL'
    fit.energy_threshold_low = '100 GeV'
    fit.energy_threshold_high = '10 TeV'
    fit.run(method='sherpa')
    assert_allclose(fit.model.gamma.val, 2.0, rtol=1e-1)

    # broken
    # fit.run(method='hspec')


@requires_dependency('yaml')
@requires_dependency('scipy')
@requires_dependency('sherpa')
@requires_data('gammapy-extra')
def test_spectrum_analysis_from_configfile(tmpdir):
    configfile = gammapy_extra.filename('test_datasets/spectrum/spectrum_analysis_example.yaml')
    config = read_yaml(configfile)
    config['general']['outdir'] = str(tmpdir)

    fit = run_spectral_fit_using_config(config)
    assert_allclose(fit.model.gamma.val, 2.0, rtol=1e-1)

    config['off_region']['type'] = 'ring'
    config['off_region']['inner_radius'] = '0.3 deg'
    config['off_region']['outer_radius'] = '0.4 deg'

    fit = run_spectral_fit_using_config(config)
    assert_allclose(fit.model.gamma.val, 2.0, rtol=1e-1)
