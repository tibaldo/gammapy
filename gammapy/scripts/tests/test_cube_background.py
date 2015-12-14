# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, print_function, unicode_literals
import numpy as np
from astropy.tests.helper import pytest
from ...utils.testing import requires_dependency
from ...datasets import make_test_dataset
from ...background import CubeBackgroundModel
from ...data import ObservationGroups
from ..cube_background import make_bg_cube_models_main


# TODO: this test is currently broken ... fix it!
@pytest.mark.xfail
@requires_dependency('scipy')
@pytest.mark.parametrize("extra_options,something_to_test", [
    (["--test"], 0),
])
def test_make_bg_cube_models_main(extra_options, something_to_test, tmpdir):
    # create a dataset
    dataset_dir = tmpdir / 'test_dataset'
    outdir = tmpdir / 'bg_cube_models'

    observatory_name = 'HESS'
    n_obs = 2
    random_state = np.random.RandomState(seed=0)

    make_test_dataset(outdir=str(dataset_dir),
                      observatory_name=observatory_name,
                      n_obs=n_obs,
                      random_state=random_state)

    make_bg_cube_models_main([str(dataset_dir), str(outdir)] + extra_options)

    # read groups, then open bg cube model files and check that they
    # make sense
    filename = outdir / 'bg_observation_groups.ecsv'
    observation_groups = ObservationGroups.read(str(filename))

    # loop over observation groups
    groups = observation_groups.list_of_groups

    for group in groups:

        # read bg cube model from file
        filename = outdir / 'bg_cube_model_group{}_table.fits.gz'.format(group)
        # skip bins with no bg cube model file
        if not filename.is_file():
            continue  # skip the rest

        bg_cube_model = CubeBackgroundModel.read(filename, format='table')
        cubes = [bg_cube_model.counts_cube,
                 bg_cube_model.livetime_cube,
                 bg_cube_model.background_cube]
        schemes = ['bg_counts_cube', 'bg_livetime_cube', 'bg_cube']
        for cube, scheme in zip(cubes, schemes):
            assert len(cube.data.shape) == 3
            assert cube.data.shape == (len(cube.energy_edges) - 1,
                                       len(cube.coordy_edges) - 1,
                                       len(cube.coordx_edges) - 1)
            assert cube.scheme == scheme
